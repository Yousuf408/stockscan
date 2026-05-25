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
    "1D":  ("1 Day",    1),
    "1W":  ("1 Week",   7),
    "1M":  ("1 Month",  30),
    "3M":  ("3 Months", 90),
    "6M":  ("6 Months", 180),
    "1Y":  ("1 Year",   365),
}

# ── Read timeframe from query params (set by JS inside iframe) ─────────────────
params   = st.query_params
tf_key   = params.get("tf", "1D")
if tf_key not in TIMEFRAMES:
    tf_key = "1D"
tf_label, days = TIMEFRAMES[tf_key]

# ── Handle refresh flag from query params ──────────────────────────────────────
if params.get("refresh", "0") == "1":
    st.cache_data.clear()
    st.query_params["refresh"] = "0"

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

# ── Fetch data ─────────────────────────────────────────────────────────────────
if days == 1:
    with st.spinner("Fetching live sector data..."):
        data = fetch_today()
    period_label = "Today's Performance"
    col_start    = "Prev Close"
else:
    from_dt = today - datetime.timedelta(days=days)
    with st.spinner(f"Fetching {tf_label} data..."):
        data = fetch_range(str(from_dt), str(today))
    period_label = f"{from_dt.strftime('%d %b %Y')}  →  {today.strftime('%d %b %Y')}"
    col_start    = "Start Price"

if not data:
    st.error("Could not fetch sector data. Please try again.")
    st.stop()

# ── Computed values ────────────────────────────────────────────────────────────
gainers = [s for s in data if s['direction'] == 'up']
losers  = [s for s in data if s['direction'] == 'down']
top     = data[0]
bottom  = data[-1]
max_chg = max(abs(s['change']) for s in data) or 1
updated = time.strftime("%H:%M:%S")

