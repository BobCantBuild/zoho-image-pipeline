# =============================================================
#  dashboard.py  —  Zoho Pipeline Dashboard
#
#  LOCAL:   streamlit run dashboard.py
#  PUBLIC:  Deploy to share.streamlit.io → permanent link
#
#  Data source:
#    - If running locally  → reads from SQLite DB directly
#    - If running on cloud → reads from data/zoho_latest.csv
#      (auto-updated by pipeline.py via sync_to_github.py)
#
#  Zero manual work. Pipeline finishes → data auto-appears.
# =============================================================

import sqlite3, time, re, os
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Zoho Review Pipeline",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Paths ─────────────────────────────────────────────────────
# Check if on cloud (file doesn't exist), use CSV
DB_PATH  = Path(r"C:\myfiles\IFB\Project\IT\Zoho-Forms\zoho_pipeline.db") if os.name == 'nt' else Path("zoho_pipeline.db")
CSV_PATH = Path(__file__).parent / "data" / "zoho_latest.csv"

# =============================================================
#  CSS
# =============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family:'Inter',sans-serif !important; }
#MainMenu, footer, header  { visibility:hidden; }
.block-container { padding:2.2rem 2.8rem 3rem !important; max-width:100% !important; }
div[data-testid="stStatusWidget"] { display:none !important; }

