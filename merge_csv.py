# =============================================================
#  merge_csv.py  —  Standalone script
#
#  What it does:
#  1. Reads the CSV file
#  2. Cleans "File name" column (removes leading apostrophe/quote)
#  3. Adds "Ticket ID" and "Order ID" columns to SQLite if missing
#  4. Matches CSV "File name" → SQLite "file_name"
#  5. Updates matched rows with Ticket ID and Order ID
#  6. Prints a summary — how many matched, how many not found
#
#  Run:  python merge_csv.py
#  Safe: reads DB, only updates matched rows, never deletes anything
# =============================================================

import sqlite3
import csv
import os
import re
from pathlib import Path

from config import DB_PATH as CONFIG_DB_PATH
from config import ZOHO_CSV_PATH as CONFIG_CSV_PATH

# ── CONFIG — only edit these two lines if paths change ────────
CSV_PATH = os.environ.get("ZOHOPIPE_ZOHO_CSV_PATH") or str(CONFIG_CSV_PATH)
DB_PATH = os.environ.get("ZOHOPIPE_DB_PATH") or str(CONFIG_DB_PATH)
# ──────────────────────────────────────────────────────────────

# Excel silently converts long numeric IDs (folder ids, Amazon order ids) into
# scientific notation when the CSV is opened+saved — e.g. "246572000000016066"
# becomes "2.47E+17" and "40227996110609900" becomes "4.02E+16". That destroys
# the join key and any numeric Order ID. Detect it so we can recover/skip.
_SCI_RE = re.compile(r"^\s*[-+]?\d(?:\.\d+)?[eE][-+]?\d+\s*$")
# A folder / record id is a long run of digits (zoho ids are 18 digits).
_ID_FROM_PATH_RE = re.compile(r"['\"`\s]*(\d{8,})[\\/]")


def looks_sci_corrupt(raw: str) -> bool:
    """True if Excel mangled a long number into scientific notation ('2.47E+17')."""
    return bool(_SCI_RE.match(raw or ""))


def clean_filename(raw: str) -> str:
    """
    Remove leading apostrophe, quotes, spaces from File name.
    "'246572000000016066" → "246572000000016066"
    """
    if not raw:
        return ""
    return raw.strip().lstrip("'\"` ").strip()


def recover_id_from_paths(*path_values: str) -> str:
    """
    Recover the real folder / record id from an image-path cell.

    The path columns survive Excel corruption because they are text, e.g.
    "246572000000016066/ImageUpload/WhatsApp_Image_....jpeg"
    The leading digits before the first slash are the folder id.
    """
    for val in path_values:
        m = _ID_FROM_PATH_RE.match(val or "")
        if m:
            return m.group(1)
    return ""


def clean_order_id(raw: str) -> tuple[str, bool]:
    """
    Return (order_id, was_corrupt).

    Excel turns long numeric order ids (e.g. Amazon "40227996110609900") into
    scientific notation ("4.02E+16") which is unrecoverable. We return an empty
    string for those so the dashboard shows "Un-Verified" rather than a false
    "NO" from comparing against garbage. OD-prefixed Flipkart ids are text and
    survive intact.
    """
    s = (raw or "").strip()
    if not s:
        return "", False
    if looks_sci_corrupt(s):
        return "", True
    return s, False


def add_columns_if_missing(conn: sqlite3.Connection):
    """Add Ticket/Order/Branch/Added Time columns to zoho_records if not there."""
    existing = [row[1] for row in conn.execute("PRAGMA table_info(zoho_records)")]
    if "ticket_id" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN ticket_id TEXT")
        print("  [DB] Added column: ticket_id")
    if "csv_order_id" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN csv_order_id TEXT")
        print("  [DB] Added column: csv_order_id")
    if "added_time" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN added_time TEXT")
        print("  [DB] Added column: added_time")
    if "branch" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN branch TEXT")
        print("  [DB] Added column: branch")
    conn.commit()


