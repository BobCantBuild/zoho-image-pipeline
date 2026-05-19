# =============================================================
#  dashboard.py  —  Zoho Pipeline Dashboard
#  Run:  streamlit run dashboard.py
#  Host: streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
# =============================================================

import sqlite3, time, re
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Zoho Review Pipeline",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\zoho_pipeline.db"

# =============================================================
#  CSS  — large text, fixed card heights, no glitch
# =============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family:'Inter',sans-serif !important; }
#MainMenu, footer, header  { visibility:hidden; }
.block-container { padding:2rem 2.5rem 3rem !important; max-width:100% !important; }

/* ── Metric cards — ALL same fixed size ── */
.cards-row { display:flex; gap:14px; margin-bottom:20px; }
.mcard {
  flex:1; min-width:0;
  background:#fff;
  border:1.5px solid #e2e8f0;
  border-radius:14px;
  padding:20px 16px 18px;
  text-align:center;
  height:110px;
  display:flex; flex-direction:column;
  justify-content:center; align-items:center;
  box-shadow:0 2px 6px rgba(0,0,0,.05);
}
.mcard-val   { font-size:36px; font-weight:800; line-height:1; }
.mcard-label { font-size:13px; font-weight:600; color:#64748b;
               text-transform:uppercase; letter-spacing:.05em; margin-top:7px; }

