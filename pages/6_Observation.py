# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND / 6_Observation.py – UI only
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
from datetime import datetime
import pytz

# ── Import Backend ──
from observation_backend import (
    init_session_state,
    HARDCODED_SETTINGS,
    should_refresh_stage1,
    load_stage1_data,
    get_filtered_data,
    prepare_display_dataframe,
    IST
)

# ── Import DhanHQ modules ──
from tv_screener.dhan_orders import place_dhan_order
from tv_screener.frontend import display_order_result
from tv_screener.quantity_calculator import get_qty_calc_debug

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TradeOS · Professional Screener",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# PROFESSIONAL CSS
# ─────────────────────────────────────────────────────────────────────────────

PROFESSIONAL_CSS = """
<style>
    /* ─── GLOBAL BACKGROUND ─── */
    .stApp {
        background: #0a0a0f !important;
    }
    
    .stAppViewContainer {
        background: #0a0a0f !important;
    }
    
    .main > div {
        background: #0a0a0f !important;
    }
    
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        max-width: 1440px !important;
        background: #0a0a0f !important;
    }
    
    /* ─── SIDEBAR ─── */
    .css-1d391kg, .st-emotion-cache-1wmy9hl {
        background: rgba(10, 10, 15, 0.98) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    
    /* ─── HIDE STREAMLIT FOOTER/HEADER ─── */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    
    /* ─── HEADER ─── */
    .tradeos-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.6rem 2rem;
        background: rgba(10, 10, 15, 0.98);
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px);
        margin: -0.5rem -1rem 0.5rem -1rem;
        flex-wrap: wrap;
        gap: 0.5rem;
        position: sticky;
        top: 0;
        z-index: 999;
    }
    
    .header-left {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .logo {
        font-size: 1.3rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00ff88, #00ccff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .version {
        font-size: 0.6rem;
        color: #666;
        background: rgba(255, 255, 255, 0.05);
        padding: 0.1rem 0.5rem;
        border-radius: 12px;
    }
    
    .header-center {
        display: flex;
        gap: 1.5rem;
        font-size: 0.8rem;
        flex-wrap: wrap;
    }
    
    .ticker-item {
        display: flex;
        gap: 0.4rem;
        align-items: center;
        color: #e0e0e0;
    }
    
    .ticker-green { color: #00ff88; }
    .ticker-red { color: #ff4444; }
    
    .header-right {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    
    .status-indicator {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.8rem;
        color: #e0e0e0;
    }
    
    .status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #00ff88;
        box-shadow: 0 0 10px #00ff88;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    
    .clock {
        font-size: 0.8rem;
        color: #888;
        font-variant-numeric: tabular-nums;
    }
    
    /* ─── PAGE HEADER ─── */
    .page-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 1rem 0 1.25rem 0;
        flex-wrap: wrap;
        gap: 0.75rem;
    }
    
    .page-title {
        font-size: 1.4rem;
        font-weight: 600;
        color: #e0e0e0;
    }
    
    .page-title span {
        font-size: 0.8rem;
        color: #666;
        font-weight: 400;
    }
    
    /* ─── REFRESH BUTTON ─── */
    .stButton button {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        color: #e0e0e0 !important;
        border-radius: 8px !important;
        padding: 0.4rem 1.2rem !important;
        font-size: 0.8rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton button:hover {
        background: rgba(255, 255, 255, 0.1) !important;
        border-color: rgba(0, 255, 136, 0.3) !important;
    }
    
    /* ─── SCREENER CARD ─── */
    .screener-card {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        overflow: hidden;
        margin-bottom: 1rem;
    }
    
    .screener-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: rgba(255, 255, 255, 0.01);
        border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        flex-wrap: wrap;
        gap: 0.75rem;
    }
    
    .screener-stats {
        display: flex;
        gap: 1.5rem;
        font-size: 0.8rem;
        flex-wrap: wrap;
    }
    
    .stat-item {
        color: #888;
    }
    
    .stat-item strong {
        color: #fff;
        font-weight: 600;
    }
    
    .stat-count {
        color: #00ff88;
        font-weight: 600;
    }
    
    .filter-badges {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
    }
    
    .filter-badge {
        background: rgba(255, 255, 255, 0.04);
        padding: 0.2rem 0.7rem;
        border-radius: 12px;
        font-size: 0.7rem;
        color: #888;
        border: 1px solid rgba(255, 255, 255, 0.04);
    }
    
    .filter-badge.active {
        border-color: rgba(0, 255, 136, 0.2);
        color: #00ff88;
    }
    
    /* ─── CHECKBOX ─── */
    .stCheckbox label {
        color: #888 !important;
        font-size: 0.8rem !important;
    }
    
    .stCheckbox label span {
        color: #e0e0e0 !important;
    }
    
    /* ─── DATAFRAME - COMPLETE FIX ─── */
    .stDataFrame {
        background: transparent !important;
    }
    
    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: transparent !important;
        border: none !important;
    }
    
    .stDataFrame table {
        background: transparent !important;
    }
    
    .stDataFrame tbody {
        background: transparent !important;
    }
    
    .stDataFrame tr {
        background: transparent !important;
    }
    
    .stDataFrame thead tr th {
        background: rgba(255, 255, 255, 0.03) !important;
        color: #888 !important;
        font-size: 0.6rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
        padding: 0.6rem 0.8rem !important;
        font-weight: 600 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    
    .stDataFrame tbody tr td {
        background: rgba(255, 255, 255, 0.02) !important;
        color: #e0e0e0 !important;
        padding: 0.6rem 0.8rem !important;
        border: none !important;
        font-size: 0.85rem !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    
    .stDataFrame tbody tr:hover td {
        background: rgba(255, 255, 255, 0.06) !important;
    }
    
    .st-emotion-cache-1r6slb0 {
        background: transparent !important;
    }
    
    .st-emotion-cache-1wmy9hl {
        background: transparent !important;
    }
    
    .element-container {
        background: transparent !important;
    }
    
    [data-testid="stDataFrameResizable"] {
        background: transparent !important;
    }
    
    [data-testid="stDataFrame"] {
        background: transparent !important;
    }
    
    /* ─── FOOTER BAR ─── */
    .footer-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.75rem 1.5rem;
        border-top: 1px solid rgba(255, 255, 255, 0.03);
        font-size: 0.7rem;
        color: #555;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    
    .footer-bar .highlight {
        color: #888;
    }
    
    .footer-bar .live {
        color: #00ff88;
    }
    
    /* ─── BUY BUTTONS ─── */
    .stButton button[kind="secondary"] {
        background: linear-gradient(135deg, #00ff88, #00cc66) !important;
        border: none !important;
        color: #000 !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton button[kind="secondary"]:hover {
        transform: scale(1.05) !important;
        box-shadow: 0 0 20px rgba(0, 255, 136, 0.3) !important;
    }
    
    .stButton button[kind="secondary"]:disabled {
        opacity: 0.3 !important;
        cursor: not-allowed !important;
        transform: none !important;
    }
    
    /* ─── SIDEBAR STYLING ─── */
    .stSidebar .stButton button {
        background: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        color: #e0e0e0 !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
        text-align: left !important;
        padding: 0.5rem 1rem !important;
    }
    
    .stSidebar .stButton button:hover {
        background: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(0, 255, 136, 0.2) !important;
        color: #00ff88 !important;
    }
    
    /* ─── RESPONSIVE ─── */
    @media (max-width: 768px) {
        .tradeos-header {
            padding: 0.5rem 0.75rem;
            flex-direction: column;
            gap: 0.3rem;
            margin: -0.5rem -0.5rem 0.5rem -0.5rem;
        }
        
        .header-center {
            font-size: 0.7rem;
            gap: 0.8rem;
            justify-content: center;
        }
        
        .page-title {
            font-size: 1.1rem;
        }
        
        .screener-header {
            flex-direction: column;
            align-items: flex-start;
            padding: 0.75rem;
        }
        
        .screener-stats {
            font-size: 0.7rem;
            gap: 0.8rem;
        }
        
        .footer-bar {
            flex-direction: column;
            text-align: center;
            padding: 0.5rem 0.75rem;
        }
    }
    
    /* ─── DEBUG ─── */
    .debug-section {
        margin-top: 1rem;
        padding: 1rem 1.5rem;
        background: rgba(255, 255, 255, 0.01);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.03);
    }
    
    .debug-section summary {
        cursor: pointer;
        color: #555;
        font-size: 0.75rem;
        font-weight: 500;
    }
    
    .debug-section summary:hover {
        color: #888;
    }
    
    .stAlert {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        color: #888 !important;
    }
    
    /* ─── SIGNAL BADGES IN TABLE ─── */
    .signal-buy {
        background: rgba(0, 255, 136, 0.15) !important;
        color: #00ff88 !important;
        padding: 0.15rem 0.6rem !important;
        border-radius: 12px !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
    }
    
    .signal-hold {
        background: rgba(245, 158, 11, 0.15) !important;
        color: #f59e0b !important;
        padding: 0.15rem 0.6rem !important;
        border-radius: 12px !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
    }
    
    .signal-sell {
        background: rgba(255, 68, 68, 0.15) !important;
        color: #ff4444 !important;
        padding: 0.15rem 0.6rem !important;
        border-radius: 12px !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
    }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# RENDER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def render_header():
    """Render professional header"""
    current_time = datetime.now(IST)
    
    nifty = "24,856.40"
    nifty_chg = "+0.87%"
    sensex = "81,234.56"
    sensex_chg = "+0.92%"
    bank_nifty = "52,345.67"
    bank_chg = "-0.23%"
    
    st.markdown(f"""
    <div class="tradeos-header">
        <div class="header-left">
            <span class="logo">⚡ TradeOS</span>
            <span class="version">v3.0</span>
        </div>
        <div class="header-center">
            <span class="ticker-item">NIFTY 50 {nifty} <span class="ticker-green">▲ {nifty_chg}</span></span>
            <span class="ticker-item">SENSEX {sensex} <span class="ticker-green">▲ {sensex_chg}</span></span>
            <span class="ticker-item">BANK NIFTY {bank_nifty} <span class="ticker-red">▼ {bank_chg}</span></span>
        </div>
        <div class="header-right">
            <div class="status-indicator">
                <span class="status-dot"></span>
                <span>Live</span>
            </div>
            <span class="clock">{current_time.strftime('%H:%M:%S')} IST</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_buy_buttons(display_df, amo_test_mode):
    """Render buy buttons for each stock"""
    st.markdown("---")
    st.markdown("#### 🚀 Quick Buy")
    
    num_cols = min(4, len(display_df))
    cols = st.columns(num_cols)
    
    for idx, (_, row) in enumerate(display_df.iterrows()):
        col_idx = idx % num_cols
        with cols[col_idx]:
            symbol = row['Symbol']
            max_qty = row['MaxQty']
            btn_label = f"{symbol} {int(max_qty)}" + (" 🌙" if amo_test_mode else "")
            
            if st.button(
                btn_label,
                key=f"buy_{symbol}_{idx}",
                disabled=(max_qty <= 0),
                use_container_width=True
            ):
                with st.spinner(f"Placing order for {symbol}..."):
                    result = place_dhan_order(
                        symbol,
                        quantity=int(max_qty),
                        product_type="INTRADAY",
                        after_market_order=amo_test_mode,
                        amo_time="OPEN"
                    )
                    display_order_result(symbol, result)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

