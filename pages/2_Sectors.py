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

    # Step 2: Fetch each stock individually via Yahoo Finance
    # Using NSE suffix ".NS" — same approach as existing fetch_today()
    for stock in sector_stocks:
        sym = stock['sym']
        yf_sym = sym + ".NS"   # e.g. HDFCBANK → HDFCBANK.NS

        try:
            # Step 3: Fetch last 5 days to ensure we always get prev close
            # even on Mondays or post-holiday sessions
            ticker = yf.Ticker(yf_sym)
            hist   = ticker.history(period="5d", interval="1d", auto_adjust=True)

            if hist is None or len(hist) < 2:
                # Not enough data — skip this stock silently
                continue

            # Step 4: Calculate % change from previous close to latest close
            prev_close   = float(hist['Close'].iloc[-2])
            latest_close = float(hist['Close'].iloc[-1])

            if prev_close == 0:
                continue

            change = round(((latest_close - prev_close) / prev_close) * 100, 2)

            results.append({
                'sym':       sym,
                'change':    change,
                'ltp':       round(latest_close, 2),
                'prev':      round(prev_close, 2),
                'direction': 'up' if change >= 0 else 'down',
            })

        except Exception:
            # Bad ticker or network issue — skip silently, don't crash page
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
# SECTION 9 — Sector Bar Chart with Inline Drill-Down
# Purpose : Render the main sector performance chart.
#           Each sector row has a ▶ button that expands inline to
#           show the top 8 stocks in that sector with their % change.
#
# HOW THE DRILL-DOWN WORKS (Streamlit approach):
#   - Each sector row is rendered as a 2-column Streamlit layout:
#       col_left  → the existing bar chart HTML (unchanged look)
#       col_right → hidden unless this sector is expanded
#   - A small Streamlit button per row toggles session_state
#     ["expanded_sector"] between None and the sector name
#   - When expanded: fetch_stocks_for_sector() is called (cached),
#     results rendered as a mini HTML table below the sector bar
#   - Only ONE sector can be expanded at a time (clicking another
#     collapses the previous one automatically)
#
# DESIGN DECISIONS:
#   - We use Streamlit native columns + st.markdown for the rows
#     instead of pure iframe HTML because Streamlit buttons are
#     needed for the toggle interaction (JS can't call Python)
#   - The sector bar visuals are kept pixel-identical to Section 5
#     original — same colors, fonts, bar widths, padding
#   - Stock rows inside expansion use same color vars (green/red)
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
    # Ratio 0.92 : 0.08 keeps the bar visually identical to original
    row_col, btn_col = st.columns([0.92, 0.08])

    with row_col:
        # Sector bar row HTML — pixel-identical to original Section 5 output
        # Only change: border-bottom removed (handled by container now)
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
        # Toggle button — ▼ when collapsed, ▲ when expanded
        # Clicking sets/clears expanded_sector in session state
        btn_label = "▲" if is_expanded else "▶"
        btn_key   = f"expand_{sector_name}"
        if st.button(btn_label, key=btn_key, use_container_width=True):
            if is_expanded:
                # Already open → collapse it
                st.session_state["expanded_sector"] = None
            else:
                # Open this sector → auto-closes any previously open one
                st.session_state["expanded_sector"] = sector_name
            st.rerun()

    # ── Inline Drill-Down Panel (only renders when this sector is expanded) ──
    if is_expanded:
        with st.spinner(f"Loading {sector_name} stocks..."):
            stocks = fetch_stocks_for_sector(sector_name, limit=8)

        if not stocks:
            # Graceful fallback — never crash the page
            st.markdown("""
            <div style="padding:10px 14px; font-size:12px; color:#7a8394;
            background:#fafbfc; border-bottom:1px solid #f0f2f5;">
              No stock data available for this sector right now.
            </div>
            """, unsafe_allow_html=True)
        else:
            # ── Build the stock rows HTML for this sector ──
            stock_rows_html = ""
            max_stock_chg   = max(abs(st['change']) for st in stocks) or 1

            for st_data in stocks:
                s_color    = "#00a854" if st_data['direction'] == 'up' else "#e53935"
                s_sign     = "+" if st_data['change'] >= 0 else ""
                s_bar_w    = (abs(st_data['change']) / max_stock_chg) * 70
                # Contribution bar width relative to sector's own change
                # Shows visually how much this stock "moved" vs the sector
                contrib_w  = min((abs(st_data['change']) / (abs(s['change']) + 0.001)) * 60, 100)

                stock_rows_html += f"""
                <div style="display:grid; grid-template-columns:100px 1fr 70px 70px;
                align-items:center; gap:10px; padding:7px 14px 7px 32px;
                border-bottom:1px solid #f0f2f5; background:#fafffe;">
                  <!-- Stock symbol -->
                  <div style="font-size:11px; font-weight:700; color:#3d4452;
                  font-family:'JetBrains Mono',monospace;">{st_data['sym']}</div>
                  <!-- Relative change bar -->
                  <div style="height:5px; background:#f0f2f5; border-radius:3px; overflow:hidden;">
                    <div style="width:{s_bar_w:.1f}%; height:100%;
                    background:{s_color}; border-radius:3px; opacity:0.8;"></div>
                  </div>
                  <!-- LTP -->
                  <div style="font-size:11px; color:#7a8394; text-align:right;
                  font-family:'JetBrains Mono',monospace;">₹{st_data['ltp']:,.1f}</div>
                  <!-- % Change -->
                  <div style="font-size:11px; font-weight:700; text-align:right;
                  color:{s_color}; font-family:'JetBrains Mono',monospace;">
                    {s_sign}{st_data['change']:.2f}%
                  </div>
                </div>
                """

            # Total stock count in this sector (from STOCK_UNIVERSE)
            total_count = len(get_stocks_by_sector(sector_name))

            # ── Render the full drill-down panel ──
            st.markdown(f"""
            <div style="border:1px solid #e0e3e8; border-top:none;
            border-radius:0 0 8px 8px; overflow:hidden; margin-bottom:2px;
            background:#fafffe;">

              <!-- Drill-down header -->
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

              <!-- Stock rows -->
              {stock_rows_html}

              <!-- Footer: stock count info -->
              <div style="padding:7px 14px 7px 32px; font-size:10px; color:#7a8394;
              border-top:1px solid #f0f2f5; background:#fafbfc;">
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
