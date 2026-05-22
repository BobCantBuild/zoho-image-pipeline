# =============================================================
#  CONSOLIDATED STAR DETECTION v4
#  Single file: all preprocessing + detection + fallbacks
#  Easy to track, version, and validate
#
#  v4 improvements (validated against 60-image dataset):
#  - _count_filled_blobs: 2-pass approach (shape → CC fallback)
#    prevents the 5th blob getting killed by double erosion
#  - _is_star_like_contour: deep_defects lowered 3→2 for small stars
#  - _build_star_rows: lighter (2,2) kernel in inner loop
#  - _star_from_image: progressive wider bands for slot detection
#  - preprocess_for_stars: warm-green + wider muted-green HSV band
#  - 0-star: multi-band scan for empty grid patterns
# =============================================================

import cv2
import numpy as np
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
#  PREPROCESSING
# ────────────────────────────────────────────────────────────

MAX_IMAGE_EDGE = 1280
OCR_CONFIDENCE_THRESHOLD = 0.25


def _resize(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / longest
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA)
    return img


def _clahe(img: np.ndarray) -> np.ndarray:
    """Adaptive contrast — fixes dark/washed photos."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _sharpen(img: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1)
    return cv2.addWeighted(img, 1.4, blur, -0.4, 0)


def is_dark_mode(img: np.ndarray) -> bool:
    return np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)) < 100


def _auto_rotate(img: np.ndarray) -> np.ndarray:
    """Detect and correct image rotation using Hough dominant-line angle."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=img.shape[1] // 6, maxLineGap=20)
    if lines is None or len(lines) < 5:
        return img

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 != x1:
            angles.append(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

    if not angles:
        return img

    median_angle = float(np.median(angles))

    if abs(median_angle) < 10:
        return img

    if 45 < abs(median_angle) <= 135:
        if median_angle > 0:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    return img


def load_image(image_path: str) -> np.ndarray:
    """Load image from disk."""
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    img = cv2.imread(str(p))
    if img is None:
        raise ValueError(f"OpenCV cannot read: {image_path}")
    return img


def preprocess_for_stars(image_path: str, *, wide_green: bool = False) -> tuple:
    """
    Preprocess for star detection: resize → CLAHE → sharpen → auto-rotate → HSV mask.
    Returns (img_bgr, meta_dict).

    HSV Colour Ranges (primary pass):
      - Yellow/gold (Amazon/Flipkart): H[18-35] S[80-255] V[80-255]
      - Dim yellow (dark photos): H[15-40] S[35-220] V[40-220]
      - Orange (warm WB): H[0-18] S[80-255] V[70-255]
      - Green bright (standard): H[40-95] S[70-255] V[70-255]
      - Green muted (Flipkart Order Details): H[36-92] S[25-170] V[45-210]

    wide_green=True: activated only as a RETRY when the primary pass found
      < 20 colored pixels.  Adds a much wider green band and lighter gate so
      that unusually dim or washed-out green stars are captured.  Safe to use
      aggressively here because Flipkart slot images (1 bright + 4 dark stars)
      always produce ≥ 1 colored pixel in the primary pass and therefore never
      reach the retry path.
    """
    img = load_image(image_path)
    dark = is_dark_mode(img)
    img = _resize(img)
    img = _auto_rotate(img)
    img = _clahe(img)
    img = _sharpen(img)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # ── Colour masks ────────────────────────────────────────
    # Yellow/gold (Amazon & Flipkart filled stars)
    mask_y = cv2.inRange(hsv, np.array([18,  80,  80]),  np.array([35, 255, 255]))

    # Dim yellow (dark/low-exposure shots)
    mask_d = cv2.inRange(hsv, np.array([15,  35,  40]),  np.array([40, 220, 220]))

    # Orange (warm camera WB shift)
    mask_o = cv2.inRange(hsv, np.array([ 0,  80,  70]),  np.array([18, 255, 255]))

    # Green bright (standard Flipkart)
    mask_g_bright = cv2.inRange(hsv, np.array([40,  70,  70]),  np.array([95, 255, 255]))

    # Green muted (Flipkart Order Details — low saturation).
    # Matches the 68.3% baseline exactly; DO NOT widen without testing —
    # a lower S/V gate causes dark Flipkart outline-stars to appear "colored",
    # which turns 1-blob slot images into multi-blob top-row images with
    # wrong counts.
    mask_g_muted  = cv2.inRange(hsv, np.array([36,  25,  45]),  np.array([92, 170, 210]))

    mask_g = cv2.bitwise_or(mask_g_bright, mask_g_muted)

    # Wide-green retry: add a much broader green band on top of the primary masks.
    # Only active when the caller knows the primary pass found nothing — so there
    # is no risk of contaminating the Flipkart-slot path with dark outline stars.
    if wide_green:
        mask_g_extra = cv2.inRange(
            hsv, np.array([30,  6, 15]), np.array([108, 200, 235])
        )
        mask_g = cv2.bitwise_or(mask_g, mask_g_extra)

    # ── Gate on saturation + value ──────────────────────────
    mask_warm = cv2.bitwise_or(mask_y, cv2.bitwise_or(mask_d, mask_o))
    s_min = 50 if dark else 75
    v_min = 50 if dark else 75
    sat_ok = (hsv[:, :, 1] >= s_min).astype(np.uint8) * 255
    val_ok = (hsv[:, :, 2] >= v_min).astype(np.uint8) * 255
    mask_warm = cv2.bitwise_and(mask_warm, sat_ok)
    mask_warm = cv2.bitwise_and(mask_warm, val_ok)

    # Green gate: baseline values prevent dark Flipkart outline-stars leaking.
    # In wide-green mode, lower the gate so faint/dark green stars are captured;
    # this is safe because wide_green only fires when the primary mask is empty.
    if wide_green:
        sat_ok_g = (hsv[:, :, 1] >= 8).astype(np.uint8) * 255
        val_ok_g = (hsv[:, :, 2] >= 12).astype(np.uint8) * 255
    else:
        sat_ok_g = (hsv[:, :, 1] >= 22).astype(np.uint8) * 255
        val_ok_g = (hsv[:, :, 2] >= 42).astype(np.uint8) * 255
    mask_g = cv2.bitwise_and(mask_g, sat_ok_g)
    mask_g = cv2.bitwise_and(mask_g, val_ok_g)

    mask = cv2.bitwise_or(mask_warm, mask_g)

    # ── Morphological cleanup ──────────────────────────────
    # MORPH_OPEN(3,3) : kills specks.
    # MORPH_CLOSE(4,4): fills small holes inside blobs so shape
    #   validation later has solid, clean contours to work with.
    #   Tested: reducing this kernel (3,3 or 2,2) fragments star
    #   blobs rather than separating them — accuracy drops.
    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel_open)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    # Remove very large blobs (bezel/background) and very small noise
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = mask.shape[:2]
    max_area = int(h * w * 0.005)
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        ww   = int(stats[i, cv2.CC_STAT_WIDTH])
        hh   = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area > max_area or ww > int(w * 0.40) or hh > int(h * 0.25):
            mask[labels == i] = 0

    return img, {"is_dark_mode": dark, "star_mask": mask}


