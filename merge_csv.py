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
from pathlib import Path

from config import DB_PATH as CONFIG_DB_PATH
from config import ZOHO_CSV_PATH as CONFIG_CSV_PATH

# ── CONFIG — only edit these two lines if paths change ────────
CSV_PATH = os.environ.get("ZOHOPIPE_ZOHO_CSV_PATH") or str(CONFIG_CSV_PATH)
DB_PATH = os.environ.get("ZOHOPIPE_DB_PATH") or str(CONFIG_DB_PATH)
# ──────────────────────────────────────────────────────────────


def clean_filename(raw: str) -> str:
    """
    Remove leading apostrophe, quotes, spaces from File name.
    "'246572000000016066" → "246572000000016066"
    """
    if not raw:
        return ""
    return raw.strip().lstrip("'\"` ").strip()


def add_columns_if_missing(conn: sqlite3.Connection):
    """Add Ticket_ID and Order_ID columns to zoho_records if not there."""
    existing = [row[1] for row in conn.execute("PRAGMA table_info(zoho_records)")]
    if "ticket_id" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN ticket_id TEXT")
        print("  [DB] Added column: ticket_id")
    if "csv_order_id" not in existing:
        conn.execute("ALTER TABLE zoho_records ADD COLUMN csv_order_id TEXT")
        print("  [DB] Added column: csv_order_id")
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
    Find the actual column names for File name, Ticket ID, Order ID.
    Case-insensitive, handles slight name variations.
    Returns (file_col, ticket_col, order_col).
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

    missing = []
    if not file_col:   missing.append("'File name'")
    if not ticket_col: missing.append("'Ticket ID'")
    if not order_col:  missing.append("'Order ID'")

    if missing:
        raise ValueError(
            f"\n  Could not find columns: {', '.join(missing)}\n"
            f"  Available columns: {headers}\n"
            f"  Check the CSV column names and update find() keywords if needed.\n"
        )

    print(f"  [CSV] Mapped  →  file='{file_col}'  "
          f"ticket='{ticket_col}'  order='{order_col}'")
    return file_col, ticket_col, order_col


def run(csv_path: str | None = None, db_path: str | None = None):
    print()
    print("=" * 60)
    print("  CSV → SQLite Merge")
    print("=" * 60)

    # ── 1. Read CSV ────────────────────────────────────────────
    csv_path = csv_path or CSV_PATH
    db_path = db_path or DB_PATH

    rows = read_csv(csv_path)
    file_col, ticket_col, order_col = find_columns(rows)

    # Build lookup dict:  clean_filename → {ticket_id, csv_order_id}
    lookup = {}
    skipped = 0
    for row in rows:
        fname   = clean_filename(row.get(file_col, ""))
        ticket  = (row.get(ticket_col) or "").strip()
        orderid = (row.get(order_col)  or "").strip()
        if not fname:
            skipped += 1
            continue
        lookup[fname] = {"ticket_id": ticket, "csv_order_id": orderid}

    print(f"  [CSV] Valid file name rows : {len(lookup)}")
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
                       csv_order_id = :csv_order_id
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
    print("  Open DB Browser → Browse Data → select 'zoho_view'")
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
