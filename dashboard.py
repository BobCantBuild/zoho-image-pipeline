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

/* Cards */
.cards-row { display:flex; gap:16px; margin-bottom:24px; }
.mcard {
  flex:1; min-width:0; background:#fff;
  border:2px solid #e2e8f0; border-radius:16px;
  padding:22px 12px 20px; text-align:center;
  height:120px; display:flex; flex-direction:column;
  justify-content:center; align-items:center;
  box-shadow:0 2px 8px rgba(0,0,0,.06);
}
.mcard-val   { font-size:38px; font-weight:800; line-height:1; }
.mcard-label { font-size:13px; font-weight:600; color:#64748b;
               text-transform:uppercase; letter-spacing:.06em; margin-top:8px; }

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
  margin:8px 0 14px; letter-spacing:-.01em;
}

/* Filter labels */
.filter-label {
  font-size:13px; font-weight:700; color:#475569;
  text-transform:uppercase; letter-spacing:.06em; margin-bottom:5px;
}

/* Uniform control row sizing (prevents overlap/misalignment) */
div[data-baseweb="select"] > div { min-height:46px !important; }
div[data-baseweb="input"] > div { min-height:46px !important; }
div[data-testid="stDateInput"] div[data-baseweb="input"] { min-height:46px !important; }
div[data-testid="stDownloadButton"] button,
div[data-testid="stButton"] button {
  height:46px !important;
  padding:0 16px !important;
  border-radius:12px !important;
  display:flex !important;
  align-items:center !important;
  justify-content:center !important;
  white-space:nowrap !important;
}