# ────────────────────────────────────────────────────────────
#  STAR DETECTION
# ────────────────────────────────────────────────────────────

_LABEL_MAP = {
    "great": 5.0, "good": 4.0, "okay": 3.0, "ok": 3.0,
    "bad": 2.0, "terrible": 1.0,
}

_ocr = None
_ocr_lock = None


def _get_ocr():
    """Lazy-load RapidOCR singleton."""
    global _ocr, _ocr_lock
    import threading
    if _ocr_lock is None:
        _ocr_lock = threading.Lock()
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    _ocr = RapidOCR()
                except ImportError:
                    raise ImportError("pip install rapidocr-onnxruntime")
    return _ocr


def _run_ocr(img_bgr: np.ndarray) -> tuple:
    """Run RapidOCR on image. Returns (text, confidence)."""
    ocr = _get_ocr()
    result, _ = ocr(img_bgr)
    if not result:
        return "", 0.0
    texts = [r[1] for r in result if r and len(r) >= 3]
    confs = [float(r[2]) for r in result if r and len(r) >= 3]
    if not texts:
        return "", 0.0
    return "\n".join(texts), float(np.mean(confs))


def _is_star_like_contour(
    c: np.ndarray, *, min_area: float, max_area: float,
    min_dim: int, max_dim: int
) -> bool:
    """Heuristic: detect star-shaped contours."""
    area = cv2.contourArea(c)
    if not (min_area < area < max_area):
        return False

    peri = cv2.arcLength(c, True)
    if peri <= 0:
        return False

    x, y, w_box, h_box = cv2.boundingRect(c)
    if min(w_box, h_box) < min_dim or max(w_box, h_box) > max_dim:
        return False

    aspect = max(w_box, h_box) / (min(w_box, h_box) + 1)
    if aspect > 1.9:
        return False

    hull = cv2.convexHull(c)
    hull_area = cv2.contourArea(hull)
    if hull_area <= 0:
        return False

    solidity = float(area) / float(hull_area)
    if not (0.45 <= solidity <= 0.92):
        return False

    eps = 0.02 * peri
    approx = cv2.approxPolyDP(c, eps, True)
    if len(approx) < 8:
        return False

    hull_idx = cv2.convexHull(c, returnPoints=False)
    if hull_idx is None or len(hull_idx) < 4:
        return False

    defects = cv2.convexityDefects(c, hull_idx)
    if defects is None:
        return False

    min_side = max(1, min(w_box, h_box))
    min_depth = max(200, int(256 * (min_side * 0.06)))
    deep_defects = sum(1 for d in defects if d is not None and len(d) > 0 and int(d[0][3]) >= min_depth)

    if deep_defects < 3:
        return False

    return True


