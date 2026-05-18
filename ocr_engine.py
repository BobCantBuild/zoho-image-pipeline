# =============================================================
#  ocr_engine.py  —  RapidOCR + OpenCV  |  ARM64 native
#
#  Why RapidOCR?
#  ┌──────────────┬─────────┬──────────┬───────────┬─────────┐
#  │ Engine       │ RAM     │ Install  │ ARM64     │ Speed   │
#  ├──────────────┼─────────┼──────────┼───────────┼─────────┤
#  │ EasyOCR      │ 1.5 GB  │ pip      │ emulated  │ slow    │
#  │ Tesseract    │ 50 MB   │ binary!  │ emulated  │ medium  │
#  │ RapidOCR     │ 300 MB  │ pip only │ NATIVE ✓  │ fast ✓  │
#  └──────────────┴─────────┴──────────┴───────────┴─────────┘
#  Install: pip install rapidocr-onnxruntime
#  No binary. No PATH. No admin. Works on ARM64 natively.
# =============================================================

import re
import logging
import threading
from typing import Optional

import cv2
import numpy as np

from config import OCR_CONFIDENCE_THRESHOLD
from image_preprocess import preprocess, preprocess_for_stars

logger  = logging.getLogger(__name__)

# =============================================================
#  RapidOCR  —  singleton, thread-safe
# =============================================================

_ocr      = None
_ocr_lock = threading.Lock()


def _get_ocr():
    global _ocr
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    _ocr = RapidOCR()
                    logger.warning("RapidOCR ready (ONNX native ARM64).")
                except ImportError:
                    raise ImportError(
                        "\n\n"
                        "  RapidOCR not installed. Run:\n"
                        "  pip install rapidocr-onnxruntime\n"
                    )
    return _ocr


def _run_ocr(img_bgr: np.ndarray) -> tuple:
    """
    Run RapidOCR on a BGR numpy array.
    Returns (full_text: str, mean_confidence: float 0-1).
    """
    ocr = _get_ocr()
    # RapidOCR returns: (result, elapse)
    # result = list of [bbox, text, confidence]  or None
    result, _ = ocr(img_bgr)
    if not result:
        return "", 0.0
    texts = [r[1] for r in result if r and len(r) >= 3]
    confs = [float(r[2]) for r in result if r and len(r) >= 3]
    if not texts:
        return "", 0.0
    return "\n".join(texts), float(np.mean(confs))


# =============================================================
#  ORDER ID  —  5-strategy cascade
#
#  Strategies (fastest/most-reliable first):
#  S1 — Amazon  3-7-7 pattern
#  S2 — Clean OD + 18 digits in raw text
#  S3 — Per-token char correction (O→0, D→d, I→1 …) then match
#  S4 — Stitch whitespace away then match  ("OD 436" → "OD436")
#  S5 — Tail rescue: 15-18 digit block near keyword → prepend OD
# =============================================================

_FIX = str.maketrans({
    'O': '0', 'o': '0',
    'D': 'd',
    'I': '1', 'i': '1', 'l': '1', 'L': '1',
    'S': '5', 's': '5',
    'B': '8', 'G': '6',
    'Z': '2', 'z': '2',
    'A': '4', ' ': '',
})

_PAT_AMAZON      = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
# Amazon 3-7-7 where OCR inserted space INSIDE the middle segment
# e.g. "402-279961 1.0609959" → middle "2799611" split as "279961" + " " + "1"
_PAT_AMAZON_SPLIT= re.compile(r"\b(\d{3})[-\s](\d{4,7})\s(\d{1,4})[-\.\s](\d{7})\b")
# Amazon stitched fallback — strip all non-digits, check total = 17
_PAT_OD_RAW      = re.compile(r"\b([Oo][Dd]\d{18})\b")
_PAT_OD_FIXED    = re.compile(r"0d(\d{18})", re.IGNORECASE)
# "00" prefix (OD read as 00) + 18 digits — the most common failure
_PAT_OD_00       = re.compile(r"\b00(\d{18})\b")
# Truncated: "OD3371401480..." — grab what's there then find the rest nearby
_PAT_OD_TRUNC    = re.compile(r"\b[Oo0][Dd0](\d{10,17})\.{2,}")
_PAT_TAIL        = re.compile(r"\b(\d{15,18})\b")

_KW = re.compile(
    r"order\s*(number|id|no\.?|#?)"
    r"|order\s*#"
    r"|invoice\s*(no\.?|number|id)"
    r"|mtbe|supply\s*(number|no\.?)",
    re.IGNORECASE
)