/* ── Progress bar ── */
.prog-wrap { margin:6px 0 22px; }
.prog-label { font-size:14px; font-weight:600; color:#334155; margin-bottom:6px; }
.prog-track { background:#e2e8f0; border-radius:99px; height:10px; overflow:hidden; }
.prog-fill  { height:100%; border-radius:99px;
              background:linear-gradient(90deg,#3b82f6,#6366f1);
              transition:width .5s ease; }
.prog-sub   { font-size:13px; color:#64748b; margin-top:5px; }

/* ── Section heading ── */
.sec-head {
  font-size:15px; font-weight:700; color:#0f172a;
  border-left:4px solid #6366f1; padding-left:12px;
  margin:8px 0 16px;
}

/* ── Filter bar ── */
.filter-bar {
  background:#f8fafc; border:1.5px solid #e2e8f0;
  border-radius:12px; padding:14px 18px; margin-bottom:16px;
}

/* ── Table ── */
.ztable { width:100%; border-collapse:collapse; }
.ztable thead tr { background:#f1f5f9; }
.ztable thead th {
  padding:13px 14px; text-align:left;
  font-size:13px; font-weight:700; color:#334155;
  text-transform:uppercase; letter-spacing:.06em;
  white-space:nowrap; border-bottom:2px solid #e2e8f0;
}
.ztable tbody tr { border-bottom:1px solid #f1f5f9; }
.ztable tbody tr:hover { background:#f8fafc; }
.ztable td {
  padding:11px 14px; font-size:14px;
  color:#1e293b; vertical-align:middle; white-space:nowrap;
}
.ztable td.mono { font-family:monospace; font-size:13px; }
.ztable td.ctr  { text-align:center; }
.ztable td.num  { text-align:center; color:#94a3b8; font-size:13px; }

/* ── Badges ── */
.badge {
  display:inline-block; padding:4px 14px; border-radius:99px;
  font-size:13px; font-weight:700; letter-spacing:.03em;
}
.b-yes  { background:#dcfce7; color:#15803d; }
.b-no   { background:#fee2e2; color:#b91c1c; }

/* ── Top bar ── */
.topbar { display:flex; align-items:center;
          justify-content:space-between; margin-bottom:26px; }
.topbar-title { font-size:22px; font-weight:800; color:#0f172a; }
.topbar-sub   { font-size:14px; color:#64748b; margin-top:2px; }
.topbar-time  { font-size:13px; color:#94a3b8; }

/* ── Inputs larger ── */
div[data-testid="stTextInput"] input {
  font-size:14px !important; border-radius:8px !important;
  border:1.5px solid #e2e8f0 !important; padding:8px 12px !important;
}
div[data-testid="stSelectbox"] > div > div {
  font-size:14px !important; border-radius:8px !important;
}
div[data-testid="stDownloadButton"] button,
div[data-testid="stButton"] button {
  font-size:14px !important; font-weight:600 !important;
  border-radius:8px !important; padding:8px 20px !important;
}

/* ── Pagination info ── */
.pag-info { font-size:14px; color:#64748b; padding-top:9px; }

/* ── Footer ── */
.footer { text-align:center; font-size:13px; color:#cbd5e1; margin-top:28px; }
.footer code { font-size:12px; }

/* ── Kill streamlit rerun flash ── */
div[data-testid="stStatusWidget"] { display:none !important; }
</style>
""", unsafe_allow_html=True)


# =============================================================
#  HELPERS
# =============================================================

def normalise_oid(raw: str) -> str:
    """Normalise order ID for comparison: strip #, fix 0D→OD, uppercase."""
    if not raw:
        return ""
    s = str(raw).strip().lstrip("#").strip()
    s = re.sub(r"\s+", "", s).upper()
    s = re.sub(r"^0D", "OD", s)       # 0D → OD  (OCR misread)
    return s


def badge(val: str) -> str:
    if val == "YES": return '<span class="badge b-yes">✓ YES</span>'
    if val == "NO":  return '<span class="badge b-no">✕ NO</span>'
    return f'<span class="badge">{val}</span>'


def star_html(val) -> str:
    try:
        n = float(val)
        filled = int(n)
        s = "★" * filled + "☆" * (5 - filled)
        c = "#f59e0b" if n >= 4 else "#94a3b8"
        return (f'<span style="color:{c};font-size:17px">{s}</span>'
                f'<span style="color:#64748b;font-size:13px;margin-left:6px">'
                f'{n:.1f}</span>')
    except:
        return '<span style="color:#cbd5e1;font-size:14px">—</span>'


def safe(val) -> str:
    v = str(val or "").strip()
    if v in ("", "None", "nan", "NaN"):
        return '<span style="color:#cbd5e1">—</span>'
    return v


# =============================================================
#  DATA
# =============================================================

@st.cache_data(ttl=10)
def load_data() -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT sno, ticket_id, csv_order_id, file_order_id,
               file_star, file_name, flag AS pipeline_flag
        FROM zoho_records ORDER BY sno
    """, conn)
    conn.close()
    if df.empty:
        return df

    df["Zoho_order_ID"] = df["csv_order_id"].fillna("")

    def order_flag(r):
        z = normalise_oid(r["Zoho_order_ID"])
        f = normalise_oid(r["file_order_id"] or "")
        return "YES" if z and f and z == f else "NO"

    def star_flag(r):
        try:    return "YES" if float(r["file_star"]) >= 4 else "NO"
        except: return "NO"

    df["Order_ID_Flag"]  = df.apply(order_flag, axis=1)
    df["file_star_flag"] = df.apply(star_flag,  axis=1)
    df["Flag"] = df.apply(
        lambda r: "YES" if r["Order_ID_Flag"]  == "YES"
                        and r["file_star_flag"] == "YES" else "NO", axis=1)
    return df


@st.cache_data(ttl=10)
def load_stats() -> dict:
    if not Path(DB_PATH).exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    q = lambda s: conn.execute(s).fetchone()[0]
    out = {
        "total":    q("SELECT COUNT(*) FROM zoho_records"),
        "pending":  q("SELECT COUNT(*) FROM zoho_records WHERE flag='PENDING'"),
        "ok":       q("SELECT COUNT(*) FROM zoho_records WHERE flag='OK'"),
        "no_order": q("SELECT COUNT(*) FROM zoho_records WHERE file_order_id IS NULL AND flag!='PENDING'"),
        "no_star":  q("SELECT COUNT(*) FROM zoho_records WHERE file_star IS NULL AND flag!='PENDING'"),
        "low_conf": q("SELECT COUNT(*) FROM zoho_records WHERE flag LIKE '%LOW_CONF%'"),
        "errors":   q("SELECT COUNT(*) FROM zoho_records WHERE flag='ERROR'"),
    }
    conn.close()
    return out


# =============================================================
#  TOP BAR
# =============================================================

stats   = load_stats()
df      = load_data()
total   = max(stats.get("total",   1), 1)
pending = stats.get("pending", 0)
done    = total - pending
pct     = done / total * 100

now_str = time.strftime("%d %b %Y  %H:%M")
st.markdown(f"""
<div class="topbar">
  <div>
    <div class="topbar-title">📦 &nbsp;Zoho Review Pipeline</div>
    <div class="topbar-sub">Image Processing &amp; Order Verification Dashboard</div>
  </div>
  <div class="topbar-time">⏱ &nbsp;{now_str}</div>
</div>""", unsafe_allow_html=True)


# =============================================================
#  METRIC CARDS  — all same fixed height via flex
# =============================================================

def mcard(val, label, color):
    return f"""
    <div class="mcard">
      <div class="mcard-val" style="color:{color}">{val:,}</div>
      <div class="mcard-label">{label}</div>
    </div>"""

cards_html = (
    '<div class="cards-row">'
    + mcard(stats.get("total",    0), "Total",        "#0f172a")
    + mcard(stats.get("pending",  0), "Processing",   "#d97706")
    + mcard(stats.get("ok",       0), "Completed",    "#16a34a")
    + mcard(stats.get("no_order", 0), "No Order ID",  "#dc2626")
    + mcard(stats.get("no_star",  0), "No Star",      "#7c3aed")
    + mcard(stats.get("low_conf", 0), "Low Conf",     "#2563eb")
    + mcard(stats.get("errors",   0), "Errors",       "#be123c")
    + '</div>'
)
st.markdown(cards_html, unsafe_allow_html=True)


# =============================================================
#  PROGRESS BAR
# =============================================================

st.markdown(f"""
<div class="prog-wrap">
  <div class="prog-label">Pipeline Progress &nbsp;
    <span style="font-weight:400;color:#64748b">
      {done:,} of {total:,} records completed
    </span>
  </div>
  <div class="prog-track">
    <div class="prog-fill" style="width:{pct:.2f}%"></div>
  </div>
  <div class="prog-sub">{pct:.1f}% done
    {"&nbsp;·&nbsp; ⚡ Auto-refreshing every 10 s" if pending > 0
     else "&nbsp;·&nbsp; ✅ Pipeline complete"}
  </div>
</div>""", unsafe_allow_html=True)


# =============================================================
#  FILTERS
# =============================================================

st.markdown('<div class="sec-head">Records</div>', unsafe_allow_html=True)

fa, fb, fc, fd, fe, ff = st.columns([3, 1.2, 1.2, 1.2, 1.2, 1.2])
with fa: search       = st.text_input("", placeholder="🔍  Search file name, order ID, ticket…",
                                       label_visibility="collapsed")
with fb: flag_filter  = st.selectbox("", ["All","YES","NO"],
                                      label_visibility="collapsed",
                                      key="f1",
                                      help="Overall FLAG")
with fc: order_filter = st.selectbox("", ["All","YES","NO"],
                                      label_visibility="collapsed",
                                      key="f2",
                                      help="Order ID Match")
with fd: star_filter  = st.selectbox("", ["All","YES","NO"],
                                      label_visibility="collapsed",
                                      key="f3",
                                      help="Star ≥ 4")
with fe: pipe_filter  = st.selectbox("", ["All","OK","PENDING","ERROR",
                                          "NO_ORDER_ID","NO_STAR","LOW_CONF_ORDER"],
                                      label_visibility="collapsed",
                                      key="f4",
                                      help="Processing status")
with ff:
    if st.button("✕ Clear", use_container_width=True):
        st.cache_data.clear(); st.rerun()


# =============================================================
#  FILTER DATA
# =============================================================

if df.empty:
    st.warning("No data found. Run `pipeline.py` first.")
    st.stop()

filt = df.copy()
if flag_filter  != "All": filt = filt[filt["Flag"]           == flag_filter]
if order_filter != "All": filt = filt[filt["Order_ID_Flag"]  == order_filter]
if star_filter  != "All": filt = filt[filt["file_star_flag"] == star_filter]
if pipe_filter  != "All":
    filt = filt[filt["pipeline_flag"].fillna("").str.contains(pipe_filter)]
if search:
    s = search.lower()
    filt = filt[
        filt["file_name"].fillna("").str.lower().str.contains(s)      |
        filt["file_order_id"].fillna("").str.lower().str.contains(s)  |
        filt["Zoho_order_ID"].str.lower().str.contains(s)             |
        filt["ticket_id"].fillna("").str.lower().str.contains(s)
    ]

filt = filt.reset_index(drop=True)


# =============================================================
#  PAGINATION + EXPORT ROW
# =============================================================

PAGE_SIZE   = 50
total_pages = max(1, (len(filt) - 1) // PAGE_SIZE + 1)

pa, pb, pc, pd_col, pe = st.columns([2, 1, 1, 1, 2])

with pa:
    st.markdown(
        f'<div class="pag-info"><b>{len(filt):,}</b> records found</div>',
        unsafe_allow_html=True)

with pb:
    prev_btn = st.button("‹ Prev", use_container_width=True)

with pc:
    page = st.number_input("", min_value=1, max_value=total_pages,
                           value=1, label_visibility="collapsed")

with pd_col:
    next_btn = st.button("Next ›", use_container_width=True)

with pe:
    exp_df = filt[[
        "sno","ticket_id","Zoho_order_ID","file_order_id",
        "Order_ID_Flag","file_star","file_star_flag","Flag","file_name"
    ]].copy()
    exp_df.columns = [
        "#","Ticket ID","Zoho Order ID","File Order ID",
        "Order ID Flag","File Star","Star Flag","FLAG","File Name"
    ]
    st.download_button(
        "⬇️  Export to CSV",
        data=exp_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="zoho_export.csv", mime="text/csv",
        use_container_width=True,
    )

if prev_btn and page > 1:           page = int(page) - 1
if next_btn and page < total_pages: page = int(page) + 1
page = int(page)


# =============================================================
#  TABLE
# =============================================================

start   = (page - 1) * PAGE_SIZE
page_df = filt.iloc[start: start + PAGE_SIZE]

def flag_cell(val):
    bg = "#dcfce7" if val == "YES" else "#fee2e2"
    return f'<td class="ctr" style="background:{bg}">{badge(val)}</td>'

rows_html = ""
for i, (_, row) in enumerate(page_df.iterrows(), start=start + 1):
    rows_html += f"""
    <tr>
      <td class="num">{i}</td>
      <td class="mono">{safe(row['ticket_id'])}</td>
      <td class="mono">{safe(row['Zoho_order_ID'])}</td>
      <td class="mono">{safe(row['file_order_id'])}</td>
      {flag_cell(row['Order_ID_Flag'])}
      <td class="ctr">{star_html(row['file_star'])}</td>
      {flag_cell(row['file_star_flag'])}
      <td class="mono" style="color:#64748b;font-size:12px">{safe(row['file_name'])}</td>
      {flag_cell(row['Flag'])}
    </tr>"""

st.markdown(f"""
<div style="border:1.5px solid #e2e8f0;border-radius:14px;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,.06);background:#fff;overflow-x:auto;">
  <table class="ztable">
    <thead><tr>
      <th style="width:52px;text-align:center">#</th>
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
<div style="margin-top:10px;font-size:13px;color:#94a3b8;text-align:right">
  Page {page} of {total_pages} &nbsp;·&nbsp;
  Rows {start+1}–{min(start+PAGE_SIZE, len(filt))} of {len(filt):,}
</div>
""", unsafe_allow_html=True)


# =============================================================
#  FOOTER
# =============================================================

st.markdown(
    f'<div class="footer">Zoho Review Pipeline &nbsp;·&nbsp; '
    f'<code>{DB_PATH}</code></div>',
    unsafe_allow_html=True)


# =============================================================
#  AUTO REFRESH
# =============================================================

if pending > 0:
    time.sleep(10)
    st.cache_data.clear()
    st.rerun()