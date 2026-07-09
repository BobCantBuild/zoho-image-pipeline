# =============================================================
#  sheet_source.py  —  Google Sheet → rows → local Drive images
#
#  Replaces the old CSV+folder-scan input:
#    - fetch_rows()             pulls the sheet (as CSV) and normalizes columns
#    - ensure_row_images(row)   downloads the two Drive images to IMAGE_CACHE_DIR
#
#  The sheet layout is fixed:
#    Added Time | IP Address | Branch | Ticket ID | Order ID
#    | <image1 URL — order screen>   | <image2 URL — rating & review>
# =============================================================
import csv
import io
import re
import urllib.request
from pathlib import Path
from typing import Optional

from config import SHEET_CSV_URL, IMAGE_CACHE_DIR

_DRIVE_ID_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")
_UA = "Mozilla/5.0 (zoho-image-pipeline)"


# ── SHEET FETCH ───────────────────────────────────────────────

def fetch_sheet_csv(url: str = SHEET_CSV_URL, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")


def _pick_col(headers: list[str], *needles: str) -> Optional[str]:
    for h in headers:
        hl = (h or "").lower()
        if all(n in hl for n in needles):
            return h
    return None


def parse_rows(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []

    c_added   = _pick_col(headers, "added", "time")
    c_branch  = _pick_col(headers, "branch")
    c_ticket  = _pick_col(headers, "ticket")
    c_order   = _pick_col(headers, "order", "id")
    c_image1  = _pick_col(headers, "order", "screen")            # "…order screen on the customer's phone."
    c_image2  = _pick_col(headers, "rating", "review")           # "…rating and review screen…"

    missing = [name for name, col in [
        ("Added Time", c_added), ("Branch", c_branch), ("Ticket ID", c_ticket),
        ("Order ID", c_order), ("Image1 URL", c_image1), ("Image2 URL", c_image2),
    ] if not col]
    if missing:
        raise ValueError(f"Sheet is missing expected columns: {missing}. Got: {headers}")

    out: list[dict] = []
    for r in reader:
        ticket = (r.get(c_ticket) or "").strip()
        if not ticket:
            continue
        out.append({
            "ticket_id":  ticket,
            "order_id":   (r.get(c_order)  or "").strip(),
            "added_time": (r.get(c_added)  or "").strip(),
            "branch":     (r.get(c_branch) or "").strip(),
            "image1_url": (r.get(c_image1) or "").strip(),
            "image2_url": (r.get(c_image2) or "").strip(),
        })
    return out


def fetch_rows() -> list[dict]:
    return parse_rows(fetch_sheet_csv())


# ── DRIVE IMAGE DOWNLOAD ──────────────────────────────────────

def _drive_id(url: str) -> str:
    m = _DRIVE_ID_RE.search(url or "")
    return m.group(1) if m else ""


def _download(url: str, dest: Path, timeout: int = 60) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except Exception:
        return False
    if not data or data[:15].lower().startswith((b"<!doctype", b"<html")):
        # Drive returned an interstitial (large-file confirm page or 403 page).
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def ensure_image(url: str, dest: Path) -> Optional[Path]:
    """Download the Drive-hosted image to `dest` if not already cached."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    fid = _drive_id(url)
    if not fid:
        return None
    if _download(f"https://drive.google.com/uc?export=download&id={fid}", dest):
        return dest
    return None


def ensure_row_images(row: dict, cache_dir: Path | str = IMAGE_CACHE_DIR) -> tuple[Optional[str], Optional[str]]:
    """Ensure image1 & image2 for this row are on disk. Return (image1_path, image2_path)."""
    folder = Path(cache_dir) / row["ticket_id"]
    p1 = ensure_image(row.get("image1_url", ""), folder / "image1.jpg")
    p2 = ensure_image(row.get("image2_url", ""), folder / "image2.jpg")
    return (str(p1) if p1 else None, str(p2) if p2 else None)
