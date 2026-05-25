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

# Global CSS Overrides — Forcing tight, compact padding & exact heights
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

    div[data-testid="stHorizontalBlock"] button[key="refresh_btn"] {
        height: 42px !important;
        background-color: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        font-size: 14px !important;
        color: #3d4452 !important;
    }

    /* ── TIGHT COMPACT MATRIX ROW CONTAINERS ── */
    .sector-row-container {
        border: 1px solid #e0e3e8;
        border-radius: 6px;
        padding: 4px 14px !important;
        margin-bottom: 4px !important;
        background: #ffffff;
        min-height: 38px !important;
        max-height: 38px !important;
        display: flex;
        align-items: center;
        transition: background-color 0.1s ease;
    }
    
    .sector-row-container:hover {
        background-color: #fafbfc;
    }
    
    .sector-row-container-active {
        border: 1px solid #e0e3e8;
        border-bottom: none;
        border-radius: 6px 6px 0px 0px;
        padding: 4px 14px !important;
        margin-bottom: 0px !important;
        background: #ffffff;
        min-height: 38px !important;
        max-height: 38px !important;
        display: flex;
        align-items: center;
    }

    /* Force Streamlit's inner block containers to match the 38px grid height and center items */
    div[data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        height: 100% !important;
    }
    
    /* Clear out extra native block gap spacing injected by Streamlit inside rows */
    div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {
        gap: 0px !important;
    }

    .bar-track {
        height: 6px;
        background: #f0f2f5;
        border-radius: 3px;
        overflow: hidden;
        width: 100%;
    }

    /* Target the toggle button icon specifically to remain a sharp, borderless interactive target */
    div[data-testid="column"] div[data-testid="stButton"] {
        height: 24px !important;
        display: flex !important;
        justify-content: flex-end !important;
        align-items: center !important;
    }

    div[data-testid="column"] div[data-testid="stButton"] > button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #7a8394 !important;
        font-size: 20px !important;
        font-weight: 400 !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 24px !important;
        height: 24px !important;
        text-align: right !important;
        line-height: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-end !important;
    }

    div[data-testid="column"] div[data-testid="stButton"] > button:hover,
    div[data-testid="column"] div[data-testid="stButton"] > button:focus,
    div[data-testid="column"] div[data-testid="stButton"] > button:active {
        color: #00a854 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    .breakdown-box {
        background: #fafbfc;
        border: 1px solid #e0e3e8;
        border-top: none;
        border-radius: 0px 0px 6px 6px;
        padding: 4px 20px 10px 20px;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Session state initializations
if "selected_tf" not in st.session_state:
    st.session_state["selected_tf"] = "1 Day"
if "expanded_sector" not in st.session_state:
    st.session_state["expanded_sector"] = None

# 2. Data Fetching Engines
@st.cache_data(ttl=30)
def fetch_sector_indices():
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
                             'direction': 'up' if change >= 0 else 'down', 'ltp': cp})
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

@st.cache_data(ttl=30)
def fetch_sector_stocks_live(sector_name):
    stocks = get_stocks_by_sector(sector_name)
    if not stocks:
        return []
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    stock_results = []
    
    for s in stocks[:15]:
        sym = f"{s['sym']}.NS"
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
            resp = requests.get(url, headers=headers, timeout=3)
            if not resp.ok: continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                ltp = meta.get('regularMarketPrice', 0)
                prev_close = meta.get('chartPreviousClose', 0)
                chg = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0
                
                stock_results.append({
                    'ticker': s['sym'],
                    'ltp': round(ltp, 2),
                    'change': round(chg, 2)
                })
        except:
            continue
            
    stock_results.sort(key=lambda x: x['change'], reverse=True)
    return stock_results

# 3. Calculate Performance Metrics Block
tf = st.session_state["selected_tf"]
with st.spinner("Analyzing sector feeds..."):
    sector_data = fetch_sector_indices()

if not sector_data:
    st.error("No real-time market indices available right now.")
    st.stop()

gainers = [s for s in sector_data if s['direction'] == 'up']
losers  = [s for s in sector_data if s['direction'] == 'down']
top     = sector_data[0]
bottom  = sector_data[-1]

