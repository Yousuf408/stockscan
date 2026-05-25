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

# ── Top bar: Refresh button ───────────────────────────────────────────────────
col_title, col_refresh = st.columns([11, 1])
with col_refresh:
    if st.button("⟳ Refresh", key="sector_refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Mode selector + single calendar ──────────────────────────────────────────
mode_col, cal_col, spacer = st.columns([2, 2, 6])

with mode_col:
    view_mode = st.radio(
        "Mode",
        ["Today", "Custom Date"],
        label_visibility="collapsed",
        key="view_mode"
    )

# Only show calendar when Custom Date is selected
date_from = None
if view_mode == "Custom Date":
    with cal_col:
        date_from = st.date_input(
            "Start date",
            value=today - datetime.timedelta(days=30),
            min_value=datetime.date(2010, 1, 1),
            max_value=today - datetime.timedelta(days=1),
            label_visibility="collapsed",
            key="date_from"
        )

st.divider()

# ── TODAY mode: live fetch via Yahoo Finance chart API (original code) ────────
@st.cache_data(ttl=30)
def fetch_sector_data_today():
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{requests.utils.quote(symbol)}?interval=1d&range=1d"
            )
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok:
                continue
            meta = (
                resp.json()
                .get('chart', {})
                .get('result', [{}])[0]
                .get('meta', {})
            )
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                pc = meta.get('chartPreviousClose', 0)
                change = ((cp - pc) / pc * 100) if pc else 0.0
                data.append({
                    'name': name,
                    'change': round(change, 2),
                    'direction': 'up' if change >= 0 else 'down',
                    'ltp': round(cp, 2),
                    'prev': round(pc, 2)
                })
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data


# ── CUSTOM DATE mode: fetch via yfinance (from_date → today) ─────────────────
@st.cache_data(ttl=300)
def fetch_sector_data_range(from_date: str, to_date: str):
    data = []
    end = (datetime.date.fromisoformat(to_date) + datetime.timedelta(days=1)).isoformat()
    for name, symbol in SECTOR_YAHOO.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=from_date, end=end, interval="1d", auto_adjust=True)
            if hist.empty:
                continue
            if len(hist) == 1:
                open_p  = hist['Open'].iloc[0]
                close_p = hist['Close'].iloc[0]
                change  = ((close_p - open_p) / open_p * 100) if open_p else 0.0
                data.append({
                    'name': name, 'change': round(change, 2),
                    'direction': 'up' if change >= 0 else 'down',
                    'ltp': round(close_p, 2), 'prev': round(open_p, 2)
                })
                continue
            start_close = hist['Close'].iloc[0]
            end_close   = hist['Close'].iloc[-1]
            change = ((end_close - start_close) / start_close * 100) if start_close else 0.0
            data.append({
                'name': name, 'change': round(change, 2),
                'direction': 'up' if change >= 0 else 'down',
                'ltp': round(end_close, 2), 'prev': round(start_close, 2)
            })
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data


# ── Fetch ─────────────────────────────────────────────────────────────────────
if view_mode == "Today":
    with st.spinner("Fetching live sector data..."):
        data = fetch_sector_data_today()
    period_label = "Today's Performance"
    table_cols   = ['Sector', 'LTP', 'Prev Close', 'Change %']
else:
    with st.spinner(f"Fetching data from {date_from} to {today}..."):
        data = fetch_sector_data_range(str(date_from), str(today))
    period_label = f"Performance: {date_from.strftime('%d %b %Y')} → {today.strftime('%d %b %Y')}"
    table_cols   = ['Sector', 'End Price', 'Start Price', 'Change %']

if not data:
    st.error("Could not fetch sector data. Try a different date or check your connection.")
    st.stop()

# ── Build HTML chart (original rendering logic, untouched) ────────────────────
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
        <div style="width:{bar_w:.1f}%;height:100%;background:{color};
        border-radius:4px;"></div>
      </div>
      <div style="font-size:12px;font-weight:700;text-align:right;
      color:{color};font-family:'JetBrains Mono',monospace;">{sign}{s['change']}%</div>
    </div>"""

html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#f0f2f5; font-family:'Inter',sans-serif; }}
.metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:14px; }}
.card {{ background:#fff; border:1px solid #e0e3e8; border-radius:10px;
  padding:14px 18px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.label {{ font-size:10px; font-weight:600; letter-spacing:0.1em;
  text-transform:uppercase; color:#7a8394; margin-bottom:6px; }}
.value {{ font-size:15px; font-weight:700; font-family:'JetBrains Mono',monospace; }}
.chart {{ background:#fff; border:1px solid #e0e3e8; border-radius:10px;
  overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.chart-header {{ padding:10px 14px; font-size:11px; font-weight:600;
  color:#7a8394; background:#fafbfc; border-bottom:1px solid #f0f2f5; }}
.footer {{ padding:8px 12px; font-size:10px; color:#7a8394; text-align:right;
  border-top:1px solid #f0f2f5; }}
</style></head><body>
<div class="metrics">
  <div class="card"><div class="label">Top Gainer</div>
    <div class="value" style="color:#00a854;">▲ {top['name']} {top['change']:+.2f}%</div></div>
  <div class="card"><div class="label">Top Loser</div>
    <div class="value" style="color:#e53935;">▼ {bottom['name']} {bottom['change']:+.2f}%</div></div>
  <div class="card"><div class="label">Breadth</div>
    <div class="value"><span style="color:#00a854;">{len(gainers)}↑</span>
    <span style="color:#cdd1d8;"> / </span>
    <span style="color:#e53935;">{len(losers)}↓</span></div></div>
</div>
<div class="chart">
  <div class="chart-header">📅 {period_label}</div>
  {rows_html}
  <div class="footer">Updated: {updated}</div>
</div>
</body></html>"""

components.html(html, height=len(data) * 40 + 220)

# ── Data Table (original expander, unchanged) ─────────────────────────────────
with st.expander("📋 Data Table"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    df.columns = table_cols
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