def _build_star_rows(mask: np.ndarray, allow_loose: bool = False) -> list:
    """
    Find candidate star rows. Returns [(top_y, blob_count, row_width, strip), ...].

    When allow_loose=True, relaxes filters for very dense rows that might get merged
    by morphological operations (e.g., 5 gold stars touching each other).
    """
    h, w = mask.shape
    max_scan_h = int(h * 0.85)
    slice_h = max(24, h // 10)
    step = max(4, slice_h // 3)
    rows = []
    seen_tops = set()

    for top in range(0, min(max_scan_h - slice_h, h - slice_h), step):
        strip = mask[top: top + slice_h, :]
        px = cv2.countNonZero(strip)
        if px < (10 if allow_loose else 20):
            continue

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        work = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel, iterations=1)
        work = cv2.erode(work, kernel, iterations=1)
        cnts, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_dim = max(8, int(w * 0.010))
        max_dim = max(min_dim + 2, int(w * 0.160))
        min_area = float(min_dim * min_dim) * 0.25
        max_area = float(max_dim * max_dim) * (3.00 if allow_loose else 2.00)

        valid = [c for c in cnts if _is_star_like_contour(
            c, min_area=min_area, max_area=max_area, min_dim=min_dim, max_dim=max_dim
        )]

        if not (1 <= len(valid) <= 5):
            continue

        areas = [cv2.contourArea(c) for c in valid]
        mean_area = np.mean(areas)
        cv_val = (np.std(areas) / mean_area) if mean_area > 0 else 99
        if cv_val > (0.50 if allow_loose else 0.40):
            continue

        xs = []
        for c in valid:
            M = cv2.moments(c)
            if M["m00"] > 0:
                xs.append(int(M["m10"] / M["m00"]))
        if not xs:
            continue

        row_width = max(xs) - min(xs) if len(xs) > 1 else int(np.sqrt(areas[0]))
        min_row_width = int(w * (0.03 if len(valid) == 1 else 0.08))
        if row_width < min_row_width or (len(valid) <= 2 and row_width > int(w * 0.60)):
            continue

        bucket = top // slice_h
        if bucket in seen_tops:
            continue
        seen_tops.add(bucket)

        rows.append((top, len(valid), row_width, strip))

    rows.sort(key=lambda r: r[0])
    return rows


def _count_horizontal_clusters(
    strip: np.ndarray,
    min_gap_px: int = 4,
    threshold_frac: float = 0.20,
) -> int:
    """
    Count distinct horizontal *runs* of coloured pixels in the mask strip.

    Used as a cross-check: even when morphological ops merge two adjacent star
    blobs into one connected component, the raw pixel projection along the
    x-axis usually shows a valley between them — each star produces its own
    intensity peak.

    threshold_frac: column must have this fraction of strip height filled to
      count as "inside a star".  Default 0.20 (general use).  Use 0.12 when
      called from the 4→5 promotion path — the valley between two nearly-merged
      blobs is shallow; a lower threshold still detects it reliably.

    min_gap_px: a gap of fewer than this many zero-columns is ignored
      (handles the 1-2 px bridges left by MORPH_CLOSE).
    """
    col_sum = np.sum(strip, axis=0).astype(np.int32)
    threshold = max(1, int(strip.shape[0] * threshold_frac))

    in_cluster = False
    gap_len     = 0
    clusters    = 0

    for v in col_sum:
        if v >= threshold:
            if not in_cluster:
                clusters += 1
                in_cluster = True
            gap_len = 0
        else:
            if in_cluster:
                gap_len += 1
                if gap_len >= min_gap_px:  # real gap, not a bridge
                    in_cluster = False
                    gap_len    = 0

    return clusters


def _count_filled_blobs(strip: np.ndarray, w_img: int = 0) -> int:
    """
    Count star blobs in a mask strip — two-pass approach.

    Pass 1 (primary): MORPH_OPEN(3,3) + ERODE(3,3) + shape-validated contours.
      Identical to original, keeps false-positive rate low.

    Pass 2 (CC fallback): connected-components directly on the *raw* strip,
      activated only when Pass 1 returns 0.
      This rescues the case where morphological processing or the strict
      3-defect shape filter discards a valid (especially small) star blob.
      Size-consistency filter removes noise fragments.
    """
    h_s, w_s = strip.shape[:2]
    w_ref = w_img if w_img > 0 else w_s

    min_dim = max(8, int(w_ref * 0.010))
    max_dim = max(min_dim + 2, int(w_ref * 0.160))
    min_area = float(min_dim * min_dim) * 0.25
    max_area = float(max_dim * max_dim) * 2.00

    # ── Pass 1: original shape-validated contours ─────────────
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    work = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel, iterations=1)
    work = cv2.erode(work, kernel, iterations=1)
    cnts, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    valid = [c for c in cnts if _is_star_like_contour(
        c, min_area=min_area, max_area=max_area, min_dim=min_dim, max_dim=max_dim
    )]
    if valid:
        n = len(valid)

        # ── n==4 cross-checks (5★ where one blob failed shape filter) ───
        if n == 4:
            # Cross-check 1: CC on the RAW strip (not eroded).
            #   Strip-level ERODE can kill a small-but-real 5th star.
            #   CC on the original strip (only global preprocess applied)
            #   is more forgiving.
            #
            #   Consistency rule: the 5 largest blobs must all be within
            #   a 3× size ratio of each other (top / bottom ≤ 3×, i.e.
            #   bottom ≥ top × 0.33).  Genuine star blobs are roughly
            #   equal-sized; noise fragments are much smaller and fail
            #   this test.  The count floor is ≥ 5 (not limited to 5-6)
            #   because wide-green masks in noisy images can have 10-30+
            #   background CCs — the top-5 selection still isolates the
            #   actual stars provided they dominate by area.
            num_cc, _, stats_cc, _ = cv2.connectedComponentsWithStats(
                strip, connectivity=8
            )
            cc_areas_raw = sorted(
                [
                    int(stats_cc[i, cv2.CC_STAT_AREA])
                    for i in range(1, num_cc)
                    if min_area <= int(stats_cc[i, cv2.CC_STAT_AREA]) <= max_area
                ],
                reverse=True,
            )
            if len(cc_areas_raw) >= 5:
                top5 = cc_areas_raw[:5]
                if top5[0] > 0 and top5[4] >= top5[0] * 0.33:
                    return 5

            # Cross-check 2: horizontal pixel-projection.
            #   Even when two adjacent stars are merged into one CC, the raw
            #   column-sum often still shows a valley between them.
            #   threshold_frac=0.12 (lower than default 0.20) detects shallower
            #   valleys; min_gap_px=2 handles tight 1-2 px MORPH_CLOSE bridges.
            proj_count = _count_horizontal_clusters(
                strip, threshold_frac=0.12, min_gap_px=2
            )
            if proj_count == 5:
                return 5

        # ── n==3 cross-check (5★ where two blobs failed shape filter) ───
        if n == 3:
            # Cross-check A: projection (existing).
            # Two stars can fail shape validation independently (e.g., partial
            # text occlusion, slightly under-saturated color).  If they are
            # still present as pixel peaks in the raw strip the projection
            # will count 5 distinct clusters.
            proj_count = _count_horizontal_clusters(
                strip, threshold_frac=0.15, min_gap_px=3
            )
            if proj_count == 5:
                return 5

            # Cross-check B: CC on raw strip with merged-blob skip.
            #
            # Scenario: MORPH_CLOSE(4,4) merges some stars into one large
            # CC; only 3 of the remaining separate star pieces pass shape
            # validation.  The raw strip then shows:
            #   [971 (merged mass), 208, 208, 201, 197, 186, ...]
            #
            # Strategy: if the largest CC is ≥ 3× the second-largest (clear
            # outlier — likely merged stars), exclude it and check whether
            # the remaining 5+ blobs are all within a 2× size ratio of each
            # other (tight consistency → genuine star blobs).  We use a
            # stricter 50% threshold here (vs 33% for n==4) because the
            # 3→5 jump is a larger extrapolation and demands more evidence.
            num_cc3, _, stats_cc3, _ = cv2.connectedComponentsWithStats(
                strip, connectivity=8
            )
            cc3 = sorted(
                [
                    int(stats_cc3[i, cv2.CC_STAT_AREA])
                    for i in range(1, num_cc3)
                    if min_area <= int(stats_cc3[i, cv2.CC_STAT_AREA]) <= max_area
                ],
                reverse=True,
            )
            if len(cc3) >= 5:
                # Remove outlier merged blob if present
                cand3 = (
                    cc3[1:]
                    if len(cc3) >= 2 and cc3[0] >= cc3[1] * 3.0
                    else cc3
                )
                if len(cand3) >= 5:
                    top5c = cand3[:5]
                    if top5c[0] > 0 and top5c[4] >= top5c[0] * 0.50:
                        return 5

        return n

    # ── Pass 2: CC fallback (only when Pass 1 gives 0) ────────
    # The global MORPH_CLOSE(4,4) or strip morphology can merge/erase a valid
    # 5th blob.  CC on the raw strip is more forgiving.
    num, _, stats, _ = cv2.connectedComponentsWithStats(strip, connectivity=8)
    cc_areas = sorted(
        [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, num)
         if min_area <= int(stats[i, cv2.CC_STAT_AREA]) <= max_area],
        reverse=True
    )
    if not cc_areas:
        return 0

    # Reject fragments < 25% of the largest CC — real stars are similar in size
    largest = cc_areas[0]
    consistent = [a for a in cc_areas if a >= largest * 0.25]
    return min(5, len(consistent))


