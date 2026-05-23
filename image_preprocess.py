# =============================================================
#  image_preprocess.py  —  Fast OpenCV preprocessing
#
#  Design principle: every step must earn its place.
#  REMOVED: fastNlMeansDenoising  → 3-8s per image, marginal benefit
#  REMOVED: HoughLines deskew     → slow + unreliable on phone shots
#  KEPT:    resize                → controls RAM + speed
#  KEPT:    CLAHE contrast        → essential for dark/washed images
#  KEPT:    threshold binarise    → Tesseract reads black-on-white best
#  KEPT:    sharpen               → cheap, helps thin fonts
#  KEPT:    HSV star mask         → colour blob, no OCR cost
# =============================================================

import cv2
import numpy as np
from pathlib import Path
from config import MAX_IMAGE_EDGE


def _resize(img: np.ndarray) -> np.ndarray:
    h, w    = img.shape[:2]
    longest = max(h, w)
    if longest > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / longest
        img   = cv2.resize(img, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    return img


def _clahe(img: np.ndarray) -> np.ndarray:
    """Adaptive contrast — fixes dark-mode & washed-out photos."""
    lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l       = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _sharpen(img: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1)          # sigma=1 → gentle
    return cv2.addWeighted(img, 1.4, blur, -0.4, 0)


def _binarise(img: np.ndarray) -> np.ndarray:
    """
    Convert to grayscale + adaptive threshold.
    Tesseract accuracy improves significantly on clean B&W.
    Returns a 3-channel image (Tesseract accepts both).
    """
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Adaptive threshold handles mixed lighting within one image
    bw    = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,   # neighbourhood size — larger = more context
        C=10            # constant subtracted from mean
    )
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


def is_dark_mode(img: np.ndarray) -> bool:
    return np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)) < 100


def load(image_path: str) -> np.ndarray:
    """Load image from disk. Raises if missing or unreadable."""
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    img = cv2.imread(str(p))
    if img is None:
        raise ValueError(f"OpenCV cannot read: {image_path}")
    return img


def preprocess(image_path: str) -> tuple:
    """
    Full preprocessing pipeline for OCR.
    Returns (processed_bgr, meta_dict).
    Pipeline: load → resize → CLAHE → sharpen → binarise
    Total time: ~50-150ms per image (vs 4-10s with denoise/deskew).
    """
    img  = load(image_path)
    dark = is_dark_mode(img)    # check before CLAHE changes brightness
    img  = _resize(img)
    img  = _clahe(img)
    img  = _sharpen(img)
    img  = _binarise(img)
    return img, {"is_dark_mode": dark}


def preprocess_colour(image_path: str) -> tuple:
    """
    Colour-only preprocessing — no binarization.

    Used as a fallback for phone-photo-of-screen images where adaptive
    thresholding fragments text due to Moiré patterns from the screen
    pixel grid or uneven backlight reflections.

    Pipeline: load → resize → CLAHE → sharpen  (NO binarise)
    """
    img  = load(image_path)
    dark = is_dark_mode(img)
    img  = _resize(img)
    img  = _clahe(img)
    img  = _sharpen(img)
    return img, {"is_dark_mode": dark}


def _auto_rotate(img: np.ndarray) -> np.ndarray:
    """
    Detect and correct image rotation using dominant line angles (Hough).
    Handles phone screenshots taken sideways (±90°).
    Returns the corrected image (or original if angle is < 10°).
    """
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
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

    # Only correct significant tilts (rotated phone shots are ≈ ±90°)
    if abs(median_angle) < 10:
        return img

    if 45 < abs(median_angle) <= 135:
        # Rotated ~90° — rotate back
        if median_angle > 0:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    return img


def preprocess_for_stars(image_path: str) -> tuple:
    """
    Preprocessing for star detection.
    Uses colour (no binarise) so HSV masks work correctly.
    Returns (colour_bgr, meta_with_star_mask).

    v2 changes:
    - Auto-rotation correction (handles sideways phone shots)
    - Expanded green range (Flipkart Order Details uses muted mid-green)
    - Separate green mask bypasses the global sat/val gate (green is naturally less saturated)
    - Emoji-star orange/red blobs included so Great-emoji is found by color
    """
    img  = load(image_path)
    dark = is_dark_mode(img)
    img  = _resize(img)
    img  = _auto_rotate(img)       # ← fix rotated phone shots (Image 1)
    img  = _clahe(img)
    img  = _sharpen(img)
    # Do NOT binarise — we need colour for HSV star masks

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # ── COLOUR RANGES ─────────────────────────────────────────
    # Yellow/gold — Amazon & Flipkart filled stars
    mask_y = cv2.inRange(hsv, np.array([18,  80,  80]),  np.array([35, 255, 255]))

    # Dim yellow — dark-mode / low-exposure shots
    mask_d = cv2.inRange(hsv, np.array([15,  35,  40]),  np.array([40, 220, 220]))

    # Orange — warm camera WB shift or sunset-toned UI
    mask_o = cv2.inRange(hsv, np.array([ 0,  80,  70]),  np.array([18, 255, 255]))

    # Green — Flipkart Order Details "Great ★★★★★" uses a muted mid-green.
    # Two bands: bright green (standard) + muted green (Flipkart Order Details).
    # Green bypasses the global sat/val gate below because it's naturally less vivid.
    mask_g_bright = cv2.inRange(hsv, np.array([40,  70,  70]),  np.array([95, 255, 255]))
    mask_g_muted  = cv2.inRange(hsv, np.array([38,  30,  50]),  np.array([90, 160, 200]))  # ← NEW
    mask_g = cv2.bitwise_or(mask_g_bright, mask_g_muted)

    # Combine yellow / orange / dim-yellow — gate on saturation+value together
    mask_warm = cv2.bitwise_or(mask_y, cv2.bitwise_or(mask_d, mask_o))
    s_min = 50 if dark else 75
    v_min = 50 if dark else 75
    sat_ok = (hsv[:, :, 1] >= s_min).astype(np.uint8) * 255
    val_ok = (hsv[:, :, 2] >= v_min).astype(np.uint8) * 255
    mask_warm = cv2.bitwise_and(mask_warm, sat_ok)
    mask_warm = cv2.bitwise_and(mask_warm, val_ok)

    # Green uses its own lighter gate (muted green has lower saturation)
    sat_ok_g = (hsv[:, :, 1] >= 25).astype(np.uint8) * 255
    val_ok_g = (hsv[:, :, 2] >= 45).astype(np.uint8) * 255
    mask_g = cv2.bitwise_and(mask_g, sat_ok_g)
    mask_g = cv2.bitwise_and(mask_g, val_ok_g)

    mask = cv2.bitwise_or(mask_warm, mask_g)

    # ── MORPHOLOGICAL CLEANUP ─────────────────────────────────
    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel_open)   # kill specks
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)  # fill holes

    # ── REMOVE OVERSIZED BLOBS (bezel / skin tone) ────────────
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
