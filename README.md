# Zoho Image Pipeline (OCR → Dashboard)

End-to-end pipeline to:
1) OCR images from Zoho Forms uploads (File Order ID + Star rating)
2) Merge Zoho CSV metadata (Added Time, Branch, Ticket ID, Zoho Order ID)
3) Publish a Streamlit dashboard (local + Streamlit Cloud) that always shows the same data

## Repo layout

- `pipeline.py` — scans folders, runs OCR, writes SQLite (`zoho_pipeline.db`)
- `ocr_engine.py` — RapidOCR + OpenCV extraction logic
- `image_preprocess.py` — image cleanup helpers for OCR
- `merge_csv.py` — merges Zoho CSV fields into SQLite (`added_time`, `branch`, `ticket_id`, `csv_order_id`)
- `bse_api.py` — BSE API client that looks up the Amazon/Flipkart Web Order ID (`web_order_id`)
- `sync_to_github.py` — exports SQLite → `data/zoho_latest.csv` and pushes to GitHub
- `dashboard.py` — Streamlit UI (reads SQLite locally, reads CSV on Streamlit Cloud)
- `streamlit_app.py` — Streamlit Cloud entrypoint (runs `dashboard.py`)
- `db.py` — SQLite schema + helpers
- `config.py` — paths and worker settings
- `ocr_check.py` — manual OCR debugging/inspection script for a single image or folder
- `data/zoho_latest.csv` — the file Streamlit Cloud reads (auto-updated)
- `data/images/` — source screenshots (git-ignored: large, contains customer data)

## 0 → Hero (local)

### 1) Configure paths
Edit `config.py`:
- `BASE_DIR` — folder that contains one subfolder per record (each with `ImageUpload/` + `ImageUpload1/`)
- `DB_PATH` — where SQLite is stored
- `ZOHO_CSV_PATH` — your Zoho export CSV (Added Time / Branch / Ticket ID / Order ID)

### 2) Install dependencies
Streamlit Cloud installs from `requirements.txt`.
For local dev you can use either `uv` (recommended) or plain `pip`.

**Option A: uv (recommended)**
Install uv:
- `winget install Astral.uv`
- or `pipx install uv`

Create a venv and install deps:
```bash
uv venv
uv pip install -r requirements.txt
```

**Option B: pip**
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Run the pipeline
```bash
# test run
python pipeline.py --limit 5 --fresh

# full run (auto-resumes)
python pipeline.py
```
At the end, `pipeline.py` automatically runs `merge_csv.py`, so your DB has:
`added_time`, `branch`, `ticket_id`, `csv_order_id`.

### 4) Run the dashboard locally
```bash
streamlit run dashboard.py
```

## Streamlit Cloud deployment (sync = guaranteed)

Streamlit Cloud reads `data/zoho_latest.csv` from GitHub.
After every pipeline run, `sync_to_github.py` exports & pushes that CSV automatically.

If Streamlit Cloud shows old data:
- Streamlit Cloud → **Clear cache** + **Reboot app**
- Verify GitHub `main` has the latest `data/zoho_latest.csv`

## Common commands

```bash
# export to Excel
python pipeline.py --export

# run just the CSV merge (metadata into DB)
python merge_csv.py

# run just the GitHub sync (DB → CSV → push)
python sync_to_github.py
```

## Notes
- OCR engine is RapidOCR