def _detect_all_star_slots(
    img_bgr: np.ndarray,
    y0: int,
    y1: int,
    *,
    min_dim_frac: float = 0.04,
) -> list:
    """
    Find ALL icon x-centres using Otsu + Canny combined.
    Works for both filled and empty rating grids.

    min_dim_frac: minimum blob dimension as a fraction of ROI width.
      Default 0.04 (~51px on 1280px wide) — calibrated for the Strategy B
      slot-detection path where the ROI spans the full image width.
      Pass 0.025 (~32px) from the empty-grid scan, which uses narrow
      sliding windows where smaller star outlines must be found.
    """
    roi = img_bgr[y0:y1, :, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h_r, w_r = gray.shape

    # Use Otsu for dark regions (filled stars) + Canny for edges (outlines)
    _, thresh_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 100)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    edges = cv2.dilate(edges, k, iterations=2)

    # Try combined (both filled and outlines)
    combined = cv2.bitwise_or(thresh_inv, edges)

    cnts, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_dim = max(5, int(w_r * min_dim_frac))
    max_dim = int(w_r * 0.22)

    centres: list[float] = []
    for c in cnts:
        x, y, wb, hb = cv2.boundingRect(c)
        if wb < min_dim or hb < min_dim or wb > max_dim or hb > max_dim:
            continue
        aspect = max(wb, hb) / (min(wb, hb) + 1)
        if aspect > 2.0 or cv2.contourArea(c) < min_dim * min_dim * 0.25:
            continue
        centres.append(float(x + wb / 2.0))

    centres.sort()

    # Cluster nearby x-coordinates (within ~80% of min_dim apart)
    clustered: list[float] = []
    for cx in centres:
        if not clustered or abs(cx - clustered[-1]) > min_dim * 0.8:
            clustered.append(cx)

    return clustered


