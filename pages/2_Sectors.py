import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import time
import datetime
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from stocks import SECTOR_YAHOO, get_stocks_by_sector

# 1. Page Configuration
st.set_page_config(page_title="TradeSentry — Sectors", layout="wide", page_icon="📊")
apply_styles()
sidebar_brand()
page_header("Sector Performance — NSE Indices")

# Global CSS Overrides for absolute white layout canvas & crisp progress bars
st.markdown("""
<style>
    .stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"] {
        background-color: #ffffff !important;
    }
    
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

    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: none !important;
    }
    
    div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlock"] {
        gap: 0rem !important;
    }

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

    /* Custom CSS components mimicking your UI design mock-up */
    .sector-row {
        background: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 6px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    .sector-row-active {
        background: #f0faf5;
        border: 1px solid #00a85440;
        border-radius: 8px 8px 0px 0px;
        padding: 12px 16px;
        margin-bottom: 0px;
    }
    .breakdown-container {
        background: #ffffff;
        border-left: 1px solid #00a85440;
        border-right: 1px solid #00a85440;
        border-bottom: 1px solid #00a85440;
        border-radius: 0px 0px 8px 8px;
        padding: 16px 24px;
        margin-bottom: 12px;
    }
    .bar-track {
        height: 6px;
        background: #f0f2f5;
        border-radius: 3px;
        overflow: hidden;
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
if "expanded_sector" not in st.session_state:
    st.session_state["expanded_sector"] = None

# 2. Data Fetchers
@st.cache_data(ttl=30)
def fetch_today():
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
                data.append({'name': name, 'symbol': symbol, 'change': round(change, 2),
                             'direction': 'up' if change >= 0 else 'down',
                             'ltp': round(cp, 2), 'prev': round(pc, 2)})
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

@st.cache_data(ttl=30)
def fetch_top_stocks_for_sector(sector_name, days):
    """Fetch performance for underlying symbols from stock universe mapping file."""
    stocks = get_stocks_by_sector(sector_name)
    if not stocks:
        return []
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    stock_perf = []
    
    # Batch processing via Yahoo Finance for speed optimization
    symbols_list = [f"{s['sym']}.NS" for s in stocks[:12]] # Limit to top 12 for UI performance
    symbols_str = " ".join(symbols_list)
    
    period = "1d" if days == 1 else f"{days}d"
    try:
        tickers = yf.Tickers(symbols_str)
        for s in stocks[:12]:
            sym = f"{s['sym']}.NS"
            hist = tickers.tickers[sym].history(period=period)
            if not hist.empty:
                start_p = hist['Close'].iloc[0]
                end_p = hist['Close'].iloc[-1]
                chg = ((end_p - start_p) / start_p * 100) if start_p else 0.0
                # Approximate equal-weight contribution to sector mapping index
                contrib = chg / len(stocks)
                stock_perf.append({
                    'ticker': s['sym'],
                    'change': round(chg, 2),
                    'contribution': round(contrib, 2)
                })
    except:
        pass
        
    stock_perf.sort(key=lambda x: x['change'], reverse=True)
    return stock_perf[:5] # Return top contributors

# 3. Handle Data Calculations
tf   = st.session_state["selected_tf"]
days = TIMEFRAMES[tf]

with st.spinner("Fetching performance metrics..."):
    data = fetch_today()

if not data:
    st.error("Could not fetch sector data. Please try again.")
    st.stop()

gainers = [s for s in data if s['direction'] == 'up']
losers  = [s for s in data if s['direction'] == 'down']
top     = data[0]
bottom  = data[-1]
updated = time.strftime("%H:%M:%S")

# 4. Interactive Control Row Layout Configuration
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
        "TIMEFRAME", list(TIMEFRAMES.keys()),
        index=list(TIMEFRAMES.keys()).index(st.session_state["selected_tf"]),
        label_visibility="collapsed", key="tf_select"
    )
    if chosen != st.session_state["selected_tf"]:
        st.session_state["selected_tf"] = chosen
        st.cache_data.clear()
        st.rerun()

with c5:
    st.markdown('<div style="font-size:10px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:transparent; margin-bottom:2px; user-select:none;">Action</div>', unsafe_allow_html=True)
    if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

# 5. Native Accordion Layout Engine with Full Row Custom Rendering
max_chg = max(abs(s['change']) for s in data) or 1

st.markdown(f"""
<div style="font-size:11px; font-weight:600; color:#7a8394; padding-bottom:8px; display:flex; justify-content:space-between;">
    <span>📅 Performance Heat Breakdown</span>
    <span>Click any sector row below to inspect top constituents</span>
</div>
""", unsafe_allow_html=True)

for s in data:
    is_expanded = (st.session_state["expanded_sector"] == s['name'])
    bar_w = (abs(s['change']) / max_chg) * 100
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    opacity_color = "rgba(0, 168, 84, 0.15)" if s['direction'] == 'up' else "rgba(229, 57, 53, 0.15)"
    sign  = "+" if s['change'] >= 0 else ""
    
    # 1. Render Row Element Header using native columns to keep clicks responsive
    row_class = "sector-row-active" if is_expanded else "sector-row"
    
    # Outer visual container markup
    st.markdown(f"""
    <div class="{row_class}">
        <div style="display: grid; grid-template-columns: 120px 1fr 80px; align-items: center; gap: 16px;">
            <div style="font-size: 13px; font-weight: 700; color: #0f1117; font-family: 'JetBrains Mono', monospace;">
                {s['name']} { '▴' if is_expanded else '▾' }
            </div>
            <div class="bar-track">
                <div style="width: {bar_w:.1f}%; height: 100%; background: {color}; border-radius: 3px;"></div>
            </div>
            <div style="font-size: 13px; font-weight: 700; text-align: right; color: {color}; font-family: 'JetBrains Mono', monospace;">
                {sign}{s['change']:.2f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Hidden selection controller button positioned over layout safely
    btn_label = f"Inspect {s['name']}" if not is_expanded else f"Close {s['name']}"
    if st.button(btn_label, key=f"btn_{s['name']}", use_container_width=True, help="Toggle stock view breakdown"):
        st.session_state["expanded_sector"] = None if is_expanded else s['name']
        st.rerun()
        
    # 2. Inside expansion card canvas matching Option 1 structure
    if is_expanded:
        with st.container():
            st.markdown(f"""
            <div class="breakdown-container">
                <div style="font-size: 11px; font-weight: 700; color: #7a8394; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; display: flex; justify-content: space-between;">
                    <span>Top Contributors • {s['name']} Nifty Portfolio Proxy</span>
                    <span>% Return / Index Weight Contribution</span>
                </div>
            """, unsafe_allow_html=True)
            
            # Fetch underlying dynamic stock tickers
            stocks_data = fetch_top_stocks_for_sector(s['name'], days)
            
            if not stocks_data:
                st.markdown("<div style='font-size:12px; color:#7a8394;'>No stock data available for this timeline.</div>", unsafe_allow_html=True)
            else:
                max_stock_chg = max(abs(stk['change']) for stk in stocks_data) or 1
                for stk in stocks_data:
                    stk_bar_w = (abs(stk['change']) / max_stock_chg) * 100
                    stk_color = "#00a854" if stk['change'] >= 0 else "#e53935"
                    stk_sign = "+" if stk['change'] >= 0 else ""
                    
                    st.markdown(f"""
                    <div style="display: grid; grid-template-columns: 140px 1fr 80px 80px; align-items: center; gap: 16px; padding: 8px 0; border-bottom: 1px dashed #f0f2f5;">
                        <div style="font-size: 12px; font-weight: 600; color: #3d4452; font-family: 'Inter', sans-serif;">{stk['ticker']}</div>
                        <div class="bar-track" style="height: 4px; background: #f8f9fb;">
                            <div style="width: {stk_bar_w:.1f}%; height: 100%; background: {stk_color}; opacity: 0.85; border-radius: 2px;"></div>
                        </div>
                        <div style="font-size: 12px; font-weight: 600; text-align: right; color: {stk_color}; font-family: 'JetBrains Mono', monospace;">{stk_sign}{stk['change']:.1f}%</div>
                        <div style="font-size: 12px; font-weight: 600; text-align: right; color: #7a8394; font-family: 'JetBrains Mono', monospace;">{stk_sign}{stk['contribution']:.2f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
            st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

# 6. Supplementary Data Segment
with st.expander("📋 Data Table View"):
    df = pd.DataFrame(data)[['name', 'ltp', 'prev', 'change']]
    col_start = "Prev Close" if days == 1 else "Start Price"
    df.columns = ['Sector', 'LTP', col_start, 'Change %']
    df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df, use_container_width=True, hide_index=True)
