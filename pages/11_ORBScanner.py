# ═══════════════════════════════════════════════════════════════════════════════
# 6_OBSERVATION.PY – PROFESSIONAL SCREENER (WHITE THEME) WITH AUTO-BUY
# OPTIMIZED VERSION: Batch downloading + Parallel Auto-Buy + WebSocket Live Prices
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, col
from datetime import datetime
import pytz
import concurrent.futures
import warnings
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

from tv_screener.quantity_calculator import calculate_max_quantity_column, get_qty_calc_debug
from tv_screener.dhan_orders import place_dhan_order
from tv_screener.frontend import display_order_result
from tv_screener.dhan_websocket import start_websocket, get_live_price, stop_websocket

warnings.filterwarnings('ignore')
IST = pytz.timezone('Asia/Kolkata')

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gap Screener", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
SESSION_DEFAULTS = {
    'user_capital': 100000.0,
    'num_parts': 4,
    'amo_mode': False,
    'stage1_data': None,
    'stage1_loaded': False,
    'show_inside_only': False,
    'show_breakout_only': False,
    'show_small_candle': False,
    'auto_buy_enabled': False,
    'auto_buy_bought_today': 0,
    'auto_buy_max_stocks': 5,
    'auto_buy_orders_placed': [],
    'auto_buy_orders_failed': [],
    'auto_buy_last_check': None,
    'auto_buy_stocks_bought': [],
    'auto_buy_date': datetime.now().date(),
    'inside_pass_symbols': [],
    'inside_pass_date': None,
    'prev_ema_slider': 3.0,
    'prev_checkbox': False,
    'force_table_refresh': False,
    'ws_initialized': False,
}
for key, val in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val
if 'stage1_last_refresh' not in st.session_state:
    st.session_state['stage1_last_refresh'] = datetime.now(IST)

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
HARDCODED_SETTINGS = {
    'price_min': 200,
    'price_max': 3000,
    'market_cap_min': 41_000_000_000,
    'gap_threshold': 2.0,
    'ema_gap_threshold': 0.03,
    'tv_limit': 150,
    'cache_ttl': 86400,
    'max_workers': 20,
    'small_candle_threshold': 1.5,
    'batch_size': 25,
    'max_batch_workers': 4,
}

