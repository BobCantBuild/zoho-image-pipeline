# =============================================================
#  bse_api.py  —  BSE API client for Web Order ID lookup
# =============================================================
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

_AUTH_URL   = "https://bseapi.ifbsupport.com/api/Auth/login"
_ORDER_URL  = "https://bseapi.ifbsupport.com/api/ZohoPipeline/GetAmazonFlipkartOrderIddetails"
_CREDS      = {"userName": "IFBFollowUPAPP", "password": "U29tZVJhbmRvbUJhc2U2NA=="}

_token: str | None = None
_token_expiry: float = 0.0
_token_lock = threading.Lock()


def _get_token() -> str:
    """Get a valid bearer token, refreshing if expired."""
    global _token, _token_expiry
    with _token_lock:
        if _token and time.time() < _token_expiry - 60:
            return _token
        resp = requests.post(_AUTH_URL, json=_CREDS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _token = data["token"]
        _token_expiry = time.time() + 3500
        return _token


def fetch_web_order_id(ticket_id: str) -> str | None:
    """Fetch the web order ID for a single ticket from the BSE API.

    Returns amazonOrderID if non-empty, else orderid, else None.
    """
    if not requests or not ticket_id or not str(ticket_id).strip():
        return None
    tid = str(ticket_id).strip()
    try:
        token = _get_token()
        resp = requests.get(
            _ORDER_URL,
            params={"TicketNo": tid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 401:
            global _token_expiry
            _token_expiry = 0.0
            token = _get_token()
            resp = requests.get(
                _ORDER_URL,
                params={"TicketNo": tid},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            return None
        item = items[0] if isinstance(items, list) else items
        amazon_oid = (item.get("amazonOrderID") or "").strip()
        if amazon_oid:
            return amazon_oid
        order_id = (item.get("orderid") or "").strip()
        return order_id if order_id else None
    except Exception as e:
        logger.warning("BSE API error for ticket %s: %s", tid, e)
        return None


def fetch_web_order_ids_batch(ticket_ids: list[str], max_workers: int = 8) -> dict[str, str | None]:
    """Fetch web order IDs for multiple tickets in parallel.

    Returns {ticket_id: web_order_id} dict.
    """
    results: dict[str, str | None] = {}
    if not requests or not ticket_ids:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_web_order_id, tid): tid for tid in ticket_ids}
        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                results[tid] = fut.result()
            except Exception:
                results[tid] = None
    return results
