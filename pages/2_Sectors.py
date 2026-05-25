# ══════════════════════════════════════════════════════════════════
#  TRADESENTRY — 2_Sectors.py
#  Page: Sector Performance — NSE Indices
#
#  SECTIONS IN THIS FILE:
#  ─────────────────────────────────────────────────────────────────
#  SECTION 1  →  Imports & Path Setup
#  SECTION 2  →  Page Config, Styles, Header  (UNCHANGED)
#  SECTION 3  →  Page-Level CSS Overrides      (UNCHANGED)
#  SECTION 4  →  Constants & Session State     (UNCHANGED)
#  SECTION 5  →  Sector Data Fetchers          (UNCHANGED)
#  SECTION 6  →  [NEW] Stock Drill-Down Fetcher
#  SECTION 7  →  Data Calculations & Derived Stats  (UNCHANGED)
#  SECTION 8  →  Control Row (Metrics + Timeframe + Refresh) (UNCHANGED)
#  SECTION 9  →  Sector Bar Chart with Inline Drill-Down  (MODIFIED)
#  SECTION 10 →  Supplementary Data Table Expander  (UNCHANGED)
# ══════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────
# SECTION 1 — Imports & Path Setup
# Purpose : Pull in all libraries + make sibling modules importable
# ──────────────────────────────────────────────────────────────────
import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import yfinance as yf
import time
import datetime
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from stocks import SECTOR_YAHOO, STOCK_UNIVERSE, get_stocks_by_sector


# ──────────────────────────────────────────────────────────────────
# SECTION 2 — Page Config, Styles, Header
# Purpose : Set Streamlit page-level settings + apply global theme
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")
apply_styles()
sidebar_brand()
page_header("Sector Performance — NSE Indices")


# ──────────────────────────────────────────────────────────────────
# SECTION 3 — Page-Level CSS Overrides
# Purpose : Fine-tune layout: white bg, card heights, button styles
#           These are very specific to the 5-column control row
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Force the main app body wrapper background color to pure white */
    .stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"] {
        background-color: #ffffff !important;
    }

    /* Style column 4 to look exactly like the metrics cards */
    div[data-testid="stHorizontalBlock"] > div:nth-child(4) {
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        padding: 14px 18px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        min-height: 65px !important;
        max-height: 65px !important;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    /* REFRESH BUTTON FIX: Stretch column 5 + remove outer card background */
    div[data-testid="stHorizontalBlock"] > div:nth-child(5) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0px !important;
        min-height: 65px !important;
        max-height: 65px !important;
        min-width: 110px !important;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }

    /* Force the native Streamlit selectbox inner frame to pure white */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: none !important;
    }

    /* Remove default nested padding under inputs inside layout cards */
    div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlock"] {
        gap: 0rem !important;
    }

    /* Turn the refresh button into the clean white card container */
    div[data-testid="stHorizontalBlock"] button[key="refresh_btn"] {
        height: 42px !important;
        background-color: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        font-size: 14px !important;
        color: #3d4452 !important;
        margin-bottom: 0px !important;
    }

    /* ── [NEW] Drill-down expand/collapse button inside the chart iframe ──
       These styles live inside the iframe HTML (Section 9), but kept here
       as reference so future devs know where the design tokens come from  */
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# SECTION 4 — Constants & Session State
# Purpose : Define timeframe options + initialise session defaults
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
today = datetime.date.today()

TIMEFRAMES = {
    "1 Day":    1,
    "1 Week":   7,
    "1 Month":  30,
    "3 Months": 90,
    "6 Months": 180,
    "1 Year":   365,
}

if "selected_tf" not in st.session_state:
    st.session_state["selected_tf"] = "1 Day"

# Track which sector row is currently expanded for drill-down
# None means all collapsed; a sector name string means that one is open
if "expanded_sector" not in st.session_state:
    st.session_state["expanded_sector"] = None


# ──────────────────────────────────────────────────────────────────
# SECTION 5 — Sector Data Fetchers
# Purpose : fetch_today()  → live 1-day % change per sector index
#           fetch_range()  → historical % change over N days
# Cache   : 30s for live, 5 min for historical
# NOTE    : UNCHANGED — do not modify these functions
# ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def fetch_today():
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                   f"{requests.utils.quote(symbol)}?interval=1d&range=1d")
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok:
                continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                pc = meta.get('chartPreviousClose', 0)
                change = ((cp - pc) / pc * 100) if pc else 0.0
                data.append({'name': name, 'change': round(change, 2),
                             'direction': 'up' if change >= 0 else 'down',
                             'ltp': round(cp, 2), 'prev': round(pc, 2)})
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data


