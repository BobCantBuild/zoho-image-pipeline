# CLAUDE.md — Project Memory: Zoho Image Pipeline

> Last updated: 2026-05-21 (session 2)
> This file is the authoritative memory for Claude across all sessions.
> Read this first before touching any file.

---

## 1. What This Project Does

End-to-end pipeline that:
1. Scans local image folders → OCR extracts **Order ID** and **Star Rating** from customer screenshots
2. Merges Zoho Forms CSV metadata (Added Time, Branch, Ticket ID, Zoho Order ID) into SQLite
3. Auto-publishes a Streamlit dashboard — runs locally (SQLite) and on Streamlit Cloud (GitHub CSV)

**Live cloud URL:** `https://zoho-image-pipeline.streamlit.app/`
**Streamlit deploys from:** `https://github.com/BobCantBuild/zoho-image-pipeline.git` (remote: `origin`)
**Internal mirror:** `https://github.com/IFB-Analytics/zoho-form-audit.git` (remote: `ifb`)

---

## 2. Key File Map

| File | Role |
|---|---|
| `pipeline.py` | Main runner — scans folders, OCR, writes SQLite, periodic GitHub sync |
| `ocr_engine.py` | RapidOCR + OpenCV extraction (Order ID + Star Rating) |
| `image_preprocess.py` | Image cleanup helpers |
| `merge_csv.py` | Merges Zoho CSV → SQLite (`added_time`, `branch`, `ticket_id`, `csv_order_id`) |
| `sync_to_github.py` | SQLite → `data/zoho_latest.csv` → git push |
| `db.py` | SQLite schema + helpers (`upsert_record`, `get_stats`, `fetch_ok_names`) |
| `config.py` | `BASE_DIR`, `DB_PATH`, `ZOHO_CSV_PATH`, `OCR_WORKERS` |
| `dashboard.py` | **Main dashboard** — all UI logic lives here |
| `streamlit_app.py` | Cloud entrypoint — `runpy.run_path("dashboard.py")` |
| `data/zoho_latest.csv` | What Streamlit Cloud reads (auto-updated by sync) |
| `data/last_sync.txt` | Exact timestamp written by `sync_to_github.py` on every push — dashboard reads this for "Data last synced" display (file mtime is unreliable on Streamlit Cloud) |
| `.streamlit/config.toml` | Theme: light, primaryColor `#6366f1`, bg `#f8fafc` |

---

## 3. Data Flow

```
Image folders (BASE_DIR)
    ↓  pipeline.py (OCR)
SQLite zoho_pipeline.db          ← local only (Windows path)
    ↓  merge_csv.py
SQLite  (+ ticket_id, branch, csv_order_id, added_time)
    ↓  sync_to_github.py  (every 30 s during run + at end)
data/zoho_latest.csv + data/last_sync.txt  →  git push origin main → GitHub (BobCantBuild)
    ↓  Streamlit Cloud auto-pulls
zoho-image-pipeline.streamlit.app
```

**Local dashboard** reads SQLite directly.
**Cloud dashboard** reads `data/zoho_latest.csv`.

---

## 4. SQLite Schema (`zoho_records`)

```sql
sno                    INTEGER PRIMARY KEY AUTOINCREMENT
ticket_id              TEXT          -- from merge_csv
csv_order_id           TEXT          -- Zoho form order ID (from merge_csv)
added_time             TEXT          -- from merge_csv
branch                 TEXT          -- from merge_csv
file_name              TEXT NOT NULL UNIQUE   -- folder name = record key
image1_path            TEXT
image2_path            TEXT
file_order_id          TEXT          -- OCR-extracted order ID
file_star              REAL          -- OCR-extracted star rating
remarks_file_order_id  TEXT
remarks_file_star      TEXT
flag                   TEXT          -- PENDING | OK | NO_ORDER_ID | NO_STAR | ERROR | ...
ocr_engine_order       TEXT
ocr_engine_star        TEXT
processed_at           TEXT
raw_ocr_image1         TEXT
raw_ocr_image2         TEXT
```

**Important:** `file_order_id` is extracted by OCR from the order screenshot.
`csv_order_id` is the order ID the customer typed into the Zoho form.
These two are compared in the dashboard to produce `Order_ID_Flag`.

---

## 5. Dashboard: Computed Columns (compute_flags)

All three flag columns are computed in Python at load time (not stored in DB).

### `_is_blank(val)` helper
Handles `None`, `float('nan')` (pandas NaN), and string placeholders (`"None"`, `"nan"`, `"NaN"`, `"—"`).
**Critical:** `bool(float('nan'))` is `True` in Python — always use `_is_blank()`, never `if not val`.

### `Order_ID_Flag`
| Condition | Result |
|---|---|
| `file_order_id` is blank/NaN | `"Un-Verified"` |
| `csv_order_id` (Zoho_order_ID) is blank | `"Un-Verified"` |
| Both present and match | `"YES"` |
| Both present, no match | `"NO"` |