def _norm(s: str) -> str:
    return s.replace(" ", "").translate(_FIX)



def _strategies(corpus: str, near_kw: bool) -> tuple:
    """Returns (order_id | None, 'HIGH'|'LOW'|None)."""

    # S1a — Amazon 3-7-7 exact
    m = _PAT_AMAZON.search(corpus)
    if m: return m.group(1), "HIGH"

    # S1b — Amazon with space INSIDE middle segment: "402-279961 1.0609959"
    m = _PAT_AMAZON_SPLIT.search(corpus)
    if m:
        a   = m.group(1)                        # "402"
        mid = m.group(2) + m.group(3)           # "279961" + "1" = "2799611"
        c   = m.group(4)                        # "0609959"
        if len(a) == 3 and len(mid) == 7 and len(c) == 7:
            return f"{a}-{mid}-{c}", "HIGH"

    # S1c — Amazon keyword-adjacent digit strip: grab all digits near keyword,
    #        if exactly 17 digits → format as 3-7-7
    if near_kw:
        digits = re.sub(r"[^\d]", "", corpus)
        if len(digits) == 17:
            return f"{digits[:3]}-{digits[3:10]}-{digits[10:]}", "HIGH"

    # S1d — Amazon stitched (remove all spaces then match)
    stitched = re.sub(r"\s+", "", corpus)
    m = _PAT_AMAZON.search(stitched)
    if m: return m.group(1), "HIGH"

    # S2 — Clean OD+18 in raw text
    m = _PAT_OD_RAW.search(corpus)
    if m: return m.group(1).upper(), "HIGH"

    # S3 — "00" prefix (OD misread as 00) — most common failure
    #        Catches: "00337122575350022100" → "OD337122575350022100"
    m = _PAT_OD_00.search(corpus)
    if m: return f"OD{m.group(1)}", "HIGH"
    m = _PAT_OD_00.search(stitched)
    if m: return f"OD{m.group(1)}", "HIGH"

    # S4 — Per-token char fix then match
    for tok in re.findall(r"[A-Za-z0-9]{6,22}", corpus):
        m = _PAT_OD_FIXED.fullmatch(_norm(tok))
        if m: return f"OD{m.group(1)}", "HIGH"

    # S5 — Stitch full corpus, fix, match
    m = _PAT_OD_FIXED.search(_norm(stitched))
    if m: return f"OD{m.group(1)}", "HIGH"
    m = _PAT_OD_RAW.search(stitched)
    if m: return m.group(1).upper(), "HIGH"

    # S6 — Truncated OD (e.g. "OD3371401480...") — grab digits then
    #        look for the remaining digits on the next line
    m = _PAT_OD_TRUNC.search(corpus)
    if m:
        partial = m.group(1)
        # Find a nearby digit block that could be the suffix
        suffix_pat = re.compile(r"\b(\d{" + str(18 - len(partial)) + r"})\b")
        # Search in a window after the truncation
        pos = m.end()
        window = corpus[pos: pos + 120]
        sm = suffix_pat.search(window)
        if sm:
            return f"OD{partial}{sm.group(1)}", "HIGH"

    # S7 — Tail rescue: 15-18 digit block near keyword
    if near_kw:
        candidates = [c for c in
                      _PAT_TAIL.findall(re.sub(r"\s+", "", corpus)) +
                      _PAT_TAIL.findall(corpus)
                      if len(c) >= 15]
        if candidates:
            best = max(candidates, key=len)
            if len(best) < 18:
                best = best.zfill(18)
            return f"OD{best}", "LOW"

    return None, None


def _extract_order_id(text: str) -> tuple:
    """Returns (order_id | None, 'HIGH'|'LOW'|None)."""
    lines    = text.splitlines()
    kw_lines = []
    for i, line in enumerate(lines):
        if _KW.search(line):
            kw_lines.extend(lines[i: i + 5])

    if kw_lines:
        oid, conf = _strategies("\n".join(kw_lines), near_kw=True)
        if oid: return oid, conf

    # Full text — run all strategies except noisy tail rescue
    return _strategies(text, near_kw=False)


# =============================================================
#  STAR RATING  —  text first, colour blobs second
# =============================================================

