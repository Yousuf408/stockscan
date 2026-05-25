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

    /* Kill gaps — scoped to not break control row */
    div[data-testid="stVerticalBlock"] > div { gap: 0 !important; }
    div[data-testid="stVerticalBlock"] div[data-testid="element-container"] {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    /* But restore spacing inside horizontal blocks (control row) */
    div[data-testid="stHorizontalBlock"] div[data-testid="element-container"] {
        margin-top: revert !important;
        margin-bottom: revert !important;
        padding-top: revert !important;
        padding-bottom: revert !important;
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


    /* ── SECTOR TOGGLE BUTTON: invisible click target ──
       Card HTML overlays on top via negative margin-top. */
    [data-testid="stBaseButton-secondary"] {
        width: 100% !important;
        height: 38px !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        opacity: 0 !important;
        position: relative !important;
        z-index: 2 !important;
        cursor: pointer !important;
    }

    /* ── Restore Refresh button visibility specifically ── */
    button[data-testid="stBaseButton-secondary"][kind="secondary"]:has(> div > p:only-child) {
        opacity: 1 !important;
    }
    /* Fallback: target by key via aria-label or just restore all buttons NOT in sector list */
    div[data-testid="stHorizontalBlock"] [data-testid="stBaseButton-secondary"] {
        opacity: 1 !important;
        height: 42px !important;
        background-color: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        font-size: 14px !important;
        color: #3d4452 !important;
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
        grid-template-columns: 140px 1fr 100px 30px;
        align-items: center;
        gap: 16px;
        margin-top: -44px;
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
        grid-template-columns: 140px 1fr 100px 30px;
        align-items: center;
        gap: 16px;
        margin-top: -44px;
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

# Timeframe → Yahoo (interval, range) mapping
TF_MAP = {
    "1 Day":   ("1d",  "1d"),
    "1 Week":  ("1d",  "5d"),
    "1 Month": ("1d",  "1mo"),
    "1 Year":  ("1wk", "1y"),
}

# 2. Data Fetchers
@st.cache_data(ttl=30)
def fetch_sector_indices(tf: str = "1 Day"):
    interval, range_ = TF_MAP.get(tf, ("1d", "1d"))
    data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, symbol in SECTOR_YAHOO.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval={interval}&range={range_}"
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok: continue
            result = resp.json().get('chart', {}).get('result', [{}])[0]
            meta   = result.get('meta', {})
            if meta:
                cp = meta.get('regularMarketPrice', 0)
                # For multi-day timeframes, compare vs first candle's open for period % change
                if tf == "1 Day":
                    pc = meta.get('chartPreviousClose', 0)
                else:
                    quotes = result.get('indicators', {}).get('quote', [{}])[0]
                    opens  = [o for o in quotes.get('open', []) if o is not None]
                    pc     = opens[0] if opens else meta.get('chartPreviousClose', 0)
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
    results = []
    for s in stocks[:5]:
        sym = f"{s['sym']}.NS"
        try:
            # Changed range=1d to range=2d to ensure we capture the explicit yesterday vs today candle arrays
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d"
            resp = requests.get(url, headers=headers, timeout=3)
            if not resp.ok: continue
            
            result = resp.json().get('chart', {}).get('result', [{}])[0]
            meta   = result.get('meta', {})
            indicators = result.get('indicators', {}).get('quote', [{}])[0]
            
            # Safely extract historical open and close arrays
            opens = indicators.get('open', [])
            closes = indicators.get('close', [])
            
            if meta:
                ltp = meta.get('regularMarketPrice', 0)
                prev_close = meta.get('chartPreviousClose', 0)
                chg = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0

                # Robust Gap Calculation using sequence arrays
                gap_pct = None
                if len(opens) >= 2 and closes[0] is not None and opens[1] is not None:
                    # Case A: We have at least 2 distinct days of data (Yesterday Close -> Today Open)
                    gap_pct = ((opens[1] - closes[0]) / closes[0]) * 100
                elif len(opens) == 1 and opens[0] is not None and prev_close:
                    # Case B: Only 1 day returned, fallback using metadata previous close
                    gap_pct = ((opens[0] - prev_close) / prev_close) * 100
                elif meta.get('regularMarketOpen') and prev_close:
                    # Case C: Hard fallback to metadata parameters
                    gap_pct = ((meta.get('regularMarketOpen') - prev_close) / prev_close) * 100

                results.append({
                    'ticker': s['sym'],
                    'ltp': round(ltp, 2),
                    'change': round(chg, 2),
                    'gap': round(gap_pct, 2) if gap_pct is not None else None,
                })
        except:
            continue
    results.sort(key=lambda x: x['change'], reverse=True)
    return results

# 3. Fetch + derive stats
with st.spinner("Analyzing sector feeds..."):
    sector_data = fetch_sector_indices(st.session_state["selected_tf"])

if not sector_data:
    st.error("No real-time market indices available right now.")
    st.stop()

gainers = [s for s in sector_data if s['direction'] == 'up']
losers  = [s for s in sector_data if s['direction'] == 'down']
top     = sector_data[0]
bottom  = sector_data[-1]

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
    # pointer-events: none ensures clicks pass through card to the button below
    st.markdown(f"""
    <div class="{card_class}">
        <div style="font-size:13px; font-weight:700; color:#0f1117;">{s['name']}</div>
        <div class="bar-track">
            <div style="width:{bar_w:.1f}%; height:100%; background:{color}; border-radius:3px;"></div>
        </div>
        <div style="font-size:13px; font-weight:700; text-align:right; color:{color}; font-family:'JetBrains Mono',monospace;">
            {sign}{s['change']:.2f}%
        </div>
        <div class="expand-icon">{icon}</div>
    </div>
    """, unsafe_allow_html=True)

    # STEP 3: Stock drill-down panel — only renders when this sector is expanded
    if is_expanded:
        st.markdown('<div class="breakdown-box">', unsafe_allow_html=True)
        stocks_list = fetch_sector_stocks_live(s['name'])

        if not stocks_list:
            st.markdown("<div style='font-size:12px; color:#7a8394; padding:12px 0;'>No constituents available.</div>", unsafe_allow_html=True)
        else:
            # Header row
            st.markdown("""
            <div style="display:grid; grid-template-columns:120px 1fr 100px 72px 80px;
            gap:12px; padding:6px 12px; border-bottom:1px solid #e0e3e8; margin-bottom:4px;">
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em;">Stock</div>
                <div style="font-size:10px; font-weight:700; color:#7a8394; text-transform:uppercase; letter-spacing:0.06em; padding-left:4px;">Change</div>
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
                gap = stk.get('gap')
                if gap is not None:
                    is_gap_up   = gap >= 0
                    gap_color   = "#00a854" if is_gap_up else "#e53935"
                    gap_bg      = "#d4f0de" if is_gap_up else "#fcd9d7"
                    gap_border  = "#a8d5b5" if is_gap_up else "#f5a9a5"
                    gap_sign    = "▲ +" if is_gap_up else "▼ "
                    gap_label   = f"{gap_sign}{gap:.2f}%"
                    gap_html = (
                        f'<div style="font-size:11px; font-weight:700; text-align:center; '
                        f'color:{gap_color}; font-family:\'JetBrains Mono\',monospace; '
                        f'background:{gap_bg}; border:1px solid {gap_border}; '
                        f'border-radius:5px; padding:3px 7px; white-space:nowrap;">'
                        f'{gap_label}</div>'
                    )
                else:
                    gap_html = '<div style="font-size:11px; text-align:right; color:#c0c4cc;">—</div>'

                st.markdown(f"""
                <div style="display:grid; grid-template-columns:120px 1fr 100px 72px 80px;
                gap:12px; align-items:center; padding:9px 12px; border-bottom:1px solid #f0f2f5;">
                    <div style="font-size:13px; font-weight:600; color:#3d4452;">{stk['ticker']}</div>
                    <div style="height:6px; background:#f0f2f5; border-radius:3px; overflow:hidden;">
                        <div style="width:{stk_bar_w:.1f}%; height:100%; background:{stk_color}; border-radius:3px;"></div>
                    </div>
                    <div style="font-size:13px; font-weight:600; text-align:right; color:#0f1117; font-family:'JetBrains Mono',monospace;">&#8377;{stk['ltp']:,.1f}</div>
                    <div style="font-size:13px; font-weight:700; text-align:right; color:{stk_color}; font-family:'JetBrains Mono',monospace;">{stk_sign}{stk['change']:.2f}%</div>
                    {gap_html}
                </div>
                """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
