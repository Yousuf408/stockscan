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

st.markdown("""
<style>
    .stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"] {
        background-color: #ffffff !important;
    }

    /* Kill Streamlit vertical gaps between sector button+card pairs */
    div[data-testid="stVerticalBlock"] > div { gap: 0 !important; }
    div[data-testid="element-container"] {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
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
        justify-content: center;
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


    /* ── SECTOR TOGGLE BUTTON: invisible click target ── */
    [data-testid="stBaseButton-secondary"] {
        width: 100% !important;
        height: 44px !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        opacity: 0 !important;
        position: relative !important;
        z-index: 2 !important;
        cursor: pointer !important;
    }

    /* ── Restore Refresh button — lives inside stHorizontalBlock ── */
    div[data-testid="stHorizontalBlock"] [data-testid="stBaseButton-secondary"] {
        opacity: 1 !important;
        height: 42px !important;
        background-color: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        font-size: 14px !important;
        color: #3d4452 !important;
        position: static !important;
    }

    /* ── CARD overlays on top of the invisible button ── */
    .sector-card {
        background: #ffffff;
        border-left: 1px solid #e0e3e8;
        border-right: 1px solid #e0e3e8;
        border-top: 1px solid #e0e3e8;
        border-bottom: none;
        border-radius: 0px;
        padding: 10px 18px;
        display: grid;
        grid-template-columns: 90px 1fr 110px 30px;
        align-items: center;
        gap: 16px;
        margin-top: -50px;
        margin-bottom: 0px;
        pointer-events: none;
        box-shadow: none;
        position: relative;
        z-index: 1;
    }

    .sector-card-active {
        background: #f5fdf8;
        border-left: 1px solid #c8e6c9;
        border-right: 1px solid #c8e6c9;
        border-top: 1px solid #c8e6c9;
        border-bottom: none;
        border-radius: 0px;
        padding: 10px 18px;
        display: grid;
        grid-template-columns: 90px 1fr 110px 30px;
        align-items: center;
        gap: 16px;
        margin-top: -50px;
        margin-bottom: 0px;
        pointer-events: none;
        box-shadow: none;
        position: relative;
        z-index: 1;
    }

    /* ── Expanded stock breakdown panel ── */
    .breakdown-box {
        background: #fafbfc;
        border-left: 3px solid #c8e6c9;
        border-right: 3px solid #c8e6c9;
        border-top: none;
        border-bottom: none;
        border-radius: 0px;
        margin: 0 1%;
        padding: 10px 16px 14px 16px;
    }

    .bar-track {
        height: 6px;
        background: #f0f2f5;
        border-radius: 3px;
        overflow: hidden;
    }

    .expand-icon {
        font-size: 16px;
        font-weight: 400;
        color: #7a8394;
        text-align: right;
        user-select: none;
    }
</style>
""", unsafe_allow_html=True)

# Session state
if "selected_tf" not in st.session_state:
    st.session_state["selected_tf"] = "1 Day"
if "expanded_sector" not in st.session_state:
    st.session_state["expanded_sector"] = None

# 2. Timeframe → Yahoo Finance param mapping
TF_MAP = {
    "1 Day":   {"interval": "1d",  "range": "1d"},
    "1 Week":  {"interval": "1d",  "range": "5d"},
    "1 Month": {"interval": "1d",  "range": "1mo"},
    "1 Year":  {"interval": "1wk", "range": "1y"},
}


# Gap classification helper
def calculate_gap(open_price, prev_close):
    """Calculate gap % and classify: gap_up, gap_down, or flat"""
    if not open_price or not prev_close or prev_close == 0:
        return {"gap_pct": 0, "category": "flat"}
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct > 0.30:
        category = "gap_up"
    elif gap_pct < -0.30:
        category = "gap_down"
    else:
        category = "flat"
    return {"gap_pct": round(gap_pct, 2), "category": category}

# 2. Data Fetchers
@st.cache_data(ttl=30)
def fetch_sector_indices(tf="1 Day"):
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            params = TF_MAP.get(tf, TF_MAP["1 Day"])
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval={params['interval']}&range={params['range']}"
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok: continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                pc = meta.get('chartPreviousClose', 0)
                op = meta.get('regularMarketOpen', 0)
                change = ((cp - pc) / pc * 100) if pc else 0.0
                gap_info = calculate_gap(op, pc)
                data.append({'name': name, 'symbol': symbol, 'change': round(change, 2),
                             'direction': 'up' if change >= 0 else 'down', 'ltp': cp,
                             'open': op, 'gap_pct': gap_info['gap_pct'], 'gap_category': gap_info['category']})
        except:
            continue
    data.sort(key=lambda x: x['change'], reverse=True)
    return data

