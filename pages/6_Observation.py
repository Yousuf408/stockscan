# ═══════════════════════════════════════════════════════════════════════════════
# PAGES / 6_OBSERVATION.PY – PROFESSIONAL SCREENER (WHITE THEME) WITH AUTO-BUY
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query
from tradingview_screener.column import col
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
    get_qty_calc_debug,
    get_access_token,
    _supabase_save_token
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

# ─── TOKEN SESSION STATE ───
if 'show_token_input' not in st.session_state:
    st.session_state['show_token_input'] = False

if 'user_manual_access_token' not in st.session_state:
    st.session_state['user_manual_access_token'] = ''

if 'token_save_success' not in st.session_state:
    st.session_state['token_save_success'] = False

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

HARDCODED_SETTINGS = {
    'price_min': 200,
    'price_max': 2000,
    'market_cap_min': 41_000_000_000,
    'stocks_limit': 50
}

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
        padding: 0.4rem 2rem;
        background: #ffffff;
        border-bottom: 1px solid #e9ecef;
        margin: -0.5rem -1rem 0.3rem -1rem;
        flex-wrap: wrap;
        gap: 0.3rem;
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
        font-size: 1.1rem;
        font-weight: 700;
        color: #1a1a2e;
    }
    .version {
        font-size: 0.55rem;
        color: #888;
        background: #f1f3f5;
        padding: 0.1rem 0.5rem;
        border-radius: 12px;
    }
    .header-center {
        display: flex;
        gap: 1.2rem;
        font-size: 0.75rem;
        flex-wrap: wrap;
    }
    .ticker-item {
        display: flex;
        gap: 0.3rem;
        align-items: center;
        color: #333;
    }
    .ticker-green { color: #28a745; }
    .ticker-red { color: #dc3545; }
    .header-right {
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }
    .status-indicator {
        display: flex;
        align-items: center;
        gap: 0.3rem;
        font-size: 0.75rem;
        color: #333;
    }
    .status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #28a745;
        animation: pulse 2s infinite;
        display: inline-block;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    .clock {
        font-size: 0.75rem;
        color: #888;
        font-variant-numeric: tabular-nums;
    }
    
    .screener-card {
        background: #ffffff;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        overflow: hidden;
        margin-bottom: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .screener-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 1.2rem;
        background: #f8f9fa;
        border-bottom: 1px solid #e9ecef;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    .screener-stats {
        display: flex;
        gap: 1.2rem;
        font-size: 0.75rem;
        flex-wrap: wrap;
        align-items: center;
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
    .screener-controls {
        display: flex;
        gap: 0.8rem;
        align-items: center;
        flex-wrap: wrap;
    }
    .screener-controls .stNumberInput {
        width: 80px !important;
    }
    .screener-controls .stButton button {
        padding: 0.2rem 0.8rem !important;
        font-size: 0.7rem !important;
    }
    
    .filter-badges {
        display: flex;
        gap: 0.3rem;
        flex-wrap: wrap;
    }
    .filter-badge {
        background: #f1f3f5;
        padding: 0.15rem 0.6rem;
        border-radius: 12px;
        font-size: 0.65rem;
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
        padding: 0.5rem 1.2rem;
        background: #f8f9fa;
        border-top: 1px solid #e9ecef;
        flex-wrap: wrap;
        align-items: center;
    }
    
    .stCheckbox label {
        color: #555 !important;
        font-size: 0.75rem !important;
    }
    .stCheckbox label span {
        color: #333 !important;
    }
    
    .stDataFrame {
        background: #ffffff !important;
    }
    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: #ffffff !important;
        border: none !important;
        border-radius: 0 !important;
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
        font-size: 0.55rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        border-bottom: 2px solid #e9ecef !important;
        padding: 0.4rem 0.6rem !important;
        font-weight: 600 !important;
    }
    .stDataFrame tbody tr td {
        background: #ffffff !important;
        color: #333 !important;
        padding: 0.4rem 0.6rem !important;
        border: none !important;
        border-bottom: 1px solid #f1f3f5 !important;
        font-size: 0.75rem !important;
    }
    .stDataFrame tbody tr:hover td {
        background: #f8f9fa !important;
    }
    .stDataFrame tbody tr:last-child td {
        border-bottom: none !important;
    }
    
    .stButton button {
        background: #f1f3f5 !important;
        border: 1px solid #dee2e6 !important;
        color: #333 !important;
        border-radius: 6px !important;
        padding: 0.25rem 0.8rem !important;
        font-size: 0.75rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton button:hover {
        background: #e9ecef !important;
        border-color: #adb5bd !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #28a745, #20c997) !important;
        border: none !important;
        color: #fff !important;
        font-weight: 600 !important;
    }
    .stButton button[kind="primary"]:hover {
        transform: scale(1.03) !important;
        box-shadow: 0 0 20px rgba(40, 167, 69, 0.25) !important;
    }
    .stButton button[kind="primary"]:disabled {
        opacity: 0.3 !important;
        cursor: not-allowed !important;
        transform: none !important;
    }
    
    .footer-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 1.2rem;
        border-top: 1px solid #e9ecef;
        font-size: 0.65rem;
        color: #888;
        flex-wrap: wrap;
        gap: 0.3rem;
    }
    .footer-bar .highlight {
        color: #555;
    }
    .footer-bar .live {
        color: #28a745;
    }
    
    .token-input-container {
        position: relative;
        display: inline-block;
    }
    .token-input-container .stTextInput {
        margin: 0 !important;
        padding: 0 !important;
    }
    .token-input-container .stTextInput input {
        font-size: 0.75rem !important;
        padding: 0.2rem 0.5rem !important;
        height: 28px !important;
        border-radius: 6px !important;
        border: 1px solid #dee2e6 !important;
    }
    .token-input-container .stTextInput input:focus {
        border-color: #28a745 !important;
        box-shadow: 0 0 0 1px #28a745 !important;
    }
    .token-status {
        font-size: 0.6rem;
        color: #28a745;
        margin-left: 0.3rem;
    }
    .token-status.error {
        color: #dc3545;
    }
    
    /* Gear icon button */
    .gear-btn {
        background: transparent !important;
        border: none !important;
        color: #888 !important;
        font-size: 1rem !important;
        padding: 0 0.3rem !important;
        cursor: pointer !important;
    }
    .gear-btn:hover {
        color: #333 !important;
    }
    .gear-btn.active {
        color: #28a745 !important;
    }
    
    @media (max-width: 768px) {
        .tradeos-header {
            padding: 0.3rem 0.75rem;
            flex-direction: column;
            gap: 0.2rem;
        }
        .screener-header {
            flex-direction: column;
            align-items: flex-start;
            padding: 0.4rem 0.75rem;
        }
        .screener-stats {
            font-size: 0.65rem;
            gap: 0.6rem;
        }
        .filter-row {
            padding: 0.3rem 0.75rem;
            gap: 0.5rem;
        }
        .footer-bar {
            flex-direction: column;
            text-align: center;
            padding: 0.3rem 0.75rem;
        }
        .header-center {
            font-size: 0.65rem;
            gap: 0.6rem;
            justify-content: center;
        }
        .screener-controls {
            gap: 0.4rem;
        }
        .screener-controls .stNumberInput {
            width: 60px !important;
        }
    }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_gap_filtered_stocks(df):
    yahoo_tickers = []
    ticker_map = {}
    for row in df.itertuples():
        base = row.ticker.replace('NSE:', '')
        yahoo_ticker = base + '.NS'
        yahoo_tickers.append(yahoo_ticker)
        ticker_map[yahoo_ticker] = row.ticker

    data = yf.download(
        tickers=yahoo_tickers,
        period="10d",
        interval="1d",
        group_by='ticker',
        progress=False,
        threads=True,
        auto_adjust=False
    )

    filtered = []
    rejected = []

    for yahoo_ticker, original_ticker in ticker_map.items():
        if yahoo_ticker not in data:
            filtered.append(original_ticker)
            continue

        hist = data[yahoo_ticker]
        if hist.empty or len(hist) < 2:
            filtered.append(original_ticker)
            continue

        latest_date = hist.index[-1].date()
        latest_data = hist[hist.index.date == latest_date]
        if latest_data.empty:
            filtered.append(original_ticker)
            continue
        today_open = float(latest_data.iloc[0]['Open'])

        prev_rows = hist[hist.index.date < latest_date]
        if prev_rows.empty:
            filtered.append(original_ticker)
            continue
        prev_close = float(prev_rows.iloc[-1]['Close'])
        if prev_close == 0:
            filtered.append(original_ticker)
            continue
        gap_percent = ((today_open - prev_close) / prev_close) * 100

        if abs(gap_percent) >= 2.0:
            rejected.append({
                'ticker': original_ticker,
                'gap_percent': gap_percent,
                'type': 'Gap UP' if gap_percent > 0 else 'Gap DOWN',
                'reason': f"Gap {gap_percent:.2f}%"
            })
        else:
            filtered.append(original_ticker)

    return filtered, rejected

def get_tradingview_stocks():
    try:
        count, df = (Query()
            .select(
                'name', 'close', 'change', 'volume',
                'relative_volume', 'market_cap_basic', 'sector'
            )
            .set_markets('india')
            .where(
                col('close') > HARDCODED_SETTINGS['price_min'],
                col('close') <= HARDCODED_SETTINGS['price_max'],
                col('market_cap_basic') > HARDCODED_SETTINGS['market_cap_min'],
                col('exchange') == 'NSE'
            )
            .order_by('change', ascending=False)
            .limit(HARDCODED_SETTINGS['stocks_limit'])
            .get_scanner_data()
        )
        return count, df
    except Exception as e:
        st.error(f"Error fetching from TradingView: {str(e)}")
        return 0, pd.DataFrame()

def get_intraday_data_for_symbol(yahoo_ticker, period="10d", interval="5m"):
    try:
        data = yf.download(yahoo_ticker, period=period, interval=interval,
                           progress=False, auto_adjust=False, threads=False)
        if data.empty:
            return None
        ist = pytz.timezone('Asia/Kolkata')
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC').tz_convert(ist)
        else:
            data.index = data.index.tz_convert(ist)
        return data
    except:
        return None

def calculate_ema_200(data_5min):
    """Calculate 200 EMA on 5-minute data"""
    if data_5min is None or len(data_5min) < 200:
        return None
    try:
        close_prices = data_5min['Close'].astype(float)
        ema = close_prices.ewm(span=200, adjust=False).mean()
        return float(ema.iloc[-1])
    except:
        return None

def get_candle_data_bulk(tickers_list, max_workers=20):
    results = {}
    symbol_formats = ['.NS', '-NS', '']

    def fetch_one(ticker):
        base_ticker = ticker.replace('NSE:', '')
        for suffix in symbol_formats:
            yahoo_ticker = base_ticker + suffix
            data = get_intraday_data_for_symbol(yahoo_ticker, period="5d", interval="5m")
            if data is not None and not data.empty:
                ist = pytz.timezone('Asia/Kolkata')
                today = datetime.now(ist).date()
                today_data = data[data.index.date == today]
                yesterday_data = data[data.index.date < today]
                prev_close = float(yesterday_data.iloc[-1]['Close']) if len(yesterday_data) > 0 else None
                if today_data.empty:
                    continue
                df_day = today_data

                mask_first = (df_day.index.hour == 9) & (df_day.index.minute >= 10) & (df_day.index.minute <= 20)
                if mask_first.sum() == 0:
                    mask_first = (df_day.index.hour == 9) & (df_day.index.minute < 30)
                    if mask_first.sum() == 0:
                        first_candle = df_day.iloc[0]
                    else:
                        first_candle = df_day[mask_first].iloc[0]
                else:
                    first_candle = df_day[mask_first].iloc[0]

                mask_second = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 25)
                if mask_second.sum() == 0:
                    if len(df_day) >= 2:
                        second_candle = df_day.iloc[1]
                    else:
                        continue
                else:
                    second_candle = df_day[mask_second].iloc[0]

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
                    gap_percent = ((high_9_20 - prev_close) / prev_close) * 100
                else:
                    gap_percent = 0.0
                    prev_close = float(first_candle['Close'])

                # Calculate 200 EMA
                ema_200 = calculate_ema_200(data)
                
                # Get current price for EMA comparison
                current_price = float(data['Close'].iloc[-1])
                ema_status = None
                if ema_200 is not None:
                    ema_status = 'ABOVE' if current_price > ema_200 else 'BELOW'
                else:
                    ema_status = 'NO DATA'

                result = {
                    'high_9_15': float(first_candle['High']),
                    'low_9_15': low_9_15,
                    'close_9_15': float(first_candle['Close']),
                    'open_9_20': float(second_candle['Open']),
                    'high_9_20': float(second_candle['High']),
                    'low_9_20': float(second_candle['Low']),
                    'close_9_20': float(second_candle['Close']),
                    'max_high_up_to_10_15': max_high,
                    'hit_low_9_20_to_35': hit_low_9_20_to_35,
                    'breakout_9_30_to_9_45': breakout_9_30_to_9_45,
                    'prev_close': prev_close,
                    'gap_percent': gap_percent,
                    'yahoo_ticker': yahoo_ticker,
                    'data_date': today.strftime("%Y-%m-%d"),
                    'ema_200_5m': ema_200,
                    'price_vs_ema_200': ema_status,
                    'current_price': float(data['Close'].iloc[-1])
                }
                return base_ticker, result
        return None, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(fetch_one, ticker): ticker for ticker in tickers_list}
        for future in concurrent.futures.as_completed(future_to_ticker):
            base, data = future.result()
            if base and data:
                results[base] = data
    return results