@st.cache_data(ttl=300)
def fetch_range(from_date: str, to_date: str):
    data = []
    end = (datetime.date.fromisoformat(to_date) + datetime.timedelta(days=1)).isoformat()
    for name, symbol in SECTOR_YAHOO.items():
        try:
            hist = yf.Ticker(symbol).history(
                start=from_date, end=end, interval="1d", auto_adjust=True
            )
            if hist.empty:
                continue
            s = hist['Close'].iloc[0]
            e = hist['Close'].iloc[-1]
            change = ((e - s) / s * 100) if s else 0.0
            data.append({'name': name, 'change': round(change, 2),
                         'direction': 'up' if change >= 0 else 'down',
                         'ltp': round(e, 2), 'prev': round(s, 2)})
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data


# ──────────────────────────────────────────────────────────────────
# SECTION 6 — [NEW] Stock Drill-Down Fetcher
# Purpose : Fetch individual stock % change for stocks inside a
#           given sector. Called only when user clicks a sector row.
#
# How it works:
#   1. get_stocks_by_sector(sector) → pulls stock list from stocks.py
#   2. Appends ".NS" to each symbol → Yahoo Finance NSE format
#   3. yf.download() fetches 2 days of data (today + prev close)
#   4. Calculates % change = (today_close - prev_close) / prev_close
#   5. Sorts by absolute % change → biggest movers first
#   6. Returns top N stocks (default 8) as list of dicts
#
# Cache   : 60s TTL — stocks refresh every minute is sufficient
# Safety  : try/except per stock → one bad ticker won't break page
# ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_stocks_for_sector(sector_name: str, limit: int = 8) -> list:
    """
    Fetch top `limit` stocks for a sector with their % change today.

    Returns list of dicts:
        [{'sym': 'HDFCBANK', 'change': 2.31, 'ltp': 1823.5, 'direction': 'up'}, ...]
    Sorted by abs(change) descending — biggest movers at the top.
    """
    # Step 1: Get all stocks belonging to this sector from STOCK_UNIVERSE
    sector_stocks = get_stocks_by_sector(sector_name)  # [{'sym': 'HDFCBANK', 'token': '1333'}, ...]

    if not sector_stocks:
        return []

    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    # Step 2: Fetch each stock via Yahoo Finance chart API
    # Using the SAME approach as fetch_today() — regularMarketPrice avoids
    # NaN issues that yf.Ticker.history() has during live market hours.
    # NSE suffix ".NS" required for Yahoo Finance (e.g. HDFCBANK.NS)
    for stock in sector_stocks:
        sym    = stock['sym']
        yf_sym = sym + ".NS"

        try:
            # Step 3: Hit Yahoo Finance chart endpoint — same URL pattern as fetch_today()
            url  = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                    f"{requests.utils.quote(yf_sym)}?interval=1d&range=5d")
            resp = requests.get(url, headers=headers, timeout=5)

            if not resp.ok:
                continue

            result = resp.json().get('chart', {}).get('result', [])
            if not result:
                continue

            meta = result[0].get('meta', {})

            # Step 4: Use regularMarketPrice (live) and chartPreviousClose
            # These are the same fields fetch_today() uses — guaranteed non-NaN
            cp = meta.get('regularMarketPrice', 0)
            pc = meta.get('chartPreviousClose', 0)

            if not cp or not pc:
                continue

            # Step 5: % change calculation — identical formula to fetch_today()
            change = round(((cp - pc) / pc) * 100, 2)

            results.append({
                'sym':       sym,
                'change':    change,
                'ltp':       round(cp, 2),
                'prev':      round(pc, 2),
                'direction': 'up' if change >= 0 else 'down',
            })

        except Exception:
            # Bad ticker or network error — skip silently, never crash page
            continue

    # Step 5: Sort by biggest absolute move — most impactful stocks first
    results.sort(key=lambda x: abs(x['change']), reverse=True)

    # Step 6: Return only top N stocks
    return results[:limit]


# ──────────────────────────────────────────────────────────────────
# SECTION 7 — Data Calculations & Derived Stats
# Purpose : Resolve which timeframe is active, fetch the right data,
#           compute summary stats (gainers, losers, top, bottom)
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
tf   = st.session_state["selected_tf"]
days = TIMEFRAMES[tf]

if days == 1:
    with st.spinner("Fetching live sector data..."):
        data = fetch_today()
    period_label = "Today's Performance"
    col_start    = "Prev Close"
