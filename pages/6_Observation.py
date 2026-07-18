# ═══════════════════════════════════════════════════════════════════════════════
# PAGES / 6_OBSERVATION.PY – INDIA STOCK SCREENER (OPTIMIZED)
# Stage 1: Refreshes every 1 minute (data updates)
# Stage 2: Instant filtering on updated data
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
# PAGE CONFIG & STYLES
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TradingView Screener India",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header { font-size: 2.5rem; color: #00ff88; text-align: center; padding: 1rem 0; background: linear-gradient(90deg, #1a1a2e, #16213e, #0f3460); border-radius: 10px; margin-bottom: 2rem; }
    .stage-header { font-size: 1.3rem; color: #00ff88; padding: 0.5rem; background: rgba(0, 255, 136, 0.1); border-left: 4px solid #00ff88; margin: 1rem 0; }
    .success-text { color: #00ff88; font-weight: bold; }
    .fail-text { color: #ff4444; font-weight: bold; }
    .warning-text { color: #ffaa00; font-weight: bold; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────

if 'user_capital' not in st.session_state:
    st.session_state['user_capital'] = 100000.0

if 'amo_mode' not in st.session_state:
    st.session_state['amo_mode'] = False

if 'stage1_data' not in st.session_state:
    st.session_state['stage1_data'] = None

if 'stage1_timestamp' not in st.session_state:
    st.session_state['stage1_timestamp'] = None

if 'stage1_loaded' not in st.session_state:
    st.session_state['stage1_loaded'] = False

# Stage 2 filter states (preserved across refreshes)
if 'show_inside_only' not in st.session_state:
    st.session_state['show_inside_only'] = False

if 'show_breakout_only' not in st.session_state:
    st.session_state['show_breakout_only'] = False

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED STAGE 1 FILTERS (Removed from UI)
# ─────────────────────────────────────────────────────────────────────────────

HARDCODED_SETTINGS = {
    'price_min': 200,
    'price_max': 2000,
    'market_cap_min': 41_000_000_000,  # 41B (Large Cap)
    'stocks_limit': 50  # Number of top stocks to display
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_gap_filtered_stocks(df):
    """Filter stocks with gap ±2%"""
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
    """Fetch stocks from TradingView with hardcoded filters"""
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

def get_intraday_data_for_symbol(yahoo_ticker, period="2d", interval="5m"):
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

def get_candle_data_bulk(tickers_list, max_workers=20):
    results = {}
    symbol_formats = ['.NS', '-NS', '']

    def fetch_one(ticker):
        base_ticker = ticker.replace('NSE:', '')
        for suffix in symbol_formats:
            yahoo_ticker = base_ticker + suffix
            data = get_intraday_data_for_symbol(yahoo_ticker)
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
                    'data_date': today.strftime("%Y-%m-%d")
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
                     'candle_check_status', 'yahoo_ticker', 'inside_9_15']:
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
                        'gap_percent', 'yahoo_ticker', 'data_date']:
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
                if not cond1: reasons.append('9:20 close > 9:15 high')
                if not cond2: reasons.append('9:20 high/low not below 9:15 high')
                if not cond4: reasons.append('9:20 candle not bearish')
                if not cond5: reasons.append('Touched 9:15 low')
                df.at[idx, 'candle_check_status'] = 'FAIL ✗ (' + ', '.join(reasons) + ')'
                invalid_stocks.append(ticker)

        else:
            failed_to_fetch.append(ticker)

    return df, valid_stocks, invalid_stocks, failed_to_fetch

def color_change(val):
    try:
        if isinstance(val, (int, float)):
            color = '#00ff88' if val > 0 else '#ff4444'
            return f'color: {color}'
        return ''
    except:
        return ''

def load_stage1_data():
    """Load all Stage 1 data (called every 1 minute)"""
    with st.spinner("🔄 Refreshing Stage 1 data..."):
        # Step 1: Fetch from TradingView
        count, df = get_tradingview_stocks()
        if count == 0:
            return None
        
        # Step 2: Apply gap filter
        filtered_tickers, rejected = get_gap_filtered_stocks(df)
        df = df[df['ticker'].isin(filtered_tickers)].copy()
        df = df.sort_values('change', ascending=False)
        df = df.head(HARDCODED_SETTINGS['stocks_limit'])
        
        # Step 3: Candle analysis
        tickers_list = df['ticker'].tolist()
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list)
        
        # Store results
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
# AUTO-REFRESH LOGIC (Stage 1 only, every 1 minute)
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone('Asia/Kolkata')

def should_refresh_stage1():
    """Check if Stage 1 needs refresh (every 1 minute)"""
    if 'stage1_last_refresh' not in st.session_state:
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        return True
    
    time_diff = datetime.now(IST) - st.session_state['stage1_last_refresh']
    if time_diff.total_seconds() >= 60:  # 1 minute
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR (Only Stage 2 & Dhan settings)
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.markdown("## 💰 Margin Settings")
total_capital = st.sidebar.number_input(
    "Total Capital (₹)", 
    min_value=1000, 
    value=100000, 
    step=1000,
    key="user_capital"
)

st.sidebar.markdown("---")
amo_test_mode = st.sidebar.checkbox(
    "🌙 After Market Order",
    value=False,
    key="amo_mode",
    help="AMO mode: order queues for next market open instead of rejecting."
)

st.sidebar.markdown("---")
st.sidebar.caption(f"⚡ Stage 1 refresh: Every 1 minute")
st.sidebar.caption(f"📊 Filters: Price ₹{HARDCODED_SETTINGS['price_min']}-{HARDCODED_SETTINGS['price_max']}, Mkt Cap ≥{HARDCODED_SETTINGS['market_cap_min']/1e9:.0f}B")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="main-header">📈 India Stock Screener (Auto-Refresh Every 1 min)</div>', unsafe_allow_html=True)

current_time = datetime.now(IST)
is_after_9_30 = current_time >= current_time.replace(hour=9, minute=30, second=0)
is_after_9_25 = current_time >= current_time.replace(hour=9, minute=25, second=0)

col1, col2, col3 = st.columns(3)
with col1:
    status = "🟢 Open" if is_after_9_30 else "🔴 Closed"
    st.metric("🇮🇳 Market", status, delta="NSE India")
with col2:
    st.metric("🕐 Time", current_time.strftime("%H:%M IST"), delta="")
with col3:
    st.metric("📅 Date", current_time.strftime("%d %b %Y"), delta="")

if not is_after_9_30:
    st.warning("⚠️ Market is closed. Data shown is from last trading day.")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: LOAD DATA (Runs every 1 minute with auto-refresh)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="stage-header">📊 STAGE 1: Loading & Filtering (Gap ±2%)</div>', unsafe_allow_html=True)

# Check if we need to load Stage 1 data (auto-refresh every 1 minute)
if should_refresh_stage1() or st.session_state['stage1_data'] is None:
    stage1_data = load_stage1_data()
    if stage1_data:
        st.session_state['stage1_data'] = stage1_data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.session_state['stage1_loaded'] = True
        st.rerun()  # Rerun to update display with new data

# Display Stage 1 status
if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Total Stocks", data['total_count'])
    with col2:
        st.metric("✅ After Gap Filter", data['filtered_count'])
    with col3:
        last_refresh = st.session_state.get('stage1_last_refresh', datetime.now(IST))
        st.metric("🕐 Last Refresh", last_refresh.strftime("%H:%M:%S"))
    
    if data['rejected']:
        with st.expander(f"📊 Show Rejected ({len(data['rejected'])})"):
            for s in data['rejected'][:20]:
                st.write(f"- {s['ticker']}: {s['reason']}")
    
    st.info(f"✅ {data['filtered_count']} stocks match. Stage 2 (candle analysis) running automatically...")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: FILTERING & DISPLAY (Instant, uses cached data)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown('<div class="stage-header">📊 STAGE 2: Candle Analysis & Filters</div>', unsafe_allow_html=True)

if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1: 
        st.metric("Analyzed", len(df))
    with col2: 
        st.metric("Pass All 4 Conditions", len(data['valid']), delta="✓")
    with col3: 
        st.metric("Fail / No Data", len(data['invalid'])+len(data['failed']), delta="✗")

    # ── FILTER CHECKBOXES (Stage 2 only - PRESERVED in session state) ──
    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:
        if is_after_9_25:
            show_inside_only = st.checkbox(
                "📊 Show only stocks where 9:20 candle is INSIDE 9:15 range",
                value=st.session_state['show_inside_only'],
                key="inside_checkbox",
                help="Filters to show only stocks where 9:20 high ≤ 9:15 high AND 9:20 low ≥ 9:15 low"
            )
            # Save to session state (preserved across refreshes)
            st.session_state['show_inside_only'] = show_inside_only
        else:
            st.info("⏳ 9:20 candle not yet complete – filter available after 9:25 AM.")
            show_inside_only = False

    with filter_col2:
        if is_after_9_30:
            show_breakout_only = st.checkbox(
                "⚡ Show ONLY Breakout Stocks (9:30-9:45)",
                value=st.session_state['show_breakout_only'],
                key="breakout_checkbox",
                help="Filters to show only stocks that broke above 9:15 High between 9:30-9:45"
            )
            # Save to session state (preserved across refreshes)
            st.session_state['show_breakout_only'] = show_breakout_only
        else:
            st.info("⏳ Breakout filter available after 9:30 AM.")
            show_breakout_only = False

    # ── APPLY STAGE 2 FILTERS (INSTANT - no reload) ──
    display_df = df.copy()
    if show_breakout_only:
        display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]
    if show_inside_only and is_after_9_25:
        display_df = display_df[display_df['inside_9_15'] == True]

    if display_df.empty:
        st.warning("⚠️ No stocks match the selected filters.")
    else:
        st.subheader(f"📋 Final Results ({len(display_df)} stocks)")

        # 1. Compute derived columns
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)

        # 2. Select columns
        display_cols = [
            'name', 'close', 'change', 'volume', 'relative_volume',
            'market_cap_b', 'sector',
            'hit_low_9_20_to_35', 'breakout_9_30_to_9_45',
            'inside_9_15', 'candle_check_status'
        ]
        available = [c for c in display_cols if c in display_df.columns]
        display_df = display_df[available].copy()

        # 3. Rename columns
        rename = {
            'name': 'Stock',
            'close': 'Price (₹)',
            'change': 'Change %',
            'volume': 'Volume',
            'relative_volume': 'Rel Vol',
            'market_cap_b': 'Mkt Cap (B₹)',
            'sector': 'Sector',
            'hit_low_9_20_to_35': 'Hit Low (9:20-9:35)?',
            'breakout_9_30_to_9_45': 'Breakout (9:30-9:45)?',
            'inside_9_15': '9:20 inside 9:15?',
            'candle_check_status': 'Candle Status'
        }
        rename = {k: v for k, v in rename.items() if k in display_df.columns}
        display_df = display_df.rename(columns=rename)

        # 4. Round numeric columns
        for c in display_df.columns:
            if pd.api.types.is_numeric_dtype(display_df[c]):
                display_df[c] = display_df[c].round(2)

        # ── Add DhanHQ margin columns & MaxQty ──
        display_df['Price'] = display_df['Price (₹)']
        display_df['Symbol'] = display_df['Stock']
        
        # Calculate MaxQty using DhanHQ
        with st.spinner("Calculating max quantity (DhanHQ margin)..."):
            display_df['MaxQty'] = calculate_max_quantity_column(
                display_df,
                total_capital=st.session_state['user_capital'],
                num_parts=4
            )

        # ── Display styled table ──
        if 'Change %' in display_df.columns:
            styled_df = display_df.style.applymap(color_change, subset=['Change %'])
        else:
            styled_df = display_df.style

        st.dataframe(styled_df, use_container_width=True, height=500)

        # ── BUY BUTTONS ──
        st.markdown("---")
        st.subheader("📊 Buy Orders — Dhan (Manual)")
        
        # Buttons in columns
        num_cols = min(4, len(display_df))
        cols = st.columns(num_cols)
        for idx, (_, row) in enumerate(display_df.iterrows()):
            col_idx = idx % num_cols
            with cols[col_idx]:
                symbol = row['Stock']
                max_qty = row.get('MaxQty', 0)
                btn_label = f"{symbol} {int(max_qty)}" + (" 🌙" if amo_test_mode else "")
                
                if st.button(
                    btn_label,
                    key=f"buy_dhan_obs_{symbol}_{idx}",
                    disabled=(max_qty <= 0),
                    use_container_width=True
                ):
                    with st.spinner(f"Placing order for {symbol} via Dhan..."):
                        result = place_dhan_order(
                            symbol,
                            quantity=int(max_qty),
                            product_type="INTRADAY",
                            after_market_order=amo_test_mode,
                            amo_time="OPEN"
                        )
                        display_order_result(symbol, result)

        # ── Debug expander ──
        with st.expander("🔍 Debug: Max Qty calculation"):
            debug_info = get_qty_calc_debug()
            st.write("**Token last generated:**", debug_info.get('token_last_generated'))
            st.write("**Token error:**", debug_info.get('token_error'))
            st.write("**Security map size:**", debug_info.get('security_map_size'))
            st.write("**Security map error:**", debug_info.get('security_map_error'))
            st.write("**Per-symbol results:**")
            st.json(debug_info.get('per_symbol', {}))

        # CSV download
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f'candle_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )

# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REFRESH TRIGGER (Stage 1 only, every 1 minute)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #666; padding: 1rem;'>
        🔄 Stage 1 refreshes every 1 minute • Last refresh: {st.session_state.get('stage1_last_refresh', datetime.now(IST)).strftime('%H:%M:%S')}
        <br>
        ✅ Stage 2 filters preserved • Checkbox states maintained
        <br>
        Made with ❤️ using Streamlit | Data from TradingView & Yahoo Finance | Orders via DhanHQ
    </div>
    """,
    unsafe_allow_html=True
)