/* Top bar */
.topbar {
  display:flex; align-items:center; justify-content:space-between;
  background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);
  border-radius:16px; padding:24px 30px; margin-bottom:28px;
}
.topbar-title { font-size:30px; font-weight:800; color:#ffffff; line-height:1.15; }
.topbar-sub   { font-size:16px; color:#93c5fd; margin-top:5px; }
.topbar-badge {
  background:rgba(255,255,255,.18); border-radius:8px;
  padding:6px 14px; font-size:14px; color:#e0f2fe;
  margin-top:10px; display:inline-block; font-weight:600;
}
.topbar-time { font-size:15px; color:#bfdbfe; text-align:right; }
.topbar-tval { font-size:20px; font-weight:700; color:#fff; margin-bottom:4px; }

/* ── Metric Grid ─────────────────────────────────────────── */
.mg-row   { display:flex; gap:12px; margin-bottom:22px; align-items:stretch; }
.mg-card  { background:#fff; border:2px solid #e2e8f0; border-radius:14px;
            padding:16px 18px; box-shadow:0 2px 8px rgba(0,0,0,.05);
            display:flex; flex-direction:column; justify-content:center; }

/* Slim: just a big number + label */
.mg-slim  { flex:0 0 130px; text-align:center; }
.mg-title { font-size:11px; font-weight:700; color:#64748b;
            text-transform:uppercase; letter-spacing:.08em; margin-bottom:6px; }
.mg-bignum{ font-size:36px; font-weight:800; line-height:1; }
.mg-hint  { font-size:11px; color:#94a3b8; margin-top:6px; font-weight:500; }

/* Wide: title + three equal sub-cells */
.mg-wide  { flex:1; min-width:0; }
.mg-trio  { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:10px; }
.mg-trio-cell {
  border:1.5px solid #e2e8f0; border-radius:10px;
  padding:10px 8px; text-align:center; background:#f8fafc;
}
.mg-trio-n { font-size:26px; font-weight:800; line-height:1; }
.mg-trio-l { font-size:11px; font-weight:600; color:#64748b;
             margin-top:5px; letter-spacing:.03em; }

/* Colour helpers */
.c-dark   { color:#0f172a; } .c-green  { color:#16a34a; } .c-red    { color:#dc2626; }
.c-orange { color:#d97706; } .c-amber  { color:#d97706; } .c-gray   { color:#64748b; }

/* Progress */
.prog-wrap  { margin:4px 0 24px; }
.prog-title { font-size:16px; font-weight:700; color:#1e293b; margin-bottom:8px; }
.prog-track { background:#e2e8f0; border-radius:99px; height:12px; overflow:hidden; }
.prog-fill  { height:100%; border-radius:99px;
              background:linear-gradient(90deg,#3b82f6,#6366f1); }
.prog-sub   { font-size:14px; color:#64748b; margin-top:6px; }

/* Section heading */
.sec-head {
  font-size:17px; font-weight:800; color:#0f172a;
  border-left:5px solid #6366f1; padding-left:13px;
  margin:16px 0 12px; letter-spacing:-.01em;
}

/* Filter labels */
.filter-label {
  font-size:11px; font-weight:700; color:#475569;
  text-transform:uppercase; letter-spacing:.07em; margin-bottom:3px;
}

/* Uniform control row sizing — compact */
div[data-baseweb="select"] > div { min-height:36px !important; font-size:13px !important; }
div[data-baseweb="select"] span  { font-size:13px !important; }
div[data-baseweb="input"] > div  { min-height:36px !important; font-size:13px !important; }
div[data-testid="stDateInput"] div[data-baseweb="input"] { min-height:36px !important; }
/* From / To date labels — keep them small and tight */
div[data-testid="stDateInput"] label { font-size:11px !important; color:#64748b !important;
  font-weight:600 !important; margin-bottom:2px !important; }
div[data-testid="stDownloadButton"] button,
div[data-testid="stButton"] button {
  height:36px !important;
  padding:0 12px !important;
  border-radius:8px !important;
  font-size:13px !important;
  display:flex !important;
  align-items:center !important;
  justify-content:center !important;
  white-space:nowrap !important;
}

/* Clear (X) buttons */
button[kind="secondary"] { padding:0 !important; }
button[kind="secondary"] span { font-size:14px !important; line-height:1 !important; }

/* Table */
.ztable { width:100%; border-collapse:collapse; table-layout:auto; }
.ztable thead tr { background:#f1f5f9; }
.ztable thead th {
  padding:9px 10px; text-align:left; font-size:11px;
  font-weight:700; color:#334155; text-transform:uppercase;
  letter-spacing:.05em; white-space:nowrap;
  border-bottom:2px solid #e2e8f0;
}
.ztable tbody tr { border-bottom:1px solid #f1f5f9; }
.ztable tbody tr:hover { background:#f8fafc; }
.ztable td { padding:8px 10px; font-size:13px; color:#1e293b;
             vertical-align:middle; white-space:nowrap; }
.ztable td.mono { font-family:monospace; font-size:12px; }
.ztable td.ctr  { text-align:center; }
.ztable td.num  { text-align:center; color:#94a3b8; font-size:12px; }

/* Badges */
.badge { display:inline-block; padding:3px 10px; border-radius:99px;
         font-size:12px; font-weight:700; letter-spacing:.02em; }
.b-yes { background:#dcfce7; color:#15803d; }
.b-no  { background:#fee2e2; color:#b91c1c; }
.b-und { background:#f1f5f9; color:#64748b; }

/* Search input — target both the BaseUI wrapper AND the raw input */
div[data-testid="stTextInput"] { width:100% !important; margin-bottom:0 !important; padding-bottom:0 !important; }
div[data-testid="stTextInput"] > div { width:100% !important; margin-bottom:0 !important; }
/* BaseUI wrapper — this is what actually paints the visible border */
div[data-testid="stTextInput"] div[data-baseweb="input"] {
  border:2px solid #94a3b8 !important;
  border-top:2px solid #94a3b8 !important;
  border-bottom:2px solid #94a3b8 !important;
  border-radius:10px !important;
  box-shadow:0 1px 3px rgba(0,0,0,.06) !important;
  min-height:42px !important;
}
div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
  border-color:#6366f1 !important;
  box-shadow:0 0 0 3px rgba(99,102,241,.12) !important;
}
div[data-testid="stTextInput"] input {
  font-size:14px !important; background:transparent !important;
  border:none !important; padding:10px 16px !important;
  width:100% !important; box-sizing:border-box !important;
  outline:none !important;
}
div[data-testid="stTextInput"] input::placeholder { font-size:14px !important; color:#94a3b8 !important; }
div[data-testid="stTextInput"] + div[data-testid="stVerticalBlock"] { margin-top:0 !important; }
div[data-testid="stSelectbox"] > div > div {
  font-size:15px !important; border-radius:10px !important;
}
div[data-testid="stDownloadButton"] button,
div[data-testid="stButton"] button {
  font-size:15px !important; font-weight:700 !important;
  border-radius:10px !important; padding:10px 22px !important;
}
.pag-info { font-size:15px; color:#64748b; padding-top:10px; }
.source-pill {
  display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0;
  border-radius:8px; padding:4px 12px; font-size:13px; color:#475569;
  font-weight:600; margin-bottom:20px;
}
.footer { text-align:center; font-size:13px; color:#cbd5e1; margin-top:30px; }
</style>
""", unsafe_allow_html=True)


# =============================================================
#  HELPERS
# =============================================================

def normalise_oid(raw: str) -> str:
    if not raw: return ""
    s = str(raw).strip().lstrip("#").strip()
    s = re.sub(r"\s+", "", s).upper()
    s = re.sub(r"^0D", "OD", s)
    return s

def badge(val):
    if val == "YES":          return '<span class="badge b-yes">✓ YES</span>'
    if val == "NO":           return '<span class="badge b-no">✕ NO</span>'
    if val == "Un-Verified":  return '<span class="badge b-und">Un-Verified</span>'
    return f'<span class="badge">{val}</span>'

def star_html(val):
    try:
        n = float(val)
        s = "★" * int(n) + "☆" * (5 - int(n))
        c = "#f59e0b" if n >= 4 else "#94a3b8"
        return (f'<span style="color:{c};font-size:19px">{s}</span>'
                f'<span style="color:#64748b;font-size:14px;margin-left:7px">{n:.1f}</span>')
    except:
        return '<span style="color:#cbd5e1;font-size:15px">—</span>'

def safe(val):
    v = str(val or "").strip()
    return '<span style="color:#cbd5e1">—</span>' if v in ("","None","nan","NaN") else v

def flag_cell(val):
    if val == "YES":       bg = "#dcfce7"
    elif val == "NO":      bg = "#fee2e2"
    else:                  bg = "#f1f5f9"
    return f'<td class="ctr" style="background:{bg}">{badge(val)}</td>'

def _is_blank(val) -> bool:
    """True for None, NaN (float), or empty/placeholder strings.
    Handles the pandas NaN-as-float case where bool(nan) is True."""
    if val is None:
        return True
    if isinstance(val, float):
        return pd.isna(val)          # catches float('nan')
    return str(val).strip() in ("", "None", "nan", "NaN", "—")


def compute_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add Order_ID_Flag, file_star_flag, Flag columns."""
    df["Zoho_order_ID"] = df.get("Zoho_order_ID",
                          df.get("csv_order_id", pd.Series([""] * len(df)))).fillna("")

    def order_flag(r):
        raw_f = r.get("file_order_id", None)
        if _is_blank(raw_f):
            return "Un-Verified"   # File Order ID not extracted — cannot determine match
        f = normalise_oid(str(raw_f))
        if not f:
            return "Un-Verified"
        z = normalise_oid(r.get("Zoho_order_ID", ""))
        if not z:
            return "Un-Verified"   # Zoho Order ID missing
        return "YES" if z == f else "NO"

    def star_flag(r):
        val = r.get("file_star", None)
        if _is_blank(val):
            return "Un-Verified"   # Star rating not extracted from image
        try:    return "YES" if float(val) >= 4 else "NO"
        except: return "Un-Verified"

    def verified_flag(r):
        oid  = r["Order_ID_Flag"]
        star = r["file_star_flag"]
        if oid == "YES" and star == "YES":
            return "YES"
        if oid == "NO" or star == "NO":
            return "NO"
        return "Un-Verified"   # Either or both are Un-Verified, none is NO

    df["Order_ID_Flag"]  = df.apply(order_flag,     axis=1)
    df["file_star_flag"] = df.apply(star_flag,       axis=1)
    df["Flag"]           = df.apply(verified_flag,   axis=1)
    return df


def add_posting_date(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise `added_time` into a sortable date column for calendar-like filtering."""
    if "added_time" not in df.columns:
        df["added_time"] = ""
    dt = pd.to_datetime(df["added_time"], errors="coerce", utc=False)
    df["date_of_posting"] = dt.dt.date
    df["date_of_posting_str"] = dt.dt.strftime("%d %b %Y")
    return df


# =============================================================
#  DATA SOURCE  — SQLite locally, CSV on cloud
# =============================================================

@st.cache_data(ttl=8)
def load_data(db_mtime: float, csv_mtime: float) -> tuple:
    """Returns (dataframe, source_label, stats_dict).

    Cache key includes both file mtimes — any write to the DB or CSV
    immediately produces a different key, bypassing the stale cache entry.
    ttl=8 is a safety net; mtime invalidation is the primary mechanism.
    """
    # ── Try SQLite first (local machine) ──────────────────────
    if Path(DB_PATH).exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("""
                SELECT sno, added_time, branch, ticket_id,
                       csv_order_id AS Zoho_order_ID,
                       file_order_id, file_star, file_name,
                       flag AS pipeline_flag,
                       remarks_file_order_id, remarks_file_star
                FROM zoho_records ORDER BY sno
            """, conn)

            q = lambda s: conn.execute(s).fetchone()[0]
            stats = {
                "total":        q("SELECT COUNT(*) FROM zoho_records"),
                "pending":      q("SELECT COUNT(*) FROM zoho_records WHERE flag='PENDING'"),
                "ok":           q("SELECT COUNT(*) FROM zoho_records WHERE flag='OK'"),
                "orders_found": q("SELECT COUNT(*) FROM zoho_records WHERE file_order_id IS NOT NULL AND flag!='PENDING'"),
                "stars_found":  q("SELECT COUNT(*) FROM zoho_records WHERE file_star  IS NOT NULL AND flag!='PENDING'"),
            }
            conn.close()

            if not df.empty:
                df = compute_flags(df)
                df = add_posting_date(df)
                return df, "🖥️  Live — SQLite database", stats
        except Exception:
            pass   # fall through to CSV

    # ── Fallback: CSV from repo (cloud / shared access) ───────
    if CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", dtype=str)
        pf = df.get("pipeline_flag", pd.Series(dtype=str))
        stats = {
            "total":        len(df),
            "pending":      int((pf == "PENDING").sum()),
            "ok":           int((pf == "OK").sum()),
            "orders_found": int(df["file_order_id"].notna().sum() if "file_order_id" in df else 0),
            "stars_found":  int(df["file_star"].notna().sum()     if "file_star"     in df else 0),
        }
        if not df.empty:
            df = compute_flags(df)
            df = add_posting_date(df)
            mtime_str = time.strftime("%d %b %Y  %H:%M", time.localtime(CSV_PATH.stat().st_mtime))
            return df, f"☁️  Cloud — GitHub CSV (updated {mtime_str})", stats

    return pd.DataFrame(), "⚠️  No data source found", {}


# =============================================================
#  LOAD  — pass current file mtimes as cache-key arguments
# =============================================================

def _file_mtime(p: Path) -> float:
    """Return file modification time in seconds, or 0 if file absent."""
    try:
        return p.stat().st_mtime if p.exists() else 0.0
    except Exception:
        return 0.0

_db_mtime  = _file_mtime(DB_PATH)
_csv_mtime = _file_mtime(CSV_PATH)
df, source_label, stats = load_data(db_mtime=_db_mtime, csv_mtime=_csv_mtime)

total   = max(stats.get("total",   1), 1)
pending = stats.get("pending", 0)
done    = total - pending
pct     = done / total * 100
now_str = time.strftime("%d %b %Y  %H:%M")


# =============================================================
#  TOP BAR
# =============================================================

st.markdown(f"""
<div class="topbar">
  <div style="display:flex;align-items:center;gap:16px">
    <span style="font-size:42px">📦</span>
    <div>
      <div class="topbar-title">Zoho Review Pipeline</div>
      <div class="topbar-sub">Image Processing &amp; Order Verification Dashboard</div>
      <div class="topbar-badge">
        {"⚡ Pipeline running — auto-refreshing every 10 s"
         if pending > 0 else "✅ Pipeline complete — all records processed"}
      </div>
    </div>
  </div>
  <div class="topbar-time">
    <div class="topbar-tval">{now_str}</div>
    <div>Last refreshed</div>
    <div style="margin-top:10px;font-size:13px;color:#93c5fd">{source_label}</div>
  </div>
</div>""", unsafe_allow_html=True)


# =============================================================
#  METRIC GRID  (new architecture)
# =============================================================

# ── Derived counts from computed df ──────────────────────────
if not df.empty:
    _f  = df["Flag"].fillna("")
    _oi = df["Order_ID_Flag"].fillna("")
    _sf = df["file_star_flag"].fillna("")
    oid_yes  = int((_oi == "YES").sum())
    oid_no   = int((_oi == "NO").sum())
    oid_unv  = int((_oi == "Un-Verified").sum())
    star_yes = int((_sf == "YES").sum())
    star_no  = int((_sf == "NO").sum())
    star_unv = int((_sf == "Un-Verified").sum())
    v_yes    = int((_f  == "YES").sum())
    v_no     = int((_f  == "NO").sum())
    v_unv    = int((_f  == "Un-Verified").sum())
else:
    oid_yes = oid_no = oid_unv = 0
    star_yes = star_no = star_unv = 0
    v_yes = v_no = v_unv = 0

# ── Folder count (filesystem or fallback to DB total) ─────────
try:
    from config import BASE_DIR as _BD
    _bp = Path(str(_BD))
    folder_count = sum(1 for e in _bp.iterdir() if e.is_dir()) if _bp.exists() else stats.get("total", 0)
except Exception:
    folder_count = stats.get("total", 0)

_pend = stats.get("pending", 0)
_done = folder_count - _pend

st.markdown(f"""
<div class="mg-row">

  <!-- 1 · In Pipeline -->
  <div class="mg-card mg-slim">
    <div class="mg-title">In Pipeline</div>
    <div class="mg-bignum c-dark">{folder_count:,}</div>
    <div class="mg-hint">Total records</div>
  </div>

  <!-- 2 · Pending -->
  <div class="mg-card mg-slim">
    <div class="mg-title">Pending</div>
    <div class="mg-bignum c-orange">{_pend:,}</div>
    <div class="mg-hint">Awaiting processing</div>
  </div>

  <!-- 3 · Order ID Match breakdown -->
  <div class="mg-card mg-wide">
    <div class="mg-title">Order ID Match</div>
    <div class="mg-trio">
      <div class="mg-trio-cell" style="border-color:#bbf7d0;background:#f0fdf4;">
        <div class="mg-trio-n c-green">{oid_yes:,}</div>
        <div class="mg-trio-l">✓ Match</div>
      </div>
      <div class="mg-trio-cell" style="border-color:#fecaca;background:#fff1f2;">
        <div class="mg-trio-n c-red">{oid_no:,}</div>
        <div class="mg-trio-l">✕ Mismatch</div>
      </div>
      <div class="mg-trio-cell">
        <div class="mg-trio-n c-gray">{oid_unv:,}</div>
        <div class="mg-trio-l">— Un-Verified</div>
      </div>
    </div>
  </div>

  <!-- 4 · Star Rating breakdown -->
  <div class="mg-card mg-wide">
    <div class="mg-title">Star Rating</div>
    <div class="mg-trio">
      <div class="mg-trio-cell" style="border-color:#fde68a;background:#fffbeb;">
        <div class="mg-trio-n c-amber">{star_yes:,}</div>
        <div class="mg-trio-l">★ ≥ 4</div>
      </div>
      <div class="mg-trio-cell">
        <div class="mg-trio-n c-gray">{star_no:,}</div>
        <div class="mg-trio-l">★ &lt; 4</div>
      </div>
      <div class="mg-trio-cell">
        <div class="mg-trio-n c-gray">{star_unv:,}</div>
        <div class="mg-trio-l">— Un-Verified</div>
      </div>
    </div>
  </div>

  <!-- 5 · Verified breakdown -->
  <div class="mg-card mg-wide" style="border-color:#e0e7ff;">
    <div class="mg-title">Verified</div>
    <div class="mg-trio">
      <div class="mg-trio-cell" style="border-color:#bbf7d0;background:#f0fdf4;">
        <div class="mg-trio-n c-green">{v_yes:,}</div>
        <div class="mg-trio-l">✓ YES</div>
      </div>
      <div class="mg-trio-cell" style="border-color:#fecaca;background:#fff1f2;">
        <div class="mg-trio-n c-red">{v_no:,}</div>
        <div class="mg-trio-l">✕ NO</div>
      </div>
      <div class="mg-trio-cell">
        <div class="mg-trio-n c-gray">{v_unv:,}</div>
        <div class="mg-trio-l">— Un-Verified</div>
      </div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)


# =============================================================
#  PROGRESS + REFRESH
# =============================================================

rc, pc2 = st.columns([1, 8])
with rc:
    if st.button("⟳ Refresh", use_container_width=True):
        st.cache_data.clear(); st.rerun()
with pc2:
    st.markdown(f"""
    <div class="prog-wrap">
      <div class="prog-title">Pipeline Progress &nbsp;
        <span style="font-weight:500;color:#64748b;font-size:15px">
          {done:,} of {total:,} records &nbsp;·&nbsp; {pct:.1f}% complete
        </span>
      </div>
      <div class="prog-track">
        <div class="prog-fill" style="width:{pct:.2f}%"></div>
      </div>
    </div>""", unsafe_allow_html=True)


# =============================================================
#  FILTERS
# =============================================================

st.markdown('<div class="sec-head">Records</div>', unsafe_allow_html=True)

st.text_input("", placeholder="🔍  Search by file name, Zoho order ID, file order ID or ticket ID…",
              label_visibility="collapsed", key="search_box")
search = st.session_state.get("search_box", "")

# ── Branch options ─────────────────────────────────────────────
if "branch" in df.columns:
    branches = sorted({(b or "").strip() for b in df["branch"].fillna("").tolist()} - {""})
else:
    branches = []

# ── Pagination callbacks (must be defined before buttons render) ─
def _prev_page():
    p = int(st.session_state.get("page", 1))
    if p > 1:
        st.session_state["page"] = p - 1

def _next_page():
    p   = int(st.session_state.get("page", 1))
    top = int(st.session_state.get("_total_pages", 1))
    if p < top:
        st.session_state["page"] = p + 1

# =============================================================
#  FILTER CONTAINER  — single-row, bordered box
# =============================================================

if df.empty:
    st.warning("⚠️  No data available. Run `pipeline.py` to process records.")
    st.stop()

with st.container(border=True):
    fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns(
        [1, 1, 1, 1, 1.7, 1.1, 0.8], vertical_alignment="bottom"
    )

    with fc1:
        st.markdown('<div class="filter-label">✦ Verified</div>', unsafe_allow_html=True)
        flag_filter = st.selectbox("", ["All","YES","NO","Un-Verified"],
                                   label_visibility="collapsed", key="ff1")
    with fc2:
        st.markdown('<div class="filter-label">🔗 Order ID Match</div>', unsafe_allow_html=True)
        order_filter = st.selectbox("", ["All","YES","NO","Un-Verified"],
                                    label_visibility="collapsed", key="ff2")
    with fc3:
        st.markdown('<div class="filter-label">⭐ Star Rating ≥ 4</div>', unsafe_allow_html=True)
        star_filter = st.selectbox("", ["All","YES","NO","Un-Verified"],
                                   label_visibility="collapsed", key="ff3")
    with fc4:
        st.markdown('<div class="filter-label">🏢 Branch</div>', unsafe_allow_html=True)
        branch_filter = st.selectbox("", ["All", *branches],
                                     label_visibility="collapsed", key="branch_filter")
    with fc5:
        st.markdown('<div class="filter-label">📅 Date of Posting</div>', unsafe_allow_html=True)
        date_range = st.date_input(
            "", value=[], format="DD/MM/YYYY",
            label_visibility="collapsed", key="date_range",
        )
    with fc6:
        st.markdown('<div class="filter-label">&nbsp;</div>', unsafe_allow_html=True)
        export_slot = st.empty()   # filled after filt is computed
    with fc7:
        st.markdown('<div class="filter-label">&nbsp;</div>', unsafe_allow_html=True)
        if st.button("✕ Clear", use_container_width=True):
            for k in ["search_box","ff1","ff2","ff3",
                      "branch_filter","date_range","page"]:
                if k in st.session_state: del st.session_state[k]
            st.cache_data.clear(); st.rerun()


# =============================================================
#  APPLY FILTERS
# =============================================================

PAGE_SIZE = 50

filt = df.copy()
if flag_filter  != "All": filt = filt[filt["Flag"]           == flag_filter]
if order_filter != "All": filt = filt[filt["Order_ID_Flag"]  == order_filter]
if star_filter  != "All": filt = filt[filt["file_star_flag"] == star_filter]
if "branch" in filt.columns and branch_filter != "All":
    filt = filt[filt["branch"].fillna("") == branch_filter]
if "date_of_posting" in filt.columns:
    _dr = date_range if isinstance(date_range, (list, tuple)) else []
    if len(_dr) == 2:
        _dp = pd.to_datetime(filt["date_of_posting"], errors="coerce").dt.date
        filt = filt[(_dp >= _dr[0]) & (_dp <= _dr[1])]
    elif len(_dr) == 1:
        _dp = pd.to_datetime(filt["date_of_posting"], errors="coerce").dt.date
        filt = filt[_dp >= _dr[0]]
if search:
    s = search.lower()
    filt = filt[
        filt["file_name"].fillna("").str.lower().str.contains(s)     |
        filt["file_order_id"].fillna("").str.lower().str.contains(s) |
        filt["Zoho_order_ID"].fillna("").str.lower().str.contains(s) |
        filt["ticket_id"].fillna("").str.lower().str.contains(s)
    ]

filt = filt.reset_index(drop=True)
total_pages = max(1, (len(filt) - 1) // PAGE_SIZE + 1)
st.session_state["_total_pages"] = total_pages   # used by _next_page callback

# ── Fill export button now that filt is ready ─────────────────
exp_cols = ["sno","date_of_posting_str","branch","ticket_id","Zoho_order_ID",
            "file_order_id","Order_ID_Flag","file_star","file_star_flag","file_name","Flag"]
exp_df = filt[[c for c in exp_cols if c in filt.columns]].copy()
exp_df.columns = ["#","Date of Posting","Branch","Ticket ID","Zoho Order ID",
                  "File Order ID","Order ID Match","Star Rating","Star ≥ 4",
                  "File Name","Verified"][: len(exp_df.columns)]
with export_slot:
    st.download_button("⬇️ Export to CSV",
                       data=exp_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="zoho_export.csv", mime="text/csv",
                       use_container_width=True)

st.markdown(f'<div class="pag-info"><b>{len(filt):,}</b> records found</div>',
            unsafe_allow_html=True)

# Page state driven by session_state (callbacks update it before table renders)
page = max(1, min(total_pages, int(st.session_state.get("page", 1))))
st.session_state["page"] = page


# =============================================================
#  TABLE
# =============================================================

start   = (page - 1) * PAGE_SIZE
page_df = filt.iloc[start: start + PAGE_SIZE]

rows_html = ""
for i, (_, row) in enumerate(page_df.iterrows(), start=start + 1):
    rows_html += f"""
    <tr>
      <td class="num">{i}</td>
      <td class="mono">{safe(row.get('date_of_posting_str',''))}</td>
      <td class="mono">{safe(row.get('branch',''))}</td>
      <td class="mono">{safe(row.get('ticket_id',''))}</td>
      <td class="mono">{safe(row.get('Zoho_order_ID',''))}</td>
      <td class="mono">{safe(row.get('file_order_id',''))}</td>
      {flag_cell(row['Order_ID_Flag'])}
      <td class="ctr">{star_html(row.get('file_star',''))}</td>
      {flag_cell(row['file_star_flag'])}
      <td class="mono" style="color:#64748b;font-size:13px">{safe(row.get('file_name',''))}</td>
      {flag_cell(row['Flag'])}
    </tr>"""

st.markdown(f"""
<div style="border:2px solid #e2e8f0;border-radius:16px;overflow:hidden;
            box-shadow:0 2px 10px rgba(0,0,0,.07);background:#fff;overflow-x:auto;">
  <table class="ztable">
    <thead><tr>
      <th style="width:56px;text-align:center">#</th>
      <th>Date of Posting</th>
      <th>Branch</th>
      <th>Ticket ID</th>
      <th>Zoho Order ID</th>
      <th>File Order ID</th>
      <th style="text-align:center">Order ID Match</th>
      <th style="text-align:center">Star Rating</th>
      <th style="text-align:center">Star ≥ 4</th>
      <th>File Name</th>
      <th style="text-align:center">✦ Verified</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>""", unsafe_allow_html=True)

# ── Pagination bar — sits directly below the table ────────────
_pa, _pb, _pc = st.columns([1, 4, 1])
with _pa:
    st.button("‹ Prev", on_click=_prev_page, use_container_width=True, type="secondary")
with _pb:
    st.markdown(
        f'<div style="text-align:center;font-size:13px;color:#94a3b8;padding-top:8px">'
        f'Page <b style="color:#334155">{page}</b> of <b style="color:#334155">{total_pages}</b>'
        f' &nbsp;·&nbsp; '
        f'Rows {start+1}–{min(start+PAGE_SIZE,len(filt))} of {len(filt):,}'
        f'</div>', unsafe_allow_html=True,
    )
with _pc:
    st.button("Next ›", on_click=_next_page, use_container_width=True, type="secondary")


# =============================================================
#  FOOTER
# =============================================================

st.markdown(
    f'<div class="footer">Zoho Review Pipeline &nbsp;·&nbsp; '
    f'Data source: {source_label}</div>',
    unsafe_allow_html=True)


# =============================================================
#  AUTO REFRESH — every 8 s, unconditionally
#
#  No explicit cache.clear() needed: load_data() uses the current
#  file mtime as a cache-key argument. On each rerun Streamlit
#  re-evaluates _file_mtime(DB_PATH / CSV_PATH).
#    • mtime unchanged  →  cache HIT  (instant, no DB read)
#    • mtime changed    →  cache MISS →  fresh DB/CSV read
#
#  This means any pipeline write (including --fresh) is reflected
#  within 8 s automatically, with zero manual refresh needed.
# =============================================================

time.sleep(8)
st.rerun()
