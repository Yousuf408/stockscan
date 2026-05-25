# ══════════════════════════════════════════
#  TRADESENTRY — pages/2_Sectors.py
#  UI only — all data imported from stocks.py
#  Logic: fetch Yahoo Finance sector indices
# ══════════════════════════════════════════

import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import time
import sys, os

# ── Import master data from stocks.py (root level) ──
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from stocks import SECTOR_YAHOO, get_all_sectors, get_sector_count

st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")

# ── Hide Streamlit chrome ──
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0.8rem 1rem 0 1rem !important; }
.stApp { background: #0a0a0f; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
#  FETCH SECTOR DATA (Yahoo Finance v8)
# ══════════════════════════════════════════
@st.cache_data(ttl=30)
def fetch_sector_data():
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval=1d&range=1d"
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok:
                continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                pc = meta.get('chartPreviousClose', 0)
                change = ((cp - pc) / pc * 100) if pc else 0.0
                data.append({
                    'name': name, 'symbol': symbol,
                    'change': round(change, 2),
                    'direction': 'up' if change >= 0 else 'down',
                    'ltp': round(cp, 2), 'prev': round(pc, 2),
                })
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

# ══════════════════════════════════════════
#  HEADER + REFRESH
# ══════════════════════════════════════════
col1, col2 = st.columns([6, 1])
with col1:
    st.markdown("""
    <div style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;
    color:#e8e8f0;padding:4px 0 10px 0;">
    TRADE<span style="color:#00e676;">SENTRY</span>
    <span style="font-size:11px;color:#888899;margin-left:12px;font-weight:400;">
    📊 SECTOR PERFORMANCE — NSE INDICES</span></div>
    """, unsafe_allow_html=True)
with col2:
    if st.button("⟳  REFRESH"):
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════
#  FETCH + RENDER
# ══════════════════════════════════════════
with st.spinner(""):
    data = fetch_sector_data()

if not data:
    st.error("⚠️ Failed to fetch sector data. Yahoo Finance may be rate-limiting. Try refreshing.")
    st.stop()

# Build metrics
gainers   = [s for s in data if s['direction'] == 'up']
losers    = [s for s in data if s['direction'] == 'down']
top       = data[0]
bottom    = data[-1]
max_chg   = max(abs(s['change']) for s in data) or 1

# Build sector rows HTML
rows_html = ""
for s in data:
    bar_w = (abs(s['change']) / max_chg) * 88
    color = "#00e676" if s['direction'] == 'up' else "#ff4444"
    sign  = "+" if s['change'] >= 0 else ""
    rows_html += f"""
    <div class="sector-row">
      <div class="sector-name">{s['name']}</div>
      <div class="sector-bar-track">
        <div class="sector-bar-fill" style="width:{bar_w:.1f}%;background:{color};"></div>
      </div>
      <div class="sector-change" style="color:{color};">{sign}{s['change']}%</div>
    </div>"""

updated = time.strftime("%H:%M:%S")

html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0a0a0f; color:#e8e8f0; font-family:'JetBrains Mono',monospace; }}
.metrics-row {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px; }}
.metric-card {{ background:#111118; border:1px solid #ffffff12; border-radius:8px; padding:12px 16px; }}
.metric-label {{ font-size:9px; color:#888899; letter-spacing:0.12em; margin-bottom:6px; }}
.metric-value {{ font-size:14px; font-weight:700; }}
.sector-row {{ display:grid; grid-template-columns:90px 1fr 64px; align-items:center;
  gap:12px; padding:7px 0; border-bottom:1px solid #ffffff0a; }}
.sector-row:last-child {{ border-bottom:none; }}
.sector-name {{ font-size:10px; font-weight:700; letter-spacing:0.08em; color:#c8c8d8; }}
.sector-bar-track {{ height:7px; background:#1a1a24; border-radius:4px;
  overflow:hidden; border:1px solid #ffffff10; }}
.sector-bar-fill {{ height:100%; border-radius:4px; }}
.sector-change {{ font-size:11px; font-weight:700; text-align:right; }}
.footer {{ margin-top:12px; font-size:9px; color:#555566; text-align:right; letter-spacing:0.06em; }}
</style></head><body>
<div class="metrics-row">
  <div class="metric-card">
    <div class="metric-label">TOP GAINER</div>
    <div class="metric-value" style="color:#00e676;">▲ {top['name']} {top['change']:+.2f}%</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">TOP LOSER</div>
    <div class="metric-value" style="color:#ff4444;">▼ {bottom['name']} {bottom['change']:+.2f}%</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">MARKET BREADTH</div>
    <div class="metric-value">
      <span style="color:#00e676;">{len(gainers)}↑</span>
      <span style="color:#555566;"> / </span>
      <span style="color:#ff4444;">{len(losers)}↓</span>
    </div>
  </div>
</div>
{rows_html}
<div class="footer">⟳ Updated: {updated} &nbsp;|&nbsp; Data: Yahoo Finance &nbsp;|&nbsp; Auto-refresh: 30s</div>
</body></html>"""

components.html(html, height=len(data) * 38 + 160, scrolling=False)

# Raw table
with st.expander("📋 Raw Data Table"):
    df = pd.DataFrame(data)[['name','ltp','prev','change']]
    df.columns = ['Sector','LTP','Prev Close','Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)

# Auto-refresh 30s
st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",
            unsafe_allow_html=True)