/* Table */
.ztable { width:100%; border-collapse:collapse; }
.ztable thead tr { background:#f1f5f9; }
.ztable thead th {
  padding:14px 16px; text-align:left; font-size:13px;
  font-weight:700; color:#334155; text-transform:uppercase;
  letter-spacing:.07em; white-space:nowrap;
  border-bottom:2px solid #e2e8f0;
}
.ztable tbody tr { border-bottom:1px solid #f1f5f9; }
.ztable tbody tr:hover { background:#f8fafc; }
.ztable td { padding:13px 16px; font-size:15px; color:#1e293b;
             vertical-align:middle; white-space:nowrap; }
.ztable td.mono { font-family:monospace; font-size:14px; }
.ztable td.ctr  { text-align:center; }
.ztable td.num  { text-align:center; color:#94a3b8; font-size:14px; }

/* Badges */
.badge { display:inline-block; padding:5px 16px; border-radius:99px;
         font-size:14px; font-weight:700; letter-spacing:.02em; }
.b-yes { background:#dcfce7; color:#15803d; }
.b-no  { background:#fee2e2; color:#b91c1c; }

/* Inputs */
div[data-testid="stTextInput"] input {
  font-size:15px !important; border-radius:10px !important;
  border:2px solid #e2e8f0 !important; padding:10px 14px !important;
}
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
    if val == "YES": return '<span class="badge b-yes">✓ YES</span>'
    if val == "NO":  return '<span class="badge b-no">✕ NO</span>'
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
    bg = "#dcfce7" if val == "YES" else "#fee2e2"
    return f'<td class="ctr" style="background:{bg}">{badge(val)}</td>'

def compute_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add Order_ID_Flag, file_star_flag, Flag columns."""
    df["Zoho_order_ID"] = df.get("Zoho_order_ID",
                          df.get("csv_order_id", pd.Series([""] * len(df)))).fillna("")

    def order_flag(r):
        z = normalise_oid(r.get("Zoho_order_ID",""))
        f = normalise_oid(r.get("file_order_id","") or "")
        return "YES" if z and f and z == f else "NO"

    def star_flag(r):
        try:    return "YES" if float(r.get("file_star", 0)) >= 4 else "NO"
        except: return "NO"

    df["Order_ID_Flag"]  = df.apply(order_flag, axis=1)
    df["file_star_flag"] = df.apply(star_flag,  axis=1)
    df["Flag"] = df.apply(
        lambda r: "YES" if r["Order_ID_Flag"]  == "YES"
                        and r["file_star_flag"] == "YES" else "NO", axis=1)
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

@st.cache_data(ttl=10)
def load_data() -> tuple:
    """Returns (dataframe, source_label, stats_dict)."""

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

            # Stats from DB
            q = lambda s: conn.execute(s).fetchone()[0]
            stats = {
                "total":          q("SELECT COUNT(*) FROM zoho_records"),
                "pending":        q("SELECT COUNT(*) FROM zoho_records WHERE flag='PENDING'"),
                "ok":             q("SELECT COUNT(*) FROM zoho_records WHERE flag='OK'"),
                "orders_found":   q("SELECT COUNT(*) FROM zoho_records WHERE file_order_id IS NOT NULL AND flag!='PENDING'"),
                "stars_found":    q("SELECT COUNT(*) FROM zoho_records WHERE file_star IS NOT NULL AND flag!='PENDING'"),
            }
            conn.close()

            if not df.empty:
                df = compute_flags(df)
                df = add_posting_date(df)
                return df, "🖥️  Live — SQLite database", stats
        except Exception as e:
            pass   # fall through to CSV

    # ── Fallback: CSV from repo (cloud / shared access) ───────
    if CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", dtype=str)

        # Derive stats from CSV
        pf = df.get("pipeline_flag", pd.Series(dtype=str))
        stats = {
            "total":    len(df),
            "pending":  int((pf == "PENDING").sum()),
            "ok":       int((pf == "OK").sum()),
            "orders_found": int(df["file_order_id"].notna().sum() if "file_order_id" in df else 0),
            "stars_found":  int(df["file_star"].notna().sum()     if "file_star"     in df else 0),
        }

        if not df.empty:
            df = compute_flags(df)
            df = add_posting_date(df)
            mtime = time.strftime("%d %b %Y  %H:%M", time.localtime(CSV_PATH.stat().st_mtime))
            return df, f"☁️  Cloud — GitHub CSV (zoho_latest.csv • updated {mtime})", stats

    return pd.DataFrame(), "⚠️  No data source found", {}


# =============================================================
#  LOAD
# =============================================================

df, source_label, stats = load_data()

if st.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

with st.expander("🧪 Diagnostics", expanded=False):
    st.write("App file:", str(Path(__file__).resolve()))
    st.write("OS:", os.name)
    st.write("DB_PATH:", str(DB_PATH), "exists:", Path(DB_PATH).exists())
    st.write("CSV_PATH:", str(CSV_PATH), "exists:", CSV_PATH.exists())
    if CSV_PATH.exists():
        st.write("CSV bytes:", CSV_PATH.stat().st_size)
        st.write("CSV mtime:", time.strftime("%d %b %Y %H:%M:%S", time.localtime(CSV_PATH.stat().st_mtime)))
        try:
            preview = pd.read_csv(CSV_PATH, encoding="utf-8-sig", dtype=str).head(5)
            st.write("CSV preview (top 5 rows):")
            st.dataframe(preview, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"CSV read failed: {e}")
    data_dir = CSV_PATH.parent
    st.write("data/ listing:", [p.name for p in data_dir.glob('*')] if data_dir.exists() else "(missing)")

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
#  METRIC CARDS
# =============================================================

def mcard(val, label, color):
    return (f'<div class="mcard">'
            f'<div class="mcard-val" style="color:{color}">{val:,}</div>'
            f'<div class="mcard-label">{label}</div></div>')

st.markdown(
    '<div class="cards-row">'
    + mcard(stats.get("total",    0), "Total Records",  "#0f172a")
    + mcard(stats.get("pending",  0), "Processing",     "#d97706")
    + mcard(stats.get("ok",       0), "Completed OK",   "#16a34a")
    + mcard(stats.get("orders_found", 0), "File orders detected", "#2563eb")
    + mcard(stats.get("stars_found",  0), "Star rating counted",  "#7c3aed")
    + mcard(int((df.get("Flag", pd.Series(dtype=str)) == "YES").sum()) if not df.empty else 0, "Flag", "#dc2626")
    + '</div>', unsafe_allow_html=True)


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

fc1, fc2, fc3, fc4, fc5 = st.columns([1, 1, 1, 1, 1], vertical_alignment="bottom")

PIPE_OPTIONS = [
    "All — Show everything",
    "OK — Fully processed",
    "PENDING — Still running",
    "ERROR — Failed records",
    "NO_ORDER_ID — Order ID not found in image",
    "NO_STAR — Star rating not found in image",
    "LOW_CONF_ORDER — Low confidence match (verify manually)",
]

with fc1:
    st.markdown('<div class="filter-label">✦ Overall FLAG</div>',
                unsafe_allow_html=True)
    flag_filter = st.selectbox("", ["All","YES","NO"],
                               label_visibility="collapsed", key="ff1")
with fc2:
    st.markdown('<div class="filter-label">🔗 Order ID Match</div>',
                unsafe_allow_html=True)
    order_filter = st.selectbox("", ["All","YES","NO"],
                                label_visibility="collapsed", key="ff2")
with fc3:
    st.markdown('<div class="filter-label">⭐ Star Rating ≥ 4</div>',
                unsafe_allow_html=True)
    star_filter = st.selectbox("", ["All","YES","NO"],
                               label_visibility="collapsed", key="ff3")
with fc4:
    st.markdown('<div class="filter-label">⚙️ Processing Status</div>',
                unsafe_allow_html=True)
    pipe_sel    = st.selectbox("", PIPE_OPTIONS,
                               label_visibility="collapsed", key="ff4")
    pipe_key    = pipe_sel.split(" — ")[0].strip()
with fc5:
    st.markdown('<div class="filter-label">&nbsp;</div>', unsafe_allow_html=True)
    if st.button("✕  Clear All Filters", use_container_width=True):
        for k in ["search_box","ff1","ff2","ff3","ff4","branch_filter","date_range","page"]:
            if k in st.session_state: del st.session_state[k]
        st.cache_data.clear(); st.rerun()


# =============================================================
#  APPLY FILTERS
# =============================================================

if df.empty:
    st.warning("⚠️  No data available. Run `pipeline.py` to process records.")
    st.stop()


# =============================================================
#  PAGINATION + EXPORT
# =============================================================

PAGE_SIZE = 50

# ---- Branch + Date filters (with clear X) ----
if "branch" in df.columns:
    branches = sorted({(b or "").strip() for b in df["branch"].fillna("").tolist()} - {""})
else:
    branches = []

dates = pd.to_datetime(df.get("date_of_posting", pd.Series([], dtype="datetime64[ns]")), errors="coerce").dropna()
default_date_range = None
if len(dates) > 0:
    default_date_range = (dates.min().date(), dates.max().date())

count_col, branch_col, date_col, prev_col, next_col, export_col = st.columns(
    [2.2, 1.8, 3.2, 1, 1, 2.2],
    vertical_alignment="bottom",
)

with branch_col:
    st.markdown('<div class="filter-label">🏢 Branch</div>', unsafe_allow_html=True)
    b1, b2 = st.columns([5, 1], vertical_alignment="bottom")
    with b1:
        branch_filter = st.selectbox(
            "",
            ["All", *branches],
            label_visibility="collapsed",
            key="branch_filter",
        )
    with b2:
        if st.button("✕", key="branch_clear", use_container_width=True):
            if "branch_filter" in st.session_state:
                del st.session_state["branch_filter"]
            st.cache_data.clear()
            st.rerun()

with date_col:
    st.markdown('<div class="filter-label">📅 Date of Posting</div>', unsafe_allow_html=True)
    d1, d2 = st.columns([8, 1], vertical_alignment="bottom")
    with d1:
        date_range = st.date_input(
            "",
            value=st.session_state.get("date_range", default_date_range),
            label_visibility="collapsed",
            key="date_range",
        )
    with d2:
        if st.button("✕", key="date_clear", use_container_width=True):
            if "date_range" in st.session_state:
                del st.session_state["date_range"]
            st.cache_data.clear()
            st.rerun()

# ---- APPLY FILTERS ----
filt = df.copy()
if flag_filter  != "All": filt = filt[filt["Flag"]           == flag_filter]
if order_filter != "All": filt = filt[filt["Order_ID_Flag"]  == order_filter]
if star_filter  != "All": filt = filt[filt["file_star_flag"] == star_filter]
if pipe_key     != "All":
    filt = filt[filt["pipeline_flag"].fillna("").str.contains(pipe_key)]
if "branch" in filt.columns and branch_filter != "All":
    filt = filt[filt["branch"].fillna("") == branch_filter]
if "date_of_posting" in filt.columns and isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    d0, d1 = date_range
    if d0 and d1:
        filt = filt[
            (pd.to_datetime(filt["date_of_posting"], errors="coerce").dt.date >= d0)
            & (pd.to_datetime(filt["date_of_posting"], errors="coerce").dt.date <= d1)
        ]
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

with count_col:
    st.markdown(f'<div class="pag-info"><b>{len(filt):,}</b> records found</div>', unsafe_allow_html=True)

with prev_col:
    prev_btn = st.button("‹ Prev", use_container_width=True)

with next_col:
    next_btn = st.button("Next ›", use_container_width=True)

with export_col:
    exp_cols = [
        "sno",
        "date_of_posting_str",
        "branch",
        "ticket_id",
        "Zoho_order_ID",
        "file_order_id",
        "Order_ID_Flag",
        "file_star",
        "file_star_flag",
        "file_name",
        "Flag",
    ]
    exp_df = filt[[c for c in exp_cols if c in filt.columns]].copy()
    exp_df.columns = [
        "#",
        "Date of Posting",
        "Branch",
        "Ticket ID",
        "Zoho Order ID",
        "File Order ID",
        "Order ID Match",
        "Star Rating",
        "Star ≥ 4",
        "File Name",
        "✦ FLAG",
    ][: len(exp_df.columns)]
    st.download_button("⬇️ Export to CSV",
                       data=exp_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="zoho_export.csv", mime="text/csv",
                       use_container_width=True)

# Page state (kept in session_state, so Prev/Next works without a number input)
page = int(st.session_state.get("page", 1))
if prev_btn and page > 1:
    page -= 1
if next_btn and page < total_pages:
    page += 1
page = max(1, min(total_pages, int(page)))
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
      <th style="text-align:center">✦ FLAG</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>
<div style="margin-top:10px;font-size:14px;color:#94a3b8;text-align:right">
  Page {page} of {total_pages} &nbsp;·&nbsp;
  Rows {start+1}–{min(start+PAGE_SIZE,len(filt))} of {len(filt):,}
</div>""", unsafe_allow_html=True)


# =============================================================
#  FOOTER
# =============================================================

st.markdown(
    f'<div class="footer">Zoho Review Pipeline &nbsp;·&nbsp; '
    f'Data source: {source_label}</div>',
    unsafe_allow_html=True)


# =============================================================
#  AUTO REFRESH  — only while pipeline running
# =============================================================

if pending > 0:
    time.sleep(10)
    st.cache_data.clear()
    st.rerun()
