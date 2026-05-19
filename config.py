# =============================================================
#  config.py  —  ALL settings live here. Only edit this file.
# =============================================================

# ── PATHS ─────────────────────────────────────────────────────
BASE_DIR   = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\Final\15_05_2026\Final"
DB_PATH    = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\zoho_pipeline.db"
LOG_FILE   = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\pipeline.log"
EXPORT_DIR = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\exports"

# â”€â”€ ZOHO CSV (Ticket ID + Order ID) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Used by merge_csv.py to populate `ticket_id` and `csv_order_id` into the DB.
ZOHO_CSV_PATH = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\Final\15_05_2026\CustomerReviewSubmissionFormforSAs_Records_1.csv"

# ── SUBFOLDER NAMES ───────────────────────────────────────────
IMAGE_FOLDER_1 = "ImageUpload"    # Image1 → order screenshot
IMAGE_FOLDER_2 = "ImageUpload1"   # Image2 → review / star screenshot

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
