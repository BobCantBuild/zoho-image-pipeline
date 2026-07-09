# =============================================================
#  flags.py  —  Computed verification columns (stored in SQLite)
#
#  Same logic as the dashboard's compute_flags, but persisted:
#    Order ID Match      : OCR "Zoho Order ID" vs sheet "Order ID"
#    SERVICE RATING >=4  : YES / NO / Un-Verified
#    PRODUCT RATING >=4  : YES / NO / Un-Verified
#    ✦ Verified          : YES / NO / Un-Verified
# =============================================================
import re

_PLACEHOLDERS = {"", "none", "nan", "—", "null"}


def _blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:      # NaN — bool(nan) is True, never trust truthiness
        return True
    return str(v).strip().lower() in _PLACEHOLDERS


def _norm_oid(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if not _blank(s) else ""


def _ge4_flag(rating) -> str:
    if _blank(rating):
        return "Un-Verified"
    return "YES" if float(rating) >= 4 else "NO"


def compute_flags(rec: dict) -> dict:
    """Return the four computed columns for a record dict that carries
    file_order_id, csv_order_id, service_rating, product_rating, file_star."""
    ocr_oid   = rec.get("file_order_id")
    sheet_oid = rec.get("csv_order_id")

    if _blank(ocr_oid) or _blank(sheet_oid):
        match = "Un-Verified"
    elif _norm_oid(ocr_oid) == _norm_oid(sheet_oid):
        match = "YES"
    else:
        match = "NO"

    svc  = rec.get("service_rating")
    prod = rec.get("product_rating")
    gen  = rec.get("file_star")

    # Star flag: first populated category wins (service → product → general)
    star = next((v for v in (svc, prod, gen) if not _blank(v)), None)
    star_flag = _ge4_flag(star)

    if match == "YES" and star_flag == "YES":
        verified = "YES"
    elif match == "NO" or star_flag == "NO":
        verified = "NO"
    else:
        verified = "Un-Verified"

    return {
        "order_id_match":      match,
        "service_rating_ge4":  _ge4_flag(svc),
        "product_rating_ge4":  _ge4_flag(prod),
        "verified":            verified,
    }
