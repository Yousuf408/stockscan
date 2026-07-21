# ═══════════════════════════════════════════════════════════════════════════════
# 6_OBSERVATION.PY – PROFESSIONAL SCREENER (WHITE THEME) WITH AUTO-BUY
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, col
from datetime import datetime, timedelta
import pytz
import concurrent.futures
import warnings
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Import DhanHQ modules ──
from tv_screener.quantity_calculator import (
    calculate_max_quantity_column,
    get_qty_calc_debug
)
from tv_screener.dhan_orders import place_dhan_order
from tv_screener.frontend import display_order_result

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Gap Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────

if 'user_capital' not in st.session_state:
    st.session_state['user_capital'] = 100000.0

if 'num_parts' not in st.session_state:
    st.session_state['num_parts'] = 4

if 'amo_mode' not in st.session_state:
    st.session_state['amo_mode'] = False

if 'stage1_data' not in st.session_state:
    st.session_state['stage1_data'] = None

if 'stage1_loaded' not in st.session_state:
    st.session_state['stage1_loaded'] = False

if 'show_inside_only' not in st.session_state:
    st.session_state['show_inside_only'] = False

if 'show_breakout_only' not in st.session_state:
    st.session_state['show_breakout_only'] = False

if 'stage1_last_refresh' not in st.session_state:
    IST = pytz.timezone('Asia/Kolkata')
    st.session_state['stage1_last_refresh'] = datetime.now(IST)

# ─── AUTO-BUY SESSION STATE ───
if 'auto_buy_enabled' not in st.session_state:
    st.session_state['auto_buy_enabled'] = False

if 'auto_buy_bought_today' not in st.session_state:
    st.session_state['auto_buy_bought_today'] = 0

if 'auto_buy_max_stocks' not in st.session_state:
    st.session_state['auto_buy_max_stocks'] = 5

if 'auto_buy_orders_placed' not in st.session_state:
    st.session_state['auto_buy_orders_placed'] = []

if 'auto_buy_orders_failed' not in st.session_state:
    st.session_state['auto_buy_orders_failed'] = []

if 'auto_buy_last_check' not in st.session_state:
    st.session_state['auto_buy_last_check'] = None

if 'auto_buy_stocks_bought' not in st.session_state:
    st.session_state['auto_buy_stocks_bought'] = []

if 'auto_buy_date' not in st.session_state:
    st.session_state['auto_buy_date'] = datetime.now().date()

# ─── INSIDE 9:15 CACHE ───
if 'inside_pass_symbols' not in st.session_state:
    st.session_state['inside_pass_symbols'] = []

if 'inside_pass_date' not in st.session_state:
    st.session_state['inside_pass_date'] = None

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

HARDCODED_SETTINGS = {
    'price_min': 200,
    'price_max': 3000,
    'market_cap_min': 41_000_000_000,
    'gap_threshold': 2.0,            # Gap ≤ 2%
    'ema_gap_threshold': 0.03        # 3% max gap between open and 200 EMA
}

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Filter Settings")
    st.markdown("---")
    
    # ─── SECTION 1: 200 EMA DISTANCE ───
    st.markdown("### 📈 200 EMA Distance %")
    
    ema_gap_threshold = st.slider(
        "Max distance from 200 EMA",
        min_value=0.5,
        max_value=10.0,
        value=3.0,
        step=0.25,
        key="ema_gap_threshold_slider",
        help="9:15 Open must be within this % above 200 EMA"
    )
    
    st.caption(f"Current: **{ema_gap_threshold}%**")
    
    # Show count of stocks that pass EMA filter
    if 'stage1_data' in st.session_state and st.session_state['stage1_data'] is not None:
        df = st.session_state['stage1_data']['df']
        if 'open_9_15' in df.columns and 'ema_200_9_15' in df.columns:
            df['_ema_gap_pct'] = (df['open_9_15'] - df['ema_200_9_15']) / df['ema_200_9_15']
            count = len(df[df['_ema_gap_pct'] <= (ema_gap_threshold / 100)])
            st.caption(f"📊 Stocks passing: **{count}**")
    
    st.markdown("---")
    
    # ─── SECTION 2: ABOVE PREVIOUS HIGH ───
    st.markdown("### 📊 Previous Day High Filter")
    
    st.checkbox(
        "9:15 High > Previous Day High",
        key="filter_above_prev_high",
        help="Show only stocks where 9:15 candle high is above yesterday's high"
    )
    
    if st.session_state.get('filter_above_prev_high', False):
        st.caption("✅ Active: 9:15 High must be above previous day high")
    else:
        st.caption("⚪ Off: No filter applied")
    
    st.markdown("---")
    
    # Show current filters summary
    st.markdown("**🔍 Active Filters**")
    st.caption(f"📈 EMA Distance: ≤ {ema_gap_threshold}%")
    st.caption(f"📊 Above Prev High: {'✅ ON' if st.session_state.get('filter_above_prev_high', False) else '❌ OFF'}")

# ─────────────────────────────────────────────────────────────────────────────
# CSS - WHITE THEME
# ─────────────────────────────────────────────────────────────────────────────