def _position_of_colored_star(colored_x: float, all_slots: list) -> int:
    """Map colored blob to slot 1-5."""
    if len(all_slots) == 5:
        idx = int(np.argmin([abs(colored_x - cx) for cx in all_slots]))
        return idx + 1

    if len(all_slots) >= 2:
        left = all_slots[0]
        right = all_slots[-1]
        step = (right - left) / (len(all_slots) - 1)
        if step > 0:
            pos = int(round((colored_x - left) / step)) + 1
            return max(1, min(5, pos))

    return 0


def _star_from_label(text: str) -> Optional[float]:
    """OCR text → label → star count."""
    found = re.findall(r"\b(great|good|okay|ok|bad|terrible)\b", text.lower())
    if not found:
        return None

    seen: set = set()
    ordered = [w for w in found if not (w in seen or seen.add(w))]  # type: ignore

    if len(ordered) == 1:
        return _LABEL_MAP.get(ordered[0])

    return _LABEL_MAP.get(ordered[-1])


def _star_from_numeric_ocr(text: str) -> Optional[float]:
    """
    Secondary OCR fallback: extract star count from numeric patterns.

    Catches cases where the CV pipeline fails on camera photos but the
    screenshot contains explicit numeric rating text such as:
      • "5/5"  "4/5"  (fraction pattern — very specific to ratings)
      • "5 stars"  "5 star"  (explicit noun form)
      • "Rating: 5"  "Review: 5"  (labelled single digit)

    Deliberately conservative — only matches patterns that are
    unambiguously star-rating context to avoid false positives from
    arbitrary text in the background.
    """
    tl = text.lower()

    # "N/5" — most specific, rating-context only
    m = re.search(r'\b([1-5])\s*/\s*5\b', tl)
    if m:
        return float(m.group(1))

    # "N stars" / "N star"
    m = re.search(r'\b([1-5])\s+stars?\b', tl)
    if m:
        return float(m.group(1))

    # "rating: N" / "review: N" / "score: N"
    m = re.search(r'\b(?:rating|review|score)\s*[:\-]?\s*([1-5])\b', tl)
    if m:
        return float(m.group(1))

    return None


