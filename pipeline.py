# =============================================================
#  pipeline.py  —  Main runner
#
#  python pipeline.py              → process all (auto-resumes)
#  python pipeline.py --limit 5   → test 5 folders
#  python pipeline.py --fresh     → clear DB + reprocess all
#  python pipeline.py --debug     → print raw OCR text per image
#  python pipeline.py --export    → export to Excel after run
# =============================================================

import sys, time, logging, argparse, sqlite3, threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from config import (
    BASE_DIR, DB_PATH, LOG_FILE, LOG_LEVEL,
    IMAGE_FOLDER_1, IMAGE_FOLDER_2, OCR_WORKERS, IMAGE_CACHE_DIR
)
from db       import init_db, upsert_record, fetch_ok_names, get_stats
from ocr_engine import extract_order_id, extract_star_rating, get_raw_ocr, classify_star_category
from sheet_source import fetch_rows, ensure_row_images
from flags import compute_flags

# ── Logging → file only; terminal output via print() ──────────
logging.basicConfig(
    level   = getattr(logging, LOG_LEVEL, logging.WARNING),
    format  = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    handlers= [logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
logger = logging.getLogger("pipeline")

# ── ANSI colours (work on Windows 10+ terminals) ──────────────
R="\033[0m"; GR="\033[92m"; YL="\033[93m"; RD="\033[91m"
CY="\033[96m"; BD="\033[1m"


# =============================================================
#  SHEET SCANNER  (Google Sheet → rows + Drive image downloads)
# =============================================================

def scan_sheet(limit: Optional[int]) -> list:
    """Pull the Google Sheet and return records with image URLs only.
    Images are downloaded later inside process_record() in parallel —
    NOT here — so this function returns instantly and all PENDING stubs
    can be written before any slow network work starts."""
    print(f"  {CY}Fetching sheet…{R}")
    rows = fetch_rows()
    print(f"  Sheet rows: {len(rows):,}")
    if limit:
        rows = rows[:limit]

    return [{
        "file_name":    row["ticket_id"],
        "ticket_id":    row["ticket_id"],
        "csv_order_id": row["order_id"],
        "added_time":   row["added_time"],
        "branch":       row["branch"],
        "image1_url":   row.get("image1_url", ""),
        "image2_url":   row.get("image2_url", ""),
        "image1_path":  None,
        "image2_path":  None,
        "sheet_row":    i + 1,   # 1-based row number from the sheet
    } for i, row in enumerate(rows)]


# =============================================================
#  RECORD PROCESSOR
# =============================================================

def process_record(rec: dict, debug: bool = False) -> dict:
    fname = rec["file_name"]

    # Download images now (parallel workers handle this concurrently)
    img1 = rec.get("image1_path")
    img2 = rec.get("image2_path")
    if not img1 or not img2:
        img1, img2 = ensure_row_images(rec, IMAGE_CACHE_DIR)

    out = dict(
        file_name             = fname,
        image1_path           = img1,
        image2_path           = img2,
        file_order_id         = None,
        service_rating        = None,   # stars when image shows "Installation and Demo"
        product_rating        = None,   # stars when image shows "Rate your experience"
        file_star             = None,   # stars when neither keyword detected (general)
        remarks_file_order_id = None,
        remarks_file_star     = None,
        flag                  = None,
        ocr_engine_order      = None,
        ocr_engine_star       = None,
        raw_ocr_image1        = None,
        raw_ocr_image2        = None,
    )
    flags = []

    # ── ORDER ID ─────────────────────────────────────────────
    oid = rem_o = eng_o = None

    if img1:
        raw1 = get_raw_ocr(img1)
        out["raw_ocr_image1"] = raw1
        if debug:
            print(f"\n{CY}  [DEBUG OCR] {fname} / Image1:{R}\n{raw1}\n")
        oid, rem_o, eng_o = extract_order_id(img1)

    if not oid and img2:
        raw2 = get_raw_ocr(img2)
        out["raw_ocr_image2"] = raw2
        if debug:
            print(f"\n{CY}  [DEBUG OCR] {fname} / Image2:{R}\n{raw2}\n")
        oid, rem_o, eng_o = extract_order_id(img2)
        if oid:
            rem_o = "Order ID found in Image2"

    if not oid:
        rem_o = "Order ID not found in files"
        flags.append("NO_ORDER_ID")
    # Legacy compatibility (older engine labels)
    if eng_o in {"tesseract_partial", "partial"}:
        flags.append("LOW_CONF_ORDER")

    out.update(file_order_id=oid, remarks_file_order_id=rem_o, ocr_engine_order=eng_o)

    # ── STAR RATING — Image 2 ONLY ────────────────────────────
    # Image 1 is the ORDER screenshot: it often contains unrelated star
    # graphics (seller ratings, "rate this product" widgets), which give
    # false counts. Never fall back to it for stars.
    star = rem_s = eng_s = None
    star_img_text = ""      # OCR text of the rating screenshot

    if img2:
        if out["raw_ocr_image2"] is None:
            out["raw_ocr_image2"] = get_raw_ocr(img2)
        star_img_text = out["raw_ocr_image2"] or ""
        star, rem_s, eng_s = extract_star_rating(img2)

    if star is None:
        rem_s = "Stars not found in Image2"
        flags.append("NO_STAR")

    # ── Route star count into the correct category field ─────
    # Exactly one of service_rating / product_rating / file_star
    # will be set; the others stay None.
    #   "Installation and Demo" screen                       → service_rating
    #   "Rate your experience" / "Share your experience"     → product_rating
    #   neither phrase detected                              → file_star (general)
    # Keywords are matched against Image 2's text only — Image 1 (order
    # page) can contain phrases like "share your experience" and mis-route.
    service_rating = product_rating = file_star_val = None
    if star is not None:
        category = classify_star_category(star_img_text)
        if category == "service":
            service_rating = star
        elif category == "product":
            product_rating = star
        else:
            file_star_val = star   # general / unknown context

    out.update(
        service_rating  = service_rating,
        product_rating  = product_rating,
        file_star       = file_star_val,
        remarks_file_star = rem_s,
        ocr_engine_star   = eng_s,
    )

    # ── FLAGS ─────────────────────────────────────────────────
    if not img1: flags.append("MISSING_IMG1")
    if not img2: flags.append("MISSING_IMG2")
    out["flag"] = "OK" if not flags else "|".join(flags)
    return out


# =============================================================
#  DISPLAY
# =============================================================

def _flag_str(flag: str) -> str:
    if flag == "OK":           return f"{GR}OK{R}"
    if "ERROR"    in flag:     return f"{RD}ERROR{R}"
    if "MISSING"  in flag:     return f"{RD}MISSING{R}"
    if "LOW_CONF" in flag:     return f"{CY}LOW_CONF{R}"
    return f"{YL}{flag[:14]}{R}"


def _bar(done: int, total: int, w: int = 30) -> str:
    f = int(w * done / total) if total else 0
    return f"{GR}{'█'*f}{R}{'░'*(w-f)}"


def _header(total: int, skipped: int):
    print()
    print(f"{BD}{'='*68}{R}")
    print(f"{BD}  ZOHO FORMS IMAGE PIPELINE  —  RapidOCR + OpenCV{R}")
    print(f"{'='*68}")
    print(f"  {CY}Database  :{R} {DB_PATH}")
    print(f"  To process: {total:,}   Already done: {skipped:,}   Workers: {OCR_WORKERS}")
    print(f"{'='*68}")
    print(f"  {BD}{'#':<6}  {'Folder':<22}  {'Order ID':<24}  {'Star':<6}  Flag{R}")
    print(f"  {'─'*66}")


def _row(sno: int, fname: str, oid, star, flag: str):
    o = str(oid)[:22]  if oid  is not None else f"{YL}—{R}"
    s = f"{star:.1f}"  if star is not None else f"{YL}—{R}"
    print(f"  {sno:<6}  {fname[:22]:<22}  {o:<24}  {s:<6}  {_flag_str(flag)}")


def _progress(done: int, total: int, rate: float, eta: float, errs: int):
    eta_s = f"{eta/60:.1f}min" if eta > 90 else f"{eta:.0f}s"
    print(
        f"  {_bar(done,total)}  {done}/{total}  "
        f"{done/total*100:.1f}%  {rate:.1f}/s  ETA {eta_s}  Err:{errs}   ",
        end="\r", flush=True
    )


def _footer(stats: dict, elapsed: float):
    print(f"\n{'='*68}")
    print(f"{BD}  DONE{R}")
    print(f"{'='*68}")
    for k, v in stats.items():
        print(f"  {k:<22}: {v:,}")
    print(f"  {'elapsed':<22}: {elapsed/60:.1f} min")
    print(f"  {CY}Database at: {DB_PATH}{R}")
    print(f"{'='*68}\n")


# =============================================================
#  REAL-TIME GITHUB SYNC  (background thread during run)
# =============================================================

def _periodic_github_sync(stop_event: threading.Event, interval: int = 30):
    """Push DB → CSV → GitHub every `interval` seconds while pipeline runs.
    Runs as a daemon thread so it never blocks process exit."""
    while not stop_event.wait(interval):
        try:
            from sync_to_github import sync
            sync()
        except Exception as e:
            logger.debug("periodic_sync: %s", e)


# =============================================================
#  MAIN
# =============================================================

def _added_time_key(rec: dict) -> datetime:
    """Parse the sheet's 'Added Time' (e.g. '03-Jul-2026 23:37:58') for sorting.
    Unparseable/blank values sort last so they never block chronological rows."""
    raw = (rec.get("added_time") or "").strip()
    try:
        return datetime.strptime(raw, "%d-%b-%Y %H:%M:%S")
    except ValueError:
        return datetime.max


def run(limit: Optional[int] = None, fresh: bool = False, debug: bool = False,
        retry_failed: bool = False):
    init_db()

    if fresh:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("DELETE FROM zoho_records")
            c.commit()
        print(f"\n  {YL}Fresh mode: database cleared.{R}")

    all_recs  = scan_sheet(limit)
    done_names= fetch_ok_names(retry_failed=retry_failed)
    pending   = [r for r in all_recs if r["file_name"] not in done_names]
    pending.sort(key=_added_time_key)   # process row-wise: oldest Added Time first
    skipped   = len(all_recs) - len(pending)

    # Refresh sheet-side metadata for already-processed rows too (branch, order id,
    # etc. can change in the sheet after we OCR'd), then skip them for OCR.
    for rec in all_recs:
        if rec["file_name"] in done_names:
            upsert_record({
                "file_name":    rec["file_name"],
                "ticket_id":    rec["ticket_id"],
                "csv_order_id": rec["csv_order_id"],
                "added_time":   rec["added_time"],
                "branch":       rec["branch"],
            })

    if not pending:
        print(f"\n  {GR}All records already processed.{R}")
        print(f"  Database: {DB_PATH}\n")
        return

    _header(len(pending), skipped)

    # ── Start background sync thread (pushes every 30 s to GitHub) ──
    _stop_sync = threading.Event()
    _sync_thread = threading.Thread(
        target=_periodic_github_sync,
        args=(_stop_sync, 30),
        daemon=True,
        name="github-sync",
    )
    _sync_thread.start()
    print(f"  {CY}Live sync:{R} GitHub dashboard updating every 30 s…\n")

    sno_c = [0]; err_c = [0]
    t0    = time.time()
    lock  = threading.Lock()

    with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
        futs = {pool.submit(process_record, r, debug): r for r in pending}

        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.error("Error %s: %s", rec["file_name"], e)
                res = {"file_name": rec["file_name"], "file_order_id": None,
                       "file_star": None, "flag": "ERROR",
                       "remarks_file_order_id": str(e)[:200]}
                err_c[0] += 1
            # Sheet metadata + persisted verification flags in one write
            res.update(
                ticket_id    = rec.get("ticket_id"),
                csv_order_id = rec.get("csv_order_id"),
                added_time   = rec.get("added_time"),
                branch       = rec.get("branch"),
                sheet_row    = rec.get("sheet_row"),
            )
            res.update(compute_flags(res))
            upsert_record(res)

            with lock:
                sno_c[0] += 1
                sno      = sno_c[0]
                elapsed  = time.time() - t0
                rate     = sno / elapsed if elapsed else 0.001
                eta      = (len(pending) - sno) / rate
                _row(sno, res["file_name"],
                     res.get("file_order_id"),
                     res.get("file_star"),
                     res.get("flag","?"))
                _progress(sno, len(pending), rate, eta, err_c[0])

    # ── Stop background sync; do one final sync ──────────────────
    _stop_sync.set()
    _sync_thread.join(timeout=5)

    print()
    _footer(get_stats(), time.time() - t0)


# =============================================================
#  ENTRY POINT
# =============================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Zoho Forms Pipeline — RapidOCR + OpenCV")
    ap.add_argument("--limit",  type=int,           help="Process only N folders")
    ap.add_argument("--fresh",  action="store_true", help="Clear DB + reprocess all")
    ap.add_argument("--debug",  action="store_true", help="Print raw OCR text per image")
    ap.add_argument("--export", action="store_true", help="Export DB to Excel after run")
    ap.add_argument("--retry-failed", action="store_true",
                     help="Also re-attempt rows previously flagged NO_ORDER_ID/NO_STAR")
    a = ap.parse_args()

    run(limit=a.limit, fresh=a.fresh, debug=a.debug, retry_failed=a.retry_failed)

    # Sheet fields (Ticket ID / Order ID / Branch / Added Time) are written
    # inline by scan_sheet(); merge_csv is no longer needed.

    if a.export:
        from export import export_to_excel
        p = export_to_excel()
        if p: print(f"  Exported: {p}")

    # Auto-sync to GitHub → public dashboard updates automatically
    try:
        from sync_to_github import sync
        sync()
    except Exception as e:
        print(f"  [GitHub sync skipped]: {e}")