WHITE_THEME_CSS = """
<style>
    .stApp {
        background: #ffffff !important;
    }
    .stAppViewContainer {
        background: #ffffff !important;
    }
    .main > div {
        background: #ffffff !important;
    }
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        max-width: 1440px !important;
        background: #ffffff !important;
    }
    .css-1d391kg, .st-emotion-cache-1wmy9hl {
        background: #f8f9fa !important;
        border-right: 1px solid #e9ecef !important;
    }
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    
    .tradeos-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.6rem 2rem;
        background: #ffffff;
        border-bottom: 1px solid #e9ecef;
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
        color: #1a1a2e;
    }
    .version {
        font-size: 0.6rem;
        color: #888;
        background: #f1f3f5;
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
        color: #333;
    }
    .ticker-green { color: #28a745; }
    .ticker-red { color: #dc3545; }
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
        color: #333;
    }
    .status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #28a745;
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
        color: #1a1a2e;
    }
    .page-title span {
        font-size: 0.8rem;
        color: #888;
        font-weight: 400;
    }
    
    .stButton button {
        background: #f1f3f5 !important;
        border: 1px solid #dee2e6 !important;
        color: #333 !important;
        border-radius: 8px !important;
        padding: 0.4rem 1.2rem !important;
        font-size: 0.8rem !important;
        transition: all 0.3s ease !important;
    }
    .stButton button:hover {
        background: #e9ecef !important;
        border-color: #adb5bd !important;
    }
    
    .screener-card {
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        overflow: hidden;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .screener-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: #f8f9fa;
        border-bottom: 1px solid #e9ecef;
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
        color: #1a1a2e;
        font-weight: 600;
    }
    .stat-count {
        color: #28a745;
        font-weight: 600;
    }
    .filter-badges {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
    }
    .filter-badge {
        background: #f1f3f5;
        padding: 0.2rem 0.7rem;
        border-radius: 12px;
        font-size: 0.7rem;
        color: #888;
        border: 1px solid #e9ecef;
    }
    .filter-badge.active {
        border-color: #28a745;
        color: #28a745;
        background: #f0fff4;
    }
    
    .filter-row {
        display: flex;
        gap: 1.5rem;
        padding: 0.75rem 1.5rem;
        background: #f8f9fa;
        border-top: 1px solid #e9ecef;
        flex-wrap: wrap;
        align-items: center;
    }
    
    .stCheckbox label {
        color: #555 !important;
        font-size: 0.8rem !important;
    }
    .stCheckbox label span {
        color: #333 !important;
    }
    
    .stDataFrame {
        background: #ffffff !important;
    }
    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: #ffffff !important;
        border: 1px solid #e9ecef !important;
        border-radius: 8px !important;
    }
    .stDataFrame table {
        background: #ffffff !important;
    }
    .stDataFrame tbody {
        background: #ffffff !important;
    }
    .stDataFrame tr {
        background: #ffffff !important;
    }
    .stDataFrame thead tr th {
        background: #f8f9fa !important;
        color: #888 !important;
        font-size: 0.6rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        border-bottom: 2px solid #e9ecef !important;
        padding: 0.6rem 0.8rem !important;
        font-weight: 600 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    .stDataFrame tbody tr td {
        background: #ffffff !important;
        color: #333 !important;
        padding: 0.6rem 0.8rem !important;
        border: none !important;
        border-bottom: 1px solid #f1f3f5 !important;
        font-size: 0.85rem !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    .stDataFrame tbody tr:hover td {
        background: #f8f9fa !important;
    }
    .stDataFrame tbody tr:last-child td {
        border-bottom: none !important;
    }
    
    .footer-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.75rem 1.5rem;
        border-top: 1px solid #e9ecef;
        font-size: 0.7rem;
        color: #888;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .footer-bar .highlight {
        color: #555;
    }
    .footer-bar .live {
        color: #28a745;
    }
    
    .stButton button[kind="secondary"] {
        background: linear-gradient(135deg, #28a745, #20c997) !important;
        border: none !important;
        color: #fff !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.3s ease !important;
    }
    .stButton button[kind="secondary"]:hover {
        transform: scale(1.05) !important;
        box-shadow: 0 0 20px rgba(40, 167, 69, 0.3) !important;
    }
    .stButton button[kind="secondary"]:disabled {
        opacity: 0.3 !important;
        cursor: not-allowed !important;
        transform: none !important;
    }
    
    .stSidebar .stButton button {
        background: transparent !important;
        border: none !important;
        color: #333 !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
        text-align: left !important;
        padding: 0.5rem 1rem !important;
    }
    .stSidebar .stButton button:hover {
        background: #f1f3f5 !important;
        color: #28a745 !important;
    }
    
    /* Auto-buy styles */
    .auto-buy-enabled {
        background: #f0fff4 !important;
        border: 2px solid #28a745 !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        margin: 0.5rem 0 !important;
    }
    .auto-buy-disabled {
        background: #f8f9fa !important;
        border: 2px solid #dee2e6 !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        margin: 0.5rem 0 !important;
    }
    .auto-buy-status-active {
        color: #28a745 !important;
        font-weight: 600 !important;
    }
    .auto-buy-status-inactive {
        color: #888 !important;
        font-weight: 600 !important;
    }
    
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
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND FUNCTIONS (Data & Logic)
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone('Asia/Kolkata')


def get_tradingview_stocks():
    """
    Fetch ALL stocks meeting price & market cap filters (no limit).
    Uses 'gap' column directly from TradingView.
    """
    try:
        count, df = (Query()
            .select(
                'name',
                'close',
                'change',
                'volume',
                'relative_volume',
                'market_cap_basic',
                'sector',
                'gap'
            )
            .set_markets('india')
            .where(
                col('close') > HARDCODED_SETTINGS['price_min'],
                col('close') <= HARDCODED_SETTINGS['price_max'],
                col('market_cap_basic') > HARDCODED_SETTINGS['market_cap_min'],
                col('exchange') == 'NSE'
            )
            .order_by('change', ascending=False)
            .limit(100)
            .get_scanner_data()
        )
        return count, df
    except Exception as e:
        st.error(f"Error fetching from TradingView: {str(e)}")
        return 0, pd.DataFrame()


def filter_by_gap(df):
    """
    Filter stocks with absolute gap <= 2% using TradingView's 'gap' column.
    KEEPS stocks with gap <= 2%.
    """
    df['gap'] = pd.to_numeric(df['gap'], errors='coerce')
    mask = df['gap'].notna() & (abs(df['gap']) <= HARDCODED_SETTINGS['gap_threshold'])
    filtered = df[mask].copy()
    rejected = df[~mask].copy()
    rejected['rejection_reason'] = rejected['gap'].apply(
        lambda x: f"Gap {x:.2f}% (> 2%)" if pd.notna(x) else "No gap data"
    )
    return filtered, rejected


def get_intraday_data_for_symbol(yahoo_ticker, period="5d", interval="5m"):
    """Fetch 5‑min intraday data for a single symbol and convert to IST."""
    try:
        data = yf.download(yahoo_ticker, period=period, interval=interval,
                           progress=False, auto_adjust=False, threads=False)
        if data.empty:
            return None
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC').tz_convert(IST)
        else:
            data.index = data.index.tz_convert(IST)
        return data
    except:
        return None


def calculate_ema_200(data_5min):
    """Calculate 200 EMA on 5‑minute data (last value)."""
    if data_5min is None or len(data_5min) < 200:
        return None
    try:
        close_prices = data_5min['Close'].astype(float)
        ema = close_prices.ewm(span=200, adjust=False).mean()
        return float(ema.iloc[-1])
    except:
        return None


def get_candle_data_bulk(tickers_list, max_workers=20):
    """
    For a list of tickers (NSE:...), fetch 5‑min data and extract key candle values
    (9:15, 9:20, breakout, 200 EMA at 9:15, prev_high, etc.).
    Returns a dict {base_ticker: result_dict}.
    """
    results = {}
    symbol_formats = ['.NS', '-NS', '']

    def fetch_one(ticker):
        base_ticker = ticker.replace('NSE:', '')
        for suffix in symbol_formats:
            yahoo_ticker = base_ticker + suffix
            
            # ─── FETCH 5-MIN INTRADAY DATA ───
            data = get_intraday_data_for_symbol(yahoo_ticker, period="5d", interval="5m")
            if data is None or data.empty:
                continue
            
            today = datetime.now(IST).date()
            today_data = data[data.index.date == today]
            if today_data.empty:
                continue
            
            # ─── FETCH PREVIOUS DAY DATA USING COLAB METHOD ───
            # Download last 2 days of daily data
            daily_data = yf.download(yahoo_ticker, period='2d', progress=False)
            if daily_data.empty or len(daily_data) < 2:
                prev_close = None
                prev_high = None
            else:
                # Get yesterday's data (second last row)
                yesterday = daily_data.iloc[-2]
                prev_close = float(yesterday['Close'].iloc[0]) if hasattr(yesterday['Close'], 'iloc') else float(yesterday['Close'])
                prev_high = float(yesterday['High'].iloc[0]) if hasattr(yesterday['High'], 'iloc') else float(yesterday['High'])
            
            df_day = today_data

            # 9:15 candle (approx 9:10–9:20)
            mask_first = (df_day.index.hour == 9) & (df_day.index.minute >= 10) & (df_day.index.minute <= 20)
            if mask_first.sum() == 0:
                mask_first = (df_day.index.hour == 9) & (df_day.index.minute < 30)
                if mask_first.sum() == 0:
                    first_candle = df_day.iloc[0]
                else:
                    first_candle = df_day[mask_first].iloc[0]
            else:
                first_candle = df_day[mask_first].iloc[0]

            # 9:20 candle (approx 9:20–9:25)
            mask_second = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 25)
            if mask_second.sum() == 0:
                if len(df_day) >= 2:
                    second_candle = df_day.iloc[1]
                else:
                    continue
            else:
                second_candle = df_day[mask_second].iloc[0]

            # Max high up to 10:15
            mask_morning = ((df_day.index.hour == 9) & (df_day.index.minute >= 20)) | \
                           ((df_day.index.hour == 10) & (df_day.index.minute <= 15))
            if mask_morning.sum() > 0:
                max_high = float(df_day.loc[mask_morning, 'High'].max())
            else:
                max_high = float(second_candle['High'])

            low_9_15 = float(first_candle['Low'])
            mask_20_to_35 = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 35)
            hit_low_9_20_to_35 = False
            if mask_20_to_35.sum() > 0:
                candles = df_day.loc[mask_20_to_35]
                hit_low_9_20_to_35 = ((candles['Low'] <= low_9_15) | (candles['Close'] <= low_9_15)).any().item()

            high_9_15 = float(first_candle['High'])
            mask_30_to_45 = (df_day.index.hour == 9) & (df_day.index.minute >= 30) & (df_day.index.minute <= 45)
            breakout_9_30_to_9_45 = False
            if mask_30_to_45.sum() > 0:
                candles = df_day.loc[mask_30_to_45]
                breakout_9_30_to_9_45 = (candles['High'] > high_9_15).any().item()

            if prev_close is not None and prev_close > 0:
                high_9_20 = float(second_candle['High'])
                gap_percent_fallback = ((high_9_20 - prev_close) / prev_close) * 100
            else:
                gap_percent_fallback = 0.0
                prev_close = float(first_candle['Close'])

            first_candle_time = first_candle.name

            # 200 EMA at 9:15
            data_until_9_15 = data[data.index <= first_candle_time]
            ema_200_9_15 = calculate_ema_200(data_until_9_15)

            # Current 200 EMA (for auto‑buy eligibility)
            ema_200_current = calculate_ema_200(data)

            current_price = float(data['Close'].iloc[-1])

            open_9_15 = float(first_candle['Open'])
            if ema_200_9_15 is not None and open_9_15 > ema_200_9_15:
                ema_status_9_15 = 'ABOVE'
            else:
                ema_status_9_15 = 'BELOW'

            if ema_200_current is not None and current_price > ema_200_current:
                ema_status_current = 'ABOVE'
            else:
                ema_status_current = 'BELOW'

            result = {
                'high_9_15': float(first_candle['High']),
                'low_9_15': low_9_15,
                'open_9_15': open_9_15,
                'close_9_15': float(first_candle['Close']),
                'open_9_20': float(second_candle['Open']),
                'high_9_20': float(second_candle['High']),
                'low_9_20': float(second_candle['Low']),
                'close_9_20': float(second_candle['Close']),
                'max_high_up_to_10_15': max_high,
                'hit_low_9_20_to_35': hit_low_9_20_to_35,
                'breakout_9_30_to_9_45': breakout_9_30_to_9_45,
                'prev_close': prev_close,
                'prev_high': prev_high,
                'gap_percent_fallback': gap_percent_fallback,
                'yahoo_ticker': yahoo_ticker,
                'data_date': today.strftime("%Y-%m-%d"),
                'ema_200_9_15': ema_200_9_15,
                'ema_200_current': ema_200_current,
                '200 EMA': ema_status_9_15,
                'current_200_ema_status': ema_status_current,
                'current_price': float(data['Close'].iloc[-1])
            }
            return base_ticker, result
        return None, None

    # CACHE THE ENTIRE BULK FETCH - 24 HOURS
    # Only ONE Yahoo call per day for ALL stocks!
    @st.cache_data(ttl=86400)  # 24 hours
    def _get_cached_candle_data_bulk(tickers_tuple):
        """Cached version - runs only once per day."""
        tickers_list = list(tickers_tuple)
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_ticker = {executor.submit(fetch_one, ticker): ticker for ticker in tickers_list}
            for future in concurrent.futures.as_completed(future_to_ticker):
                base, data = future.result()
                if base and data:
                    results[base] = data
        return results
    
    # Convert list to tuple for caching (hashable)
    tickers_tuple = tuple(tickers_list)
    return _get_cached_candle_data_bulk(tickers_tuple)


def check_candle_conditions(df, tickers_list):
    """
    Enrich dataframe with candle data and compute inside_9_15 and candle pass/fail.
    Returns enriched df, valid_stocks, invalid_stocks, failed_to_fetch.
    """
    with st.spinner('Fetching intraday data from Yahoo Finance...'):
        candle_data = get_candle_data_bulk(tickers_list)

    for col_name in ['candle_9_15_high', 'candle_9_15_low', 'candle_9_20_open',
                     'candle_9_20_high', 'candle_9_20_low', 'candle_9_20_close',
                     'max_high_up_to_10_15', 'hit_low_9_20_to_35',
                     'breakout_9_30_to_9_45', 'data_date', 'prev_close',
                     'prev_high',
                     'gap_percent_fallback', 'open_gap_percent', 'passes_candle_check',
                     'candle_check_status', 'yahoo_ticker', 'inside_9_15',
                     'ema_200_9_15', 'ema_200_current', '200 EMA', 'current_200_ema_status', 'current_price',
                     'open_9_15']:
        df[col_name] = None if col_name != 'inside_9_15' else False
    df['inside_9_15'] = False

    valid_stocks = []
    invalid_stocks = []
    failed_to_fetch = []

    for idx, row in df.iterrows():
        ticker = row['ticker']
        base_ticker = ticker.replace('NSE:', '')
        if base_ticker in candle_data:
            data = candle_data[base_ticker]
            for key in ['high_9_15', 'low_9_15', 'close_9_15', 'open_9_15',
                        'open_9_20', 'high_9_20', 'low_9_20', 'close_9_20',
                        'max_high_up_to_10_15', 'hit_low_9_20_to_35',
                        'breakout_9_30_to_9_45', 'prev_close', 'prev_high',
                        'gap_percent_fallback',
                        'yahoo_ticker', 'data_date', 'ema_200_9_15', 'ema_200_current',
                        '200 EMA', 'current_200_ema_status', 'current_price']:
                df.at[idx, key] = data[key]
            df.at[idx, 'open_gap_percent'] = data['gap_percent_fallback']

            inside_9_15 = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] >= data['low_9_15'])
            df.at[idx, 'inside_9_15'] = inside_9_15

            cond1 = data['close_9_20'] <= data['high_9_15']
            cond2 = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] <= data['high_9_15'])
            cond4 = data['close_9_20'] < data['open_9_20']
            cond5 = not data['hit_low_9_20_to_35']

            if cond1 and cond2 and cond4 and cond5:
                df.at[idx, 'passes_candle_check'] = True
                df.at[idx, 'candle_check_status'] = 'PASS ✓'
                valid_stocks.append(ticker)
            else:
                reasons = []
                if not cond1:
                    reasons.append('9:20 close > 9:15 high')
                if not cond2:
                    reasons.append('9:20 high/low not below 9:15 high')
                if not cond4:
                    reasons.append('9:20 candle not bearish')
                if not cond5:
                    reasons.append('Touched 9:15 low')
                df.at[idx, 'candle_check_status'] = 'FAIL ✗ (' + ', '.join(reasons) + ')'
                invalid_stocks.append(ticker)

        else:
            failed_to_fetch.append(ticker)

    return df, valid_stocks, invalid_stocks, failed_to_fetch


def load_stage1_data():
    """
    Load and process all data for stage1:
    1. Fetch ALL stocks from TV
    2. Apply gap filter (<= 2% from TV)
    3. Fetch candle data (cached for 24 hours)
    4. Apply 200 EMA filter from sidebar slider
    5. Apply Above Previous High filter from sidebar checkbox
    6. Return filtered stocks
    """
    with st.spinner("🔄 Loading market data..."):
        # Step 1: Fetch ALL stocks from TradingView
        count, df = get_tradingview_stocks()
        if count == 0:
            return None
        
        # Step 2: Apply gap filter (<= 2% from TradingView's 'gap' column)
        df, rejected_gap = filter_by_gap(df)
        if df.empty:
            return {
                'df': pd.DataFrame(),
                'valid': [],
                'invalid': [],
                'failed': [],
                'rejected': rejected_gap.to_dict('records') if not rejected_gap.empty else [],
                'total_count': count,
                'filtered_count': 0,
                'timestamp': datetime.now(IST)
            }
        
        # Step 3: Sort by change (gainers)
        df = df.sort_values('change', ascending=False)
        
        # Step 4: Fetch candle data for ALL gap-filtered stocks (CACHED 24 HOURS)
        tickers_list = df['ticker'].tolist()
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list)
        
        # Step 5: APPLY 200 EMA FILTER FROM SIDEBAR SLIDER
        if 'open_9_15' in df.columns and 'ema_200_9_15' in df.columns:
            df['open_9_15'] = pd.to_numeric(df['open_9_15'], errors='coerce')
            df['ema_200_9_15'] = pd.to_numeric(df['ema_200_9_15'], errors='coerce')
            df['_ema_gap_pct'] = (df['open_9_15'] - df['ema_200_9_15']) / df['ema_200_9_15']
            
            # Get EMA gap from sidebar (default 3%)
            ema_gap_limit = st.session_state.get('ema_gap_threshold_slider', 3.0) / 100
            
            mask = (
                (df['open_9_15'].notna()) &
                (df['ema_200_9_15'].notna()) &
                (df['ema_200_9_15'] > 0) &
                (df['open_9_15'] > df['ema_200_9_15']) &
                (df['_ema_gap_pct'] <= ema_gap_limit)
            )
            df = df[mask].copy()
            if '_ema_gap_pct' in df.columns:
                df = df.drop(columns=['_ema_gap_pct'])
        
        # Step 6: APPLY ABOVE PREVIOUS HIGH FILTER (if checkbox is checked)
        if st.session_state.get('filter_above_prev_high', False):
            if 'high_9_15' in df.columns and 'prev_high' in df.columns:
                df['high_9_15'] = pd.to_numeric(df['high_9_15'], errors='coerce')
                df['prev_high'] = pd.to_numeric(df['prev_high'], errors='coerce')
                
                mask = (
                    df['high_9_15'].notna() &
                    df['prev_high'].notna() &
                    (df['prev_high'] > 0) &
                    (df['high_9_15'] >= df['prev_high'])
                )
                df = df[mask].copy()
        
        # Step 7: Show ALL stocks that pass filters
        df = df.sort_values('change', ascending=False)
        
        # Update valid list based on final df
        final_valid = df[df['passes_candle_check'] == True]['ticker'].tolist()
        
        return {
            'df': df,
            'valid': final_valid,
            'invalid': invalid,
            'failed': failed,
            'rejected': rejected_gap.to_dict('records') if not rejected_gap.empty else [],
            'total_count': count,
            'filtered_count': len(df),
            'timestamp': datetime.now(IST)
        }


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REFRESH LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def should_refresh_stage1():
    if 'stage1_last_refresh' not in st.session_state:
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        return True
    
    time_diff = datetime.now(IST) - st.session_state['stage1_last_refresh']
    if time_diff.total_seconds() >= 60:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-BUY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def check_auto_buy_conditions(row):
    """
    Check if a stock meets all auto-buy conditions.
    
    Conditions:
    1. Inside 9:15 checkbox is checked (filter active) - ALREADY FILTERED BY TABLE
    2. Current price > (9:15 High * 1.0015) [0.15% above]
    """
    high_9_15 = row.get('9:15 High', 0)
    current_price = row.get('Price', 0)
    
    if isinstance(current_price, str):
        try:
            current_price = float(current_price.replace('₹', '').replace(',', ''))
        except:
            return False, "Invalid Price format"
    
    if high_9_15 is None or pd.isna(high_9_15) or high_9_15 <= 0:
        return False, "No 9:15 High data"
    
    if current_price is None or pd.isna(current_price) or current_price <= 0:
        return False, "No current price data"
    
    required_price = high_9_15 * 1.0015
    if current_price <= required_price:
        return False, f"Price {current_price:.2f} <= 9:15 High + 0.15% ({required_price:.2f})"
    
    return True, "All conditions met"


def execute_auto_buy(display_df):
    """
    Execute auto-buy for stocks meeting all conditions.
    Returns: (placed_orders, failed_orders, error_message)
    """
    today = datetime.now().date()
    if st.session_state['auto_buy_date'] != today:
        st.session_state['auto_buy_bought_today'] = 0
        st.session_state['auto_buy_stocks_bought'] = []
        st.session_state['auto_buy_date'] = today
    
    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
        return [], [], f"Daily limit of {st.session_state['auto_buy_max_stocks']} stocks reached"
    
    available_stocks = display_df[
        ~display_df['Symbol'].isin(st.session_state['auto_buy_stocks_bought'])
    ].copy()
    
    if available_stocks.empty:
        return [], [], "No new stocks available"
    
    placed_orders = []
    failed_orders = []
    stocks_bought = []
    
    for idx, row in available_stocks.iterrows():
        if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
            break
        
        symbol = row['Symbol']
        meets_conditions, reason = check_auto_buy_conditions(row)
        
        if not meets_conditions:
            failed_orders.append({'symbol': symbol, 'reason': reason})
            continue
        
        max_qty = row.get('MaxQty', 0)
        if max_qty <= 0:
            failed_orders.append({'symbol': symbol, 'reason': 'No quantity available (insufficient margin)'})
            continue
        
        current_price = row.get('Price', 0)
        if isinstance(current_price, str):
            try:
                current_price = float(current_price.replace('₹', '').replace(',', ''))
            except:
                current_price = 0
        
        result = place_dhan_order(
            symbol=symbol,
            quantity=int(max_qty),
            product_type="INTRADAY",
            after_market_order=st.session_state.get('amo_mode', False)
        )
        
        if result['success']:
            placed_orders.append({
                'symbol': symbol,
                'quantity': int(max_qty),
                'price': current_price,
                'order_id': result.get('order_id', 'N/A')
            })
            stocks_bought.append(symbol)
            st.session_state['auto_buy_bought_today'] += 1
        else:
            failed_orders.append({
                'symbol': symbol,
                'quantity': int(max_qty),
                'reason': result.get('error', 'Unknown error')
            })
    
    st.session_state['auto_buy_stocks_bought'].extend(stocks_bought)
    return placed_orders, failed_orders, None


# ─────────────────────────────────────────────────────────────────────────────
# BREAKOUT HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def check_real_time_breakout(row):
    """Check if stock is breaking out in real-time (9:30 onwards)"""
    high_9_15 = row.get('high_9_15', 0)
    current_price = row.get('current_price', 0)
    
    if high_9_15 is None or pd.isna(high_9_15) or high_9_15 <= 0:
        return False
    if current_price is None or pd.isna(current_price) or current_price <= 0:
        return False
    return current_price > high_9_15


def get_breakout_time_status():
    """Returns: ('before_9_30', 'live_checking', 'locked')"""
    current_time = datetime.now(IST)
    time_9_30 = current_time.replace(hour=9, minute=30, second=0)
    time_9_45 = current_time.replace(hour=9, minute=45, second=0)
    
    if current_time < time_9_30:
        return 'before_9_30'
    elif time_9_30 <= current_time <= time_9_45:
        return 'live_checking'
    else:
        return 'locked'


# ─────────────────────────────────────────────────────────────────────────────
# RENDER HEADER
# ─────────────────────────────────────────────────────────────────────────────

def render_header():
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
            <span class="logo">📊 Gap Screener</span>
            <span class="version">v1.0</span>
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


# ─────────────────────────────────────────────────────────────────────────────
# APPLY CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(WHITE_THEME_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

# Render Header
render_header()

# ─── Check if slider/checkbox changed → reload data ───
if 'prev_ema_slider' not in st.session_state:
    st.session_state['prev_ema_slider'] = st.session_state.get('ema_gap_threshold_slider', 3.0)

current_slider = st.session_state.get('ema_gap_threshold_slider', 3.0)
current_checkbox = st.session_state.get('filter_above_prev_high', False)

if 'prev_checkbox' not in st.session_state:
    st.session_state['prev_checkbox'] = current_checkbox

if (current_slider != st.session_state['prev_ema_slider']) or (current_checkbox != st.session_state['prev_checkbox']):
    st.session_state['prev_ema_slider'] = current_slider
    st.session_state['prev_checkbox'] = current_checkbox
    st.session_state['stage1_data'] = None

# ─── Check auto-refresh ───
if should_refresh_stage1() or st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()

# ─── Page Header ───
col1, col2, col3, col4 = st.columns([3, 1.2, 0.8, 1])

with col1:
    st.markdown('<div class="page-title">🔍 Gap Screener <span>· Professional Trading Scanner</span></div>', unsafe_allow_html=True)

with col2:
    user_capital = st.number_input(
        "💰",
        min_value=1000,
        max_value=10000000,
        value=int(st.session_state['user_capital']),
        step=1000,
        key="capital_input",
        label_visibility="collapsed",
        help="Total capital to divide among stocks"
    )
    st.session_state['user_capital'] = user_capital

with col3:
    num_parts = st.number_input(
        "📊",
        min_value=1,
        max_value=10,
        value=int(st.session_state.get('num_parts', 4)),
        step=1,
        key="parts_input",
        label_visibility="collapsed",
        help="Divide capital into how many parts"
    )
    st.session_state['num_parts'] = num_parts

with col4:
    def refresh_table_only():
        st.session_state['stage1_data'] = None
        st.session_state['force_table_refresh'] = True
    
    st.button(
        "🔄 Refresh", 
        key="refresh_btn", 
        use_container_width=True,
        on_click=refresh_table_only
    )

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
                <span class="filter-badge active">📈 Gap ≤ 2%</span>
                <span class="filter-badge active">📈 EMA ≤ {st.session_state.get('ema_gap_threshold_slider', 3.0)}%</span>
                {f'<span class="filter-badge active">📊 Above Prev High ✅</span>' if st.session_state.get('filter_above_prev_high', False) else ''}
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # ─── Apply Filters ───
    is_after_9_25 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=25, second=0)
    is_after_9_30 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=30, second=0)
    is_after_9_45 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=45, second=0)
    
    # ─── Filter Row ───
    st.markdown('<div class="filter-row">', unsafe_allow_html=True)
    
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.8, 1.8, 1.2, 1.2, 1.8])
    
    with filter_col1:
        if is_after_9_25:
            st.checkbox(
                "📊 Inside 9:15",
                key="show_inside_only"
            )
        else:
            st.info("⏳ 9:20 after 9:25 AM")
    
    with filter_col2:
        breakout_status = get_breakout_time_status()
        if breakout_status == 'before_9_30':
            st.info("⏳ Breakout after 9:30 AM")
        else:
            st.checkbox(
                "⚡ Breakout 9:30-9:45",
                key="show_breakout_only"
            )
    
    with filter_col3:
        st.checkbox(
            "🌙 AMO",
            key="amo_mode"
        )
    
    with filter_col4:
        st.checkbox(
            "🤖 Auto-Buy",
            key="auto_buy_enabled"
        )
    
    with filter_col5:
        if st.session_state.get('auto_buy_enabled', False):
            if not st.session_state.get('show_inside_only', False):
                st.markdown('<span style="color:#dc3545;font-size:0.7rem;font-weight:600;">⚠️ Need Inside 9:15</span>', unsafe_allow_html=True)
            else:
                remaining = st.session_state['auto_buy_max_stocks'] - st.session_state['auto_buy_bought_today']
                eligible_count = 0
                if 'display_df' in locals() and not display_df.empty and 'Auto-Buy Status' in display_df.columns:
                    eligible_count = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
                
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:8px;font-size:0.7rem;padding:2px 0;">
                    <span style="color:#28a745;font-weight:600;">🟢 ACTIVE</span>
                    <span style="color:#888;">|</span>
                    <span style="color:#333;">🎯 {eligible_count}</span>
                    <span style="color:#888;">|</span>
                    <span style="color:#333;">📊 {remaining}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#888;font-size:0.7rem;">⚪ Auto-Buy OFF</span>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # Close screener-card
    
    # ─── Apply filters to dataframe ───
    display_df = df.copy()
    
    # Get breakout time status
    breakout_status = get_breakout_time_status()
    
    # --- INSIDE 9:15 FILTER (with caching) ---
    if st.session_state.get('show_inside_only', False) and is_after_9_25:
        today = datetime.now().date()
        if st.session_state.get('inside_pass_date') == today and st.session_state.get('inside_pass_symbols'):
            # Use cached symbols
            display_df = display_df[display_df['ticker'].isin(st.session_state['inside_pass_symbols'])]
        else:
            # Compute the filter condition (inside_9_15 only - EMA already filtered)
            if 'inside_9_15' in display_df.columns:
                mask = display_df['inside_9_15'] == True
                pass_symbols = display_df.loc[mask, 'ticker'].tolist()
                st.session_state['inside_pass_symbols'] = pass_symbols
                st.session_state['inside_pass_date'] = today
                display_df = display_df[mask].copy()
            else:
                display_df = display_df[display_df['inside_9_15'] == True]
    
    # --- BREAKOUT FILTER ---
    if st.session_state.get('show_breakout_only', False):
        if breakout_status == 'before_9_30':
            pass
        elif breakout_status == 'live_checking':
            display_df['_real_time_breakout'] = display_df.apply(check_real_time_breakout, axis=1)
            display_df = display_df[display_df['_real_time_breakout'] == True]
        else:
            display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]
    
    if display_df.empty:
        st.warning("⚠️ No stocks match the selected filters.")
    else:
        # ─── Prepare display dataframe ───
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)
        
        display_df['Price'] = display_df['close']
        display_df['Symbol'] = display_df['name']
        
        with st.spinner("Calculating max quantity (DhanHQ margin)..."):
            display_df['MaxQty'] = calculate_max_quantity_column(
                display_df,
                total_capital=st.session_state['user_capital'],
                num_parts=st.session_state.get('num_parts', 4)
            )
        
        # ─── Create display columns ───
        display_cols = [
            'name', 'close', 'change', 'gap', 'volume', 'relative_volume',
            'inside_9_15', 'breakout_9_30_to_9_45', '200 EMA', 'MaxQty', 'sector',
            'high_9_15', 'current_price', 'close_9_15', 'ema_200_9_15', 'ema_200_current',
            'current_200_ema_status', 'prev_high'
        ]
        available = [c for c in display_cols if c in display_df.columns]
        display_df = display_df[available].copy()
        
        display_df = display_df.rename(columns={
            'name': 'Symbol',
            'close': 'Price',
            'change': 'Chg%',
            'gap': 'Gap%',
            'volume': 'Volume',
            'relative_volume': 'Rel Vol',
            'inside_9_15': 'Inside 9:15',
            'breakout_9_30_to_9_45': 'Breakout',
            'MaxQty': 'MaxQty',
            'sector': 'Sector',
            'high_9_15': 'high_9_15',
            'current_price': 'current_price',
            'prev_high': 'Prev Day High'
        })
        
        # ─── Format columns with NaN handling ───
        if 'high_9_15' in display_df.columns:
            display_df['9:15 High'] = display_df['high_9_15'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        else:
            display_df['9:15 High'] = "N/A"
        
        if 'Prev Day High' in display_df.columns:
            display_df['Prev Day High'] = display_df['Prev Day High'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        else:
            display_df['Prev Day High'] = "N/A"
        
        if 'Price' in display_df.columns:
            display_df['Price'] = display_df['Price'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        
        def format_chg(x):
            if pd.isna(x) or x is None:
                return "0.00%"
            return f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%"
        
        if 'Chg%' in display_df.columns:
            display_df['Chg%'] = display_df['Chg%'].apply(format_chg)
        
        def format_gap(x):
            if pd.isna(x) or x is None:
                return "0.00%"
            return f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%"
        
        if 'Gap%' in display_df.columns:
            display_df['Gap%'] = display_df['Gap%'].apply(format_gap)
        
        def format_volume(x):
            if pd.isna(x) or x is None:
                return "0"
            if x >= 1e6:
                return f"{x/1e6:.1f}M"
            elif x >= 1e3:
                return f"{x/1e3:.1f}K"
            return f"{x:.0f}"
        
        if 'Volume' in display_df.columns:
            display_df['Volume'] = display_df['Volume'].apply(format_volume)
        
        def format_relvol(x):
            if pd.isna(x) or x is None:
                return "0x"
            return f"{x:.2f}x"
        
        if 'Rel Vol' in display_df.columns:
            display_df['Rel Vol'] = display_df['Rel Vol'].apply(format_relvol)
        
        if 'Inside 9:15' in display_df.columns:
            display_df['Inside 9:15'] = display_df['Inside 9:15'].apply(lambda x: "✅" if x else "❌")
        
        # ─── Breakout Column - Show real-time status during live checking ───
        def get_breakout_display(row):
            breakout_status = get_breakout_time_status()
            
            if breakout_status == 'before_9_30':
                return "⏳ Waiting"
            elif breakout_status == 'live_checking':
                high_9_15 = row.get('high_9_15', 0)
                current_price = row.get('current_price', 0)
                if high_9_15 <= 0 or current_price <= 0:
                    return "⚪ N/A"
                if current_price > high_9_15:
                    return "✅ BREAKOUT"
                else:
                    return "❌ Below 9:15 High"
            else:
                breakout_val = row.get('Breakout', False)
                return "✅" if breakout_val else "❌"
        
        display_df['Breakout'] = display_df.apply(get_breakout_display, axis=1)
        
        # ─── 200 EMA Column - Show 200 EMA at 9:15 AM with color ───
        def format_ema_with_color(row):
            ema_value = row.get('ema_200_9_15')
            
            if ema_value is None or pd.isna(ema_value) or ema_value <= 0:
                return "⚪ N/A"
            
            close_9_15 = row.get('close_9_15', 0)
            if close_9_15 > ema_value:
                return f"🟢 ₹{ema_value:,.2f}"
            else:
                return f"🔴 ₹{ema_value:,.2f}"
        
        display_df['200 EMA'] = display_df.apply(format_ema_with_color, axis=1)
        
        # ─── Auto-Buy Eligibility Check ───
        def check_auto_buy_eligible(row):
            inside_value = row.get('Inside 9:15')
            if inside_value != '✅':
                return '❌ Not Inside'
            
            ema_status = row.get('current_200_ema_status')
            if ema_status != 'ABOVE':
                return '❌ Below EMA'
            
            high_9_15 = row.get('high_9_15')
            current_price = row.get('Price')
            
            if isinstance(current_price, str):
                try:
                    current_price = float(current_price.replace('₹', '').replace(',', ''))
                except:
                    return '❌ Invalid Price'
            
            if high_9_15 is None or pd.isna(high_9_15) or high_9_15 <= 0:
                return '❌ No 9:15 High'
            
            if current_price is None or pd.isna(current_price) or current_price <= 0:
                return '❌ No Price'
            
            required_price = high_9_15 * 1.0015
            if current_price > required_price:
                return '✅ ELIGIBLE'
            else:
                return f'❌ Need > {required_price:.2f}'
        
        display_df['Auto-Buy Status'] = display_df.apply(check_auto_buy_eligible, axis=1)
        
        # ─── Reset index ───
        display_df = display_df.reset_index(drop=True)
        display_df.index = display_df.index + 1
        
        # ─── Final columns ───
        final_cols = [
            'Symbol', 'Price', 'Chg%', 'Gap%', 'Volume', 
            'Rel Vol', 'Inside 9:15', 'Breakout', '200 EMA',
            '9:15 High', 'Prev Day High', 'Auto-Buy Status', 'MaxQty', 'Sector'
        ]
        
        existing_cols = [c for c in final_cols if c in display_df.columns]
        display_df = display_df[existing_cols]
        
        # ─── Auto-Buy Execution ───
        if st.session_state.get('auto_buy_enabled', False) and st.session_state.get('show_inside_only', False):
            eligible_count = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
            
            if eligible_count > 0 and st.session_state['auto_buy_bought_today'] < st.session_state['auto_buy_max_stocks']:
                with st.spinner("🤖 Auto-buy executing..."):
                    filtered_symbols = display_df['Symbol'].tolist()
                    
                    auto_buy_df = df[df['name'].isin(filtered_symbols)].copy()
                    auto_buy_df['Symbol'] = auto_buy_df['name']
                    auto_buy_df['Price'] = auto_buy_df['close']
                    auto_buy_df['9:15 High'] = auto_buy_df['high_9_15']
                    
                    maxqty_dict = display_df.set_index('Symbol')['MaxQty'].to_dict()
                    auto_buy_df['MaxQty'] = auto_buy_df['Symbol'].map(maxqty_dict).fillna(0)
                    
                    placed, failed, error = execute_auto_buy(auto_buy_df)
                
                if error:
                    st.warning(f"⚠️ {error}")
                else:
                    if placed:
                        st.success(f"✅ {len(placed)} orders placed successfully!")
                        placed_df = pd.DataFrame(placed)
                        st.dataframe(placed_df, use_container_width=True)
                        st.session_state['auto_buy_orders_placed'].extend(placed)
                    
                    if failed:
                        st.warning(f"⚠️ {len(failed)} orders failed")
                        failed_df = pd.DataFrame(failed)
                        st.dataframe(failed_df, use_container_width=True)
                        st.session_state['auto_buy_orders_failed'].extend(failed)
                    
                    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
                        st.success(f"🎯 Daily limit of {st.session_state['auto_buy_max_stocks']} stocks reached!")
        
        # ─── TABLE + BUY BUTTONS ───
        table_col, button_col = st.columns([8.5, 1.5])
        
        with table_col:
            st.dataframe(
                display_df,
                use_container_width=True,
                height=600,
                column_config={
                    "Symbol": st.column_config.TextColumn("SYMBOL", width="small"),
                    "Price": st.column_config.TextColumn("PRICE", width="small"),
                    "Chg%": st.column_config.TextColumn("CHG%", width="small"),
                    "Gap%": st.column_config.TextColumn("GAP%", width="small"),
                    "Volume": st.column_config.TextColumn("VOLUME", width="small"),
                    "Rel Vol": st.column_config.TextColumn("RELVOL", width="small"),
                    "Inside 9:15": st.column_config.TextColumn("INSIDE", width="small"),
                    "Breakout": st.column_config.TextColumn("BREAKOUT", width="small"),
                    "200 EMA": st.column_config.TextColumn("200 EMA", width="small"),
                    "9:15 High": st.column_config.TextColumn("9:15 HIGH", width="small"),
                    "Prev Day High": st.column_config.TextColumn("PREV HIGH", width="small"),
                    "Auto-Buy Status": st.column_config.TextColumn("AUTO-BUY", width="small"),
                    "MaxQty": st.column_config.NumberColumn("MAXQTY", width="small"),
                    "Sector": st.column_config.TextColumn("SECTOR", width="medium"),
                }
            )
        
        with button_col:
            for idx, (_, row) in enumerate(display_df.iterrows()):
                symbol = row['Symbol']
                max_qty = row['MaxQty']
                btn_label = f"{symbol}" + (" 🌙" if st.session_state.get('amo_mode', False) else "")
                
                if st.button(
                    btn_label,
                    key=f"buy_{symbol}_{idx}",
                    disabled=(max_qty <= 0 or st.session_state.get('auto_buy_enabled', False)),
                    use_container_width=True
                ):
                    with st.spinner(f"Placing order for {symbol}..."):
                        result = place_dhan_order(
                            symbol,
                            quantity=int(max_qty),
                            product_type="INTRADAY",
                            after_market_order=st.session_state.get('amo_mode', False),
                            amo_time="OPEN"
                        )
                        display_order_result(symbol, result)
            
            if st.session_state.get('auto_buy_enabled', False):
                st.caption("🔒 Manual buttons disabled when Auto-Buy is ON")
        
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
        <span>🤖 Auto-Buy: {'🟢 ON' if st.session_state.get('auto_buy_enabled', False) else '⚪ OFF'} · 
        {st.session_state.get('auto_buy_bought_today', 0)}/{st.session_state.get('auto_buy_max_stocks', 5)} today</span>
    </div>
    """, unsafe_allow_html=True)
    
    # ─── Debug Section ───
    with st.expander("🔍 Debug: Max Qty Calculation"):
        debug_info = get_qty_calc_debug()
        st.json(debug_info)

# ─── Footer ───
st.markdown("""
<div style="text-align:center; padding:1.5rem; color:#888; font-size:0.65rem; border-top:1px solid #e9ecef; margin-top:1rem;">
    📊 Gap Screener · Professional Trading Scanner<br>
    Data: TradingView · Yahoo Finance · DhanHQ
</div>
""", unsafe_allow_html=True)