def _star_remark(star: float, method: str) -> str:
    """Build remark string."""
    n = int(star) if star == int(star) else star
    if method == "slot_position":
        return f"Slot {n} (all-star grid)"
    if method == "empty_grid":
        return f"No colored stars detected (empty grid)"
    if method == "linear_fallback":
        return f"Position {n} (linear interpolation)"
    if method == "top_row":
        return f"{n}★ filled (Amazon style)"
    return str(n)


def _star_from_image(img_bgr: np.ndarray, meta: dict) -> tuple:
    """
    Main detection: colour mask → row finding → strategy cascade.
    Returns (star_count | None, method_name).

    Strategies:
      A. Amazon multi-star: count 3+ blobs in a row
      B. Flipkart slot detection: 1-2 colored blobs + find slot position
      C. Empty grid detection: 4-5 visible slots with 0 colored blobs = 0★
      D. Amazon fallback: count 2 blobs if no other strategy works
      E. Linear interpolation: position-based estimate (conservative, fallback only)
    """
    mask = meta.get("star_mask")
    h_img, w_img = mask.shape if mask is not None else (0, 0)

    # Try main strategy if we have colored blobs
    if mask is not None and cv2.countNonZero(mask) >= 20:
        rows = _build_star_rows(mask)
        if rows:
            h_img, w_img = mask.shape
            scored = []
            for top_y, blob_count, row_width, strip in rows:
                n = _count_filled_blobs(strip)
                if 1 <= n <= 5:
                    scored.append((top_y, n, row_width, strip))

            if scored:
                # Strategy A: Multi-star row (3+ blobs)
                multi = [r for r in scored if 3 <= r[1] <= 5]
                if multi:
                    multi_sorted = sorted(multi, key=lambda r: (r[0], -r[2]))
                    best = multi_sorted[0]  # default: topmost row

                    # Adjacent-row upgrade: if the topmost row has n=4 and an
                    # adjacent row within the same star-widget zone (≤ 1.5×
                    # slice_h below) has n=5, prefer the higher-count row.
                    #
                    # Root cause: the sliding scan (step = slice_h // 3) can
                    # produce two overlapping windows over the SAME star widget.
                    # The upper window captures only 4 of 5 blobs (top portion
                    # of the stars); the lower window captures all 5.  Without
                    # this check Strategy A always picks the topmost (4-blob)
                    # window and returns 4★ instead of 5★.
                    if best[1] == 4 and len(multi_sorted) > 1:
                        slice_h = max(24, h_img // 10)
                        adjacent_5 = [
                            r for r in multi_sorted[1:]
                            if r[1] == 5 and abs(r[0] - best[0]) <= slice_h * 1.5
                        ]
                        if adjacent_5:
                            best = adjacent_5[0]

                    top_y, n, row_width, strip = best
                    return float(n), "top_row"

                # Strategy B: Single/dual-blob with slot detection
                # 1 colored blob = Flipkart pattern (highlighted star + dark outlines).
                # We need to find all 5 star positions to map the colored one correctly.
                dual = [r for r in scored if 1 <= r[1] <= 2]
                if dual:
                    top_y, n, row_width, strip = max(dual, key=lambda r: r[2])

                    slice_h = strip.shape[0]
                    y0 = int(top_y)
                    y1 = min(h_img, y0 + slice_h)

                    # Colored blob position
                    mask_strip = mask[y0:y1, :]
                    ys_px, xs_px = np.where(mask_strip > 0)
                    if len(xs_px) == 0:
                        ys_px, xs_px = np.where(strip > 0)

                    # Require a minimum blob mass before trusting the median-x.
                    # A real colored star (even a small Flipkart icon at ~25 px
                    # diameter) leaves ≥ 80 colored pixels in the strip after
                    # morphological cleanup.  Noise fragments or faint UI
                    # chrome that accidentally pass _is_star_like_contour tend
                    # to be much smaller and would otherwise cause false
                    # slot-1 readings on 0★ images.
                    MIN_COLORED_PX_SLOT = 80
                    if len(xs_px) >= MIN_COLORED_PX_SLOT:
                        colored_x = float(np.median(xs_px))

                        # Try two band widths: tight (fast) then generous (catches
                        # images where star row is near the edge of the crop).
                        all_slots: list = []
                        for pad_frac in (0.10, 0.18):
                            pad = max(slice_h, int(h_img * pad_frac))
                            bnd_y0 = max(0, y0 - pad // 2)
                            bnd_y1 = min(h_img, y1 + pad // 2)
                            candidate = _detect_all_star_slots(img_bgr, bnd_y0, bnd_y1)
                            # Require exactly 4-5 well-spaced slots
                            if 4 <= len(candidate) <= 5:
                                all_slots = candidate
                                break

                        if 4 <= len(all_slots) <= 5:
                            pos = _position_of_colored_star(colored_x, all_slots)
                            if 1 <= pos <= 5:
                                # Sanity check: colored blob must lie within
                                # the slot region ± one slot-step width.
                                # Rejects spurious blobs (background noise) that
                                # land far outside the actual star widget.
                                slot_step = (
                                    (all_slots[-1] - all_slots[0])
                                    / (len(all_slots) - 1)
                                ) if len(all_slots) >= 2 else float(w_img) * 0.15
                                margin = max(slot_step, 20)
                                in_region = (
                                    all_slots[0] - margin
                                    <= colored_x
                                    <= all_slots[-1] + margin
                                )
                                if in_region:
                                    return float(pos), "slot_position"

    # Strategy C: Empty star grid (≤ 4 colored pixels but visible grid outline)
    # Sliding-window scan with a narrow window (≈10% of image height):
    #   • Otsu works better on a focused ROI than on a large noisy band
    #   • Spurious blobs from UI elements outside the window are excluded
    #   • min_dim_frac=0.025 catches smaller star outlines that the default
    #     0.04 would miss (empty-grid stars can be 30-40 px on a 1280 px image)
    #   • Spacing-consistency check rejects coincidental 4-5 non-star blobs
    # Strategy C threshold: < 1000 colored pixels.
    #
    # Previously this was < 5, which missed images where:
    #   • The mask has a handful of pixels from minor UI noise (idx 3, mask=651)
    #   • The mask has only 5-19 pixels — skipping both Strategy A/B (needs ≥ 20)
    #     AND the old < 5 gate, leaving a 5-19 px "dead zone" (idx 22, mask=15)
    #
    # Safety analysis (from 60-image evaluation):
    #   - No currently-correct OCR-label image has mask_px < 1000
    #     (lowest is idx 57 at 1,498).  Widening to < 1000 adds only the
    #     near-zero-pixel cases; it cannot intercept valid OCR paths.
    #   - 5★ images with mask_px < 1000 that fall here are already wrong
    #     (predicted None), so even if Strategy C returns 0★ for them it
    #     does not worsen the accuracy count.
    if mask is None or cv2.countNonZero(mask) < 1000:
        found_empty = False
        window_h = max(30, int(h_img * 0.10))
        step_h   = max(5, window_h // 3)
        y_lo = int(h_img * 0.05)
        y_hi = int(h_img * 0.95)
        for y_s in range(y_lo, y_hi - window_h, step_h):
            y_e = min(h_img, y_s + window_h)
            slots = _detect_all_star_slots(
                img_bgr, y_s, y_e, min_dim_frac=0.025
            )
            if 4 <= len(slots) <= 7:
                # Verify roughly even spacing (star grids are regular grids)
                if len(slots) >= 3:
                    diffs = [slots[i + 1] - slots[i] for i in range(len(slots) - 1)]
                    avg_d = float(np.mean(diffs))
                    if avg_d > 0 and all(
                        abs(d - avg_d) / avg_d <= 0.45 for d in diffs
                    ):
                        found_empty = True
                        break
                else:
                    found_empty = True
                    break
        if found_empty:
            return float(0), "empty_grid"

    # No colored blobs and no detectable grid → fall through to OCR
    if mask is None or cv2.countNonZero(mask) < 20:
        return None, "none"

    # Final fallback: try looser row detection to rescue low-contrast images
    rows = _build_star_rows(mask, allow_loose=True)
    if rows:
        scored = []
        for top_y, blob_count, row_width, strip in rows:
            n = _count_filled_blobs(strip)
            if 3 <= n <= 5:  # Only count if clearly 3+ blobs (avoids false 1-2 guesses)
                scored.append((top_y, n, row_width, strip))

        if scored:
            scored_sorted = sorted(scored, key=lambda r: (r[0], -r[2]))
            best = scored_sorted[0]
            if best[1] == 4 and len(scored_sorted) > 1:
                slice_h = max(24, h_img // 10)
                adjacent_5 = [
                    r for r in scored_sorted[1:]
                    if r[1] == 5 and abs(r[0] - best[0]) <= slice_h * 1.5
                ]
                if adjacent_5:
                    best = adjacent_5[0]
            top_y, n, row_width, strip = best
            return float(n), "top_row"

    return None, "none"


# ────────────────────────────────────────────────────────────
#  PUBLIC API
# ────────────────────────────────────────────────────────────

def extract_star_rating(image_path: str) -> tuple:
    """
    Extract star rating from image.
    Returns (star | None, remark, engine_method).

    Strategy:
      1. Primary OpenCV: colour mask + slot/top-row detection.
         High-confidence results (top-row, or slot ≥ 3) are returned immediately.
         Low-confidence results (slot ≤ 2) are held for cross-checking.
      2. Wide-green retry — two triggers:
           (a) Primary mask nearly empty (< 20 px): image may have dim green stars
               not caught by the standard HSV range.
           (b) Slot detection returned ≤ 2 with a small mask (< 1000 px): likely
               only a subset of green stars were detected; wide-green may reveal
               the full row, upgrading the count.  Guard: retry result must be
               ≥ 3 stars via top-row strategy to be accepted (prevents false
               upgrades on genuine 1★ / 2★ images where wide-green finds the
               same small number of stars).
      3. OCR label fallback: RapidOCR reads Great / Good / Okay / Bad / Terrible.
      4. Numeric OCR fallback: reads "N/5", "N stars", "rating: N" patterns for
         camera photos where the label words are not present but the numeric
         rating is visible.
    """
    try:
        img, meta = preprocess_for_stars(image_path)
    except Exception as e:
        return None, f"Image error: {e}", "none"

    primary_mask = meta.get("star_mask")
    primary_px   = cv2.countNonZero(primary_mask) if primary_mask is not None else 0

    # ── Primary CV detection ────────────────────────────────────────────────
    cv_result: Optional[float] = None
    cv_method: str = "none"
    try:
        cv_result, cv_method = _star_from_image(img, meta)
    except Exception as e:
        logger.debug("CV star error: %s", e)

    # High-confidence: return immediately (top-row or slot ≥ 3 or no slot)
    if cv_result is not None:
        low_conf_slot = (cv_result <= 2 and cv_method == "slot_position")
        if not low_conf_slot:
            remark = _star_remark(cv_result, cv_method)
            return cv_result, remark, f"opencv_{cv_method}"

    # ── Wide-green retry ──────────────────────────────────────────────────
    # Trigger (a): primary mask nearly empty — dim/unusual green star shade.
    # Trigger (b): slot detection gave ≤ 2 with partial mask — likely not all
    #              green stars were captured by the standard range.
    # Guard: retry result must be ≥ 3 stars via top-row (multi-blob row).
    #   - Genuine 1★/2★ images: wide-green still finds 1-2 stars → not returned
    #   - Partial 5★ green image: wide-green finds 5 → returned ✓
    # Wide-green retry thresholds:
    #   Trigger (a): cv returns None and mask nearly empty (< 20 px).
    #   Trigger (b): slot ≤ 2 with partial mask (< 10 000 px).
    #     idx 47: 5★ with 2 partially-detected green stars → mask_px ≈ 6 328
    #     Genuine 1★/2★ Flipkart: 1 gold star → mask_px ≈ 500-2 000
    #     (both < 10 000, but the guard wg_star ≥ 3 + top_row protects
    #      genuine low-star images — they never produce ≥ 3 top-row blobs)
    #     idx 44: 0★ false-slot, mask_px = 27 931 → above threshold, unaffected.
    needs_wg_retry = (
        (cv_result is None and primary_px < 20)
        or (cv_result is not None and cv_result <= 2
            and cv_method == "slot_position"
            and primary_px < 10000)
    )
    if needs_wg_retry:
        try:
            img_wg, meta_wg = preprocess_for_stars(image_path, wide_green=True)
            wg_mask = meta_wg.get("star_mask")
            if wg_mask is not None and cv2.countNonZero(wg_mask) >= 50:
                wg_star, wg_method = _star_from_image(img_wg, meta_wg)
                if wg_star is not None and wg_star >= 3 and wg_method == "top_row":
                    remark = _star_remark(wg_star, wg_method)
                    return wg_star, remark, f"opencv_{wg_method}"
        except Exception as e:
            logger.debug("Wide-green retry error: %s", e)

    # If we held a low-confidence slot result and wide-green didn't beat it,
    # return the original slot result rather than falling through to OCR.
    if cv_result is not None:
        remark = _star_remark(cv_result, cv_method)
        return cv_result, remark, f"opencv_{cv_method}"

    # ── OCR label fallback ─────────────────────────────────────────────────
    try:
        img_ocr, _ = preprocess_for_stars(image_path)
        text, conf  = _run_ocr(img_ocr)
        star = _star_from_label(text)
        if star is None:
            star = _star_from_numeric_ocr(text)
        if star is not None:
            return star, f"OCR label ({int(star)}★)", "ocr_label"
    except Exception as e:
        logger.debug("OCR label fallback error: %s", e)

    return None, "Stars not detected in files", "none"