def check_candle_conditions(df, tickers_list):
    with st.spinner('Fetching intraday data from Yahoo Finance...'):
        candle_data = get_candle_data_bulk(tickers_list)

    for col_name in ['candle_9_15_high', 'candle_9_15_low', 'candle_9_20_open',
                     'candle_9_20_high', 'candle_9_20_low', 'candle_9_20_close',
                     'max_high_up_to_10_15', 'hit_low_9_20_to_35',
                     'breakout_9_30_to_9_45', 'data_date', 'prev_close',
                     'gap_percent', 'open_gap_percent', 'passes_candle_check',
                     'candle_check_status', 'yahoo_ticker', 'inside_9_15',
                     'ema_200_5m', 'price_vs_ema_200', 'current_price']:
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
            for key in ['high_9_15', 'low_9_15', 'close_9_15', 'open_9_20',
                        'high_9_20', 'low_9_20', 'close_9_20', 'max_high_up_to_10_15',
                        'hit_low_9_20_to_35', 'breakout_9_30_to_9_45', 'prev_close',
                        'gap_percent', 'yahoo_ticker', 'data_date',
                        'ema_200_5m', 'price_vs_ema_200', 'current_price']:
                df.at[idx, key] = data[key]
            df.at[idx, 'open_gap_percent'] = data['gap_percent']

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
    with st.spinner("🔄 Loading market data..."):
        count, df = get_tradingview_stocks()
        if count == 0:
            return None
        
        filtered_tickers, rejected = get_gap_filtered_stocks(df)
        df = df[df['ticker'].isin(filtered_tickers)].copy()
        df = df.sort_values('change', ascending=False)
        df = df.head(HARDCODED_SETTINGS['stocks_limit'])
        
        tickers_list = df['ticker'].tolist()
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list)
        
        return {
            'df': df,
            'valid': valid,
            'invalid': invalid,
            'failed': failed,
            'rejected': rejected,
            'total_count': count,
            'filtered_count': len(df),
            'timestamp': datetime.now(IST)
        }

# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REFRESH LOGIC
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone('Asia/Kolkata')

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
    1. Inside 9:15 checkbox is checked (filter active)
    2. Current price > 200 EMA
    3. Current price > (9:15 High * 1.0015) [0.15% above]
    """
    # Condition 1: Inside 9:15 must be True
    if row.get('inside_9_15') != True:
        return False, "Not inside 9:15 range"
    
    # Condition 2: Current price > 200 EMA
    ema_status = row.get('price_vs_ema_200')
    if ema_status != 'ABOVE':
        return False, f"Not above 200 EMA (Status: {ema_status})"
    
    # Condition 3: Current price > 9:15 High * 1.0015 (0.15% above)
    high_9_15 = row.get('high_9_15', 0)
    current_price = row.get('current_price', 0)
    
    if high_9_15 <= 0:
        return False, "No 9:15 High data"
    
    if current_price <= 0:
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
    # Check if we've reached daily limit
    today = datetime.now().date()
    if st.session_state['auto_buy_date'] != today:
        # New day - reset counter
        st.session_state['auto_buy_bought_today'] = 0
        st.session_state['auto_buy_stocks_bought'] = []
        st.session_state['auto_buy_date'] = today
    
    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
        return [], [], f"Daily limit of {st.session_state['auto_buy_max_stocks']} stocks reached"
    
    # Filter stocks that haven't been bought yet
    available_stocks = display_df[
        ~display_df['Symbol'].isin(st.session_state['auto_buy_stocks_bought'])
    ].copy()
    
    if available_stocks.empty:
        return [], [], "No new stocks available"
    
    placed_orders = []
    failed_orders = []
    stocks_bought = []
    
    # Check each stock
    for idx, row in available_stocks.iterrows():
        # Check if daily limit reached
        if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
            break
        
        symbol = row['Symbol']
        
        # Check conditions
        meets_conditions, reason = check_auto_buy_conditions(row)
        
        if not meets_conditions:
            failed_orders.append({
                'symbol': symbol,
                'reason': reason
            })
            continue
        
        # Check quantity
        max_qty = row.get('MaxQty', 0)
        if max_qty <= 0:
            failed_orders.append({
                'symbol': symbol,
                'reason': 'No quantity available (insufficient margin)'
            })
            continue
        
        # Place order
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
                'price': row.get('current_price', 0),
                'high_9_15': row.get('high_9_15', 0),
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
    
    # Update bought stocks list
    st.session_state['auto_buy_stocks_bought'].extend(stocks_bought)
    
    return placed_orders, failed_orders, None

# ─────────────────────────────────────────────────────────────────────────────
# TOKEN INPUT HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def handle_token_input():
    """Handle token input and save to Supabase on Enter key"""
    token = st.session_state.get('token_input_value', '').strip()
    if token:
        # Save to Supabase
        _supabase_save_token(token)
        # Update session state
        st.session_state['user_manual_access_token'] = token
        st.session_state['token_save_success'] = True
        # Show success message
        st.success("✅ Token saved to Supabase successfully!")
        # Close the input box after saving
        st.session_state['show_token_input'] = False
        # Force rerun to update
        st.rerun()

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
    
    # Check if token exists
    token_exists = bool(st.session_state.get('user_manual_access_token', ''))
    token_status = "🟢" if token_exists else "🔴"
    
    st.markdown(f"""
    <div class="tradeos-header">
        <div class="header-left">
            <span class="logo">📊 Gap Screener</span>
            <span class="version">v1.0</span>
            <span style="font-size:0.6rem;color:#888;margin-left:0.3rem;">Token: {token_status}</span>
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
            <!-- Gear Icon for Token Input -->
            <button class="gear-btn {'active' if st.session_state.get('show_token_input', False) else ''}" 
                    onclick="document.getElementById('token_toggle').click();">
                ⚙️
            </button>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Hidden button to toggle token input (used by gear icon)
    if st.button("", key="token_toggle", help="Toggle Token Input", 
                 use_container_width=False, 
                 style="display:none;"):
        st.session_state['show_token_input'] = not st.session_state.get('show_token_input', False)
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# APPLY CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(WHITE_THEME_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