# ── Build sector bar rows ──────────────────────────────────────────────────────
rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 85
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
      <div class="row">
        <div class="row-name">{s['name']}</div>
        <div class="row-bar-bg">
          <div style="width:{bar_w:.1f}%;height:100%;background:{color};border-radius:4px;"></div>
        </div>
        <div class="row-pct" style="color:{color};">{sign}{s['change']}%</div>
      </div>"""

# ── Build timeframe option tags ────────────────────────────────────────────────
tf_options = ""
for key, (label, _) in TIMEFRAMES.items():
    selected = 'selected' if key == tf_key else ''
    tf_options += f'<option value="{key}" {selected}>{label}</option>'

# ── Full HTML — 5 cards + chart, all in one iframe ────────────────────────────
html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background:#f0f2f5;
    font-family:'Inter','Segoe UI',sans-serif;
    padding:2px 0;
  }}

  /* ── 5-card top row ── */
  .top-row {{
    display:grid;
    grid-template-columns: 1fr 1fr 1fr 1.4fr auto;
    gap:10px;
    margin-bottom:12px;
  }}

  .card {{
    background:#fff;
    border:1px solid #e0e3e8;
    border-radius:10px;
    padding:14px 16px;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
    display:flex;
    flex-direction:column;
    justify-content:space-between;
    min-height:78px;
  }}

  .card-label {{
    font-size:9.5px;
    font-weight:700;
    letter-spacing:0.09em;
    text-transform:uppercase;
    color:#9aa3b0;
    margin-bottom:8px;
  }}

  .card-value {{
    font-size:14px;
    font-weight:700;
    font-family:'Courier New',monospace;
    white-space:nowrap;
  }}

  /* Timeframe card */
  .tf-card {{
    background:#fff;
    border:1px solid #e0e3e8;
    border-radius:10px;
    padding:14px 16px;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
    display:flex;
    flex-direction:column;
    justify-content:space-between;
    min-height:78px;
  }}

  select {{
    margin-top:6px;
    width:100%;
    padding:5px 8px;
    border:1px solid #e0e3e8;
    border-radius:6px;
    font-size:12px;
    font-family:'Inter',sans-serif;
    color:#3d4452;
    background:#fafbfc;
    cursor:pointer;
    outline:none;
    appearance:auto;
  }}

  select:focus {{ border-color:#4a90e2; }}

  /* Refresh card */
  .refresh-card {{
    background:#fff;
    border:1px solid #e0e3e8;
    border-radius:10px;
    padding:14px 16px;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
    display:flex;
    align-items:center;
    justify-content:center;
    min-height:78px;
    min-width:90px;
  }}

  .refresh-btn {{
    background:#f8f9fa;
    border:1px solid #e0e3e8;
    border-radius:7px;
    padding:7px 14px;
    font-size:12px;
    font-weight:600;
    color:#3d4452;
    cursor:pointer;
    display:flex;
    align-items:center;
    gap:5px;
    transition:background 0.15s, border-color 0.15s;
    white-space:nowrap;
  }}

  .refresh-btn:hover {{
    background:#e8f4fd;
    border-color:#4a90e2;
    color:#4a90e2;
  }}

  /* ── Chart section ── */
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
    grid-template-columns:90px 1fr 68px;
    align-items:center;
    gap:12px;
    padding:8px 12px;
    border-bottom:1px solid #f0f2f5;
  }}

  .row:last-of-type {{ border-bottom:none; }}

  .row-name {{
    font-size:11px;
    font-weight:700;
    color:#3d4452;
    font-family:'Courier New',monospace;
  }}

  .row-bar-bg {{
    height:8px;
    background:#f0f2f5;
    border-radius:4px;
    overflow:hidden;
  }}

  .row-pct {{
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
    border-top:1px solid #f0f2f5;
    background:#fafbfc;
  }}
</style>
</head><body>

<!-- 5 cards in one row -->
<div class="top-row">

  <!-- Top Gainer -->
  <div class="card">
    <div class="card-label">Top Gainer</div>
    <div class="card-value" style="color:#00a854;">▲ {top['name']} {top['change']:+.2f}%</div>
  </div>

  <!-- Top Loser -->
  <div class="card">
    <div class="card-label">Top Loser</div>
    <div class="card-value" style="color:#e53935;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
  </div>

  <!-- Breadth -->
  <div class="card">
    <div class="card-label">Breadth</div>
    <div class="card-value">
      <span style="color:#00a854;">{len(gainers)}↑</span>
      <span style="color:#cdd1d8;"> / </span>
      <span style="color:#e53935;">{len(losers)}↓</span>
    </div>
  </div>

  <!-- Timeframe dropdown -->
  <div class="tf-card">
    <div class="card-label">Timeframe</div>
    <select id="tfSelect" onchange="applyTF(this.value)">
      {tf_options}
    </select>
  </div>

  <!-- Refresh button -->
  <div class="refresh-card">
    <button class="refresh-btn" onclick="doRefresh()">⟳ Refresh</button>
  </div>

</div>

<!-- Bar chart -->
<div class="chart">
  <div class="chart-header">
    <span>📅 {period_label}</span>
    <span style="font-weight:400;font-size:10px;">Updated: {updated}</span>
  </div>
  {rows_html}
  <div class="footer">TradeSentry • {updated}</div>
</div>

<script>
  // Send selected timeframe to Streamlit via query param + location reload
  function applyTF(val) {{
    const url = new URL(window.parent.location.href);
    url.searchParams.set('tf', val);
    url.searchParams.delete('refresh');
    window.parent.location.href = url.toString();
  }}

  // Refresh: clear cache flag then reload
  function doRefresh() {{
    const url = new URL(window.parent.location.href);
    url.searchParams.set('refresh', '1');
    window.parent.location.href = url.toString();
  }}
</script>

</body></html>"""

components.html(html, height=len(data) * 40 + 175, scrolling=False)

# ── Data Table (unchanged) ─────────────────────────────────────────────────────
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
