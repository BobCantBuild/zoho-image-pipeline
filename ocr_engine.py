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
from image_preprocess import preprocess, preprocess_colour, preprocess_for_stars

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
# OD number where OCR inserted spaces inside the digit string
# e.g. "OD33714786851192 9100" or "OD 337147868511929100"
# Captures up to 22 chars (18 digits + up to 4 spaces OCR noise)
_PAT_OD_SPACED   = re.compile(r"[Oo0][Dd]\s{0,2}([\d][\d ]{15,21}[\d])")

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

    # S2b — OD with internal spaces (OCR breaks long digit strings)
    # e.g. "OD33714786851192 9100" → "OD337147868511929100"
    m = _PAT_OD_SPACED.search(corpus)
    if m:
        digits = re.sub(r"\s", "", m.group(1))
        if len(digits) == 18:
            return f"OD{digits}", "HIGH"
    # Also try on stitched (catches "OD 337..." where the split is at "OD")
    m = _PAT_OD_SPACED.search(re.sub(r"\n", " ", corpus))
    if m:
        digits = re.sub(r"\s", "", m.group(1))
        if len(digits) == 18:
            return f"OD{digits}", "HIGH"

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
    lines = text.splitlines()

    # ── Pre-pass: "Order ID:" on line N, OD value on line N+1/N+2 ────────
    # Handles Flipkart invoice layout where label and value are on separate
    # lines.  We scan each non-empty line after the keyword for something
    # that looks like an OD number (with possible OCR noise).
    for i, line in enumerate(lines):
        if not _KW.search(line):
            continue
        checked = 0
        for j in range(i + 1, min(i + 6, len(lines))):
            candidate = lines[j].strip()
            if not candidate:
                continue
            checked += 1
            if checked > 3:
                break
            # Strip spaces, hyphens, dots that OCR might insert
            stitched = re.sub(r"[\s\-\.]", "", candidate)
            # Full-line OD match (exactly OD + 18 digits)
            m = re.fullmatch(r"[Oo0][Dd](\d{16,20})", stitched)
            if m:
                digits = m.group(1)
                if len(digits) == 18:
                    return f"OD{digits}", "HIGH"
                # Off by 1-2 digits — OCR clipping at line edge
                if 16 <= len(digits) <= 20:
                    return f"OD{digits[:18]}", "HIGH"
            # OD prefix may be on the SAME line as "Order ID:" — check
            # if the candidate is purely digits (prefix already consumed)
            m = re.fullmatch(r"(\d{17,19})", stitched)
            if m:
                digits = m.group(1).zfill(18)
                return f"OD{digits}", "HIGH"

    # ── Keyword-window strategy pass ──────────────────────────────────────
    # Collect up to 10 lines after every keyword match; wider than the old
    # 5-line window to handle invoice tables where OCR interleaves columns.
    kw_lines: list[str] = []
    for i, line in enumerate(lines):
        if _KW.search(line):
            kw_lines.extend(lines[i: i + 10])   # was 5

    if kw_lines:
        oid, conf = _strategies("\n".join(kw_lines), near_kw=True)
        if oid:
            return oid, conf

    # ── Full text — run all strategies except noisy tail rescue ───────────
    return _strategies(text, near_kw=False)


# =============================================================
#  STAR RATING  —  Pure OpenCV only. No OCR. No text parsing.
#
#  Key insight from real images:
#  - Image2 is a review/rating screen (Amazon or Flipkart)
#  - Stars are ALWAYS yellow or green coloured icons
#  - The OVERALL rating row is:
#      Amazon  → appears as a single row near top, largest/widest
#      Flipkart → top row before category breakdowns (cooling, etc.)
#  - Category rows (cooling, design, etc.) are smaller + lower down
#  - If Image2 is a bill/invoice → no star blobs found → return None
#
#  Algorithm:
#  1. Build HSV colour mask (yellow + green + dim yellow for dark mode)
#  2. Find ALL horizontal star-row candidates
#  3. Pick the TOPMOST row that has 1-5 uniform blobs
#     (overall rating is always above category ratings)
#  4. Count filled blobs in that row = star rating
#  5. Handle single-highlighted star (e.g. only 4th star coloured)
# =============================================================