@st.cache_data(ttl=30)
def fetch_sector_stocks_live(sector_name, tf="1 Day"):
    stocks = get_stocks_by_sector(sector_name)
    if not stocks:
        return []
    headers = {'User-Agent': 'Mozilla/5.0'}
    results = []
    for s in stocks[:5]:
        sym = f"{s['sym']}.NS"
        try:
            params = TF_MAP.get(tf, TF_MAP["1 Day"])
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={params['interval']}&range={params['range']}"
            resp = requests.get(url, headers=headers, timeout=3)
            if not resp.ok: continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                ltp = meta.get('regularMarketPrice', 0)
                pc  = meta.get('chartPreviousClose', 0)
                op  = meta.get('regularMarketOpen', 0)
                chg = ((ltp - pc) / pc * 100) if pc else 0.0
                gap_info = calculate_gap(op, pc)
                results.append({'ticker': s['sym'], 'ltp': round(ltp, 2), 'change': round(chg, 2),
                                'gap_pct': gap_info['gap_pct'], 'gap_category': gap_info['category']})
        except:
            continue
    results.sort(key=lambda x: x['change'], reverse=True)
    return results

# 3. Fetch + derive stats
with st.spinner("Analyzing sector feeds..."):
    sector_data = fetch_sector_indices(tf=st.session_state['selected_tf'])

if not sector_data:
    st.error("No real-time market indices available right now.")
    st.stop()

gainers = [s for s in sector_data if s['direction'] == 'up']
losers  = [s for s in sector_data if s['direction'] == 'down']
top     = sector_data[0]
bottom  = sector_data[-1]

# Pre-calculate gap breadth for sectors (will be used when displaying)
def get_sector_gap_breadth(sector_name, selected_tf):
    stocks = get_stocks_by_sector(sector_name)
    if not stocks:
        return {"gap_up": 0, "flat": 0, "gap_down": 0, "total": 0}
    
    gap_counts = {"gap_up": 0, "flat": 0, "gap_down": 0}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for s in stocks[:5]:
        sym = f"{s['sym']}.NS"
        try:
            params = TF_MAP.get(selected_tf, TF_MAP["1 Day"])
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={params['interval']}&range={params['range']}"
            resp = requests.get(url, headers=headers, timeout=3)
            if not resp.ok: continue
            meta = resp.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                op = meta.get('regularMarketOpen', 0)
                pc = meta.get('chartPreviousClose', 0)
                gap_info = calculate_gap(op, pc)
                gap_counts[gap_info['category']] += 1
        except:
            continue
    
    total = sum(gap_counts.values())
    return {**gap_counts, "total": total}

# 4. Control Row
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
    st.markdown('<div style="font-size:10px; margin-bottom:2px; color:transparent; user-select:none;">x</div>', unsafe_allow_html=True)
    if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

# 5. Toggle callback — keeps toggle logic clean and separate
def toggle_sector(sector_name):
    current = st.session_state.get("expanded_sector")
    st.session_state["expanded_sector"] = None if current == sector_name else sector_name

# 6. Sector rows — button is the click target, card HTML overlays on top
max_val = max(abs(s['change']) for s in sector_data) or 1

st.markdown('<div style="border-radius:8px; overflow:hidden; border:1px solid #e0e3e8; box-shadow:0 1px 4px rgba(0,0,0,0.05);">', unsafe_allow_html=True)