def _star_from_text(text: str) -> Optional[float]:
    """Parse star rating from OCR text."""
    patterns = [
        r"(\d+(?:\.\d)?)\s*(?:out\s*of\s*5|/\s*5)",
        r"(\d+(?:\.\d)?)\s*-?\s*star",
        r"star[s]?\s*[:\-]?\s*(\d+(?:\.\d)?)",
        r"rating[s]?\s*[:\-]?\s*(\d+(?:\.\d)?)",
        r"rated\s+(\d+(?:\.\d)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = float(m.group(1))
            if 0 <= v <= 5: return v

    # Unicode star symbols
    filled = len(re.findall(r"[★⭐]", text))
    empty  = len(re.findall(r"☆", text))
    if 0 < filled + empty <= 5:
        return float(filled)
    return None


def _star_from_image(img_bgr: np.ndarray, meta: dict) -> Optional[float]:
    """
    OpenCV colour blob star detection.
    Finds the most uniform horizontal strip of same-size coloured blobs.
    """
    mask = meta.get("star_mask")
    if mask is None or cv2.countNonZero(mask) == 0:
        return None

    h, w    = mask.shape
    slice_h = max(1, h // 12)
    best_score, best_top = 0.0, -1

    for top in range(0, h - slice_h, max(1, slice_h // 2)):
        strip = mask[top: top + slice_h, :]
        if cv2.countNonZero(strip) < 20: continue
        cnts, _ = cv2.findContours(strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area    = slice_h * w
        valid   = [c for c in cnts if area * 0.001 < cv2.contourArea(c) < area * 0.30]
        if not (1 <= len(valid) <= 7): continue
        areas  = [cv2.contourArea(c) for c in valid]
        cv_val = np.std(areas) / np.mean(areas) if np.mean(areas) > 0 else 99
        score  = len(valid) / (1.0 + cv_val)
        if score > best_score:
            best_score, best_top = score, top

    if best_top < 0 or best_score < 0.3:
        return None

    strip  = mask[best_top: best_top + slice_h, :]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    closed = cv2.morphologyEx(strip, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total   = strip.shape[0] * strip.shape[1]
    valid   = [c for c in cnts if total * 0.001 < cv2.contourArea(c) < total * 0.40]
    n       = len(valid)
    return float(n) if 1 <= n <= 5 else None


def _star_remark(star: float, meta: dict, mask) -> str:
    n = int(star) if star == int(star) else star
    # Detect single-highlighted star
    if mask is not None:
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total   = mask.shape[0] * mask.shape[1]
        valid   = [c for c in cnts if cv2.contourArea(c) > total * 0.0004]
        if len(valid) == 1 and star > 1:
            return f"Single - {n}"
    if meta.get("is_dark_mode"):
        return f"Dark - {n}"
    return str(n)


# =============================================================
#  PUBLIC API
# =============================================================

def extract_order_id(image_path: str) -> tuple:
    """Returns (order_id | None, remark, engine)."""
    try:
        img, _ = preprocess(image_path)
    except Exception as e:
        return None, f"Image error: {e}", "none"
    try:
        text, conf = _run_ocr(img)
        oid, confidence = _extract_order_id(text)
        if oid and confidence == "HIGH":
            return oid, "Extracted by RapidOCR", "rapidocr"
        if oid and confidence == "LOW":
            return oid, "Partial match — verify prefix digits", "rapidocr_partial"
        if conf < OCR_CONFIDENCE_THRESHOLD:
            return None, f"Low OCR confidence ({conf:.2f})", "rapidocr"
        return None, "Pattern not matched in text", "rapidocr"
    except Exception as e:
        return None, f"OCR error: {e}", "none"


def extract_star_rating(image_path: str) -> tuple:
    """Returns (star | None, remark, engine)."""
    try:
        img, meta = preprocess_for_stars(image_path)
    except Exception as e:
        return None, f"Image error: {e}", "none"

    # Method 1: text (most reliable)
    try:
        text, _ = _run_ocr(img)
        star = _star_from_text(text)
        if star is not None:
            mask   = meta.get("star_mask")
            remark = _star_remark(star, meta, mask)
            return star, remark, "rapidocr_text"
    except Exception as e:
        logger.debug("Text star error: %s", e)

    # Method 2: colour blobs
    try:
        star = _star_from_image(img, meta)
        if star is not None:
            mask   = meta.get("star_mask")
            remark = _star_remark(star, meta, mask)
            return star, remark, "opencv_color"
    except Exception as e:
        logger.debug("CV star error: %s", e)

    return None, "", "none"


def get_raw_ocr(image_path: str) -> str:
    """Return raw OCR text dump for debug column in DB."""
    try:
        img, _ = preprocess(image_path)
        text, _ = _run_ocr(img)
        return text
    except Exception as e:
        return f"error: {e}"