else:
    from_dt = today - datetime.timedelta(days=days)
    with st.spinner(f"Fetching {tf} data..."):
        data = fetch_range(str(from_dt), str(today))
    period_label = f"{from_dt.strftime('%d %b %Y')}  →  {today.strftime('%d %b %Y')}"
    col_start    = "Start Price"

if not data:
    st.error("Could not fetch sector data. Please try again.")
    st.stop()

gainers = [s for s in data if s['direction'] == 'up']
losers  = [s for s in data if s['direction'] == 'down']
top     = data[0]
bottom  = data[-1]
updated = time.strftime("%H:%M:%S")


# ──────────────────────────────────────────────────────────────────
# SECTION 8 — Control Row (Metrics + Timeframe + Refresh)
# Purpose : Render the 5-column top bar:
#           [Top Gainer] [Top Loser] [Breadth] [Timeframe] [Refresh]
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])

with c1:
    st.markdown(f"""
    <div class="ts-metric" style="height: 65px; margin-bottom: 0px;">
      <div class="ts-metric-label">Top Gainer</div>
      <div class="ts-metric-value" style="color:var(--green); font-size:15px; margin-top:4px;">▲ {top['name']} {top['change']:+.2f}%</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="ts-metric" style="height: 65px; margin-bottom: 0px;">
      <div class="ts-metric-label">Top Loser</div>
      <div class="ts-metric-value" style="color:var(--red); font-size:15px; margin-top:4px;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="ts-metric" style="height: 65px; margin-bottom: 0px;">
      <div class="ts-metric-label">Breadth</div>
      <div class="ts-metric-value" style="font-size:15px; margin-top:4px;">
        <span style="color:var(--green);">{len(gainers)}↑</span>
        <span style="color:var(--border2);"> / </span>
        <span style="color:var(--red);">{len(losers)}↓</span>
      </div>
    </div>""", unsafe_allow_html=True)

with c4:
    st.markdown('<div style="font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:#7a8394; margin-bottom:2px;">Timeframe</div>', unsafe_allow_html=True)
    chosen = st.selectbox(
        "TIMEFRAME",
        list(TIMEFRAMES.keys()),
        index=list(TIMEFRAMES.keys()).index(st.session_state["selected_tf"]),
        label_visibility="collapsed",
        key="tf_select"
    )
    if chosen != st.session_state["selected_tf"]:
        st.session_state["selected_tf"] = chosen
        st.cache_data.clear()
        st.rerun()

with c5:
    # Invisible spacer label to align button baseline with selectbox
    st.markdown('<div style="font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:transparent; margin-bottom:2px; user-select:none;">Action</div>', unsafe_allow_html=True)
    if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────
# SECTION 9 — Sector Bar Chart with Inline Drill-Down
# Purpose : Render the main sector performance chart.
#           Each sector row has a ▶ button that expands inline to
#           show the top 8 stocks in that sector with their % change.
# ──────────────────────────────────────────────────────────────────

# Calculate max change once — used for bar width scaling (same as original)
max_chg = max(abs(s['change']) for s in data) or 1

# Chart outer container header — identical to original
st.markdown(f"""
<div style="background:#fafbfc; border:1px solid #e0e3e8; border-radius:10px 10px 0 0;
padding:12px 14px; font-size:11px; font-weight:600; color:#7a8394;
display:flex; justify-content:space-between; align-items:center;">
  <span>📅 {period_label}</span>
  <span style="font-weight:400;">Updated: {updated}</span>
</div>
""", unsafe_allow_html=True)

