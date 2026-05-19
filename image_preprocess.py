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


def preprocess_for_stars(image_path: str) -> tuple:
    """
    Preprocessing for star detection.
    Uses colour (no binarise) so HSV masks work correctly.
    Returns (colour_bgr, meta_with_star_mask).
    
    IMPROVED: More restrictive HSV ranges to avoid false positives
    on path stars or artifacts.
    """
    img  = load(image_path)
    dark = is_dark_mode(img)
    img  = _resize(img)
    img  = _clahe(img)
    img  = _sharpen(img)
    # Do NOT binarise — we need colour for HSV star masks

    hsv    = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # ── IMPROVED COLOR RANGES ────────────────────────────────
    # Yellow stars: tighter hue range, higher saturation/value
    # Avoids picking up oranges, skin tones, or faded colors
    mask_y = cv2.inRange(hsv, np.array([20,  100, 100]),  np.array([30,  255, 255]))  # bright yellow
    
    # Green stars: tighter range to avoid picking up leaf/plant areas
    mask_g = cv2.inRange(hsv, np.array([50,  80,  100]),  np.array([80,  255, 255]))  # bright green
    
    # Dim yellow (dark mode): stricter saturation/value to avoid picking
    # up faded text or background patterns
    mask_d = cv2.inRange(hsv, np.array([18,  40,  50]),  np.array([35,  150, 150]))  # dim yellow
    
    # Orange/red stars (some rating systems use these)
    mask_o = cv2.inRange(hsv, np.array([5,  100,  100]),  np.array([17,  255, 255]))  # orange/red
    
    mask   = cv2.bitwise_or(mask_y, cv2.bitwise_or(mask_g, cv2.bitwise_or(mask_d, mask_o)))
    
    # ── MORPHOLOGICAL CLEANUP ─────────────────────────────────
    # Remove noise and fill small gaps in star shapes
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)  # remove tiny specks
    
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)  # fill small holes

    return img, {"is_dark_mode": dark, "star_mask": mask}