# ─────────────────────────────────────────────────────────────────────────────
# CSS - WHITE THEME
# ─────────────────────────────────────────────────────────────────────────────
WHITE_THEME_CSS = """
<style>
    .stApp, .stAppViewContainer, .main > div, .block-container { background: #ffffff !important; }
    .block-container { padding: 0 !important; max-width: 1440px !important; }
    .css-1d391kg, .st-emotion-cache-1wmy9hl { background: #f8f9fa !important; border-right: 1px solid #e9ecef !important; }
    #MainMenu, footer, header, .stDeployButton { display: none !important; }
    .tradeos-header { display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 2rem; background: #fff; border-bottom: 1px solid #e9ecef; margin: -0.5rem -1rem 0.5rem -1rem; flex-wrap: wrap; gap: 0.5rem; position: sticky; top: 0; z-index: 999; }
    .header-left { display: flex; align-items: center; gap: 0.75rem; }
    .logo { font-size: 1.3rem; font-weight: 700; color: #1a1a2e; }
    .version { font-size: 0.6rem; color: #888; background: #f1f3f5; padding: 0.1rem 0.5rem; border-radius: 12px; }
    .header-center { display: flex; gap: 1.5rem; font-size: 0.8rem; flex-wrap: wrap; }
    .ticker-item { display: flex; gap: 0.4rem; align-items: center; color: #333; }
    .ticker-green { color: #28a745; }
    .ticker-red { color: #dc3545; }
    .header-right { display: flex; align-items: center; gap: 1rem; }
    .status-indicator { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; color: #333; }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #28a745; animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .clock { font-size: 0.8rem; color: #888; font-variant-numeric: tabular-nums; }
    .page-title { font-size: 1.4rem; font-weight: 600; color: #1a1a2e; }
    .page-title span { font-size: 0.8rem; color: #888; font-weight: 400; }
    .stButton button { background: #f1f3f5 !important; border: 1px solid #dee2e6 !important; color: #333 !important; border-radius: 8px !important; padding: 0.4rem 1.2rem !important; font-size: 0.8rem !important; transition: all 0.3s ease !important; }
    .stButton button:hover { background: #e9ecef !important; border-color: #adb5bd !important; }
    .screener-card { background: #fff; border-radius: 12px; border: 1px solid #e9ecef; overflow: hidden; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .screener-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; background: #f8f9fa; border-bottom: 1px solid #e9ecef; flex-wrap: wrap; gap: 0.75rem; }
    .screener-stats { display: flex; gap: 1.5rem; font-size: 0.8rem; flex-wrap: wrap; }
    .stat-item { color: #888; }
    .stat-item strong { color: #1a1a2e; font-weight: 600; }
    .stat-count { color: #28a745; font-weight: 600; }
    .filter-badges { display: flex; gap: 0.4rem; flex-wrap: wrap; }
    .filter-badge { background: #f1f3f5; padding: 0.2rem 0.7rem; border-radius: 12px; font-size: 0.7rem; color: #888; border: 1px solid #e9ecef; }
    .filter-badge.active { border-color: #28a745; color: #28a745; background: #f0fff4; }
    .filter-row { display: flex; gap: 1.5rem; padding: 0.75rem 1.5rem; background: #f8f9fa; border-top: 1px solid #e9ecef; flex-wrap: wrap; align-items: center; }
    .stCheckbox label { color: #555 !important; font-size: 0.8rem !important; }
    .stDataFrame { background: #fff !important; }
    .stDataFrame [data-testid="stDataFrameResizable"] { background: #fff !important; border: 1px solid #e9ecef !important; border-radius: 8px !important; }
    .stDataFrame thead tr th { background: #f8f9fa !important; color: #888 !important; font-size: 0.6rem !important; text-transform: uppercase !important; border-bottom: 2px solid #e9ecef !important; padding: 0.6rem 0.8rem !important; font-weight: 600 !important; }
    .stDataFrame tbody tr td { background: #fff !important; color: #333 !important; padding: 0.6rem 0.8rem !important; border-bottom: 1px solid #f1f3f5 !important; font-size: 0.85rem !important; }
    .stDataFrame tbody tr:hover td { background: #f8f9fa !important; }
    .stDataFrame tbody tr:last-child td { border-bottom: none !important; }
    .footer-bar { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1.5rem; border-top: 1px solid #e9ecef; font-size: 0.7rem; color: #888; flex-wrap: wrap; gap: 0.5rem; }
    .footer-bar .highlight { color: #555; }
    .footer-bar .live { color: #28a745; }
    .stButton button[kind="secondary"] { background: linear-gradient(135deg, #28a745, #20c997) !important; border: none !important; color: #fff !important; font-weight: 600 !important; border-radius: 6px !important; }
    .stButton button[kind="secondary"]:hover { transform: scale(1.05) !important; box-shadow: 0 0 20px rgba(40,167,69,0.3) !important; }
    .stButton button[kind="secondary"]:disabled { opacity: 0.3 !important; cursor: not-allowed !important; transform: none !important; }
    .auto-buy-enabled { background: #f0fff4 !important; border: 2px solid #28a745 !important; border-radius: 12px !important; padding: 1rem !important; margin: 0.5rem 0 !important; }
    .auto-buy-disabled { background: #f8f9fa !important; border: 2px solid #dee2e6 !important; border-radius: 12px !important; padding: 1rem !important; margin: 0.5rem 0 !important; }
    .auto-buy-status-active { color: #28a745 !important; font-weight: 600 !important; }
    .auto-buy-status-inactive { color: #888 !important; font-weight: 600 !important; }
    @media (max-width:768px) { .tradeos-header { padding: 0.5rem 0.75rem; flex-direction: column; gap: 0.3rem; margin: -0.5rem -0.5rem 0.5rem -0.5rem; } .header-center { font-size: 0.7rem; gap: 0.8rem; justify-content: center; } .page-title { font-size: 1.1rem; } .screener-header { flex-direction: column; align-items: flex-start; padding: 0.75rem; } .screener-stats { font-size: 0.7rem; gap: 0.8rem; } .footer-bar { flex-direction: column; text-align: center; padding: 0.5rem 0.75rem; } }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def format_volume(x):
    if pd.isna(x) or x is None:
        return "0"
    if x >= 1e6:
        return f"{x/1e6:.1f}M"
    if x >= 1e3:
        return f"{x/1e3:.1f}K"
    return f"{x:.0f}"

def format_pct(x):
    if pd.isna(x) or x is None:
        return "0.00%"
    return f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%"

def format_price(x):
    return f"₹{x:,.2f}" if pd.notna(x) else "N/A"

def safe_int(x):
    try:
        if pd.isna(x) or x <= 0 or x > 1e9:
            return 0
        return int(float(x))
    except:
        return 0

# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────
def init_websocket():
    """Initialize WebSocket connection with stocks from table"""
    if st.session_state.get('stage1_data') is not None:
        df = st.session_state['stage1_data']['df']
        if not df.empty:
            symbols = df['name'].tolist()
            start_websocket(symbols)
            st.session_state['ws_initialized'] = True

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND FUNCTIONS - OPTIMIZED WITH BATCH DOWNLOADING
# ─────────────────────────────────────────────────────────────────────────────

def get_tradingview_stocks():
    try:
        count, df = (Query()
            .select('name', 'close', 'change', 'volume', 'relative_volume', 'market_cap_basic', 'sector', 'gap')
            .set_markets('india')
            .where(
                col('close') > HARDCODED_SETTINGS['price_min'],
                col('close') <= HARDCODED_SETTINGS['price_max'],
                col('market_cap_basic') > HARDCODED_SETTINGS['market_cap_min'],
                col('exchange') == 'NSE'
            )
            .order_by('change', ascending=False)
            .limit(HARDCODED_SETTINGS['tv_limit'])
            .get_scanner_data()
        )
        return count, df
    except Exception as e:
        st.error(f"Error fetching from TradingView: {str(e)}")
        return 0, pd.DataFrame()

def filter_by_gap(df):
    df['gap'] = pd.to_numeric(df['gap'], errors='coerce')
    mask = df['gap'].notna() & (abs(df['gap']) <= HARDCODED_SETTINGS['gap_threshold'])
    return df[mask].copy(), df[~mask].copy()

# ─── OPTIMIZED: Batch download for multiple stocks ───
def get_intraday_data_batch(tickers_list, period="5d", interval="5m"):
    try:
        if not tickers_list:
            return {}
        
        tickers_with_suffix = []
        for t in tickers_list:
            t = t.replace('NSE:', '')
            if not t.endswith('.NS') and not t.endswith('-NS'):
                tickers_with_suffix.append(f"{t}.NS")
            else:
                tickers_with_suffix.append(t)
        
        data = yf.download(
            tickers_with_suffix,
            period=period,
            interval=interval,
            group_by='ticker',
            progress=False,
            auto_adjust=False,
            threads=True
        )
        
        result = {}
        for ticker in tickers_with_suffix:
            if ticker in data and not data[ticker].empty:
                df = data[ticker]
                if df.index.tz is None:
                    df.index = df.index.tz_localize('UTC').tz_convert(IST)
                else:
                    df.index = df.index.tz_convert(IST)
                result[ticker] = df
        
        return result
    except Exception as e:
        print(f"Batch download error: {e}")
        return {}

# ─── OPTIMIZED: Process batch of tickers ───
def process_candle_data_batch(tickers_batch):
    results = {}
    
    if not tickers_batch:
        return results
    
    batch_data = get_intraday_data_batch(tickers_batch, period="5d", interval="5m")
    
    if not batch_data:
        return results
    
    for yahoo_ticker, data in batch_data.items():
        base_ticker = yahoo_ticker.replace('.NS', '').replace('-NS', '')
        
        if data is None or data.empty:
            continue
        
        today = datetime.now(IST).date()
        today_data = data[data.index.date == today]
        if today_data.empty:
            continue
        
        daily_data = yf.download(yahoo_ticker, period='2d', progress=False)
        if daily_data.empty or len(daily_data) < 2:
            prev_close, prev_high = None, None
        else:
            yesterday = daily_data.iloc[-2]
            prev_close = float(yesterday['Close'].iloc[0]) if hasattr(yesterday['Close'], 'iloc') else float(yesterday['Close'])
            prev_high = float(yesterday['High'].iloc[0]) if hasattr(yesterday['High'], 'iloc') else float(yesterday['High'])
        
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
        
        mask_morning = ((df_day.index.hour == 9) & (df_day.index.minute >= 20)) | ((df_day.index.hour == 10) & (df_day.index.minute <= 15))
        max_high = float(df_day.loc[mask_morning, 'High'].max()) if mask_morning.sum() > 0 else float(second_candle['High'])
        
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
        data_until_9_15 = data[data.index <= first_candle_time]
        
        ema_200_9_15 = None
        if data_until_9_15 is not None and len(data_until_9_15) >= 200:
            try:
                ema_200_9_15 = float(data_until_9_15['Close'].astype(float).ewm(span=200, adjust=False).mean().iloc[-1])
            except:
                pass
        
        ema_200_current = None
        if data is not None and len(data) >= 200:
            try:
                ema_200_current = float(data['Close'].astype(float).ewm(span=200, adjust=False).mean().iloc[-1])
            except:
                pass
        
        current_price = float(data['Close'].iloc[-1])
        open_9_15 = float(first_candle['Open'])
        
        ema_status_9_15 = 'ABOVE' if (ema_200_9_15 is not None and open_9_15 > ema_200_9_15) else 'BELOW'
        ema_status_current = 'ABOVE' if (ema_200_current is not None and current_price > ema_200_current) else 'BELOW'
        
        results[base_ticker] = {
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
            'current_price': current_price
        }
    
    return results

# ─── OPTIMIZED: Uses batch downloads ───
@st.cache_data(ttl=HARDCODED_SETTINGS['cache_ttl'])
def get_cached_processed_candle_data(tickers_tuple):
    if not tickers_tuple:
        return {}
    
    tickers_list = list(tickers_tuple)
    results = {}
    
    base_tickers = [t.replace('NSE:', '') for t in tickers_list]
    
    BATCH_SIZE = HARDCODED_SETTINGS.get('batch_size', 25)
    MAX_WORKERS = HARDCODED_SETTINGS.get('max_batch_workers', 4)
    
    batches = [base_tickers[i:i+BATCH_SIZE] for i in range(0, len(base_tickers), BATCH_SIZE)]
    
    progress_text = st.empty()
    progress_text.text(f"📦 Processing {len(base_tickers)} stocks in {len(batches)} batches...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_batch = {
            executor.submit(process_candle_data_batch, batch): idx 
            for idx, batch in enumerate(batches)
        }
        
        completed = 0
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                batch_results = future.result()
                results.update(batch_results)
                completed += 1
                progress_text.text(f"✅ Batch {completed}/{len(batches)} complete ({len(batch_results)} stocks)")
                if completed < len(batches):
                    time.sleep(0.3)
            except Exception as e:
                print(f"❌ Batch {batch_idx} failed: {e}")
                progress_text.text(f"⚠️ Batch {batch_idx} failed, continuing...")
    
    progress_text.text(f"✅ Completed! {len(results)} stocks processed")
    time.sleep(0.5)
    progress_text.empty()
    
    return results

# ─────────────────────────────────────────────────────────────────────────────
# CHECK CANDLE CONDITIONS
# ─────────────────────────────────────────────────────────────────────────────

def check_candle_conditions(df, tickers_list):
    with st.spinner('Fetching intraday data from Yahoo Finance (optimized batch mode)...'):
        candle_data = get_cached_processed_candle_data(tuple(tickers_list))
    
    for col in ['candle_9_15_high', 'candle_9_15_low', 'candle_9_20_open',
                'candle_9_20_high', 'candle_9_20_low', 'candle_9_20_close',
                'max_high_up_to_10_15', 'hit_low_9_20_to_35', 'breakout_9_30_to_9_45',
                'data_date', 'prev_close', 'prev_high', 'gap_percent_fallback',
                'open_gap_percent', 'passes_candle_check', 'candle_check_status',
                'yahoo_ticker', 'inside_9_15', 'ema_200_9_15', 'ema_200_current',
                '200 EMA', 'current_200_ema_status', 'current_price', 'open_9_15']:
        df[col] = None if col != 'inside_9_15' else False
    df['inside_9_15'] = False
    valid, invalid, failed = [], [], []
    for idx, row in df.iterrows():
        ticker = row['ticker']
        base_ticker = ticker.replace('NSE:', '')
        if base_ticker in candle_data:
            data = candle_data[base_ticker]
            for key in ['high_9_15', 'low_9_15', 'close_9_15', 'open_9_15',
                        'open_9_20', 'high_9_20', 'low_9_20', 'close_9_20',
                        'max_high_up_to_10_15', 'hit_low_9_20_to_35',
                        'breakout_9_30_to_9_45', 'prev_close', 'prev_high',
                        'gap_percent_fallback', 'yahoo_ticker', 'data_date',
                        'ema_200_9_15', 'ema_200_current', '200 EMA',
                        'current_200_ema_status', 'current_price']:
                df.at[idx, key] = data[key]
            df.at[idx, 'open_gap_percent'] = data['gap_percent_fallback']
            inside_9_15 = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] >= data['low_9_15'])
            df.at[idx, 'inside_9_15'] = inside_9_15
            cond = (data['close_9_20'] <= data['high_9_15'] and
                    (data['high_9_20'] <= data['high_9_15']) and
                    (data['low_9_20'] <= data['high_9_15']) and
                    data['close_9_20'] < data['open_9_20'] and
                    not data['hit_low_9_20_to_35'])
            if cond:
                df.at[idx, 'passes_candle_check'] = True
                df.at[idx, 'candle_check_status'] = 'PASS ✓'
                valid.append(ticker)
            else:
                reasons = []
                if data['close_9_20'] > data['high_9_15']:
                    reasons.append('9:20 close > 9:15 high')
                if not ((data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] <= data['high_9_15'])):
                    reasons.append('9:20 high/low not below 9:15 high')
                if data['close_9_20'] >= data['open_9_20']:
                    reasons.append('9:20 candle not bearish')
                if data['hit_low_9_20_to_35']:
                    reasons.append('Touched 9:15 low')
                df.at[idx, 'candle_check_status'] = 'FAIL ✗ (' + ', '.join(reasons) + ')'
                invalid.append(ticker)
        else:
            failed.append(ticker)
    return df, valid, invalid, failed

@st.cache_data(ttl=HARDCODED_SETTINGS['cache_ttl'])
def get_cached_margin_for_symbols(symbols_tuple):
    df = pd.DataFrame({'Symbol': list(symbols_tuple)})
    return calculate_max_quantity_column(df, 1, 1)

def load_stage1_data():
    with st.spinner("🔄 Loading market data..."):
        count, df = get_tradingview_stocks()
        if count == 0:
            return None
        df, rejected_gap = filter_by_gap(df)
        if df.empty:
            return {'df': pd.DataFrame(), 'valid': [], 'invalid': [], 'failed': [],
                    'rejected': rejected_gap.to_dict('records') if not rejected_gap.empty else [],
                    'total_count': count, 'filtered_count': 0, 'timestamp': datetime.now(IST)}
        df = df.sort_values('change', ascending=False)
        tickers_list = df['ticker'].tolist()
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list)
        df = df.sort_values('change', ascending=False)
        return {'df': df, 'valid': df[df['passes_candle_check'] == True]['ticker'].tolist(),
                'invalid': invalid, 'failed': failed,
                'rejected': rejected_gap.to_dict('records') if not rejected_gap.empty else [],
                'total_count': count, 'filtered_count': len(df), 'timestamp': datetime.now(IST)}

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZED AUTO-BUY FUNCTIONS (Parallel Execution)
# ─────────────────────────────────────────────────────────────────────────────

def auto_buy_status(row):
    """Check if stock is eligible for auto-buy using live price"""
    
    if row.get('current_200_ema_status') != 'ABOVE':
        return '❌ Below EMA'
    
    # Get live price
    symbol = row.get('Symbol', '')
    live_price = get_live_price(symbol)
    
    if live_price:
        cp = live_price
    else:
        cp = row.get('Price', 0)
        if isinstance(cp, str):
            try:
                cp = float(cp.replace('₹', '').replace(',', ''))
            except:
                return '❌ Invalid Price'
    
    # Get 9:15 High
    h = row.get('9:15 High', 0)
    if h == 0 or h is None:
        h = row.get('high_9_15', 0)
    if h == 0 or h is None:
        h = row.get('9:15 HIGH', 0)
    
    if isinstance(h, str):
        try:
            h = float(h.replace('₹', '').replace(',', ''))
        except:
            return '❌ Invalid 9:15 High'
    
    if h <= 0:
        return '❌ No 9:15 High'
    if cp <= 0:
        return '❌ No Price'
    
    min_price = h * 1.0015  # 0.15%
    max_price = h * 1.005   # 0.50%
    
    if cp <= min_price:
        return f'❌ Need > {min_price:.2f}'
    elif cp >= max_price:
        return '❌ Above 0.50% (too late)'
    else:
        return '✅ ELIGIBLE'

def check_auto_buy_conditions(row):
    """Check auto-buy conditions using live price"""
    
    # Get live price
    symbol = row.get('Symbol', '')
    live_price = get_live_price(symbol)
    
    if live_price:
        current_price = live_price
    else:
        current_price = row.get('Price', 0)
        if isinstance(current_price, str):
            try:
                current_price = float(current_price.replace('₹', '').replace(',', ''))
            except:
                current_price = 0
    
    # Get 9:15 High
    high_9_15 = row.get('9:15 High', 0)
    if high_9_15 == 0 or high_9_15 is None:
        high_9_15 = row.get('high_9_15', 0)
    if high_9_15 == 0 or high_9_15 is None:
        high_9_15 = row.get('9:15 HIGH', 0)
    
    if isinstance(high_9_15, str):
        try:
            high_9_15 = float(high_9_15.replace('₹', '').replace(',', ''))
        except:
            return False, "Invalid 9:15 High format"
    
    if high_9_15 is None or high_9_15 <= 0:
        return False, "No 9:15 High data"
    if current_price is None or current_price <= 0:
        return False, "No current price data"
    
    min_price = high_9_15 * 1.0015
    max_price = high_9_15 * 1.005
    
    if current_price <= min_price:
        return False, f"Price {current_price:.2f} <= 9:15 High + 0.15% ({min_price:.2f})"
    elif current_price >= max_price:
        return False, f"Price {current_price:.2f} >= 9:15 High + 0.50% ({max_price:.2f}) - Too late"
    
    return True, "All conditions met"

def place_single_order(symbol, max_qty, amo_mode):
    """Place a single order - used for parallel execution"""
    try:
        result = place_dhan_order(
            symbol,
            quantity=int(max_qty),
            product_type="INTRADAY",
            after_market_order=amo_mode,
            amo_time="OPEN"
        )
        return {
            'symbol': symbol,
            'quantity': int(max_qty),
            'success': result.get('success', False),
            'order_id': result.get('order_id', 'N/A'),
            'error': result.get('error', None)
        }
    except Exception as e:
        return {
            'symbol': symbol,
            'quantity': int(max_qty),
            'success': False,
            'order_id': None,
            'error': str(e)
        }

def execute_auto_buy_parallel(display_df):
    """
    OPTIMIZED: Execute auto-buy orders in parallel
    Uses ThreadPoolExecutor for simultaneous order placement
    """
    today = datetime.now().date()
    
    if st.session_state['auto_buy_date'] != today:
        st.session_state['auto_buy_bought_today'] = 0
        st.session_state['auto_buy_stocks_bought'] = []
        st.session_state['auto_buy_date'] = today
    
    if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
        return [], [], f"Daily limit of {st.session_state['auto_buy_max_stocks']} stocks reached"
    
    available = display_df[~display_df['Symbol'].isin(st.session_state['auto_buy_stocks_bought'])].copy()
    if available.empty:
        return [], [], "No new stocks available"
    
    orders_to_place = []
    amo_mode = st.session_state.get('amo_mode', False)
    
    for _, row in available.iterrows():
        if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
            break
        
        symbol = row['Symbol']
        max_qty = row.get('MaxQty', 0)
        
        meets, reason = check_auto_buy_conditions(row)
        if not meets:
            continue
        
        if max_qty <= 0:
            continue
        
        orders_to_place.append({
            'symbol': symbol,
            'max_qty': max_qty,
            'amo_mode': amo_mode
        })
    
    if not orders_to_place:
        return [], [], "No eligible stocks found"
    
    placed = []
    failed = []
    bought_symbols = []
    
    with ThreadPoolExecutor(max_workers=min(len(orders_to_place), 5)) as executor:
        future_to_order = {
            executor.submit(place_single_order, 
                order['symbol'], 
                order['max_qty'], 
                order['amo_mode']
            ): order for order in orders_to_place
        }
        
        for future in as_completed(future_to_order):
            order = future_to_order[future]
            try:
                result = future.result()
                if result['success']:
                    placed.append({
                        'symbol': result['symbol'],
                        'quantity': result['quantity'],
                        'order_id': result['order_id']
                    })
                    bought_symbols.append(result['symbol'])
                    st.session_state['auto_buy_bought_today'] += 1
                else:
                    failed.append({
                        'symbol': result['symbol'],
                        'quantity': result['quantity'],
                        'reason': result['error'] or 'Unknown error'
                    })
            except Exception as e:
                failed.append({
                    'symbol': order['symbol'],
                    'quantity': order['max_qty'],
                    'reason': str(e)
                })
    
    st.session_state['auto_buy_stocks_bought'].extend(bought_symbols)
    
    return placed, failed, None

# ─────────────────────────────────────────────────────────────────────────────
# BREAKOUT HELPER
# ─────────────────────────────────────────────────────────────────────────────
def check_real_time_breakout(row):
    high_9_15 = row.get('high_9_15', 0)
    current_price = row.get('current_price', 0)
    if high_9_15 is None or pd.isna(high_9_15) or high_9_15 <= 0:
        return False
    if current_price is None or pd.isna(current_price) or current_price <= 0:
        return False
    return current_price > high_9_15

def get_breakout_time_status():
    t = datetime.now(IST)
    t9_30 = t.replace(hour=9, minute=30, second=0)
    t9_45 = t.replace(hour=9, minute=45, second=0)
    return 'before_9_30' if t < t9_30 else ('live_checking' if t9_30 <= t <= t9_45 else 'locked')

# ─────────────────────────────────────────────────────────────────────────────
# RENDER HEADER
# ─────────────────────────────────────────────────────────────────────────────
def render_header():
    t = datetime.now(IST)
    ws_status = "🟢" if st.session_state.get('ws_connected', False) else "🔴"
    st.markdown(f"""
    <div class="tradeos-header">
        <div class="header-left"><span class="logo">📊 Gap Screener</span><span class="version">v1.0</span></div>
        <div class="header-center">
            <span class="ticker-item">NIFTY 50 24,856.40 <span class="ticker-green">▲ +0.87%</span></span>
            <span class="ticker-item">SENSEX 81,234.56 <span class="ticker-green">▲ +0.92%</span></span>
            <span class="ticker-item">BANK NIFTY 52,345.67 <span class="ticker-red">▼ -0.23%</span></span>
            <span class="ticker-item">WS: {ws_status}</span>
        </div>
        <div class="header-right">
            <div class="status-indicator"><span class="status-dot"></span><span>Live</span></div>
            <span class="clock">{t.strftime('%H:%M:%S')} IST</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Filter Settings")
    st.markdown("---")
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
    if 'stage1_data' in st.session_state and st.session_state['stage1_data'] is not None:
        df = st.session_state['stage1_data']['df']
        if 'open_9_15' in df.columns and 'ema_200_9_15' in df.columns:
            df['_ema_gap_pct'] = (df['open_9_15'] - df['ema_200_9_15']) / df['ema_200_9_15']
            count = len(df[df['_ema_gap_pct'] <= (ema_gap_threshold / 100)])
            st.caption(f"📊 Stocks passing: **{count}**")
    st.markdown("---")
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
    st.markdown("**🔍 Active Filters**")
    st.caption(f"📈 EMA Distance: ≤ {ema_gap_threshold}%")
    st.caption(f"📊 Above Prev High: {'✅ ON' if st.session_state.get('filter_above_prev_high', False) else '❌ OFF'}")