### `file_star_flag`
| Condition | Result |
|---|---|
| `file_star` is blank/NaN | `"Un-Verified"` |
| `file_star >= 4` | `"YES"` |
| `file_star < 4` | `"NO"` |

### `Flag` (Verified) — truth table
| `Order_ID_Flag` | `file_star_flag` | `Flag` |
|---|---|---|
| YES | YES | **YES** |
| NO | NO | **NO** |
| NO | YES | **NO** |
| YES | NO | **NO** |
| Un-Verified | YES | **Un-Verified** |
| YES | Un-Verified | **Un-Verified** |
| Un-Verified | NO | **NO** |
| NO | Un-Verified | **NO** |

Logic: `if oid=="YES" and star=="YES" → YES`, `elif oid=="NO" or star=="NO" → NO`, `else → Un-Verified`

---

## 6. Dashboard: Metric Cards (top section)

Five cards, no repetition:

| Card | Value | Note |
|---|---|---|
| **In Pipeline** | `folder_count` from `BASE_DIR` filesystem scan | Falls back to DB total |
| **Pending** | `stats["pending"]` | Records still processing |
| **Order ID Match** | 3 sub-cells: ✓ Match / ✕ Mismatch / — Un-Verified | From `Order_ID_Flag` |
| **Star Rating** | 3 sub-cells: ★ ≥4 / ★ <4 / — Un-Verified | From `file_star_flag` |
| **Verified** | 3 sub-cells: ✓ YES / ✕ NO / — Un-Verified | From `Flag` |

Metrics always use the **full `df`** (unfiltered), not `filt`.

---

## 7. Dashboard: Filter Container

Single `st.container(border=True)` with one row, 7 columns:

```
✦ Verified | 🔗 Order ID Match | ⭐ Star ≥ 4 | 🏢 Branch | 📅 Date (range) | ⬇️ Export | ✕ Clear
```

- All dropdowns: `["All", "YES", "NO", "Un-Verified"]`
- Date: single `st.date_input(value=[], format="DD/MM/YYYY")` — Streamlit native range mode
- Export slot: `st.empty()` filled after `filt` is computed
- Clear button keys: `["search_box","ff1","ff2","ff3","branch_filter","date_range","page"]`
- **Date filter is NaT-safe**: rows with no date (PENDING stubs) always included regardless of filter

---

## 8. Dashboard: Table

- PENDING rows: dimmed (opacity 45%), all flag cells show `⏳ Pending` badge (yellow)
- Non-pending rows: normal rendering with `badge()` / `flag_cell()` / `star_html()`
- Pagination: **Prev / Next** are BELOW the table (not in the filter container)
- Uses `on_click=_prev_page` / `on_click=_next_page` callbacks so session_state updates before table renders

---

## 9. Dashboard: Cache & Auto-Refresh

### Cache key
```python
@st.cache_data(ttl=120)
def load_data(db_mtime: float, csv_mtime: float) -> tuple:
```
Called as: `load_data(db_mtime=_file_mtime(DB_PATH), csv_mtime=_file_mtime(CSV_PATH))`

Any write to DB or CSV → different mtime → different cache key → instant cache miss → fresh read.
`ttl=120` is a safety backstop only.

### Auto-refresh logic

| Mode | Condition | Sleep | Action |
|---|---|---|---|
| Local | `pending > 0` | 5 s | rerun |
| Local | `_db_mtime` or `_csv_mtime` just changed | 1 s | rerun |
| Local | idle, nothing changed | none | no rerun |
| **Cloud** | `pending > 0` | 5 s | rerun |
| **Cloud** | idle | **30 s** | rerun (heartbeat to catch CSV pushes) |

Cloud mode detected by: `_is_cloud = not Path(DB_PATH).exists()`

Session state keys: `_last_db_mtime`, `_last_csv_mtime`

---

## 10. Pipeline: Real-Time GitHub Sync

`_periodic_github_sync` runs as a **daemon thread** during every pipeline run:
- Pushes DB → CSV → GitHub every **30 seconds**
- Stopped cleanly after processing completes
- Final sync always happens via existing `sync()` call at end of `pipeline.py`

Terminal shows: `Live sync: GitHub dashboard updating every 30 s…`

### Git remote targeting (critical)
`sync_to_github.py` uses `GIT_REMOTE = os.environ.get("ZOHOPIPE_GIT_REMOTE", "origin")` and
calls `git push origin <branch>` explicitly. **Never use bare `git push`** — the branch tracks
`ifb/main` as its upstream, so bare push sends to the wrong repo and Streamlit never updates.

### Sync artefacts written on every push
1. `data/zoho_latest.csv` — full DB export
2. `data/last_sync.txt` — exact timestamp string (`%d %b %Y  %H:%M`) for dashboard display

---

## 11. Known Bugs Fixed (history)

