# ═══════════════════════════════════════════════════════════════════════════════
# PAGES / 6_OBSERVATION.PY – PROFESSIONAL GAP SCREENER WITH AUTO-BUY
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

if 'auto_buy_stocks_bought' not in st.session_state:
    st.session_state['auto_buy_stocks_bought'] = []

if 'auto_buy_date' not in st.session_state:
    st.session_state['auto_buy_date'] = datetime.now().date()

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
# CSS - PROFESSIONAL CLEAN THEME
# ─────────────────────────────────────────────────────────────────────────────

PROFESSIONAL_CSS = """
<style>
    /* Reset */
    .stApp { background: #ffffff !important; }
    .stAppViewContainer { background: #ffffff !important; }
    .main > div { background: #ffffff !important; }
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
    
    /* Header */
    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.5rem 2rem;
        background: #ffffff;
        border-bottom: 1px solid #e9ecef;
        margin: -0.5rem -1rem 0.5rem -1rem;
        flex-wrap: wrap;
        gap: 0.5rem;
        position: sticky;
        top: 0;
        z-index: 999;
    }
    .logo { font-size: 1.2rem; font-weight: 700; color: #1a1a2e; }
    .version { font-size: 0.6rem; color: #888; background: #f1f3f5; padding: 0.1rem 0.5rem; border-radius: 12px; }
    .ticker-item { display: flex; gap: 0.4rem; align-items: center; color: #333; font-size: 0.8rem; }
    .ticker-green { color: #28a745; }
    .ticker-red { color: #dc3545; }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #28a745; animation: pulse 2s infinite; display: inline-block; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .clock { font-size: 0.8rem; color: #888; }
    
    /* Page Title */
    .page-title { font-size: 1.3rem; font-weight: 600; color: #1a1a2e; margin: 0.5rem 0 0.75rem 0; }
    .page-title span { font-size: 0.8rem; color: #888; font-weight: 400; }
    
    /* Screener Card */
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
        padding: 0.6rem 1.5rem;
        background: #f8f9fa;
        border-bottom: 1px solid #e9ecef;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .stat-item { color: #888; font-size: 0.75rem; }
    .stat-item strong { color: #1a1a2e; font-weight: 600; }
    .stat-count { color: #28a745; font-weight: 600; }
    .filter-badge {
        background: #f1f3f5;
        padding: 0.15rem 0.6rem;
        border-radius: 12px;
        font-size: 0.65rem;
        color: #888;
        border: 1px solid #e9ecef;
    }
    .filter-badge.active { border-color: #28a745; color: #28a745; background: #f0fff4; }
    
    /* Filter Row */
    .filter-row {
        display: flex;
        gap: 1.5rem;
        padding: 0.5rem 1.5rem;
        background: #f8f9fa;
        border-top: 1px solid #e9ecef;
        flex-wrap: wrap;
        align-items: center;
    }
    .filter-row .stCheckbox label { color: #555 !important; font-size: 0.75rem !important; }
    
    /* Data Table */
    .stDataFrame { background: #ffffff !important; }
    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: #ffffff !important;
        border: none !important;
        border-radius: 0 !important;
    }
    .stDataFrame table { background: #ffffff !important; }
    .stDataFrame tbody { background: #ffffff !important; }
    .stDataFrame tr { background: #ffffff !important; }
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
    .stDataFrame tbody tr:hover td { background: #f8f9fa !important; }
    .stDataFrame tbody tr:last-child td { border-bottom: none !important; }
    
    /* Buttons */
    .stButton button {
        background: #f1f3f5 !important;
        border: 1px solid #dee2e6 !important;
        color: #333 !important;
        border-radius: 6px !important;
        padding: 0.25rem 1rem !important;
        font-size: 0.75rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton button:hover { background: #e9ecef !important; border-color: #adb5bd !important; }
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
    .stButton button[kind="primary"]:disabled { opacity: 0.3 !important; cursor: not-allowed !important; transform: none !important; }
    
    /* Footer */
    .footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 1.5rem;
        border-top: 1px solid #e9ecef;
        font-size: 0.6rem;
        color: #888;
        flex-wrap: wrap;
        gap: 0.3rem;
    }
    .footer .highlight { color: #555; }
    .footer .live { color: #28a745; }
    
    /* Auto-Buy Status */
    .status-active { color: #28a745; font-weight: 600; }
    .status-inactive { color: #888; }
    .status-warning { color: #dc3545; font-weight: 600; }
    
    @media (max-width: 768px) {
        .header { padding: 0.3rem 0.75rem; flex-direction: column; gap: 0.2rem; }
        .filter-row { padding: 0.3rem 0.75rem; gap: 0.5rem; }
        .screener-header { padding: 0.4rem 0.75rem; flex-direction: column; align-items: flex-start; }
        .stat-item { font-size: 0.65rem; }
        .page-title { font-size: 1rem; }
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

                ema_200 = calculate_ema_200(data)
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
    with st.spinner('Fetching intraday data...'):
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
    with st.spinner("Loading market data..."):
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
    if row.get('inside_9_15') != True:
        return False, "Not inside 9:15 range"
    
    ema_status = row.get('price_vs_ema_200')
    if ema_status != 'ABOVE':
        return False, f"Not above 200 EMA"
    
    high_9_15 = row.get('high_9_15', 0)
    current_price = row.get('current_price', 0)
    
    if high_9_15 <= 0:
        return False, "No 9:15 High data"
    
    if current_price <= 0:
        return False, "No current price data"
    
    required_price = high_9_15 * 1.0015
    if current_price <= required_price:
        return False, f"Price {current_price:.2f} <= 9:15 High + 0.15%"
    
    return True, "All conditions met"

def execute_auto_buy(display_df):
    today = datetime.now().date()
    if st.session_state['auto_buy_date'] != today:
        st.session_state['auto_buy_bought_today'] = 0
        st.session_state['auto_buy_stocks_bought'] = []
        st.session_state['auto_buy_date'] = today
    
    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
        return [], [], f"Daily limit reached"
    
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
            failed_orders.append({'symbol': symbol, 'reason': 'Insufficient margin'})
            continue
        
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
# RENDER HEADER
# ─────────────────────────────────────────────────────────────────────────────

def render_header():
    current_time = datetime.now(IST)
    
    st.markdown(f"""
    <div class="header">
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span class="logo">📊 Gap Screener</span>
            <span class="version">v1.0</span>
        </div>
        <div style="display:flex;gap:1.2rem;flex-wrap:wrap;">
            <span class="ticker-item">NIFTY 50 24,856.40 <span class="ticker-green">▲ +0.87%</span></span>
            <span class="ticker-item">SENSEX 81,234.56 <span class="ticker-green">▲ +0.92%</span></span>
            <span class="ticker-item">BANK NIFTY 52,345.67 <span class="ticker-red">▼ -0.23%</span></span>
        </div>
        <div style="display:flex;align-items:center;gap:0.8rem;">
            <span class="status-dot"></span>
            <span style="font-size:0.8rem;color:#333;">Live</span>
            <span class="clock">{current_time.strftime('%H:%M:%S')} IST</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# APPLY CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(PROFESSIONAL_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