def _is_star_like_contour(
    c: np.ndarray,
    *,
    min_area: float,
    max_area: float,
    min_dim: int,
    max_dim: int,
) -> bool:
    """
    Heuristic filter to distinguish star icons from random coloured blobs.

    Key properties of filled star icons (common in Amazon/Flipkart screenshots):
    - Roughly square-ish bounding box (not long thin lines)
    - Concave shape (convex hull area noticeably larger than contour area)
    - Many vertices after polygon approximation
    - Several convexity defects (the "indentations" between star points)
    """
    area = cv2.contourArea(c)
    if not (min_area < area < max_area):
        return False

    peri = cv2.arcLength(c, True)
    if peri <= 0:
        return False

    x, y, w_box, h_box = cv2.boundingRect(c)
    if min(w_box, h_box) < min_dim:
        return False
    if max(w_box, h_box) > max_dim:
        return False
    aspect = max(w_box, h_box) / (min(w_box, h_box) + 1)
    if aspect > 1.9:
        return False

    hull = cv2.convexHull(c)
    hull_area = cv2.contourArea(hull)
    if hull_area <= 0:
        return False
    solidity = float(area) / float(hull_area)
    # Star is concave => solidity should not be too close to 1.0 (circles/rectangles).
    # But allow some variation across UIs / scaling.
    if not (0.45 <= solidity <= 0.92):
        return False

    # Polygon complexity: stars typically produce many vertices after approximation.
    eps = 0.02 * peri
    approx = cv2.approxPolyDP(c, eps, True)
    if len(approx) < 8:
        return False

    # Convexity defects: stars have multiple indentations.
    hull_idx = cv2.convexHull(c, returnPoints=False)
    if hull_idx is None or len(hull_idx) < 4:
        return False
    defects = cv2.convexityDefects(c, hull_idx)
    if defects is None:
        return False

    # `d` is distance*256; use a conservative threshold to ignore tiny notches/noise.
    # Phone photos can blur stars heavily; scale depth threshold by icon size.
    min_side = max(1, min(w_box, h_box))
    min_depth = max(200, int(256 * (min_side * 0.06)))
    deep_defects = 0
    for d in defects:
        if d is None or len(d) == 0:
            continue
        depth = int(d[0][3])
        if depth >= min_depth:
            deep_defects += 1
    if deep_defects < 3:
        return False

    return True