for idx, s in enumerate(sector_data):
    is_last = (idx == len(sector_data) - 1)
    is_expanded = (st.session_state["expanded_sector"] == s['name'])
    bar_w  = (abs(s['change']) / max_val) * 100
    color  = "#00a854" if s['direction'] == 'up' else "#e53935"
    sign   = "+" if s['change'] >= 0 else ""
    icon   = "−" if is_expanded else "+"
    card_class = "sector-card-active" if is_expanded else "sector-card"

    # STEP 1: Real Streamlit button — invisible (opacity:0 via CSS), full width
    # This is the actual click target Streamlit responds to
    st.button(
        label=s['name'],
        key=f"toggle_{s['name']}",
        on_click=toggle_sector,
        args=(s['name'],),
        use_container_width=True,
    )

    # STEP 2: Card HTML overlays on top of the button via negative margin-top
    # Get gap breadth for this sector
    gap_breadth = get_sector_gap_breadth(s['name'], st.session_state['selected_tf'])
    total_gap = gap_breadth['total'] if gap_breadth['total'] > 0 else 1
    gap_up_w = (gap_breadth['gap_up'] / total_gap) * 100
    flat_w = (gap_breadth['flat'] / total_gap) * 100
    gap_down_w = (gap_breadth['gap_down'] / total_gap) * 100
    
    # pointer-events: none ensures clicks pass through card to the button below
    st.markdown(f"""
    <div class="{card_class}">
        <div style="font-size:13px; font-weight:700; color:#0f1117; min-width:80px;">{s['name']}</div>
        <div style="flex:1; display:flex; flex-direction:column; gap:4px;">
            <div class="bar-track">
                <div style="width:{bar_w:.1f}%; height:100%; background:{color}; border-radius:3px;"></div>
            </div>
            <div style="display:flex; height:4px; border-radius:2px; overflow:hidden; gap:0.5px;">
                <div style="width:{gap_up_w:.1f}%; height:100%; background:#00a854;"></div>
                <div style="width:{flat_w:.1f}%; height:100%; background:#d3d1c7;"></div>
                <div style="width:{gap_down_w:.1f}%; height:100%; background:#e53935;"></div>
            </div>
        </div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:2px; min-width:90px;">
            <div style="font-size:13px; font-weight:700; text-align:right; color:{color}; font-family:'JetBrains Mono',monospace;">{sign}{s['change']:.2f}%</div>
            <div style="font-size:9px; color:#7a8394; font-family:monospace; text-align:right; letter-spacing:0.02em;">↑{gap_breadth['gap_up']} —{gap_breadth['flat']} ↓{gap_breadth['gap_down']}</div>
        </div>
        <div class="expand-icon">{icon}</div>
    </div>
    """, unsafe_allow_html=True)

    # STEP 3: Stock drill-down panel — only renders when this sector is expanded
    if is_expanded:
        st.markdown('<div class="breakdown-box">', unsafe_allow_html=True)
        stocks_list = fetch_sector_stocks_live(s['name'], tf=st.session_state['selected_tf'])

        if not stocks_list:
            st.markdown("<div style='font-size:12px; color:#7a8394; padding:12px 0;'>No constituents available.</div>", unsafe_allow_html=True)
        else:
            # Header row
            st.markdown("""
            <div style="display:grid; grid-template-columns:110px 1fr 90px 70px 70px;
            gap:12px; padding:6px 12px; border-bottom:1px solid #e0e3e8; margin-bottom:4px;">
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em;">Stock</div>
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em;">Change</div>
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em; text-align:right;">LTP</div>
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em; text-align:right;">Chg %</div>
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em; text-align:right;">Gap</div>
            </div>
            """, unsafe_allow_html=True)

            # Scale bars relative to max change among top 5 stocks
            max_stk_chg = max((abs(stk['change']) for stk in stocks_list), default=1) or 1

            for stk in stocks_list:
                stk_color = "#00a854" if stk['change'] >= 0 else "#e53935"
                stk_sign  = "+" if stk['change'] >= 0 else ""
                stk_bar_w = (abs(stk['change']) / max_stk_chg) * 100
                
                # Gap display
                gap_val = stk.get('gap_pct', 0)
                gap_cat = stk.get('gap_category', 'flat')
                if gap_cat == 'gap_up':
                    gap_color = "#00a854"
                    gap_text = f"↑ +{abs(gap_val):.2f}%"
                elif gap_cat == 'gap_down':
                    gap_color = "#e53935"
                    gap_text = f"↓ {gap_val:.2f}%"
                else:
                    gap_color = "#7a8394"
                    gap_text = "—"
                
                st.markdown(f"""
                <div style="display:grid; grid-template-columns:110px 1fr 90px 70px 70px;
                gap:12px; align-items:center; padding:9px 12px; border-bottom:1px solid #f0f2f5;">
                    <div style="font-size:13px; font-weight:600; color:#3d4452;">{stk['ticker']}</div>
                    <div style="height:6px; background:#f0f2f5; border-radius:3px; overflow:hidden;">
                        <div style="width:{stk_bar_w:.1f}%; height:100%; background:{stk_color}; border-radius:3px;"></div>
                    </div>
                    <div style="font-size:13px; font-weight:600; text-align:right; color:#0f1117; font-family:'JetBrains Mono',monospace;">&#8377;{stk['ltp']:,.1f}</div>
                    <div style="font-size:13px; font-weight:700; text-align:right; color:{stk_color}; font-family:'JetBrains Mono',monospace;">{stk_sign}{stk['change']:.2f}%</div>
                    <div style="font-size:12px; font-weight:600; text-align:right; color:{gap_color}; font-family:'JetBrains Mono',monospace;">{gap_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
