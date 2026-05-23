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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from config import (
    BASE_DIR, DB_PATH, LOG_FILE, LOG_LEVEL,
    IMAGE_FOLDER_1, IMAGE_FOLDER_2, OCR_WORKERS
)
from db       import init_db, upsert_record, fetch_ok_names, get_stats
from ocr_engine import extract_order_id, extract_star_rating, get_raw_ocr, classify_star_category

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
#  FOLDER SCANNER
# =============================================================

def _find_image(folder: Path) -> Optional[str]:
    if not folder.exists():
        return None
    for ext in ("*.jpg","*.jpeg","*.JPG","*.JPEG","*.png","*.PNG","*.webp"):
        hits = list(folder.glob(ext))
        if hits:
            return str(hits[0])
    return None


def scan_folders(limit: Optional[int]) -> list:
    base = Path(BASE_DIR)
    if not base.exists():
        print(f"\n{RD}  ERROR: BASE_DIR not found:{R}\n  {BASE_DIR}\n")
        sys.exit(1)
    records = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        records.append({
            "file_name":   entry.name,
            "image1_path": _find_image(entry / IMAGE_FOLDER_1),
            "image2_path": _find_image(entry / IMAGE_FOLDER_2),
        })
        if limit and len(records) >= limit:
            break
    return records


# =============================================================
#  RECORD PROCESSOR
# =============================================================

def process_record(rec: dict, debug: bool = False) -> dict:
    fname = rec["file_name"]
    img1  = rec.get("image1_path")
    img2  = rec.get("image2_path")

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

    # ── STAR RATING ──────────────────────────────────────────
    star = rem_s = eng_s = None
    star_img_text = ""      # OCR text of the image that yielded the star count

    if img2:
        if out["raw_ocr_image2"] is None:
            out["raw_ocr_image2"] = get_raw_ocr(img2)
        star_img_text = out["raw_ocr_image2"] or ""
        star, rem_s, eng_s = extract_star_rating(img2)

    if star is None and img1:
        star, rem_s, eng_s = extract_star_rating(img1)
        if star is not None:
            star_img_text = out.get("raw_ocr_image1") or ""
            rem_s = "Stars found in Image1"

    if star is None:
        rem_s = "Stars not found in files"
        flags.append("NO_STAR")

    # ── Route star count into the correct category field ─────
    # Exactly one of service_rating / product_rating / file_star
    # will be set; the others stay None.
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

def run(limit: Optional[int] = None, fresh: bool = False, debug: bool = False):
    init_db()

    if fresh:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("DELETE FROM zoho_records")
            c.commit()
        print(f"\n  {YL}Fresh mode: database cleared.{R}")

    all_recs  = scan_folders(limit)
    done_names= fetch_ok_names()
    pending   = [r for r in all_recs if r["file_name"] not in done_names]
    skipped   = len(all_recs) - len(pending)

    if not pending:
        print(f"\n  {GR}All records already processed.{R}")
        print(f"  Database: {DB_PATH}\n")
        return

    # Write PENDING stubs immediately so DB shows all rows from start
    for rec in pending:
        upsert_record({"file_name": rec["file_name"],
                       "image1_path": rec.get("image1_path"),
                       "image2_path": rec.get("image2_path"),
                       "flag": "PENDING"})

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
                upsert_record(res)
            except Exception as e:
                logger.error("Error %s: %s", rec["file_name"], e)
                res = {"file_name": rec["file_name"], "file_order_id": None,
                       "file_star": None, "flag": "ERROR",
                       "remarks_file_order_id": str(e)[:200]}
                upsert_record(res)
                err_c[0] += 1

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
    a = ap.parse_args()

    run(limit=a.limit, fresh=a.fresh, debug=a.debug)

    # Merge Zoho CSV (Ticket ID + Order ID) into DB so dashboard/export has full fields
    try:
        from merge_csv import run as merge_csv_run
        merge_csv_run()
    except Exception as e:
        print(f"  [merge_csv skipped]: {e}")

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