# ─────────────────────────────────────────────────────────────────────────────
# APPLY CSS & MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(WHITE_THEME_CSS, unsafe_allow_html=True)
render_header()

# ─── Auto-refresh check ───
if 'prev_ema_slider' not in st.session_state:
    st.session_state['prev_ema_slider'] = st.session_state.get('ema_gap_threshold_slider', 3.0)
cur_slider = st.session_state.get('ema_gap_threshold_slider', 3.0)
cur_checkbox = st.session_state.get('filter_above_prev_high', False)
if 'prev_checkbox' not in st.session_state:
    st.session_state['prev_checkbox'] = cur_checkbox
if (cur_slider != st.session_state['prev_ema_slider']) or (cur_checkbox != st.session_state['prev_checkbox']):
    st.session_state['prev_ema_slider'] = cur_slider
    st.session_state['prev_checkbox'] = cur_checkbox

if st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()

# ─── Initialize WebSocket after data loads ───
if st.session_state.get('stage1_data') is not None:
    if not st.session_state.get('ws_initialized', False):
        init_websocket()

# ─── Page Header ───
col1, col2, col3, col4 = st.columns([3, 1.2, 0.8, 1])
with col1:
    st.markdown('<div class="page-title">🔍 Gap Screener <span>· Professional Trading Scanner</span></div>', unsafe_allow_html=True)
