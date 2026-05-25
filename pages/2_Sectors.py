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
from stocks import SECTOR_YAHOO

st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")
apply_styles()
sidebar_brand()
page_header("Sector Performance — NSE Indices")

today = datetime.date.today()

TIMEFRAMES = {
    "1 Day":    1,
    "1 Week":   7,
    "1 Month":  30,
    "3 Months": 90,
    "6 Months": 180,
    "1 Year":   365,
}

# ── Session state init ─────────────────────────────────────────────────────────
if "selected_tf" not in st.session_state:
    st.session_state["selected_tf"] = "1 Day"

# ── Inject CSS to style native Streamlit controls to match cards ───────────────
st.markdown("""
<style>
/* Remove default padding Streamlit adds around columns */
div[data-testid="column"] {
    padding: 0 4px !important;
}

/* Style the selectbox to look like a clean card control */
div[data-testid="stSelectbox"] > div > div {
    border: 1px solid #e0e3e8 !important;
    border-radius: 7px !important;
    background: #fafbfc !important;
    font-size: 13px !important;
    font-family: 'Inter', sans-serif !important;
    min-height: 38px !important;
    box-shadow: none !important;
}

div[data-testid="stSelectbox"] > div > div:focus-within {
    border-color: #4a90e2 !important;
    box-shadow: 0 0 0 2px rgba(74,144,226,0.15) !important;
}

/* Style the refresh button */
div[data-testid="stButton"] > button {
    background: #fafbfc !important;
    border: 1px solid #e0e3e8 !important;
    border-radius: 7px !important;
    color: #3d4452 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    width: 100% !important;
    height: 38px !important;
    transition: background 0.15s, border-color 0.15s, color 0.15s !important;
    box-shadow: none !important;
}

div[data-testid="stButton"] > button:hover {
    background: #e8f4fd !important;
    border-color: #4a90e2 !important;
    color: #4a90e2 !important;
}

/* Remove label space above selectbox */
div[data-testid="stSelectbox"] label {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── Data fetchers (logic completely unchanged) ─────────────────────────────────
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

# ── Fetch data based on current session timeframe ──────────────────────────────
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

# ── Row 1: 3 info cards (pure HTML display, no widgets) ───────────────────────
components.html(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:transparent; font-family:'Inter','Segoe UI',sans-serif; }}
  .row {{
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    gap:10px;
  }}
  .card {{
    background:#fff;
    border:1px solid #e0e3e8;
    border-radius:10px;
    padding:14px 18px;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
    min-height:72px;
  }}
  .label {{
    font-size:9.5px;
    font-weight:700;
    letter-spacing:0.09em;
    text-transform:uppercase;
    color:#9aa3b0;
    margin-bottom:8px;
  }}
  .value {{
    font-size:15px;
    font-weight:700;
    font-family:'Courier New',monospace;
  }}
</style></head><body>
<div class="row">
  <div class="card">
    <div class="label">Top Gainer</div>
    <div class="value" style="color:#00a854;">▲ {top['name']} {top['change']:+.2f}%</div>
  </div>
  <div class="card">
    <div class="label">Top Loser</div>
    <div class="value" style="color:#e53935;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
  </div>
  <div class="card">
    <div class="label">Breadth</div>
    <div class="value">
      <span style="color:#00a854;">{len(gainers)}↑</span>
      <span style="color:#cdd1d8;"> / </span>
      <span style="color:#e53935;">{len(losers)}↓</span>
    </div>
  </div>
</div>
</body></html>""", height=90)

# ── Row 2: Timeframe selectbox + Refresh button (native Streamlit, always works)
col_tf, col_refresh, col_space = st.columns([2, 1, 6])

with col_tf:
    chosen = st.selectbox(
        "Timeframe",
        list(TIMEFRAMES.keys()),
        index=list(TIMEFRAMES.keys()).index(st.session_state["selected_tf"]),
        key="tf_select"
    )

with col_refresh:
    # Vertical align the button with the selectbox
    st.markdown("<div style='margin-top:2px'>", unsafe_allow_html=True)
    refresh_clicked = st.button("⟳ Refresh", key="refresh_btn")
    st.markdown("</div>", unsafe_allow_html=True)

# Handle interactions — rerun only when needed
if refresh_clicked:
    st.cache_data.clear()
    st.rerun()

if chosen != st.session_state["selected_tf"]:
    st.session_state["selected_tf"] = chosen
    st.cache_data.clear()
    st.rerun()

# ── Row 3: Bar chart (pure HTML display) ───────────────────────────────────────
max_chg = max(abs(s['change']) for s in data) or 1

rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 85
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
      <div class="row">
        <div class="name">{s['name']}</div>
        <div class="bar-bg">
          <div style="width:{bar_w:.1f}%;height:100%;background:{color};border-radius:4px;"></div>
        </div>
        <div class="pct" style="color:{color};">{sign}{s['change']}%</div>
      </div>"""

components.html(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:transparent; font-family:'Inter','Segoe UI',sans-serif; }}
  .chart {{
    background:#fff;
    border:1px solid #e0e3e8;
    border-radius:10px;
    overflow:hidden;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
  }}
  .chart-header {{
    padding:10px 14px;
    font-size:11px;
    font-weight:600;
    color:#7a8394;
    background:#fafbfc;
    border-bottom:1px solid #f0f2f5;
    display:flex;
    justify-content:space-between;
    align-items:center;
  }}
  .row {{
    display:grid;
    grid-template-columns:90px 1fr 72px;
    align-items:center;
    gap:12px;
    padding:8px 14px;
    border-bottom:1px solid #f5f6f8;
  }}
  .name {{
    font-size:11px;
    font-weight:700;
    color:#3d4452;
    font-family:'Courier New',monospace;
  }}
  .bar-bg {{
    height:8px;
    background:#f0f2f5;
    border-radius:4px;
    overflow:hidden;
  }}
  .pct {{
    font-size:12px;
    font-weight:700;
    text-align:right;
    font-family:'Courier New',monospace;
  }}
  .footer {{
    padding:7px 14px;
    font-size:10px;
    color:#9aa3b0;
    text-align:right;
    background:#fafbfc;
    border-top:1px solid #f0f2f5;
  }}
</style></head><body>
<div class="chart">
  <div class="chart-header">
    <span>📅 {period_label}</span>
    <span style="font-weight:400;font-size:10px;">Updated: {updated}</span>
  </div>
  {rows_html}
  <div class="footer">TradeSentry • {updated}</div>
</div>
</body></html>""", height=len(data) * 40 + 80, scrolling=False)

# ── Data Table (unchanged) ─────────────────────────────────────────────────────
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
