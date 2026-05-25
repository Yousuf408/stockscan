import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import time
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from stocks import SECTOR_YAHOO

st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")
apply_styles()
sidebar_brand()
page_header("Sector Performance", "📊 NSE INDICES — LIVE")

col1, col2 = st.columns([8, 1])
with col2:
    if st.button("⟳ Refresh"):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=30)
def fetch_sector_data():
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval=1d&range=1d"
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok: continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                pc = meta.get('chartPreviousClose', 0)
                change = ((cp - pc) / pc * 100) if pc else 0.0
                data.append({'name': name, 'change': round(change, 2),
                              'direction': 'up' if change >= 0 else 'down',
                              'ltp': round(cp, 2), 'prev': round(pc, 2)})
        except: continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

with st.spinner("Fetching live sector data..."):
    data = fetch_sector_data()

if not data:
    st.error("⚠️ Could not fetch sector data. Please refresh.")
    st.stop()

gainers = [s for s in data if s['direction'] == 'up']
losers  = [s for s in data if s['direction'] == 'down']
top     = data[0]
bottom  = data[-1]
max_chg = max(abs(s['change']) for s in data) or 1

rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 85
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    bg    = "#f0faf5" if s['direction'] == 'up' else "#fff5f5"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
    <div style="display:grid;grid-template-columns:90px 1fr 68px;align-items:center;
    gap:12px;padding:8px 12px;border-bottom:1px solid #f0f2f5;
    background:{bg if abs(s['change']) > 1 else '#fff'};transition:background 0.2s;">
      <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;
      color:#3d4452;font-family:'JetBrains Mono',monospace;">{s['name']}</div>
      <div style="height:8px;background:#f0f2f5;border-radius:4px;overflow:hidden;
      border:1px solid #e8eaed;">
        <div style="width:{bar_w:.1f}%;height:100%;background:{color};
        border-radius:4px;transition:width 0.5s ease;"></div>
      </div>
      <div style="font-size:12px;font-weight:700;text-align:right;
      color:{color};font-family:'JetBrains Mono',monospace;">{sign}{s['change']}%</div>
    </div>"""

updated = time.strftime("%H:%M:%S")

html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#f8f9fb; font-family:'Inter',sans-serif; color:#0f1117; }}
.metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:14px; }}
.card {{ background:#fff; border:1px solid #e0e3e8; border-radius:12px;
  padding:14px 18px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }}
.label {{ font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase;
  color:#7a8394; margin-bottom:6px; }}
.value {{ font-size:15px; font-weight:700; font-family:'JetBrains Mono',monospace; }}
.chart-wrap {{ background:#fff; border:1px solid #e0e3e8; border-radius:12px;
  overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.06); }}
.footer {{ padding:8px 12px; font-size:10px; color:#7a8394; text-align:right;
  border-top:1px solid #f0f2f5; background:#f8f9fb; }}
</style></head><body>
<div class="metrics">
  <div class="card">
    <div class="label">Top Gainer</div>
    <div class="value" style="color:#00a854;">▲ {top['name']} {top['change']:+.2f}%</div>
  </div>
  <div class="card">
    <div class="label">Top Loser</div>
    <div class="value" style="color:#e53935;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
  </div>
  <div class="card">
    <div class="label">Market Breadth</div>
    <div class="value">
      <span style="color:#00a854;">{len(gainers)} up</span>
      <span style="color:#cdd1d8;"> / </span>
      <span style="color:#e53935;">{len(losers)} down</span>
    </div>
  </div>
</div>
<div class="chart-wrap">
  {rows_html}
  <div class="footer">Updated: {updated} &nbsp;·&nbsp; Auto-refresh: 30s &nbsp;·&nbsp; Source: Yahoo Finance</div>
</div>
</body></html>"""

components.html(html, height=len(data) * 40 + 180, scrolling=False)

with st.expander("📋 Raw Data Table"):
    df = pd.DataFrame(data)[['name','ltp','prev','change']]
    df.columns = ['Sector','LTP (₹)','Prev Close (₹)','Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",
            unsafe_allow_html=True)