def _build_star_rows(mask: np.ndarray) -> list:
    """
    Scan the mask and return all candidate star rows as:
    [(top_y, blob_count, row_width, strip_mask), ...]
    sorted top-to-bottom (smallest top_y first).
    
    IMPROVED: 
    - Stricter size validation
    - Star-shape validation (reject non-star blobs)
    - Focus on top 60% of image (where ratings typically appear)
    - Better blob uniformity detection
    """
    h, w      = mask.shape
    
    # Focus on upper portion of image; some UIs place rating rows around mid-screen.
    max_scan_h = int(h * 0.85)
    
    # Each scan strip must be tall enough to contain a full star icon.
    # Too-small strips can slice stars in half and create false contours.
    slice_h   = max(24, h // 10)   # each scan strip height
    step      = max(4, slice_h // 3)
    rows      = []
    seen_tops = set()

    for top in range(0, min(max_scan_h - slice_h, h - slice_h), step):
        strip = mask[top: top + slice_h, :]
        px    = cv2.countNonZero(strip)
        if px < 20:  # raised threshold
            continue

        # Find contours in this strip.
        # Important: avoid aggressive CLOSE here, it can merge adjacent stars into one blob.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        work = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel, iterations=1)
        work = cv2.erode(work, kernel, iterations=1)
        cnts, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Size bounds based on image width (more stable than strip-area % for small icons)
        min_dim = max(8, int(w * 0.010))   # ~1% of width
        max_dim = max(min_dim + 2, int(w * 0.160))  # up to ~16% of width (some UIs use big stars)
        min_area = float(min_dim * min_dim) * 0.25
        max_area = float(max_dim * max_dim) * 2.00
        
        valid = []
        for c in cnts:
            if _is_star_like_contour(
                c, min_area=min_area, max_area=max_area, min_dim=min_dim, max_dim=max_dim
            ):
                valid.append(c)

        if not (1 <= len(valid) <= 5):
            continue

        # Check size uniformity — star icons are same size
        areas  = [cv2.contourArea(c) for c in valid]
        mean_area = np.mean(areas)
        
        # IMPROVED: Stricter uniformity check (CV < 0.4 instead of < 0.6)
        cv_val = (np.std(areas) / mean_area) if mean_area > 0 else 99
        if cv_val > 0.40:   # too varied → not a star row
            continue

        # Measure span width of blobs (leftmost to rightmost centroid)
        xs = []
        for c in valid:
            M = cv2.moments(c)
            if M["m00"] > 0:
                xs.append(int(M["m10"] / M["m00"]))
        if not xs:
            continue
        row_width = max(xs) - min(xs) if len(xs) > 1 else int(np.sqrt(areas[0]))
        
        # Row width constraints:
        # - Avoid single stray blobs (too narrow)
        # - Avoid 2-blob full-width artifacts (too wide)
        min_row_width = int(w * (0.03 if len(valid) == 1 else 0.08))
        if row_width < min_row_width:
            continue
        if len(valid) <= 2 and row_width > int(w * 0.60):
            continue

        # Avoid duplicates (same row detected in overlapping strips)
        bucket = top // slice_h
        if bucket in seen_tops:
            continue
        seen_tops.add(bucket)

        rows.append((top, len(valid), row_width, strip))

    # Sort top-to-bottom
    rows.sort(key=lambda r: r[0])
    return rows


def _count_filled_blobs(strip: np.ndarray) -> int:
    """
    Count star blobs in a strip after morphological close.
    
    IMPROVED: Apply same strict filters as _build_star_rows:
    - Size constraints (0.5-12% of strip area)
    - Star-shape validation
    """
    # Same rationale as _build_star_rows: do not merge stars.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    work = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel, iterations=1)
    work = cv2.erode(work, kernel, iterations=1)
    cnts, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    h_s, w_s = strip.shape[:2]
    min_dim = max(8, int(w_s * 0.010))
    max_dim = max(min_dim + 2, int(w_s * 0.160))
    min_area = float(min_dim * min_dim) * 0.25
    max_area = float(max_dim * max_dim) * 2.00
    
    valid = []
    for c in cnts:
        if _is_star_like_contour(
            c, min_area=min_area, max_area=max_area, min_dim=min_dim, max_dim=max_dim
        ):
            valid.append(c)
    
    return len(valid)


def _star_from_image(img_bgr: np.ndarray, meta: dict) -> tuple:
    """
    Detect star rating using OpenCV colour analysis.

    Returns (star_count: float | None, method: str)

    Strategy cascade
    ────────────────
    A  Amazon-style multi-star row  (2–5 uniform yellow stars in one row)
       → count filled blobs = rating. Topmost row wins on tie.

    B  Flipkart label-select style  (exactly 1 colored star; others dark)
       → _detect_all_star_slots() finds all 5 icon positions via grayscale
         threshold (dark + colored) in the same y-band.
       → _position_of_colored_star() maps the colored blob to slot 1-5.

    C  Widest-row fallback           (2 blobs, ambiguous)
       → apply B-style all-slot detection before committing.

    Rooted failure modes fixed
    ──────────────────────────
    • Emoji star (Great 🌟) fails _is_star_like_contour → B no longer
      relies on that test for the colored star; it uses the mask's raw
      centroid instead.
    • Category star rows (Image 5) inflate blob count → A now requires
      the topmost multi-star row, not the highest-count one.
    • Rotated image (Image 1) → auto-rotation in preprocess_for_stars()
      corrects before this function runs.
    • Green stars (Image 4) → expanded mask in preprocess_for_stars().
    """
    mask = meta.get("star_mask")
    if mask is None or cv2.countNonZero(mask) < 20:
        return None, "none"

    rows = _build_star_rows(mask)
    if not rows:
        return None, "none"

    h_img, w_img = mask.shape

    # Evaluate all candidate rows
    scored = []
    for top_y, blob_count, row_width, strip in rows:
        n = _count_filled_blobs(strip)
        if 1 <= n <= 5:
            scored.append((top_y, n, row_width, strip))

    if not scored:
        return None, "none"

    # ── Strategy A: Amazon-style ─────────────────────────────
    # 2–5 uniform colored blobs in one row AND that row is the topmost
    # multi-star row.  (Do NOT take highest count — that favors category rows.)
    multi = [r for r in scored if 2 <= r[1] <= 5]
    if multi:
        # Topmost first; break tie by widest (more prominent overall-rating row)
        top_y, n, row_width, strip = sorted(multi, key=lambda r: (r[0], -r[2]))[0]

        # Sanity-check: if the row has 2 blobs but the full-slot scan finds 5,
        # this is actually Flipkart style with 2 filled — handle in Strategy B.
        if n >= 3:
            return float(n), "top_row"

        # n == 2: might be Flipkart with 2 dark stars selected; fall through to B.

    # ── Strategy B: Flipkart label-select style ──────────────
    # Find the topmost row with ANY colored blob (n=1 most common, but n=2 is ok).
    # Get raw centroid of the colored region from the mask directly
    # (avoids _is_star_like_contour rejecting emoji shapes).
    single_candidates = [r for r in scored if 1 <= r[1] <= 2]
    if not single_candidates and multi:
        # n==2 case from Strategy A falls here
        single_candidates = [r for r in scored if r[1] == 2]

    if single_candidates:
        # Widest row = most prominent (the overall-rating row spans more pixels)
        top_y, n, row_width, strip = max(single_candidates, key=lambda r: r[2])

        # Get centroid of colored pixels in the strip from the full mask
        slice_h = strip.shape[0]
        y0 = int(top_y)
        y1 = min(h_img, y0 + slice_h)
        mask_strip = mask[y0:y1, :]

        ys_px, xs_px = np.where(mask_strip > 0)
        if len(xs_px) == 0:
            # Mask empty in this band — use strip directly
            ys_px, xs_px = np.where(strip > 0)

        if len(xs_px) > 0:
            # Use median x to be robust against multi-blob emoji internals
            colored_x = float(np.median(xs_px))

            # Expand the search band a bit so we capture all 5 icons
            pad = max(slice_h, int(h_img * 0.08))
            band_y0 = max(0, y0 - pad // 2)
            band_y1 = min(h_img, y1 + pad // 2)

            all_slots = _detect_all_star_slots(img_bgr, band_y0, band_y1)

            # Only use slot detection when we found a plausible row of icons
            if 3 <= len(all_slots) <= 7:
                pos = _position_of_colored_star(colored_x, all_slots)
                if 1 <= pos <= 5:
                    return float(pos), "slot_position"

            # Slot detection found too few/many — linear fallback
            left = 0.08 * w_img
            span = 0.84 * w_img
            rel  = (colored_x - left) / span
            star_pos = max(1, min(5, round(rel * 4) + 1))
            return float(star_pos), "linear_fallback"

    # ── Strategy C: multi-blob Amazon fallback ───────────────
    if multi:
        top_y, n, row_width, strip = sorted(multi, key=lambda r: (r[0], -r[2]))[0]
        return float(n), "top_row"

    return None, "none"


# =============================================================
#  FLIPKART LABEL-SELECT UI  helpers
#
#  Flipkart's review screen shows 5 labeled icons:
#    Terrible · Bad · Okay · Good · Great
#  Only the SELECTED icon is colored (yellow emoji or green fill).
#  The other 4 are dark/black outlines.
#  Strategy: detect ALL 5 icon slots via grayscale threshold, then
#  find which slot contains the colored blob → that position = rating.
#  Fallback: OCR reads the label text ("Great", "Good", …) → map to int.
# =============================================================

_LABEL_MAP: dict[str, float] = {
    "great": 5.0, "good": 4.0, "okay": 3.0, "ok": 3.0,
    "bad": 2.0, "terrible": 1.0,
}


def _detect_all_star_slots(img_bgr: np.ndarray, y0: int, y1: int) -> list[float]:
    """
    Find ALL icon/star x-centres in a horizontal band [y0, y1] regardless of color.
    Uses Otsu threshold on grayscale to detect both dark outlines AND filled blobs.
    Returns sorted list of x-centres (should be 5 for Flipkart; ≥1 for anything).
    """
    roi  = img_bgr[y0:y1, :, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h_r, w_r = gray.shape

    # Use both dark-on-light (threshold inversion) and edge-based detection,
    # then merge — covers all background colours.
    _, thresh_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 100)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    edges = cv2.dilate(edges, k, iterations=2)
    combined = cv2.bitwise_or(thresh_inv, edges)

    cnts, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_dim = max(8, int(w_r * 0.04))
    max_dim = int(w_r * 0.22)

    centres: list[float] = []
    for c in cnts:
        x, y, wb, hb = cv2.boundingRect(c)
        if wb < min_dim or hb < min_dim:
            continue
        if wb > max_dim or hb > max_dim:
            continue
        aspect = max(wb, hb) / (min(wb, hb) + 1)
        if aspect > 2.0:
            continue
        if cv2.contourArea(c) < min_dim * min_dim * 0.25:
            continue
        centres.append(float(x + wb / 2.0))

    centres.sort()
    # Cluster near-duplicates (edge detection can double-count outlines)
    clustered: list[float] = []
    for cx in centres:
        if not clustered or abs(cx - clustered[-1]) > min_dim * 0.8:
            clustered.append(cx)

    return clustered


def _position_of_colored_star(colored_x: float, all_slots: list[float]) -> int:
    """
    Given the x-centre of the colored star and all slot x-centres,
    return 1-based position of the colored star in the row.
    Falls back to linear interpolation if slot count != 5.
    """
    if len(all_slots) == 5:
        idx = int(np.argmin([abs(colored_x - cx) for cx in all_slots]))
        return idx + 1

    # Fewer slots found — use evenly-spaced grid assumption
    if len(all_slots) >= 2:
        left  = all_slots[0]
        right = all_slots[-1]
        step  = (right - left) / (len(all_slots) - 1)
        if step > 0:
            pos = int(round((colored_x - left) / step)) + 1
            return max(1, min(5, pos))

    return 0   # unknown


# Token-based classification. Whole-phrase fuzzy matching is unreliable here
# because a common word inflates the score: "installation & demo" despaced is
# "installationdemo", which an Amazon invoice line "...installation service..."
# matches at 0.75 even though it has no "demo". So instead we require EACH
# discriminating token to be independently present (with OCR tolerance):
#   service  ⇐ "installation" AND "demo"   (demo also lives inside "demonstration")
#   product  ⇐ "experience"                (the rare, defining word on that screen)
# "rate"/"installation" alone are too common (Amazon shows "Rate Seller",
# "Installation Service"), so neither can classify on its own.
_SERVICE_TOKENS = ("installation", "demo")
_PRODUCT_TOKENS = ("experience",)


def _token_present(token: str, words: list[str], flat: str) -> bool:
    """
    True if `token` appears in the OCR text, tolerating character errors.

      • substring of the despaced text  — catches merged OCR ("rateyourexperience")
        and stems ("demo" inside "demonstration")
      • fuzzy match against any single whitespace word — catches char swaps like
        "instailation" → "installation"
    Short tokens use a slightly higher word-fuzz bar to avoid chance hits.
    """
    from difflib import SequenceMatcher
    if token in flat:
        return True
    threshold = 0.80 if len(token) >= 6 else 0.78
    return any(SequenceMatcher(None, token, w).ratio() >= threshold for w in words)


def classify_star_category(text: str) -> str:
    """
    Examine the raw OCR text from the star-rating image and return which
    rating category the detected star count belongs to:

      "service"  — screen shows "Installation and Demo" (or similar)
      "product"  — screen shows "Rate your experience" (or similar)
      "general"  — neither phrase detected (default / unknown)

    Robust to the messy OCR these phone-photo / screenshot images produce.
    """
    norm  = " ".join((text or "").lower().split())   # collapsed whitespace
    words = norm.split()
    flat  = re.sub(r"[^a-z0-9]", "", norm)           # every separator removed

    if all(_token_present(t, words, flat) for t in _SERVICE_TOKENS):
        return "service"
    if all(_token_present(t, words, flat) for t in _PRODUCT_TOKENS):
        return "product"
    return "general"


def _star_from_label(text: str) -> float | None:
    """
    Flipkart OCR fallback: scan text for rating labels.
    The UI always shows all 5 labels; the SELECTED label typically appears
    last in left-to-right OCR order (rightmost = highest selected rating).
    To avoid false positives from unselected labels, we only trust this
    when exactly ONE label is found OR when the rightmost one is unambiguous.
    """
    import re
    found = re.findall(
        r"\b(great|good|okay|ok|bad|terrible)\b", text.lower()
    )
    if not found:
        return None

    # De-duplicate while preserving order
    seen: set[str] = set()
    ordered = [w for w in found if not (w in seen or seen.add(w))]  # type: ignore[func-returns-value]

    if len(ordered) == 1:
        return _LABEL_MAP.get(ordered[0])

    # Multiple labels visible (normal for Flipkart review form).
    # Rightmost = highest selected star.
    return _LABEL_MAP.get(ordered[-1])


def _star_remark(star: float, meta: dict, method: str) -> str:
    """Build remark string per spec."""
    n = int(star) if star == int(star) else star
    if method == "single":
        return f"Single - {n}"
    if meta.get("is_dark_mode"):
        return f"Dark - {n}"
    return str(n)


# =============================================================
#  PUBLIC API
# =============================================================

def extract_order_id(image_path: str) -> tuple:
    """
    Returns (order_id | None, remark, engine).

    Two-pass OCR for robustness:
    Pass 1 — binarised image (standard; best for clean screenshots)
    Pass 2 — colour image, no binarization (fallback for phone-photo-of-screen
              where adaptive threshold fragments text due to Moiré / glare)
    """
    for pass_num, _prep in enumerate((preprocess, preprocess_colour), start=1):
        try:
            img, _ = _prep(image_path)
        except Exception as e:
            return None, f"Image error: {e}", "none"
        try:
            text, conf = _run_ocr(img)
            oid, confidence = _extract_order_id(text)
            if oid and confidence == "HIGH":
                suffix = "" if pass_num == 1 else " (colour pass)"
                return oid, f"Extracted by RapidOCR{suffix}", "rapidocr"
            if oid and confidence == "LOW":
                suffix = "" if pass_num == 1 else " (colour pass)"
                return oid, f"Partial match — verify prefix digits{suffix}", "rapidocr_partial"
        except Exception as e:
            logger.debug("OCR pass %d error: %s", pass_num, e)
            if pass_num == 1:
                continue   # try colour pass
            return None, f"OCR error: {e}", "none"

    return None, "Pattern not matched in text", "rapidocr"


def extract_star_rating(image_path: str) -> tuple:
    """
    Returns (star | None, remark, engine).

    Primary:  OpenCV colour + slot-position detection
    Fallback: OCR label text  (Terrible/Bad/Okay/Good/Great → 1-5)
              Used when color detection returns None — covers edge cases
              where the UI renders stars as text/SVG icons outside the
              HSV ranges, or when image quality is too low for shape tests.
    """
    try:
        img, meta = preprocess_for_stars(image_path)
    except Exception as e:
        return None, f"Image error: {e}", "none"

    try:
        star, method = _star_from_image(img, meta)
        if star is not None:
            remark = _star_remark(star, meta, method)
            return star, remark, f"opencv_{method}"
    except Exception as e:
        logger.debug("CV star error: %s", e)

    # ── OCR label fallback ────────────────────────────────────
    # Run text OCR on the same image and look for Flipkart rating labels.
    try:
        from image_preprocess import preprocess as _preprocess_ocr
        img_ocr, _ = _preprocess_ocr(image_path)
        text, conf  = _run_ocr(img_ocr)
        star = _star_from_label(text)
        if star is not None:
            return star, f"OCR label ({int(star)}★)", "ocr_label"
    except Exception as e:
        logger.debug("OCR label fallback error: %s", e)

    return None, "Stars not found in files", "none"


# classify_star_category is already defined above — re-export for callers.
# (imported directly by pipeline.py: from ocr_engine import classify_star_category)


def get_raw_ocr(image_path: str) -> str:
    """Return raw OCR text dump for debug column in DB."""
    try:
        img, _ = preprocess(image_path)
        text, _ = _run_ocr(img)
        return text
    except Exception as e:
        return f"error: {e}"
