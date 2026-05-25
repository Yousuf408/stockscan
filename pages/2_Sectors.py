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

# 1. Page Configuration
st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")
apply_styles()
sidebar_brand()
page_header("Sector Performance — NSE Indices")

# Inject a small CSS patch to make native Streamlit containers match your custom card styling exactly
st.markdown("""
<style>
    /* Force native containers to match custom card heights and styles */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    /* Clean up internal spacing for container inputs */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 2px 2px !important;
    }
</style>
""", unsafe_allow_html=True)

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

# 2. Data Fetchers
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

# 3. Handle Data Calculations
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

# 4. Interactive Layout Control Grid
c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])

with c1:
    st.markdown(f"""
    <div class="ts-metric" style="height: 90px;">
      <div class="ts-metric-label">Top Gainer</div>
      <div class="ts-metric-value" style="color:var(--green); font-size:16px; margin-top:4px;">▲ {top['name']} {top['change']:+.2f}%</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="ts-metric" style="height: 90px;">
      <div class="ts-metric-label">Top Loser</div>
      <div class="ts-metric-value" style="color:var(--red); font-size:16px; margin-top:4px;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="ts-metric" style="height: 90px;">
      <div class="ts-metric-label">Breadth</div>
      <div class="ts-metric-value" style="font-size:16px; margin-top:4px;">
        <span style="color:var(--green);">{len(gainers)}↑</span>
        <span style="color:var(--border2);"> / </span>
        <span style="color:var(--red);">{len(losers)}↓</span>
      </div>
    </div>""", unsafe_allow_html=True)

# Containerized interactive controls (guarantees operational click actions)
with c4:
    with st.container(border=True):
        st.markdown("<div style='font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:#7a8394; margin-bottom:2px;'>Timeframe</div>", unsafe_allow_html=True)
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
    with st.container(border=True):
        st.markdown("<div style='font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:transparent; margin-bottom:2px;'>Refresh</div>", unsafe_allow_html=True)
        if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

# 5. Native Bar Chart Generation Engine
max_chg = max(abs(s['change']) for s in data) or 1

rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 85
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
    <div style="display:grid;grid-template-columns:110px 1fr 75px;align-items:center;
    gap:12px;padding:10px 14px;border-bottom:1px solid #f0f2f5;">
      <div style="font-size:12px;font-weight:700;color:#3d4452;
      font-family:'JetBrains Mono',monospace;">{s['name']}</div>
      <div style="height:8px;background:#f0f2f5;border-radius:4px;overflow:hidden;">
        <div style="width:{bar_w:.1f}%;height:100%;background:{color};border-radius:4px;"></div>
      </div>
      <div style="font-size:12px;font-weight:700;text-align:right;color:{color};
      font-family:'JetBrains Mono',monospace;">{sign}{s['change']:.2f}%</div>
    </div>"""

html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#f0f2f5; font-family:'Inter',sans-serif; }}
.chart {{ background:#fff; border:1px solid #e0e3e8; border-radius:10px;
  overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.chart-header {{ padding:12px 14px; font-size:11px; font-weight:600; color:#7a8394;
  background:#fafbfc; border-bottom:1px solid #f0f2f5;
  display:flex; justify-content:space-between; align-items:center; }}
.footer {{ padding:8px 12px; font-size:10px; color:#7a8394; text-align:right;
  border-top:1px solid #f0f2f5; }}
</style></head><body>
<div class="chart">
  <div class="chart-header">
    <span>📅 {period_label}</span>
    <span style="font-weight:400;">Updated: {updated}</span>
  </div>
  {rows_html}
  <div class="footer">TradeSentry • {updated}</div>
</div>
</body></html>"""

components.html(html, height=len(data) * 44 + 100)

# 6. Supplementary Data Segment
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
