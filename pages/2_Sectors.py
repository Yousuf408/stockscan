import streamlit as st
import requests
import pandas as pd
import time

st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")

# ══════════════════════════════════════════
#  TRADESENTRY — CSS (matches extension exactly)
# ══════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600&display=swap');

:root {
  --bg:#0a0a0f; --bg2:#111118; --bg3:#1a1a24;
  --border:#ffffff12; --border2:#ffffff22;
  --green:#00e676; --green-dim:#00e67620;
  --red:#ff4444; --red-dim:#ff444420;
  --amber:#ffab00; --amber-dim:#ffab0020;
  --blue:#448aff; --blue-dim:#448aff18;
  --text:#e8e8f0; --text2:#c8c8d8; --text3:#888899;
  --mono:'JetBrains Mono',monospace;
}

/* Hide Streamlit default UI */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
.stApp { background: var(--bg); color: var(--text); font-family: var(--mono); }

/* ── HEADER ── */
.ts-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px; background: var(--bg2);
  border-bottom: 1px solid var(--border);
}
.ts-logo { font-family: var(--mono); font-size: 14px; font-weight: 700; letter-spacing: 0.08em; }
.ts-logo span { color: var(--green); }
.ts-badge {
  font-size: 10px; font-family: var(--mono); color: var(--text3);
  background: var(--bg3); padding: 3px 10px; border-radius: 20px;
  border: 1px solid var(--border);
}

/* ── PAGE TITLE BAR ── */
.ts-titlebar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 18px; background: var(--bg2);
  border-bottom: 1px solid var(--border);
}
.ts-page-title {
  font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
  color: var(--text2); font-family: var(--mono);
}
.ts-refresh-note {
  font-size: 9px; color: var(--text3); font-family: var(--mono);
}

/* ── SECTOR CHART CONTAINER ── */
.sector-chart-wrap {
  padding: 14px 18px;
}

/* ── SECTOR ROW ── */
.sector-row {
  display: grid;
  grid-template-columns: 100px 1fr 60px;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
  animation: slideUp 0.3s ease;
}
.sector-row:last-child { border-bottom: none; }
@keyframes slideUp { from{opacity:0;transform:translateX(-6px)} to{opacity:1;transform:translateX(0)} }

.sector-name {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  color: var(--text2); font-family: var(--mono);
  white-space: nowrap;
}
.sector-bar-track {
  height: 6px; background: var(--bg3);
  border-radius: 3px; overflow: hidden;
  border: 1px solid var(--border);
}
.sector-bar-fill {
  height: 100%; border-radius: 3px;
  transition: width 0.6s ease;
}
.sector-change {
  font-size: 11px; font-weight: 700;
  font-family: var(--mono);
  text-align: right; white-space: nowrap;
}

/* ── SUMMARY METRICS ── */
.metrics-row {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 10px; padding: 12px 18px;
  border-bottom: 1px solid var(--border);
}
.metric-card {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px;
}
.metric-label {
  font-size: 9px; color: var(--text3); font-family: var(--mono);
  letter-spacing: 0.1em; margin-bottom: 4px;
}
.metric-value {
  font-size: 13px; font-weight: 700; font-family: var(--mono); color: var(--text);
}
.metric-value.green { color: var(--green); }
.metric-value.red   { color: var(--red); }

/* ── EMPTY / LOADING ── */
.empty-state {
  text-align: center; padding: 40px;
  color: var(--text3); font-family: var(--mono); font-size: 12px; line-height: 2;
}

/* ── ERROR ── */
.error-box {
  background: var(--red-dim); border: 1px solid #ff444444;
  border-radius: 6px; padding: 10px 14px;
  font-family: var(--mono); font-size: 11px; color: var(--red);
  margin: 14px 18px;
}

/* ── LAST UPDATED ── */
.last-updated {
  font-size: 9px; color: var(--text3); font-family: var(--mono);
  padding: 6px 18px; text-align: right;
}

