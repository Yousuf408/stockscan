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

# ── Timeframe state ───────────────────────────────────────────────────────────
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
if "do_refresh" not in st.session_state:
    st.session_state["do_refresh"] = False

# ── Data fetchers ─────────────────────────────────────────────────────────────
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
            hist = yf.Ticker(symbol).history(start=from_date, end=end,
                                             interval="1d", auto_adjust=True)
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

# ── Fetch based on selected timeframe ────────────────────────────────────────
tf = st.session_state["selected_tf"]
days = TIMEFRAMES[tf]

if days == 1:
    with st.spinner("Fetching live sector data..."):
        data = fetch_today()
    from_dt = today
    period_label = "Today's Performance"
    col_start = "Prev Close"
else:
    from_dt = today - datetime.timedelta(days=days)
    with st.spinner(f"Fetching {tf} sector data..."):
        data = fetch_range(str(from_dt), str(today))
    period_label = f"{from_dt.strftime('%d %b %Y')}  →  {today.strftime('%d %b %Y')}"
    col_start = "Start Price"

if not data:
    st.error("Could not fetch sector data. Please try again.")
    st.stop()

# ── Build chart values ────────────────────────────────────────────────────────
gainers = [s for s in data if s['direction'] == 'up']
losers  = [s for s in data if s['direction'] == 'down']
top     = data[0]
bottom  = data[-1]
max_chg = max(abs(s['change']) for s in data) or 1
updated = time.strftime("%H:%M:%S")

rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 85
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
    <div style="display:grid;grid-template-columns:90px 1fr 68px;align-items:center;
    gap:12px;padding:8px 12px;border-bottom:1px solid #f0f2f5;">
      <div style="font-size:11px;font-weight:700;color:#3d4452;
      font-family:'JetBrains Mono',monospace;">{s['name']}</div>
      <div style="height:8px;background:#f0f2f5;border-radius:4px;overflow:hidden;">
        <div style="width:{bar_w:.1f}%;height:100%;background:{color};border-radius:4px;"></div>
      </div>
      <div style="font-size:12px;font-weight:700;text-align:right;color:{color};
      font-family:'JetBrains Mono',monospace;">{sign}{s['change']}%</div>
    </div>"""

# Build JS callback string for timeframe buttons
tf_options_js = "\n".join([
    f'<option value="{k}" {"selected" if k == tf else ""}>{k}</option>'
    for k in TIMEFRAMES
])

html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#f0f2f5; font-family:'Inter',sans-serif; }}

.top-row {{
  display:grid;
  grid-template-columns:1fr 1fr 1fr;
  gap:10px;
  margin-bottom:14px;
  align-items:stretch;
}}

.card {{
  background:#fff;
  border:1px solid #e0e3e8;
  border-radius:10px;
  padding:14px 18px;
  box-shadow:0 1px 3px rgba(0,0,0,0.05);
}}

.label {{
  font-size:10px;
  font-weight:600;
  letter-spacing:0.1em;
  text-transform:uppercase;
  color:#7a8394;
  margin-bottom:6px;
}}

.value {{
  font-size:15px;
  font-weight:700;
  font-family:'JetBrains Mono',monospace;
}}

/* Breadth card with controls inline */
.breadth-card {{
  background:#fff;
  border:1px solid #e0e3e8;
  border-radius:10px;
  padding:14px 18px;
  box-shadow:0 1px 3px rgba(0,0,0,0.05);
  display:flex;
  flex-direction:column;
  justify-content:space-between;
}}

.breadth-top {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}}

.controls {{
  display:flex;
  align-items:center;
  gap:6px;
  margin-top:8px;
}}

select {{
  flex:1;
  padding:5px 8px;
  border:1px solid #e0e3e8;
  border-radius:6px;
  font-size:12px;
  font-family:'Inter',sans-serif;
  color:#3d4452;
  background:#fafbfc;
  cursor:pointer;
  outline:none;
}}

select:focus {{
  border-color:#4f8ef7;
}}

.refresh-btn {{
  padding:5px 10px;
  background:#fff;
  border:1px solid #e0e3e8;
  border-radius:6px;
  font-size:12px;
  cursor:pointer;
  color:#3d4452;
  white-space:nowrap;
  display:flex;
  align-items:center;
  gap:4px;
  transition:background 0.15s;
}}

.refresh-btn:hover {{ background:#f0f2f5; }}

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

.footer {{
  padding:8px 12px;
  font-size:10px;
  color:#7a8394;
  text-align:right;
  border-top:1px solid #f0f2f5;
}}
</style></head><body>

<div class="top-row">
  <!-- Top Gainer -->
  <div class="card">
    <div class="label">Top Gainer</div>
    <div class="value" style="color:#00a854;">▲ {top['name']} {top['change']:+.2f}%</div>
  </div>

  <!-- Top Loser -->
  <div class="card">
    <div class="label">Top Loser</div>
    <div class="value" style="color:#e53935;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
  </div>

  <!-- Breadth + Controls -->
  <div class="breadth-card">
    <div>
      <div class="label">Breadth</div>
      <div class="value">
        <span style="color:#00a854;">{len(gainers)}↑</span>
        <span style="color:#cdd1d8;"> / </span>
        <span style="color:#e53935;">{len(losers)}↓</span>
      </div>
    </div>
    <div class="controls">
      <select id="tfSelect" onchange="applyTF()">
        {tf_options_js}
      </select>
      <button class="refresh-btn" onclick="doRefresh()">⟳ Refresh</button>
    </div>
  </div>
</div>

<div class="chart">
  <div class="chart-header">
    <span>📅 {period_label}</span>
    <span style="font-weight:400;">Updated: {updated}</span>
  </div>
  {rows_html}
</div>

<script>
  function applyTF() {{
    const tf = document.getElementById('tfSelect').value;
    window.parent.postMessage({{type:'streamlit:setComponentValue', value:{{action:'tf', tf:tf}}}}, '*');
  }}
  function doRefresh() {{
    window.parent.postMessage({{type:'streamlit:setComponentValue', value:{{action:'refresh', tf: document.getElementById('tfSelect').value}}}}, '*');
  }}
</script>
</body></html>"""

# Render HTML component and capture interaction
result = components.html(html, height=len(data) * 40 + 260)

# ── Streamlit-side controls (hidden, driven by session state) ─────────────────
# Since postMessage from iframe has Streamlit limitations, use st widgets below
# placed invisibly — user interacts via the HTML dropdowns above.
st.markdown("<div style='display:none'>", unsafe_allow_html=True)

c1, c2 = st.columns([3, 1])
with c1:
    chosen = st.selectbox("TF", list(TIMEFRAMES.keys()),
                          index=list(TIMEFRAMES.keys()).index(st.session_state["selected_tf"]),
                          key="_tf_select_hidden",
                          label_visibility="collapsed")
with c2:
    if st.button("Refresh", key="_refresh_hidden"):
        st.cache_data.clear()
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

if chosen != st.session_state["selected_tf"]:
    st.session_state["selected_tf"] = chosen
    st.rerun()

# ── Data Table ────────────────────────────────────────────────────────────────
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
