# =============================================================
#  config.py  —  ALL settings live here. Only edit this file.
# =============================================================
from pathlib import Path

_REPO = Path(__file__).resolve().parent
_LOCAL_DATA = _REPO / "data"
_LOCAL_DATA.mkdir(exist_ok=True)

# ── DATA SOURCE (Google Sheet) ────────────────────────────────
# The pipeline reads every record from this sheet: metadata (Added Time,
# Branch, Ticket ID, Order ID) and the two image URLs (Drive links).
SHEET_ID      = "1vxmplqaecTL3K9h-G2awk5jZpdCGecZPHWPA7fm4RZk"
SHEET_GID     = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# ── PATHS (all inside the repo) ───────────────────────────────
BASE_DIR        = str(_REPO / "Final")           # legacy folder-scan (unused with sheet source)
IMAGE_CACHE_DIR = str(_LOCAL_DATA / "images")    # Drive images: <ticket_id>/image1.jpg, image2.jpg
DB_PATH         = str(_LOCAL_DATA / "zoho_pipeline.db")
LOG_FILE        = str(_LOCAL_DATA / "pipeline.log")
EXPORT_DIR      = str(_LOCAL_DATA / "exports")
Path(IMAGE_CACHE_DIR).mkdir(parents=True, exist_ok=True)
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

# ── LEGACY (kept so merge_csv.py still imports cleanly) ───────
ZOHO_CSV_PATH = str(_REPO / "CustomerReviewSubmissionFormforSAs_Records_1_1.csv")

# ── SUBFOLDER NAMES (legacy folder scan — unused) ─────────────
IMAGE_FOLDER_1 = "ImageUpload"
IMAGE_FOLDER_2 = "ImageUpload1"

# ── API ───────────────────────────────────────────────────────
API_POLL_SECONDS = 60   # background sheet-poll interval for api.py

# ── PROCESSING ────────────────────────────────────────────────
MAX_FOLDERS = None   # None = all folders. Set e.g. 10 for testing.
OCR_WORKERS = 4      # Tesseract is lightweight — 4 workers safe on laptop

# ── IMAGE ─────────────────────────────────────────────────────
MAX_IMAGE_EDGE = 1400   # Resize longest edge to this before OCR

# ── OCR ───────────────────────────────────────────────────────
# Tesseract confidence below this → try alternate strategies
OCR_CONFIDENCE_THRESHOLD = 50   # Tesseract uses 0-100 scale

# ── LOGGING ───────────────────────────────────────────────────
LOG_LEVEL = "WARNING"   # Terminal stays quiet. Full detail in LOG_FILE.