/* Streamlit button override */
div[data-testid="stButton"] button {
  background: var(--bg3) !important; border: 1px solid var(--border2) !important;
  color: var(--text2) !important; font-family: var(--mono) !important;
  font-size: 10px !important; font-weight: 700 !important;
  letter-spacing: 0.08em !important; padding: 4px 12px !important;
  border-radius: 5px !important; transition: all 0.2s !important;
}
div[data-testid="stButton"] button:hover {
  border-color: var(--green) !important; color: var(--green) !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
#  SECTOR_YAHOO MAPPING (from stocks.js)
# ══════════════════════════════════════════
SECTOR_YAHOO = {
    'BANK':      '^NSEBANK',
    'IT':        '^CNXIT',
    'AUTO':      '^CNXAUTO',
    'PHARMA':    '^CNXPHARMA',
    'FMCG':      '^CNXFMCG',
    'METAL':     '^CNXMETAL',
    'ENERGY':    '^CNXENERGY',
    'INFRA':     '^CNXINFRA',
    'REALTY':    '^CNXREALTY',
    'MEDIA':     '^CNXMEDIA',
    'FINSERV':   '^CNXFIN',
    'CONSUME':   '^CNXCONSUM',
    'CHEM':      '^CNXMETAL',
    'TELECOM':   '^CNXMEDIA',
    'DEFENCE':   '^CNXINFRA',
    'LOGISTICS': '^CNXINFRA',
}

# ══════════════════════════════════════════
#  FETCH SECTOR DATA (same logic as sectortab.js)
# ══════════════════════════════════════════
@st.cache_data(ttl=30)  # Cache 30 seconds — same as extension's auto-refresh
def fetch_sector_data():
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval=1d&range=1d"
            resp = requests.get(url, headers=headers, timeout=5)

            if not resp.ok:
                continue

            json_data = resp.json()
            meta = json_data.get('chart', {}).get('result', [{}])[0].get('meta', {})

            if meta:
                current_price   = meta.get('regularMarketPrice', 0)
                previous_close  = meta.get('chartPreviousClose', 0)

                change = 0.0
                if previous_close and previous_close != 0:
                    change = ((current_price - previous_close) / previous_close) * 100

                data.append({
                    'name':      name,
                    'symbol':    symbol,
                    'change':    round(change, 2),
                    'direction': 'up' if change >= 0 else 'down',
                    'ltp':       round(current_price, 2),
                    'prev':      round(previous_close, 2),
                })
        except Exception:
            continue

    # Sort highest to lowest (same as extension)
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

# ══════════════════════════════════════════
#  RENDER SECTOR CHART HTML
# ══════════════════════════════════════════
def render_sector_chart(data):
    if not data:
        return '<div class="empty-state"><div>📊</div><div>No sector data available</div></div>'

    max_change = max(abs(s['change']) for s in data) or 1
    bar_max = 90  # Max bar width % — same as extension

    rows_html = ""
    for s in data:
        bar_width  = (abs(s['change']) / max_change) * bar_max
        color      = "#00e676" if s['direction'] == 'up' else "#ff4444"
        sign       = "+" if s['change'] >= 0 else ""

        rows_html += f"""
        <div class="sector-row">
          <div class="sector-name">{s['name']}</div>
          <div class="sector-bar-track">
            <div class="sector-bar-fill" style="width:{bar_width:.1f}%;background:{color};"></div>
          </div>
          <div class="sector-change" style="color:{color};">{sign}{s['change']}%</div>
        </div>
        """

    return f'<div class="sector-chart-wrap">{rows_html}</div>'

# ══════════════════════════════════════════
#  SUMMARY METRICS
# ══════════════════════════════════════════
def render_metrics(data):
    if not data:
        return ""

    gainers = [s for s in data if s['direction'] == 'up']
    losers  = [s for s in data if s['direction'] == 'down']
    top     = data[0]   if data else None
    bottom  = data[-1]  if data else None

    top_html    = f'<div class="metric-value green">▲ {top["name"]} {top["change"]:+.2f}%</div>'    if top    else ""
    bottom_html = f'<div class="metric-value red">▼ {bottom["name"]} {bottom["change"]:+.2f}%</div>' if bottom else ""

    return f"""
    <div class="metrics-row">
      <div class="metric-card">
        <div class="metric-label">TOP GAINER</div>
        {top_html}
      </div>
      <div class="metric-card">
        <div class="metric-label">TOP LOSER</div>
        {bottom_html}
      </div>
      <div class="metric-card">
        <div class="metric-label">MARKET BREADTH</div>
        <div class="metric-value">
          <span style="color:#00e676;">{len(gainers)}↑</span>
          <span style="color:#888899;"> / </span>
          <span style="color:#ff4444;">{len(losers)}↓</span>
        </div>
      </div>
    </div>
    """

# ══════════════════════════════════════════
#  PAGE RENDER
# ══════════════════════════════════════════

# Header
st.markdown("""
<div class="ts-header">
  <div class="ts-logo">TRADE<span>SENTRY</span></div>
  <div class="ts-badge">📊 SECTOR PERFORMANCE</div>
</div>
""", unsafe_allow_html=True)

# Title bar + Refresh button
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.markdown("""
    <div style="padding:10px 18px 0;font-size:11px;font-weight:700;
    letter-spacing:0.12em;color:#888899;font-family:'JetBrains Mono',monospace;">
      📊 SECTOR PERFORMANCE — NSE INDICES
    </div>
    """, unsafe_allow_html=True)
with col_btn:
    refresh = st.button("⟳ REFRESH", key="sector_refresh")

if refresh:
    st.cache_data.clear()

# ── FETCH & RENDER ──
with st.spinner(""):
    data = fetch_sector_data()

if not data:
    st.markdown("""
    <div class="error-box">
      ⚠️ Failed to fetch sector data. Yahoo Finance may be rate-limiting.
      Try refreshing in a few seconds.
    </div>
    """, unsafe_allow_html=True)
else:
    # Summary metrics row
    st.markdown(render_metrics(data), unsafe_allow_html=True)

    # Sector bar chart
    st.markdown(render_sector_chart(data), unsafe_allow_html=True)

    # Last updated
    st.markdown(
        f'<div class="last-updated">⟳ Last updated: {time.strftime("%H:%M:%S")} &nbsp;|&nbsp; Auto-refresh every 30s</div>',
        unsafe_allow_html=True
    )

    # ── DATA TABLE (collapsible) ──
    with st.expander("📋 VIEW RAW DATA TABLE", expanded=False):
        df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change', 'direction']]
        df.columns = ['Sector', 'LTP', 'Prev Close', 'Change %', 'Direction']
        df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")

        def color_change(val):
            color = '#00e676' if '+' in str(val) else '#ff4444'
            return f'color: {color}; font-weight: bold; font-family: monospace;'

        styled = df.style.applymap(color_change, subset=['Change %'])
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ── AUTO REFRESH every 30s ──
st.markdown("""
<script>
setTimeout(() => { window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)
