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
    Detect star rating using pure OpenCV colour analysis.
    
    IMPROVED:
    - Stricter validation of detected shapes
    - Better handling of single-star patterns
    - Spatial constraints (must be in upper portion)

    Returns (star_count: float | None, method: str)
    method is one of: 'top_row', 'widest_row', 'single', 'none'
    """
    mask = meta.get("star_mask")
    if mask is None or cv2.countNonZero(mask) < 20:
        return None, "none"

    rows = _build_star_rows(mask)
    if not rows:
        return None, "none"

    # Evaluate all rows once (avoid committing early to a noisy topmost row).
    scored = []
    for top_y, blob_count, row_width, strip in rows:
        n = _count_filled_blobs(strip)
        if 1 <= n <= 5:
            scored.append((top_y, n, row_width, strip))

    if not scored:
        return None, "none"

    # ── Strategy A: prefer a multi-star row (3–5) and take the one with
    # the highest star count (tie-breaker: topmost). This reduces cases where
    # a partial/missed mask yields 4 when the UI clearly shows 5.
    multi = [r for r in scored if 3 <= r[1] <= 5]
    if multi:
        top_y, n, row_width, strip = sorted(multi, key=lambda r: (-r[1], r[0]))[0]
        return float(n), "top_row"

    # ── Strategy B: if only 1–2 stars detected, pick the WIDEST row (most prominent) ──
    top_y, n, row_width, strip = max(scored, key=lambda r: r[2])

    # Single-highlighted star pattern (others unfilled/black):
    if n == 1:
        xs = []
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        work = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel, iterations=1)
        work = cv2.erode(work, kernel, iterations=1)
        cnts, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h_s, w_s = strip.shape[:2]
        min_dim = max(8, int(w_s * 0.010))
        max_dim = max(min_dim + 2, int(w_s * 0.160))
        min_area = float(min_dim * min_dim) * 0.25
        max_area = float(max_dim * max_dim) * 2.00
        for c in cnts:
            if _is_star_like_contour(
                c, min_area=min_area, max_area=max_area, min_dim=min_dim, max_dim=max_dim
            ):
                M = cv2.moments(c)
                if M["m00"] > 0:
                    xs.append(int(M["m10"] / M["m00"]))

        if xs:
            # Prefer geometry from the actual (mostly black) star row, not image-wide heuristics.
            # In these UIs only 1 star is filled; the other 4 are black outlines/filled.
            # Detect all 5 stars using edges within the same strip window.
            star_x = xs[0]
            top_y, _, _, _ = max(scored, key=lambda r: r[2])
            # Rebuild the strip window in original image coords to run edge detection.
            slice_h = strip.shape[0]
            y0 = int(top_y)
            y1 = min(img_bgr.shape[0], y0 + slice_h)
            roi = img_bgr[y0:y1, :, :]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(gray, 50, 150)
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            edges = cv2.dilate(edges, k, iterations=1)
            cnts2, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            h_img, w_img = mask.shape
            x_centers = []
            for c in cnts2:
                x, y, wb, hb = cv2.boundingRect(c)
                if wb < int(w_img * 0.02) or hb < int(w_img * 0.02):
                    continue
                if wb > int(w_img * 0.20) or hb > int(w_img * 0.20):
                    continue
                aspect = max(wb, hb) / (min(wb, hb) + 1)
                if aspect > 2.2:
                    continue
                # Keep shapes near the detected filled-star y band (avoid UI icons)
                if not (0 <= y <= slice_h):
                    continue
                x_centers.append(x + wb / 2.0)

            x_centers.sort()
            # Cluster x centers (stars are evenly spaced; duplicates come from noisy edges).
            clustered = []
            for xc in x_centers:
                if not clustered or abs(xc - clustered[-1]) > int(w_img * 0.03):
                    clustered.append(xc)
            if len(clustered) >= 5:
                # Pick the best 5-star window with the most-uniform spacing.
                best = None
                for i in range(0, len(clustered) - 4):
                    win = clustered[i : i + 5]
                    diffs = [win[j + 1] - win[j] for j in range(4)]
                    if any(d <= 0 for d in diffs):
                        continue
                    step = float(np.median(diffs))
                    if not (w_img * 0.03 <= step <= w_img * 0.25):
                        continue
                    cv = float(np.std(diffs) / step) if step > 0 else 9.9
                    if best is None or cv < best[0]:
                        best = (cv, win)
                if best is not None:
                    win = best[1]
                    # Choose nearest slot center.
                    idx0 = int(np.argmin([abs(star_x - xc) for xc in win]))
                    return float(idx0 + 1), "single"

            if len(clustered) >= 3:
                # Use the median spacing to infer a 5-slot grid.
                diffs = [clustered[i + 1] - clustered[i] for i in range(len(clustered) - 1)]
                diffs = [d for d in diffs if d > 0]
                if diffs:
                    step = float(np.median(diffs))
                    left = clustered[0]
                    idx = int(round((star_x - left) / step)) + 1
                    idx = max(1, min(5, idx))
                    return float(idx), "single"

            # Fallback mapping when edge-based grid fails.
            left = 0.10 * w_img
            span = 0.80 * w_img
            rel = (star_x - left) / span
            star_pos = round(rel * 5)
            star_pos = max(1, min(5, star_pos))
            return float(star_pos), "single"

    if 1 <= n <= 5:
        return float(n), "widest_row"

    return None, "none"


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
    """
    Returns (star | None, remark, engine).
    Pure OpenCV — no OCR, no text parsing for stars.
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

    return None, "Stars not found in image", "none"


def get_raw_ocr(image_path: str) -> str:
    """Return raw OCR text dump for debug column in DB."""
    try:
        img, _ = preprocess(image_path)
        text, _ = _run_ocr(img)
        return text
    except Exception as e:
        return f"error: {e}"
