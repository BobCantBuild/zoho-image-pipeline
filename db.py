# =============================================================
#  db.py  —  SQLite helpers
# =============================================================
import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS zoho_records (
    sno                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id              TEXT,
    csv_order_id           TEXT,
    added_time             TEXT,
    branch                 TEXT,
    file_name              TEXT    NOT NULL UNIQUE,
    image1_path            TEXT,
    image2_path            TEXT,
    file_order_id          TEXT,
    service_rating         REAL,
    product_rating         REAL,
    file_star              REAL,
    remarks_file_order_id  TEXT,
    remarks_file_star      TEXT,
    flag                   TEXT,
    ocr_engine_order       TEXT,
    ocr_engine_star        TEXT,
    processed_at           TEXT DEFAULT (datetime('now')),
    raw_ocr_image1         TEXT,
    raw_ocr_image2         TEXT
);
CREATE INDEX IF NOT EXISTS ix_fname ON zoho_records(file_name);
CREATE INDEX IF NOT EXISTS ix_flag  ON zoho_records(flag);
"""

# New columns added after initial release — migrate existing DBs gracefully.
_NEW_COLUMNS = [
    ("service_rating", "REAL"),
    ("product_rating", "REAL"),
    ("order_id_match",     "TEXT"),
    ("service_rating_ge4", "TEXT"),
    ("product_rating_ge4", "TEXT"),
    ("verified",           "TEXT"),
    ("sheet_row",          "INTEGER"),  # original row position in Google Sheet (for sort order)
    ("web_order_id",       "TEXT"),     # from BSE API (amazon/flipkart order ID)
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _migrate_db(conn: sqlite3.Connection):
    """Add any columns introduced after initial schema creation."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(zoho_records)").fetchall()}
    for col_name, col_type in _NEW_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE zoho_records ADD COLUMN {col_name} {col_type}")
            logger.info("DB migration: added column %s %s", col_name, col_type)
    conn.commit()


def init_db():
    with get_conn() as c:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                c.execute(stmt)
        c.commit()
        _migrate_db(c)
    logger.info("DB ready at %s", DB_PATH)


def upsert_record(rec: dict):
    fields     = [k for k in rec if k != "file_name"]
    set_clause = ", ".join(f"{f} = :{f}" for f in fields)
    sql = f"""
        INSERT INTO zoho_records (file_name, {', '.join(fields)})
        VALUES (:file_name, {', '.join(':' + f for f in fields)})
        ON CONFLICT(file_name) DO UPDATE SET
            {set_clause},
            processed_at = datetime('now');
    """
    with get_conn() as c:
        c.execute(sql, rec)
        c.commit()


def fetch_ok_names(retry_failed: bool = False) -> set:
    """Names of rows that don't need (re)processing on the next run.

    By default, any row that has already been attempted (flag set, not
    PENDING/ERROR) counts as done — OCR misses (NO_ORDER_ID / NO_STAR) are
    NOT retried automatically on every -resume. Pass retry_failed=True
    (pipeline.py --retry-failed) to also re-attempt those rows.
    """
    with get_conn() as c:
        rows = c.execute(
            "SELECT file_name, flag FROM zoho_records WHERE flag NOT IN ('PENDING','ERROR')"
        ).fetchall()
    if retry_failed:
        return {
            r["file_name"] for r in rows
            if "NO_ORDER_ID" not in (r["flag"] or "") and "NO_STAR" not in (r["flag"] or "")
        }
    return {r["file_name"] for r in rows}


def get_stats() -> dict:
    with get_conn() as c:
        q = lambda sql: c.execute(sql).fetchone()[0]
        return {
            "total":            q("SELECT COUNT(*) FROM zoho_records"),
            "OK":               q("SELECT COUNT(*) FROM zoho_records WHERE flag='OK'"),
            "low_conf_order":   q("SELECT COUNT(*) FROM zoho_records WHERE flag LIKE '%LOW_CONF%'"),
            "missing_order_id": q("SELECT COUNT(*) FROM zoho_records WHERE file_order_id IS NULL"),
            "missing_star":     q("SELECT COUNT(*) FROM zoho_records WHERE file_star IS NULL"),
            "errors":           q("SELECT COUNT(*) FROM zoho_records WHERE flag='ERROR'"),
        }
