# Zoho Image Pipeline — OCR → Dashboard

End-to-end pipeline that:
1. Reads customer review records from a **Google Sheet** (Added Time, Branch, Ticket ID, Order ID, Drive image links)
2. Downloads the two images per record from **Google Drive**
3. OCR extracts **Order ID** and **Star Rating** from each screenshot
4. Looks up the **Web Order ID** (Amazon/Flipkart) from the **BSE API** using the Ticket ID
5. Publishes a live **Streamlit dashboard** — local (SQLite) and on Streamlit Cloud (CSV)

---

## Data Flow

```
Google Sheet (CSV export URL)
    ↓  sheet_source.py  — fetches rows + Drive image URLs
Google Drive
    ↓  sheet_source.py  — downloads image1.jpg + image2.jpg per ticket
OCR / OpenCV  (ocr_engine.py + image_preprocess.py)
    ↓  extracts File Order ID + Star Rating
BSE API  (bse_api.py)
    ↓  looks up Web Order ID via Ticket ID
SQLite  zoho_pipeline.db          ← local only
    ↓  sync_to_github.py          exports + git push origin main
data/zoho_latest.csv + data/last_sync.txt  →  GitHub → Streamlit Cloud
```

---

## Repo Layout

| File | Role |
|---|---|
| `pipeline.py` | Main runner — fetches sheet, downloads images, runs OCR, writes SQLite |
| `sheet_source.py` | Google Sheet → rows; Google Drive → local image cache |
| `ocr_engine.py` | RapidOCR + OpenCV — extracts Order ID and Star Rating |
| `image_preprocess.py` | Image cleanup helpers (rotation, HSV masks, contrast) |
| `bse_api.py` | BSE API client — looks up Amazon/Flipkart Web Order ID by Ticket ID |
| `sync_to_github.py` | SQLite → `data/zoho_latest.csv` → git push to GitHub |
| `dashboard.py` | Streamlit UI — reads SQLite locally, reads CSV on cloud |
| `streamlit_app.py` | Streamlit Cloud entrypoint — runs `dashboard.py` |
| `db.py` | SQLite schema + helpers |
| `flags.py` | Flag computation logic (Order ID match, star rating, verified) |
| `config.py` | All settings — Sheet ID, paths, API intervals, worker count |
| `ocr_check.py` | Debug script — inspect OCR output for a single image or folder |
| `star_detection.py` | Standalone star detection prototype (for testing/comparison) |
| `star_scan.py` | CLI tool — scan a folder of images and extract star ratings |
| `star_eval.py` | Evaluation script — validate star detection against ground truth |
| `run.ps1` | PowerShell launcher with `-fresh` / `-resume` / `-limit` flags |
| `data/zoho_latest.csv` | What Streamlit Cloud reads (auto-pushed on every sync) |
| `data/last_sync.txt` | Timestamp of last successful GitHub sync |
| `data/images/` | Downloaded Drive images — `<ticket_id>/image1.jpg` + `image2.jpg` (git-ignored) |

---

## Setup

### 1. Configure `config.py`

The only file you need to edit before running:

```python
SHEET_ID  = "your-google-sheet-id"   # from the sheet URL
SHEET_GID = "0"                       # tab/gid (0 = first tab)
```

Everything else (image cache, DB path, log path) is auto-derived from the repo root.

> **Sheet layout expected:**
> `Added Time | IP Address | Branch | Ticket ID | Order ID | <image1 Drive URL> | <image2 Drive URL>`

### 2. Install dependencies

**Using uv (recommended):**
```bash
uv venv
uv pip install -r requirements.txt
```

**Using pip:**
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Running the Pipeline

### Option A — PowerShell launcher (recommended on Windows)

```powershell
# Clear DB and process everything from scratch
.\run.ps1 -fresh

# Clear DB but only process first 50 records (for testing)
.\run.ps1 -fresh -limit 50

# Resume — continue unprocessed records
.\run.ps1 -resume

# Resume next 100 only
.\run.ps1 -resume -limit 100

# Resume and also retry rows that previously failed (NO_ORDER_ID / NO_STAR)
.\run.ps1 -resume -retryFailed
```

### Option B — Python directly

```bash
# Process all (auto-resumes from where it left off)
python pipeline.py

# Test run — first 10 records only
python pipeline.py --limit 10

# Fresh start — clear DB first
python pipeline.py --limit 10 --fresh

# Debug mode — print raw OCR text per image
python pipeline.py --debug

# Export to Excel after processing
python pipeline.py --export
```

---

## Dashboard

### Local

```bash
streamlit run dashboard.py
```

Opens at `http://localhost:8501`. Reads directly from SQLite.

### Streamlit Cloud

Live at: **https://zoho-image-pipeline.streamlit.app/**

Reads `data/zoho_latest.csv` from GitHub. Auto-refreshes every 30 seconds.
Pipeline pushes a new CSV to GitHub every 30 seconds while running.

If the cloud shows stale data:
- Streamlit Cloud → **Manage app → Reboot**
- Verify `data/zoho_latest.csv` on GitHub `main` is up to date

---

## Other Commands

```bash
# Manual GitHub sync (DB → CSV → push)
python sync_to_github.py

# Debug OCR for a single image
python ocr_check.py --image path/to/image.jpg

# Scan a folder of images for star ratings (standalone)
python star_scan.py --path "path/to/images" --out "data/star_scan.csv"

# Evaluate star detection accuracy against ground truth
python star_eval.py
```

---

## BSE API

The pipeline calls the BSE internal API to resolve a **Web Order ID** (Amazon/Flipkart order number) from each record's Ticket ID. This runs automatically during `pipeline.py`. No additional config needed — credentials are embedded in `bse_api.py`.

Endpoint: `https://bseapi.ifbsupport.com/api/ZohoPipeline/GetAmazonFlipkartOrderIddetails`

---

## Notes

- Images are downloaded from Google Drive and cached in `data/images/` — git-ignored (large, customer data)
- SQLite DB (`data/zoho_pipeline.db`) is git-ignored — local only
- Zoho CSV (`CustomerReviewSubmissionFormforSAs_Records_1_1.csv`) is git-ignored — sensitive, replaced by Sheet source
- Do **not** open `data/zoho_latest.csv` in Excel and save — Excel corrupts long numeric IDs to scientific notation
- OCR engine: RapidOCR + OpenCV (no Tesseract dependency)