render_header()

# ─── Check auto-refresh ───
if should_refresh_stage1() or st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()

# ─── Page Controls ───
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2.5, 1.2, 0.8, 0.8])

with ctrl_col1:
    st.markdown('<div class="page-title">🔍 Gap Screener <span>· Professional Trading Scanner</span></div>', unsafe_allow_html=True)

with ctrl_col2:
    user_capital = st.number_input(
        "💰 Capital",
        min_value=1000,
        max_value=10000000,
        value=int(st.session_state['user_capital']),
        step=1000,
        key="capital_input",
        label_visibility="collapsed"
    )
    st.session_state['user_capital'] = user_capital

with ctrl_col3:
    num_parts = st.number_input(
        "📊 Parts",
        min_value=1,
        max_value=10,
        value=int(st.session_state.get('num_parts', 4)),
        step=1,
        key="parts_input",
        label_visibility="collapsed"
    )
    st.session_state['num_parts'] = num_parts

with ctrl_col4:
    if st.button("🔄 Refresh", key="refresh_btn", use_container_width=True):
        st.session_state['stage1_data'] = None
        st.rerun()

# ─── Show Screener ───
if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()
    
    last_refresh = st.session_state.get('stage1_last_refresh', datetime.now(IST))
    pass_count = len(data['valid'])
    
    # ─── Screener Card ───
    st.markdown(f"""
    <div class="screener-card">
        <div class="screener-header">
            <div style="display:flex;gap:1.2rem;flex-wrap:wrap;">
                <span class="stat-item">📊 Total: <strong class="stat-count">{data['total_count']}</strong></span>
                <span class="stat-item">✅ After Gap: <strong class="stat-count">{data['filtered_count']}</strong></span>
                <span class="stat-item">🎯 Pass Candle: <strong class="stat-count">{pass_count}</strong></span>
                <span class="stat-item">🕐 Last: <strong>{last_refresh.strftime('%H:%M:%S')}</strong></span>
            </div>
            <div style="display:flex;gap:0.3rem;flex-wrap:wrap;">
                <span class="filter-badge active">💰 ₹{HARDCODED_SETTINGS['price_min']}-{HARDCODED_SETTINGS['price_max']}</span>
                <span class="filter-badge active">📊 ≥{HARDCODED_SETTINGS['market_cap_min']/1e9:.0f}B</span>
                <span class="filter-badge active">📈 Gap ±2%</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # ─── Time checks ───
    is_after_9_25 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=25, second=0)
    is_after_9_30 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=30, second=0)
    
    # ─── Filter Row ───
    st.markdown('<div class="filter-row">', unsafe_allow_html=True)
    
    fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns([1.8, 1.8, 1.2, 1.2, 1.8])
    
    with fcol1:
        if is_after_9_25:
            show_inside_only = st.checkbox(
                "📊 Inside 9:15",
                value=st.session_state['show_inside_only'],
                key="inside_checkbox"
            )
            st.session_state['show_inside_only'] = show_inside_only
        else:
            st.info("⏳ 9:20 candle after 9:25 AM")
            show_inside_only = False
    
    with fcol2:
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
    
    with fcol3:
        amo_test_mode = st.checkbox(
            "🌙 AMO",
            value=st.session_state['amo_mode'],
            key="amo_checkbox"
        )
        st.session_state['amo_mode'] = amo_test_mode
    
    with fcol4:
        auto_buy_toggle = st.checkbox(
            "🤖 Auto-Buy",
            value=st.session_state.get('auto_buy_enabled', False),
            key="auto_buy_toggle"
        )
        st.session_state['auto_buy_enabled'] = auto_buy_toggle
    
    with fcol5:
        if auto_buy_toggle:
            if not show_inside_only:
                st.markdown('<span style="color:#dc3545;font-size:0.7rem;font-weight:600;">⚠️ Need Inside 9:15</span>', unsafe_allow_html=True)
            else:
                remaining = st.session_state['auto_buy_max_stocks'] - st.session_state['auto_buy_bought_today']
                eligible_count = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE']) if 'display_df' in locals() else 0
                
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
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ─── Apply Filters ───
    display_df = df.copy()
    if show_breakout_only:
        display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]
    if show_inside_only and is_after_9_25:
        display_df = display_df[display_df['inside_9_15'] == True]
    
    if display_df.empty:
        st.warning("⚠️ No stocks match the selected filters.")
    else:
        # ─── Prepare Data ───
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)
        display_df['Price'] = display_df['close']
        display_df['Symbol'] = display_df['name']
        
        with st.spinner("Calculating quantities..."):
            display_df['MaxQty'] = calculate_max_quantity_column(
                display_df,
                total_capital=st.session_state['user_capital'],
                num_parts=st.session_state.get('num_parts', 4)
            )
        
        # ─── Rename Columns ───
        display_cols = ['name', 'close', 'change', 'gap_percent', 'volume', 'relative_volume',
                       'inside_9_15', 'breakout_9_30_to_9_45', 'price_vs_ema_200', 'MaxQty', 'sector',
                       'high_9_15', 'current_price']
        available = [c for c in display_cols if c in display_df.columns]
        display_df = display_df[available].copy()
        
        display_df = display_df.rename(columns={
            'name': 'Symbol', 'close': 'Price', 'change': 'Chg%', 'gap_percent': 'Gap%',
            'volume': 'Volume', 'relative_volume': 'Rel Vol',
            'inside_9_15': 'Inside 9:15', 'breakout_9_30_to_9_45': 'Breakout',
            'price_vs_ema_200': '200 EMA', 'MaxQty': 'MaxQty', 'sector': 'Sector',
            'high_9_15': 'high_9_15', 'current_price': 'current_price'
        })
        
        # ─── Format Columns ───
        if 'high_9_15' in display_df.columns:
            display_df['9:15 High'] = display_df['high_9_15'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        else:
            display_df['9:15 High'] = "N/A"
        
        if 'Price' in display_df.columns:
            display_df['Price'] = display_df['Price'].apply(
                lambda x: f"₹{x:,.2f}" if pd.notna(x) else "N/A"
            )
        
        if 'Chg%' in display_df.columns:
            display_df['Chg%'] = display_df['Chg%'].apply(
                lambda x: f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%" if pd.notna(x) else "0.00%"
            )
        
        if 'Gap%' in display_df.columns:
            display_df['Gap%'] = display_df['Gap%'].apply(
                lambda x: f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%" if pd.notna(x) else "0.00%"
            )
        
        if 'Volume' in display_df.columns:
            display_df['Volume'] = display_df['Volume'].apply(
                lambda x: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.1f}K" if x >= 1e3 else f"{x:.0f}" if pd.notna(x) else "0"
            )
        
        if 'Rel Vol' in display_df.columns:
            display_df['Rel Vol'] = display_df['Rel Vol'].apply(
                lambda x: f"{x:.2f}x" if pd.notna(x) else "0x"
            )
        
        if 'Inside 9:15' in display_df.columns:
            display_df['Inside 9:15'] = display_df['Inside 9:15'].apply(lambda x: "✅" if x else "❌")
        
        if 'Breakout' in display_df.columns:
            display_df['Breakout'] = display_df['Breakout'].apply(lambda x: "✅" if x else "❌")
        
        if '200 EMA' in display_df.columns:
            display_df['200 EMA'] = display_df['200 EMA'].apply(
                lambda x: "🟢 ABOVE" if x == 'ABOVE' else ("🔴 BELOW" if x == 'BELOW' else "⚪ NO DATA")
            )
        
        # ─── Auto-Buy Eligibility ───
        def check_auto_buy_eligible(row):
            if row.get('Inside 9:15') != '✅':
                return '❌ Not Inside'
            if row.get('200 EMA') != '🟢 ABOVE':
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
        
        # ─── Final Columns ───
        final_cols = ['Symbol', 'Price', 'Chg%', 'Gap%', 'Volume', 'Rel Vol',
                     'Inside 9:15', 'Breakout', '200 EMA', '9:15 High', 
                     'Auto-Buy Status', 'MaxQty', 'Sector']
        existing_cols = [c for c in final_cols if c in display_df.columns]
        display_df = display_df[existing_cols]
        
        # ─── Auto-Buy Execution ───
        if st.session_state.get('auto_buy_enabled', False) and st.session_state.get('show_inside_only', False):
            eligible_count = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
            
            if eligible_count > 0 and st.session_state['auto_buy_bought_today'] < st.session_state['auto_buy_max_stocks']:
                with st.spinner("🤖 Auto-buy executing..."):
                    placed, failed, error = execute_auto_buy(display_df)
                
                if error:
                    st.warning(f"⚠️ {error}")
                else:
                    if placed:
                        st.success(f"✅ {len(placed)} orders placed")
                        st.dataframe(pd.DataFrame(placed), use_container_width=True)
                        st.session_state['auto_buy_orders_placed'].extend(placed)
                    
                    if failed:
                        st.warning(f"⚠️ {len(failed)} failed")
                        st.dataframe(pd.DataFrame(failed), use_container_width=True)
                        st.session_state['auto_buy_orders_failed'].extend(failed)
                    
                    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
                        st.success(f"🎯 Daily limit of {st.session_state['auto_buy_max_stocks']} reached")
        
        # ─── Table + Buy Buttons ───
        table_col, btn_col = st.columns([8.5, 1.5])
        
        with table_col:
            st.dataframe(
                display_df,
                use_container_width=True,
                height=500,
                column_config={
                    "Symbol": st.column_config.TextColumn("SYMBOL", width="small"),
                    "Price": st.column_config.TextColumn("PRICE", width="small"),
                    "Chg%": st.column_config.TextColumn("CHG%", width="small"),
                    "Gap%": st.column_config.TextColumn("GAP%", width="small"),
                    "Volume": st.column_config.TextColumn("VOL", width="small"),
                    "Rel Vol": st.column_config.TextColumn("RELVOL", width="small"),
                    "Inside 9:15": st.column_config.TextColumn("INSIDE", width="small"),
                    "Breakout": st.column_config.TextColumn("BREAK", width="small"),
                    "200 EMA": st.column_config.TextColumn("200 EMA", width="small"),
                    "9:15 High": st.column_config.TextColumn("9:15 HIGH", width="small"),
                    "Auto-Buy Status": st.column_config.TextColumn("AUTO-BUY", width="small"),
                    "MaxQty": st.column_config.NumberColumn("MAXQTY", width="small"),
                    "Sector": st.column_config.TextColumn("SECTOR", width="medium"),
                }
            )
        
        with btn_col:
            for idx, (_, row) in enumerate(display_df.iterrows()):
                symbol = row['Symbol']
                max_qty = row['MaxQty']
                disabled = max_qty <= 0 or st.session_state.get('auto_buy_enabled', False)
                
                if st.button(
                    symbol,
                    key=f"buy_{symbol}_{idx}",
                    disabled=disabled,
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
                st.caption("🔒 Auto-Buy ON")
        
        # ─── Download ───
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 CSV",
            data=csv,
            file_name=f'screener_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )
    
    # ─── Footer ───
    st.markdown(f"""
    <div class="footer">
        <span>🔄 Refreshes every <span class="live">1 min</span></span>
        <span>📊 <span class="highlight">{len(display_df) if 'display_df' in locals() else 0}</span> stocks · 
        <span class="highlight">{pass_count}</span> pass candle</span>
        <span>🤖 Auto-Buy: <span class="{'status-active' if st.session_state.get('auto_buy_enabled', False) else 'status-inactive'}">
        {'🟢 ON' if st.session_state.get('auto_buy_enabled', False) else '⚪ OFF'}</span> · 
        {st.session_state.get('auto_buy_bought_today', 0)}/{st.session_state.get('auto_buy_max_stocks', 5)} today</span>
    </div>
    """, unsafe_allow_html=True)
    
    # ─── Debug ───
    with st.expander("🔍 Debug"):
        debug_info = get_qty_calc_debug()
        st.json(debug_info)

# ─── Footer ───
st.markdown("""
<div style="text-align:center;padding:0.8rem;color:#888;font-size:0.6rem;border-top:1px solid #e9ecef;margin-top:0.5rem;">
    📊 Gap Screener · Data: TradingView · Yahoo Finance · DhanHQ
</div>
""", unsafe_allow_html=True)