# ─── Apply CSS ───
st.markdown(PROFESSIONAL_CSS, unsafe_allow_html=True)

# ─── Initialize Session State ───
init_session_state()

# ─── Render Header ───
render_header()

# ─── Check auto-refresh ───
if should_refresh_stage1() or st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()

# ─── Page Header ───
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown('<div class="page-title">🔍 Gap Screener <span>· Professional Trading Scanner</span></div>', unsafe_allow_html=True)
with col2:
    if st.button("🔄 Refresh", key="refresh_btn", use_container_width=True):
        st.session_state['stage1_data'] = None
        st.rerun()

# ─── Show Gap Screener Content ───
if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()
    
    # ─── Screener Card Header ───
    last_refresh = st.session_state.get('stage1_last_refresh', datetime.now(IST))
    pass_count = len(data['valid'])
    
    st.markdown(f"""
    <div class="screener-card">
        <div class="screener-header">
            <div class="screener-stats">
                <span class="stat-item">📊 Total: <strong class="stat-count">{data['total_count']}</strong></span>
                <span class="stat-item">✅ After Gap: <strong class="stat-count">{data['filtered_count']}</strong></span>
                <span class="stat-item">🎯 Pass Candle: <strong class="stat-count">{pass_count}</strong></span>
                <span class="stat-item">🕐 Last: <strong>{last_refresh.strftime('%H:%M:%S')}</strong></span>
            </div>
            <div class="filter-badges">
                <span class="filter-badge active">💰 ₹{HARDCODED_SETTINGS['price_min']}-{HARDCODED_SETTINGS['price_max']}</span>
                <span class="filter-badge active">📊 ≥{HARDCODED_SETTINGS['market_cap_min']/1e9:.0f}B</span>
                <span class="filter-badge active">📈 Gap ±2%</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # ─── Apply Filters ───
    is_after_9_25 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=25, second=0)
    is_after_9_30 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=30, second=0)
    
    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
    
    with filter_col1:
        if is_after_9_25:
            show_inside_only = st.checkbox(
                "📊 Inside 9:15 Range",
                value=st.session_state['show_inside_only'],
                key="inside_checkbox"
            )
            st.session_state['show_inside_only'] = show_inside_only
        else:
            st.info("⏳ 9:20 candle available after 9:25 AM")
            show_inside_only = False
    
    with filter_col2:
        if is_after_9_30:
            show_breakout_only = st.checkbox(
                "⚡ Breakout 9:30-9:45",
                value=st.session_state['show_breakout_only'],
                key="breakout_checkbox"
            )
            st.session_state['show_breakout_only'] = show_breakout_only
        else:
            st.info("⏳ Breakout filter available after 9:30 AM")
            show_breakout_only = False
    
    with filter_col3:
        amo_test_mode = st.checkbox(
            "🌙 AMO",
            value=st.session_state['amo_mode'],
            key="amo_checkbox"
        )
        st.session_state['amo_mode'] = amo_test_mode
    
    # ─── Apply filters to dataframe ───
    display_df = get_filtered_data(df, show_inside_only, show_breakout_only)
    
    if display_df.empty:
        st.warning("⚠️ No stocks match the selected filters.")
    else:
        # ─── Prepare and format display dataframe ───
        display_df = prepare_display_dataframe(display_df, st.session_state['user_capital'])
        
        # ─── Display table ───
        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            column_config={
                "Symbol": st.column_config.TextColumn("SYMBOL", width="small"),
                "Price": st.column_config.TextColumn("PRICE", width="small"),
                "Chg%": st.column_config.TextColumn("CHG%", width="small"),
                "Gap%": st.column_config.TextColumn("GAP%", width="small"),
                "Volume": st.column_config.TextColumn("VOLUME", width="small"),
                "Rel Vol": st.column_config.TextColumn("RELVOL", width="small"),
                "Inside 9:15": st.column_config.TextColumn("INSIDE", width="small"),
                "Breakout": st.column_config.TextColumn("BREAKOUT", width="small"),
                "Signal": st.column_config.TextColumn("SIGNAL", width="small"),
                "MaxQty": st.column_config.NumberColumn("MAXQTY", width="small"),
                "Sector": st.column_config.TextColumn("SECTOR", width="medium"),
            }
        )
        
        # ─── Render Buy Buttons ───
        render_buy_buttons(display_df, amo_test_mode)
        
        # ─── Download CSV ───
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f'screener_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )
    
    # ─── Footer Bar ───
    st.markdown(f"""
    <div class="footer-bar">
        <span>🔄 Stage 1 refreshes every <span class="live">1 minute</span></span>
        <span>📊 <span class="highlight">{len(display_df) if 'display_df' in locals() else 0}</span> stocks displayed · 
        <span class="highlight">{pass_count}</span> pass candle check</span>
        <span>🕐 Last refresh: <span class="highlight">{last_refresh.strftime('%H:%M:%S')}</span></span>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ─── Debug Section ───
    with st.expander("🔍 Debug: Max Qty Calculation"):
        debug_info = get_qty_calc_debug()
        st.json(debug_info)

# ─── Footer ───
st.markdown("""
<div style="text-align:center; padding:1.5rem; color:#333; font-size:0.65rem; border-top:1px solid rgba(255,255,255,0.02); margin-top:1rem;">
    ⚡ TradeOS v3.0 · Professional Screener<br>
    Data: TradingView · Yahoo Finance · DhanHQ
</div>
""", unsafe_allow_html=True)