# ── Render each sector row individually ──
for s in data:
    sector_name = s['name']
    bar_w       = (abs(s['change']) / max_chg) * 85
    color       = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign        = "+" if s['change'] >= 0 else ""
    is_expanded = st.session_state["expanded_sector"] == sector_name

    # ── Row layout: bar chart col + expand button col ──
    row_col, btn_col = st.columns([0.92, 0.08])

    with row_col:
        st.markdown(f"""
        <div style="display:grid; grid-template-columns:110px 1fr 75px;
        align-items:center; gap:12px; padding:10px 14px;
        border-bottom:1px solid #f0f2f5;
        background:{'#f5fdf8' if is_expanded else '#ffffff'};">
          <div style="font-size:12px; font-weight:700; color:#3d4452;
          font-family:'JetBrains Mono',monospace;">{sector_name}</div>
          <div style="height:8px; background:#f0f2f5; border-radius:4px; overflow:hidden;">
            <div style="width:{bar_w:.1f}%; height:100%; background:{color}; border-radius:4px;"></div>
          </div>
          <div style="font-size:12px; font-weight:700; text-align:right; color:{color};
          font-family:'JetBrains Mono',monospace;">{sign}{s['change']:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with btn_col:
        btn_label = "▲" if is_expanded else "▶"
        btn_key   = f"expand_{sector_name}"
        if st.button(btn_label, key=btn_key, use_container_width=True):
            if is_expanded:
                st.session_state["expanded_sector"] = None
            else:
                st.session_state["expanded_sector"] = sector_name
            st.rerun()

    # ── Inline Drill-Down Panel ──
    if is_expanded:
        with st.spinner(f"Loading {sector_name} stocks..."):
            stocks = fetch_stocks_for_sector(sector_name, limit=8)

        if not stocks:
            st.markdown("""
            <div style="padding:10px 14px; font-size:12px; color:#7a8394;
            background:#fafbfc; border-bottom:1px solid #f0f2f5; border-left:1px solid #e0e3e8; border-right:1px solid #e0e3e8;">
              No stock data available for this sector right now.
            </div>
            """, unsafe_allow_html=True)
        else:
            # 1. Compile all dynamic inner rows first
            stock_rows_html = ""
            max_stock_chg = max(abs(st_data['change']) for st_data in stocks) or 1

            for st_data in stocks:
                s_color  = "#00a854" if st_data['direction'] == 'up' else "#e53935"
                s_sign   = "+" if st_data['change'] >= 0 else ""
                s_bar_w  = (abs(st_data['change']) / max_stock_chg) * 70

                stock_rows_html += f"""
                <div style="display:grid; grid-template-columns:100px 1fr 70px 70px;
                align-items:center; gap:10px; padding:7px 14px 7px 32px;
                border-bottom:1px solid #f0f2f5; background:#fafffe;">
                  <div style="font-size:11px; font-weight:700; color:#3d4452;
                  font-family:'JetBrains Mono',monospace;">{st_data['sym']}</div>
                  <div style="height:5px; background:#f0f2f5; border-radius:3px; overflow:hidden;">
                    <div style="width:{s_bar_w:.1f}%; height:100%;
                    background:{s_color}; border-radius:3px; opacity:0.8;"></div>
                  </div>
                  <div style="font-size:11px; color:#7a8394; text-align:right;
                  font-family:'JetBrains Mono',monospace;">&#8377;{st_data['ltp']:,.1f}</div>
                  <div style="font-size:11px; font-weight:700; text-align:right;
                  color:{s_color}; font-family:'JetBrains Mono',monospace;">
                    {s_sign}{st_data['change']:.2f}%
                  </div>
                </div>
                """

            total_count = len(get_stocks_by_sector(sector_name))

            # 2. Render everything together inside a single wrapper markdown container
            st.markdown(f"""
            <div style="border-left:1px solid #e0e3e8; border-right:1px solid #e0e3e8; 
            border-bottom:1px solid #e0e3e8; overflow:hidden; background:#fafffe; margin-top:-2px;">
              
              <div style="display:grid; grid-template-columns:100px 1fr 70px 70px;
              gap:10px; padding:6px 14px 6px 32px; background:#f0faf5;
              border-bottom:1px solid #e0e3e8;">
                <div style="font-size:9px; font-weight:700; color:#7a8394;
                letter-spacing:0.08em; text-transform:uppercase;">Stock</div>
                <div style="font-size:9px; font-weight:700; color:#7a8394;
                letter-spacing:0.08em; text-transform:uppercase;">Move</div>
                <div style="font-size:9px; font-weight:700; color:#7a8394;
                letter-spacing:0.08em; text-transform:uppercase; text-align:right;">LTP</div>
                <div style="font-size:9px; font-weight:700; color:#7a8394;
                letter-spacing:0.08em; text-transform:uppercase; text-align:right;">Chg %</div>
              </div>
              
              {stock_rows_html}
              
              <div style="padding:7px 14px 7px 32px; font-size:10px; color:#7a8394;
              background:#fafbfc;">
                Showing top 8 of {total_count} stocks in {sector_name}
              </div>
            </div>
            """, unsafe_allow_html=True)

# Chart bottom footer — matches original style
st.markdown(f"""
<div style="background:#fafbfc; border:1px solid #e0e3e8; border-top:none;
border-radius:0 0 10px 10px; padding:8px 14px; font-size:10px;
color:#7a8394; text-align:right;">
  TradeSentry • {updated}
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# SECTION 10 — Supplementary Data Table Expander
# Purpose : Show raw sector data as a sortable Streamlit dataframe
#           inside a collapsible expander at the bottom of the page
# NOTE    : UNCHANGED — do not modify
# ──────────────────────────────────────────────────────────────────
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