# Render Header
render_header()

# ─── Token Input Box (Shows when gear icon is clicked) ───
if st.session_state.get('show_token_input', False):
    with st.container():
        st.markdown("---")
        st.markdown("#### 🔑 Dhan Access Token")
        
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.text_input(
                "Enter your Dhan Access Token",
                value=st.session_state.get('user_manual_access_token', ''),
                key="token_input_value",
                type="password",
                placeholder="Paste your access token here...",
                label_visibility="collapsed",
                on_change=handle_token_input
            )
        with col2:
            if st.button("💾 Save", use_container_width=True):
                handle_token_input()
        with col3:
            if st.button("❌ Close", use_container_width=True):
                st.session_state['show_token_input'] = False
                st.rerun()
        
        st.caption("💡 Token will be saved to Supabase and used for all Dhan API calls.")
        st.markdown("---")

# ─── Check auto-refresh ───
if should_refresh_stage1() or st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()

# ─── Show Gap Screener Content ───
if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()
    
    # ─── Screener Card ───
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
            <div class="screener-controls">
                <span style="font-size:0.7rem;color:#888;">💰</span>
    """, unsafe_allow_html=True)
    
    # Capital Input
    user_capital = st.number_input(
        "",
        min_value=1000,
        max_value=10000000,
        value=int(st.session_state['user_capital']),
        step=1000,
        key="capital_input_header",
        label_visibility="collapsed",
        help="Total capital to divide among stocks"
    )
    st.session_state['user_capital'] = user_capital
    
    st.markdown('<span style="font-size:0.7rem;color:#888;margin-left:0.5rem;">📊</span>', unsafe_allow_html=True)
    
    # Parts Control
    num_parts = st.number_input(
        "",
        min_value=1,
        max_value=10,
        value=int(st.session_state.get('num_parts', 4)),
        step=1,
        key="parts_input_header",
        label_visibility="collapsed",
        help="Divide capital into how many parts"
    )
    st.session_state['num_parts'] = num_parts
    
    # Refresh Button
    if st.button("🔄", key="refresh_btn_header", use_container_width=False):
        st.session_state['stage1_data'] = None
        st.rerun()
    
    st.markdown('</div></div>', unsafe_allow_html=True)
    
    # ─── Apply Filters ───
    is_after_9_25 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=25, second=0)
    is_after_9_30 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=30, second=0)
    
    # ─── Filter Row ───
    st.markdown('<div class="filter-row">', unsafe_allow_html=True)
    
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.8, 1.8, 1.2, 1.2, 1.8])
    
    with filter_col1:
        if is_after_9_25:
            show_inside_only = st.checkbox(
                "📊 Inside 9:15",
                value=st.session_state['show_inside_only'],
                key="inside_checkbox"
            )
            st.session_state['show_inside_only'] = show_inside_only
        else:
            st.info("⏳ 9:20 after 9:25 AM")
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
            st.info("⏳ Breakout after 9:30 AM")
            show_breakout_only = False
    
    with filter_col3:
        amo_test_mode = st.checkbox(
            "🌙 AMO",
            value=st.session_state['amo_mode'],
            key="amo_checkbox"
        )
        st.session_state['amo_mode'] = amo_test_mode
    
    with filter_col4:
        # Auto-Buy Toggle
        auto_buy_toggle = st.checkbox(
            "🤖 Auto-Buy",
            value=st.session_state.get('auto_buy_enabled', False),
            key="auto_buy_toggle"
        )
        st.session_state['auto_buy_enabled'] = auto_buy_toggle
    
    with filter_col5:
        # Auto-Buy Status (Compact)
        if auto_buy_toggle:
            if not show_inside_only:
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
    if show_breakout_only:
        display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]
    if show_inside_only and is_after_9_25:
        display_df = display_df[display_df['inside_9_15'] == True]
    
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
            'name', 'close', 'change', 'gap_percent', 'volume', 'relative_volume',
            'inside_9_15', 'breakout_9_30_to_9_45', 'price_vs_ema_200', 'MaxQty', 'sector',
            'high_9_15', 'current_price'
        ]
        available = [c for c in display_cols if c in display_df.columns]
        display_df = display_df[available].copy()
        
        display_df = display_df.rename(columns={
            'name': 'Symbol',
            'close': 'Price',
            'change': 'Chg%',
            'gap_percent': 'Gap%',
            'volume': 'Volume',
            'relative_volume': 'Rel Vol',
            'inside_9_15': 'Inside 9:15',
            'breakout_9_30_to_9_45': 'Breakout',
            'price_vs_ema_200': '200 EMA',
            'MaxQty': 'MaxQty',
            'sector': 'Sector',
            'high_9_15': 'high_9_15',
            'current_price': 'current_price'
        })
        
        # ─── Format columns with NaN handling ───
        # Add 9:15 High column (from existing high_9_15 data)
        if 'high_9_15' in display_df.columns:
            display_df['9:15 High'] = display_df['high_9_15'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        else:
            display_df['9:15 High'] = "N/A"
        
        # Format existing Price column
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
        
        if 'Breakout' in display_df.columns:
            display_df['Breakout'] = display_df['Breakout'].apply(lambda x: "✅" if x else "❌")
        
        if '200 EMA' in display_df.columns:
            display_df['200 EMA'] = display_df['200 EMA'].apply(
                lambda x: "🟢 ABOVE" if x == 'ABOVE' else ("🔴 BELOW" if x == 'BELOW' else "⚪ NO DATA")
            )
        
        # ─── Auto-Buy Eligibility Check ───
        def check_auto_buy_eligible(row):
            # Check Inside 9:15
            inside_value = row.get('Inside 9:15')
            if inside_value != '✅':
                return '❌ Not Inside'
            
            # Check 200 EMA
            ema_value = row.get('200 EMA')
            if ema_value != '🟢 ABOVE':
                return '❌ Below EMA'
            
            # Check 0.15% above 9:15 High
            high_9_15 = row.get('high_9_15')
            current_price = row.get('Price')
            
            # Clean price if it's formatted
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
        
        # ─── Final columns ───
        final_cols = [
            'Symbol', 'Price', 'Chg%', 'Gap%', 'Volume', 
            'Rel Vol', 'Inside 9:15', 'Breakout', '200 EMA',
            '9:15 High', 'Auto-Buy Status', 'MaxQty', 'Sector'
        ]
        
        existing_cols = [c for c in final_cols if c in display_df.columns]
        display_df = display_df[existing_cols]
        
        # ─── Auto-Buy Execution (Only when enabled) ───
        if st.session_state.get('auto_buy_enabled', False) and st.session_state.get('show_inside_only', False):
            eligible_count = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
            
            if eligible_count > 0 and st.session_state['auto_buy_bought_today'] < st.session_state['auto_buy_max_stocks']:
                with st.spinner("🤖 Auto-buy executing..."):
                    placed, failed, error = execute_auto_buy(display_df)
                
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
                
                # Disable manual buttons when auto-buy is enabled
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
            
            # Show note when auto-buy is enabled
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
        <span>🔑 Token: {'✅' if st.session_state.get('user_manual_access_token', '') else '❌'}</span>
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