def read_csv(csv_path: str) -> list:
    """
    Read CSV and return list of dicts.
    Auto-detects delimiter (, or ;) and encoding.
    """
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"\n  CSV not found:\n  {csv_path}\n")

    # Try UTF-8 first, then latin-1 (handles Indian locale exports)
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(csv_path, encoding=encoding, newline="") as f:
                sample = f.read(2048)
                f.seek(0)
                # Detect delimiter
                delimiter = "," if sample.count(",") >= sample.count(";") else ";"
                reader = csv.DictReader(f, delimiter=delimiter)
                rows   = list(reader)
                print(f"  [CSV] Read {len(rows)} rows  "
                      f"(encoding={encoding}, delimiter='{delimiter}')")
                return rows
        except UnicodeDecodeError:
            continue

    raise ValueError("Cannot decode CSV — try saving it as UTF-8 from Excel")


def find_columns(rows: list) -> tuple:
    """
    Find the actual column names for File name, Ticket ID, Order ID, Added Time,
    Branch, and the two image-path columns (used to recover a corrupted File name).
    Case-insensitive, handles slight name variations.
    Returns (file_col, ticket_col, order_col, added_time_col, branch_col, path_cols).
    """
    if not rows:
        raise ValueError("CSV is empty")

    headers = list(rows[0].keys())
    print(f"  [CSV] Columns found: {headers}")

    def find(keywords):
        for h in headers:
            hl = h.lower().strip()
            if any(k in hl for k in keywords):
                return h
        return None

    file_col   = find(["file name", "file_name", "filename", "file"])
    ticket_col = find(["ticket id", "ticket_id", "ticketid", "ticket"])
    order_col  = find(["order id", "order_id", "orderid", "order"])
    added_col  = find(["added time", "added_time", "date of posting", "date_of_posting", "posting date"])
    branch_col = find(["branch"])

    # Image-path columns ("Please upload a clear picture of the order screen…").
    # These keep the real folder id even when Excel mangles the File name column.
    path_cols = [h for h in headers
                 if any(k in h.lower() for k in ("upload", "picture", "screen"))]

    missing = []
    if not file_col:   missing.append("'File name'")
    if not ticket_col: missing.append("'Ticket ID'")
    if not order_col:  missing.append("'Order ID'")
    if not added_col:  missing.append("'Added Time'")
    if not branch_col: missing.append("'Branch'")

    if missing:
        raise ValueError(
            f"\n  Could not find columns: {', '.join(missing)}\n"
            f"  Available columns: {headers}\n"
            f"  Check the CSV column names and update find() keywords if needed.\n"
        )

    print(f"  [CSV] Mapped  ->  file='{file_col}'  "
          f"ticket='{ticket_col}'  order='{order_col}'  "
          f"added='{added_col}'  branch='{branch_col}'")
    if path_cols:
        print(f"  [CSV] Path columns for id-recovery: {path_cols}")
    return file_col, ticket_col, order_col, added_col, branch_col, path_cols