| Bug | Root Cause | Fix |
|---|---|---|
| Order ID always "Un-Verified" mid-run | `csv_order_id` is NULL until `merge_csv` runs | Expected behaviour — resolves after merge |
| Order ID shows `✕ NO` when `file_order_id` is `—` | `float('nan')` is truthy in Python; `str(nan)` = `"nan"` passed through `normalise_oid` → `"NAN"` (non-empty) | Added `_is_blank()` helper using `pd.isna()` |
| Cloud dashboard frozen on stale data | `_db_mtime` always 0.0 on cloud → `_db_just_changed` always False → no auto-rerun when `pending=0` | Cloud now always heartbeats every 30 s |
| Stale data after `--fresh` | `@st.cache_data` with no argument key shared one cache entry for all calls | Cache key now includes `db_mtime` + `csv_mtime` |
| Unconditional `time.sleep(8)` blocked UI | Sleep at end of every script run, including user interactions | Conditional: only sleep when pipeline running or cloud heartbeat |
| PENDING rows filtered by date | NaT date comparisons return False → rows excluded | `_nat = _dp.isna(); filt = filt[_nat | (...)]` |
| Search bottom border invisible | Streamlit BaseUI wrapper `div[data-baseweb="input"]` overrides `<input>` border | Border CSS moved to `div[data-baseweb="input"]`, raw `<input>` set to `border:none` |
| Streamlit shows stale 10-record data despite 15-record syncs | Branch tracks `ifb/main`; bare `git push` sent to `IFB-Analytics/zoho-form-audit`, not the Streamlit-deployed `BobCantBuild/zoho-image-pipeline` | `sync_to_github.py` now calls `git push origin <branch>` explicitly |
| "Data last synced" time was wrong on cloud | `CSV_PATH.stat().st_mtime` returns container clone time on Streamlit Cloud, not actual data sync time | Write `data/last_sync.txt` with real timestamp on every sync; dashboard reads that file |

---

## 12. Pipeline CLI Reference

```bash
python pipeline.py                   # process all new (auto-resumes)
python pipeline.py --limit 10        # test 10 folders
python pipeline.py --limit 10 --fresh  # clear DB + reprocess 10
python pipeline.py --debug           # print raw OCR text per image
python pipeline.py --export          # export to Excel after run

python merge_csv.py                  # re-merge Zoho CSV into DB
python sync_to_github.py             # manual push DB → CSV → GitHub

streamlit run dashboard.py           # local dashboard
```

---

## 13. Design Decisions & Conventions

- **"Un-Verified"** (not "Undefined") — used everywhere for missing/indeterminate data
- **Badge CSS classes:** `.b-yes` (green), `.b-no` (red), `.b-und` (grey)
- **Colour helpers:** `.c-green`, `.c-red`, `.c-orange`, `.c-amber`, `.c-gray`, `.c-dark`
- **Table:** compact — cell padding `8px 10px`, font 13px, badges 12px — fits without horizontal scroll
- **Prev/Next pagination** uses `on_click` callbacks (`_prev_page`, `_next_page`) not button return values — required because buttons are defined AFTER the table
- **Export** uses `st.empty()` placeholder inside container, filled after `filt` is computed
- **Processing Status filter** was REMOVED from the UI (was ⚙️ Processing Status dropdown)
- **Date filter** is a single native Streamlit range picker (`value=[]`), format `DD/MM/YYYY`
- **Folder path** removed from "In Pipeline" metric card — clean, no clutter
- **Command hint** removed from "Pending" metric card

---

## 14. Dashboard Top Bar Design

| Element | Value | Reason |
|---|---|---|
| Emoji | 🔍 | Verification/audit context — not 📦 (shipping box) |
| Title | `Zoho Forms Analysis` | User-specified name; also set in `set_page_config(page_title=...)` |
| Subtitle | `OCR · Image Processing · Order ID & Star Rating Audit` | States the three actual operations |
| Badge (running) | `⚡ Pipeline active — processing in progress` | Generic — no counts |
| Badge (done) | `✅ Pipeline complete — results up to date` | Generic — no counts |
| Right: primary | `data/last_sync.txt` content | Actual data time, not page render time |
| Right: secondary | `Page loaded {now_str}` | Small, de-emphasised |

**Rule:** Badge must stay generic (no record counts). Counts belong in the metric cards below.

---

## 15. Streamlit Cloud Notes

- Entry point: `streamlit_app.py` → `runpy.run_path("dashboard.py")`
- Data files: `data/zoho_latest.csv` + `data/last_sync.txt` (both committed on every sync)
- Deployed from: `BobCantBuild/zoho-image-pipeline` (`origin`) — pushes must go there
- Cloud pulls new data within ~1–3 minutes of a git push to `origin`
- Cloud dashboard picks it up on next 30 s heartbeat tick
- If cloud shows very old data: Streamlit Cloud → **Manage app → Reboot**
- Theme in `.streamlit/config.toml`: light, `#6366f1` primary, `#f8fafc` background