# 4. Filter Control Row Layout
c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
with c1:
    st.markdown(f'<div class="ts-metric" style="height:65px;"><div class="ts-metric-label">Top Gainer</div><div class="ts-metric-value" style="color:var(--green); font-size:15px; margin-top:4px;">▲ {top["name"]} {top["change"]:+.2f}%</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="ts-metric" style="height:65px;"><div class="ts-metric-label">Top Loser</div><div class="ts-metric-value" style="color:var(--red); font-size:15px; margin-top:4px;">▼ {bottom["name"]} {bottom["change"]:+.2f}%</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="ts-metric" style="height:65px;"><div class="ts-metric-label">Breadth</div><div class="ts-metric-value" style="font-size:15px; margin-top:4px;"><span style="color:var(--green);">{len(gainers)}↑</span> <span style="color:var(--border2);">/</span> <span style="color:var(--red);">{len(losers)}↓</span></div></div>', unsafe_allow_html=True)
with c4:
    st.markdown('<div style="font-size:10px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; color:#7a8394; margin-bottom:2px;">Timeframe</div>', unsafe_allow_html=True)
    chosen = st.selectbox("TF", ["1 Day", "1 Week", "1 Month", "1 Year"], label_visibility="collapsed", key="tf_selector")
    if chosen != st.session_state["selected_tf"]:
        st.session_state["selected_tf"] = chosen
        st.cache_data.clear()
        st.rerun()
with c5:
    st.markdown('<div style="font-size:10px; margin-bottom:2px; color:transparent; user-select:none;">Reset</div>', unsafe_allow_html=True)
    if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<div style='margin-top:15px'></div>", unsafe_allow_html=True)

# 5. Clean, Tight Row Render Engine
max_val = max(abs(s['change']) for s in sector_data) or 1

for s in sector_data:
    is_expanded = (st.session_state["expanded_sector"] == s['name'])
    bar_w = (abs(s['change']) / max_val) * 100
    color = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign = "+" if s['change'] >= 0 else ""
    icon = "−" if is_expanded else "+"
    
    container_class = "sector-row-container-active" if is_expanded else "sector-row-container"
    
    # Outer custom stylized HTML frame wrapper
    st.markdown(f'<div class="{container_class}">', unsafe_allow_html=True)
    
    # Render aligned horizontal items inside streamlined structure columns
    col_name, col_bar, col_pct, col_btn = st.columns([140, 500, 100, 40], gap="medium")
    
    with col_name:
        st.markdown(f'<div style="font-size: 13px; font-weight: 700; color:#0f1117; line-height: 1.2;">{s["name"]}</div>', unsafe_allow_html=True)
        
    with col_bar:
        st.markdown(f"""
            <div class="bar-track" style="margin-top: 2px;">
                <div style="width: {bar_w:.1f}%; height: 100%; background: {color}; border-radius: 3px;"></div>
            </div>
        """, unsafe_allow_html=True)
        
    with col_pct:
        st.markdown(f"""
            <div style="font-size: 13px; font-weight: 700; text-align: right; color: {color}; font-family: 'JetBrains Mono', monospace; line-height: 1.2;">
                {sign}{s['change']:.2f}%
            </div>
        """, unsafe_allow_html=True)
        
    with col_btn:
        if st.button(icon, key=f"toggle_btn_{s['name']}"):
            st.session_state["expanded_sector"] = None if is_expanded else s['name']
            st.rerun()
            
    st.markdown('</div>', unsafe_allow_html=True) # Closes row box container cleanly
        
    # Dropdown stock performance metrics drawer segment
    if is_expanded:
        st.markdown('<div class="breakdown-box">', unsafe_allow_html=True)
        stocks_list = fetch_sector_stocks_live(s['name'])
        
        if not stocks_list:
            st.markdown("<div style='font-size:12px; color:#7a8394; padding: 10px 0;'>No constituents available for this sector mapping.</div>", unsafe_allow_html=True)
        else:
            for stk in stocks_list:
                stk_color = "#00a854" if stk['change'] >= 0 else "#e53935"
                stk_sign = "+" if stk['change'] >= 0 else ""
                
                st.markdown(f"""
                <div style="display: grid; grid-template-columns: 1fr 120px 100px; align-items: center; padding: 8px 0; border-bottom: 1px solid #f0f2f5;">
                    <div style="font-size: 13px; font-weight: 600; color: #3d4452;">{stk['ticker']}</div>
                    <div style="font-size: 13px; font-weight: 600; text-align: right; color: #0f1117; font-family: 'JetBrains Mono', sans-serif;">₹{stk['ltp']:,}</div>
                    <div style="font-size: 13px; font-weight: 700; text-align: right; color: {stk_color}; font-family: 'JetBrains Mono', monospace;">{stk_sign}{stk['change']:.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
                
        st.markdown('</div>', unsafe_allow_html=True)