def run(csv_path: str | None = None, db_path: str | None = None):
    print()
    print("=" * 60)
    print("  CSV -> SQLite Merge")
    print("=" * 60)

    # ── 1. Read CSV ────────────────────────────────────────────
    csv_path = csv_path or CSV_PATH
    db_path = db_path or DB_PATH

    rows = read_csv(csv_path)
    file_col, ticket_col, order_col, added_col, branch_col, path_cols = find_columns(rows)

    # Build lookup dict:  file_name → {ticket_id, csv_order_id, added_time, branch}
    lookup = {}
    skipped = 0
    recovered = 0        # File name recovered from image path (Excel corruption)
    corrupt_orders = 0   # Order IDs lost to scientific notation
    for row in rows:
        raw_fname = row.get(file_col, "")
        fname     = clean_filename(raw_fname)

        # The File name column is frequently destroyed by Excel (long numeric id
        # → "2.47E+17"). When it isn't a clean numeric id, recover the real
        # folder id from the image-path columns, which keep it intact.
        if not fname.isdigit():
            rec = recover_id_from_paths(*(row.get(pc, "") for pc in path_cols))
            if rec:
                fname = rec
                recovered += 1

        ticket  = (row.get(ticket_col) or "").strip()
        orderid, was_corrupt = clean_order_id(row.get(order_col, ""))
        if was_corrupt:
            corrupt_orders += 1
        added   = (row.get(added_col)  or "").strip()
        branch  = (row.get(branch_col) or "").strip()
        if not fname:
            skipped += 1
            continue
        lookup[fname] = {
            "ticket_id": ticket,
            "csv_order_id": orderid,
            "added_time": added,
            "branch": branch,
        }

    print(f"  [CSV] Valid file name rows : {len(lookup)}")
    if recovered:
        print(f"  [CSV] File names recovered from image path (Excel corruption): {recovered}")
    if corrupt_orders:
        print(f"  [CSV] WARNING: Order IDs lost to Excel scientific-notation: {corrupt_orders}")
        print( "        -> stored blank (shown as 'Un-Verified'). To fix, re-export the")
        print( "           CSV from Zoho Forms WITHOUT opening/saving it in Excel.")
    if skipped:
        print(f"  [CSV] Rows skipped (empty file name): {skipped}")

    # ── 2. Connect to DB ───────────────────────────────────────
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"\n  Database not found:\n  {db_path}\n"
            f"  Run pipeline.py first to create the database.\n"
        )

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")

    # ── 3. Add columns if missing ──────────────────────────────
    add_columns_if_missing(conn)

    # ── 4. Match and update ────────────────────────────────────
    matched    = 0
    not_found  = 0
    not_in_db  = []

    for fname, data in lookup.items():
        # Check if this file_name exists in DB
        row = conn.execute(
            "SELECT sno FROM zoho_records WHERE file_name = ?", (fname,)
        ).fetchone()

        if row:
            conn.execute(
                """UPDATE zoho_records
                   SET ticket_id    = :ticket_id,
                       csv_order_id = :csv_order_id,
                       added_time   = :added_time,
                       branch       = :branch
                   WHERE file_name  = :file_name""",
                {**data, "file_name": fname}
            )
            matched += 1
        else:
            not_found += 1
            not_in_db.append(fname)

    conn.commit()

    # ── 5. Reorder columns in display view ────────────────────
    # SQLite doesn't support column reordering in the real table,
    # but we create a VIEW that shows them in the right order.
    conn.execute("DROP VIEW IF EXISTS zoho_view")
    conn.execute("""
        CREATE VIEW zoho_view AS
        SELECT
            sno,
            added_time,
            branch,
            ticket_id,
            csv_order_id,
            file_name,
            image1_path,
            image2_path,
            file_order_id,
            file_star,
            remarks_file_order_id,
            remarks_file_star,
            flag,
            ocr_engine_order,
            ocr_engine_star,
            processed_at,
            raw_ocr_image1,
            raw_ocr_image2
        FROM zoho_records
        ORDER BY sno
    """)
    conn.commit()
    conn.close()

    # ── 6. Summary ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  DONE")
    print("=" * 60)
    print(f"  Matched + updated  : {matched}")
    print(f"  In CSV, not in DB  : {not_found}")
    print(f"  Database           : {db_path}")
    print()
    print("  Open DB Browser -> Browse Data -> select 'zoho_view'")
    print("  to see sno | Ticket ID | Order ID | file_name | ...")
    print("=" * 60)

    if not_in_db:
        print(f"\n  File names in CSV but not found in DB ({len(not_in_db)}):")
        for f in not_in_db[:20]:
            print(f"    {f}")
        if len(not_in_db) > 20:
            print(f"    ... and {len(not_in_db) - 20} more")
    print()


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"\n  ERROR: {e}\n")