with col2:
    st.session_state['user_capital'] = st.number_input(
        "💰", min_value=1000, max_value=10000000,
        value=int(st.session_state['user_capital']), step=1000,
        key="capital_input", label_visibility="collapsed"
    )
with col3:
    st.session_state['num_parts'] = st.number_input(
        "📊", min_value=1, max_value=10,
        value=int(st.session_state.get('num_parts', 4)), step=1,
        key="parts_input", label_visibility="collapsed"
    )
with col4:
    def set_refresh_flag():
        st.session_state['force_table_refresh'] = True
        st.session_state['stage1_data'] = None
        st.session_state['stage1_loaded'] = False
        st.session_state['ws_initialized'] = False
    
    st.button("🔄 Refresh", key="refresh_btn", use_container_width=True,
              on_click=set_refresh_flag)

# ─── Handle refresh outside callback ───
if st.session_state.get('force_table_refresh', False):
    st.session_state['force_table_refresh'] = False
    st.rerun()

# ─── Display Data ───
if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()
    last_refresh = st.session_state.get('stage1_last_refresh', datetime.now(IST))
    pass_count = len(data['valid'])
    
    # ─── Update Price column with live prices ───
    def get_live_price_display(symbol):
        live_price = get_live_price(symbol)
        if live_price:
            return f"₹{live_price:.2f}"
        return None
    
    df['Price'] = df['name'].apply(
        lambda x: get_live_price_display(x) if get_live_price_display(x) else df[df['name'] == x]['close'].iloc[0] if not df[df['name'] == x].empty else "N/A"
    )
    
    # Format price properly
    if 'close' in df.columns:
        # If live price not available, use close price
        for idx, row in df.iterrows():
            symbol = row['name']
            live_price = get_live_price(symbol)
            if live_price:
                df.at[idx, 'Price'] = f"₹{live_price:.2f}"
            else:
                df.at[idx, 'Price'] = format_price(row['close'])

    # ─── Screener Card Header ───
    ws_status = "🟢" if st.session_state.get('ws_connected', False) else "🔴"
    ws_count = st.session_state.get('ws_subscribed_count', 0)
    
    st.markdown(f"""
    <div class="screener-card">
        <div class="screener-header">
            <div class="screener-stats">
                <span class="stat-item">📊 Total: <strong class="stat-count">{data['total_count']}</strong></span>
                <span class="stat-item">✅ After Gap: <strong class="stat-count">{data['filtered_count']}</strong></span>
                <span class="stat-item">🎯 Pass Candle: <strong class="stat-count">{pass_count}</strong></span>
                <span class="stat-item">🕐 Last: <strong>{last_refresh.strftime('%H:%M:%S')}</strong></span>
                <span class="stat-item">⚡ WS: <strong>{ws_status} {ws_count}</strong></span>
                <span class="stat-item">⚡ Optimized: <strong class="stat-count">Batch Mode + Parallel Auto-Buy</strong></span>
            </div>
            <div class="filter-badges">
                <span class="filter-badge active">💰 ₹{HARDCODED_SETTINGS['price_min']}-{HARDCODED_SETTINGS['price_max']}</span>
                <span class="filter-badge active">📊 ≥{HARDCODED_SETTINGS['market_cap_min']/1e9:.0f}B</span>
                <span class="filter-badge active">📈 Gap ≤ 2%</span>
                <span class="filter-badge active">📈 EMA ≤ {st.session_state.get('ema_gap_threshold_slider', 3.0)}%</span>
                {f'<span class="filter-badge active">📊 Above Prev High ✅</span>' if st.session_state.get('filter_above_prev_high', False) else ''}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    is_after_9_25 = datetime.now(IST) >= datetime.now(IST).replace(hour=9, minute=25, second=0)
    breakout_status = get_breakout_time_status()

    # ─── Filter Row ───
    st.markdown('<div class="filter-row">', unsafe_allow_html=True)
    fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([1.8, 1.8, 1.2, 1.2, 1.8, 1.8])
    with fc1:
        if is_after_9_25:
            st.checkbox("📊 Inside 9:15", key="show_inside_only")
        else:
            st.info("⏳ 9:20 after 9:25 AM")
    with fc2:
        if breakout_status == 'before_9_30':
            st.info("⏳ Breakout after 9:30 AM")
        else:
            st.checkbox("⚡ Breakout 9:30-9:45", key="show_breakout_only")
    with fc3:
        st.checkbox("📏 Small Candle (≤ 1.5%)", key="show_small_candle")
    with fc4:
        st.checkbox("🌙 AMO", key="amo_mode")
    with fc5:
        st.checkbox("🤖 Auto-Buy", key="auto_buy_enabled")
    with fc6:
        if st.session_state.get('auto_buy_enabled', False):
            rem = st.session_state['auto_buy_max_stocks'] - st.session_state['auto_buy_bought_today']
            eligible = 0
            if 'display_df' in locals() and not display_df.empty and 'Auto-Buy Status' in display_df.columns:
                eligible = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
            st.markdown(f'''
                <div style="display:flex;align-items:center;gap:8px;font-size:0.7rem;padding:2px 0;">
                    <span style="color:#28a745;font-weight:600;">🟢 ACTIVE</span>
                    <span style="color:#888;">|</span>
                    <span style="color:#333;">🎯 {eligible}</span>
                    <span style="color:#888;">|</span>
                    <span style="color:#333;">📊 {rem}</span>
                    <span style="color:#888;">|</span>
                    <span style="color:#0066cc;">⚡ Parallel</span>
                </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#888;font-size:0.7rem;">⚪ Auto-Buy OFF</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ─── Apply Filters ───
    display_df = df.copy()
    ema_gap_limit = st.session_state.get('ema_gap_threshold_slider', 3.0) / 100
    if 'open_9_15' in display_df.columns and 'ema_200_9_15' in display_df.columns:
        display_df['_ema_gap_pct'] = ((display_df['open_9_15'] - display_df['ema_200_9_15']) / display_df['ema_200_9_15'])
        mask = display_df['_ema_gap_pct'].notna() & (display_df['_ema_gap_pct'] <= ema_gap_limit) & (display_df['open_9_15'] > display_df['ema_200_9_15'])
        display_df = display_df[mask].drop(columns=['_ema_gap_pct'])

    if st.session_state.get('filter_above_prev_high', False):
        mask = display_df['high_9_15'].notna() & display_df['prev_high'].notna() & (display_df['prev_high'] > 0) & (display_df['high_9_15'] >= display_df['prev_high'])
        display_df = display_df[mask]

    if st.session_state.get('show_inside_only', False) and is_after_9_25:
        today = datetime.now().date()
        if st.session_state.get('inside_pass_date') == today and st.session_state.get('inside_pass_symbols'):
            display_df = display_df[display_df['ticker'].isin(st.session_state['inside_pass_symbols'])]
        else:
            if 'inside_9_15' in display_df.columns:
                mask = display_df['inside_9_15'] == True
                st.session_state['inside_pass_symbols'] = display_df.loc[mask, 'ticker'].tolist()
                st.session_state['inside_pass_date'] = today
                display_df = display_df[mask]

    if st.session_state.get('show_breakout_only', False):
        if breakout_status == 'live_checking':
            display_df['_real'] = display_df.apply(check_real_time_breakout, axis=1)
            display_df = display_df[display_df['_real']]
        elif breakout_status == 'locked':
            display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]

    if st.session_state.get('show_small_candle', False):
        if 'high_9_15' in display_df.columns and 'low_9_15' in display_df.columns:
            display_df['_candle_range'] = ((display_df['high_9_15'] - display_df['low_9_15']) / display_df['low_9_15']) * 100
            display_df = display_df[display_df['_candle_range'].notna() & (display_df['_candle_range'] <= 1.5)].drop(columns=['_candle_range'])

    if display_df.empty:
        st.warning("⚠️ No stocks match the selected filters.")
    else:
        # ─── Prepare display dataframe ───
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['Symbol'] = display_df['name']
        
        # ─── Update Price with live data ───
        def get_live_price_display(symbol):
            live_price = get_live_price(symbol)
            if live_price:
                return f"₹{live_price:.2f}"
            return None
        
        display_df['Price'] = display_df['name'].apply(
            lambda x: get_live_price_display(x) if get_live_price_display(x) else format_price(display_df[display_df['name'] == x]['close'].iloc[0] if not display_df[display_df['name'] == x].empty else 0)
        )

        # ─── MaxQty Calculation ───
        with st.spinner("Calculating max quantity (DhanHQ margin)..."):
            display_df['MaxQty'] = calculate_max_quantity_column(
                display_df,
                total_capital=st.session_state['user_capital'],
                num_parts=st.session_state.get('num_parts', 4)
            )

        # ─── Columns & Formatting ───
        cols = ['name', 'close', 'change', 'gap', 'volume', 'relative_volume',
                'inside_9_15', 'breakout_9_30_to_9_45', '200 EMA', 'MaxQty', 'sector',
                'high_9_15', 'current_price', 'close_9_15', 'ema_200_9_15',
                'ema_200_current', 'current_200_ema_status', 'prev_high']
        display_df = display_df[[c for c in cols if c in display_df.columns]].copy()
        display_df.rename(columns={
            'name': 'Symbol', 'close': 'Price_old', 'change': 'Chg%',
            'gap': 'Gap%', 'volume': 'Volume', 'relative_volume': 'Rel Vol',
            'inside_9_15': 'Inside 9:15', 'breakout_9_30_to_9_45': 'Breakout',
            'MaxQty': 'MaxQty', 'sector': 'Sector', 'high_9_15': 'high_9_15',
            'current_price': 'current_price', 'prev_high': 'Prev Day High'
        }, inplace=True)
        
        # Use the live Price column we already set
        display_df['9:15 High'] = display_df['high_9_15'].apply(lambda x: format_price(x) if pd.notna(x) else "N/A")
        display_df['Prev Day High'] = display_df['Prev Day High'].apply(lambda x: format_price(x) if pd.notna(x) else "N/A")
        display_df['Chg%'] = display_df['Chg%'].apply(format_pct)
        display_df['Gap%'] = display_df['Gap%'].apply(format_pct)
        display_df['Volume'] = display_df['Volume'].apply(format_volume)
        display_df['Rel Vol'] = display_df['Rel Vol'].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "0x")
        display_df['Inside 9:15'] = display_df['Inside 9:15'].apply(lambda x: "✅" if x else "❌")

        def get_breakout_display(row):
            bs = get_breakout_time_status()
            if bs == 'before_9_30':
                return "⏳ Waiting"
            if bs == 'live_checking':
                h = row.get('high_9_15', 0)
                cp = row.get('current_price', 0)
                return "✅ BREAKOUT" if (h > 0 and cp > 0 and cp > h) else "❌ Below 9:15 High"
            return "✅" if row.get('Breakout', False) else "❌"
        display_df['Breakout'] = display_df.apply(get_breakout_display, axis=1)

        # ─── Uses OPEN instead of CLOSE for 200 EMA check ───
        def format_ema(row):
            ema = row.get('ema_200_9_15')
            if ema is None or pd.isna(ema) or ema <= 0:
                return "⚪ N/A"
            open_9_15 = row.get('open_9_15', 0)
            if open_9_15 > ema:
                return f"🟢 ₹{ema:,.2f}"
            else:
                return f"🔴 ₹{ema:,.2f}"
        display_df['200 EMA'] = display_df.apply(format_ema, axis=1)

        # ─── Auto-Buy Status ───
        display_df['Auto-Buy Status'] = display_df.apply(auto_buy_status, axis=1)

        display_df = display_df.reset_index(drop=True)
        display_df.index += 1
        final_cols = ['Symbol', 'Price', 'Chg%', 'Gap%', 'Volume', 'Rel Vol',
                      'Inside 9:15', 'Breakout', '200 EMA', '9:15 High',
                      'Prev Day High', 'Auto-Buy Status', 'MaxQty', 'Sector']
        display_df = display_df[[c for c in final_cols if c in display_df.columns]]

        # ─── Auto-Buy Execution (Parallel) ───
        if st.session_state.get('auto_buy_enabled', False):
            eligible = len(display_df[display_df['Auto-Buy Status'] == '✅ ELIGIBLE'])
            
            if eligible > 0 and st.session_state['auto_buy_bought_today'] < st.session_state['auto_buy_max_stocks']:
                with st.spinner(f"🤖 Auto-buy: {eligible} stocks eligible, placing orders in parallel..."):
                    placed, failed, error = execute_auto_buy_parallel(display_df)
                    
                    if error:
                        st.warning(f"⚠️ {error}")
                    else:
                        if placed:
                            st.success(f"✅ {len(placed)} orders placed successfully!")
                            st.dataframe(pd.DataFrame(placed), use_container_width=True)
                            st.session_state['auto_buy_orders_placed'].extend(placed)
                        if failed:
                            st.warning(f"⚠️ {len(failed)} orders failed")
                            st.dataframe(pd.DataFrame(failed), use_container_width=True)
                            st.session_state['auto_buy_orders_failed'].extend(failed)
                        if st.session_state['auto_buy_bought_today'] >= st.session_state['auto_buy_max_stocks']:
                            st.success(f"🎯 Daily limit of {st.session_state['auto_buy_max_stocks']} stocks reached!")

        # ─── Table ───
        tbl, btn = st.columns([8.5, 1.5])
        with tbl:
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

        # ─── Manual Buy Buttons ───
        with btn:
            for idx, (_, row) in enumerate(display_df.iterrows()):
                sym = row['Symbol']
                mq = row['MaxQty']
                btn_label = f"{sym}" + (" 🌙" if st.session_state.get('amo_mode', False) else "")
                if st.button(
                    btn_label,
                    key=f"buy_{sym}_{idx}",
                    disabled=(mq is None or pd.isna(mq) or mq <= 0 or st.session_state.get('auto_buy_enabled', False)),
                    use_container_width=True
                ):
                    with st.spinner(f"Placing order for {sym}..."):
                        try:
                            if mq is None or pd.isna(mq) or mq <= 0:
                                st.error(f"❌ Invalid quantity for {sym}")
                            else:
                                result = place_dhan_order(
                                    sym,
                                    quantity=int(mq),
                                    product_type="INTRADAY",
                                    after_market_order=st.session_state.get('amo_mode', False),
                                    amo_time="OPEN"
                                )
                                display_order_result(sym, result)
                        except Exception as e:
                            st.error(f"❌ Order failed: {str(e)}")
            if st.session_state.get('auto_buy_enabled', False):
                st.caption("🔒 Manual buttons disabled when Auto-Buy is ON")

        st.download_button(
            "📥 Download CSV",
            display_df.to_csv(index=False),
            f'screener_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            'text/csv',
            use_container_width=True
        )

    # ─── Footer ───
    ws_status = "🟢" if st.session_state.get('ws_connected', False) else "🔴"
    st.markdown(f"""
    <div class="footer-bar">
        <span>🔄 Stage 1 refreshes every <span class="live">1 minute</span></span>
        <span>📊 <span class="highlight">{len(display_df) if 'display_df' in locals() else 0}</span> stocks displayed · <span class="highlight">{pass_count}</span> pass candle check</span>
        <span>🕐 Last refresh: <span class="highlight">{last_refresh.strftime('%H:%M:%S')}</span></span>
        <span>🤖 Auto-Buy: {'🟢 ON' if st.session_state.get('auto_buy_enabled', False) else '⚪ OFF'} · {st.session_state.get('auto_buy_bought_today', 0)}/{st.session_state.get('auto_buy_max_stocks', 5)} today</span>
        <span>⚡ WS: {ws_status}</span>
        <span>⚡ Optimized: Batch Mode · Parallel Auto-Buy · Instant EMA Check</span>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔍 Debug: Max Qty Calculation"):
        st.json(get_qty_calc_debug())

st.markdown("""
<div style="text-align:center; padding:1.5rem; color:#888; font-size:0.65rem; border-top:1px solid #e9ecef; margin-top:1rem;">
    📊 Gap Screener · Professional Trading Scanner<br>Data: TradingView · Yahoo Finance · DhanHQ · Optimized Batch Mode · Parallel Auto-Buy · Instant EMA Check · Live WebSocket Prices
</div>
""", unsafe_allow_html=True)
