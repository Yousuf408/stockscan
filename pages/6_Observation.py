# ═══════════════════════════════════════════════════════════════════════════════
# PAGES / 6_OBSERVATION.PY – INDIA STOCK SCREENER (AUTO, WITH TIMER)
# Stage 1: Auto-load from TradingView + gap filter (±2%) ONLY
# Stage 2: Auto candle analysis with inside-9:15 & breakout checkboxes
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
import requests
import math
import pyotp
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
# MSTOCK MARGIN CALCULATOR (integrated)
# ─────────────────────────────────────────────────────────────────────────────
# Replace these with your actual credentials or use st.secrets
MSTOCK_BASE_URL = "https://api.mstock.trade/openapi/typeb"
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_USER_ID = "MA1764118"
MSTOCK_PASSWORD = "P@ssw0rd"
MSTOCK_TOTP_SECRET = "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV"

def _mstock_headers(jwt=None):
    headers = {"X-Mirae-Version": "1"}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers

def _mstock_token():
    try:
        totp = pyotp.TOTP(MSTOCK_TOTP_SECRET).now()
        resp = requests.post(
            f"{MSTOCK_BASE_URL}/connect/login",
            json={"clientcode": MSTOCK_USER_ID, "password": MSTOCK_PASSWORD, "totp": totp, "state": ""},
            headers=_mstock_headers(),
            timeout=10
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get('data', {}).get('jwtToken') if data.get('status') else None
    except:
        return None

@st.cache_data(ttl=86400)
def _mstock_token_map():
    token_map = {}
    jwt = _mstock_token()
    if not jwt:
        return token_map
    resp = requests.get(f"{MSTOCK_BASE_URL}/instruments/OpenAPIScripMaster", headers=_mstock_headers(jwt), timeout=30)
    if resp.status_code != 200:
        return token_map
    data = resp.json()
    instruments = data.get('data', []) if isinstance(data, dict) else data
    for item in instruments:
        if item.get('instrumenttype', '').upper() not in ('EQ', 'EQUITY', 'E'):
            continue
        sym = item.get('symbol') or item.get('trading_symbol')
        tok = item.get('token') or item.get('instrument_token')
        if sym and tok:
            token_map[sym.upper()] = str(tok)
    return token_map

def calculate_margin_and_qty(df, total_capital, num_parts=4, price_col='Price'):
    """
    Adds three columns to the input DataFrame (must have 'Symbol' and price_col):
        - Margin/Share (₹)
        - Leverage (x)
        - Max Qty
    """
    if df.empty or total_capital <= 0:
        df['Margin/Share (₹)'] = 0
        df['Leverage (x)'] = 0
        df['Max Qty'] = 0
        return df

    token_map = _mstock_token_map()
    if not token_map:
        df['Margin/Share (₹)'] = 0
        df['Leverage (x)'] = 0
        df['Max Qty'] = 0
        return df

    # Ensure price is numeric
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)

    if 'margin_cache' not in st.session_state:
        st.session_state['margin_cache'] = {}

    part_capital = total_capital / num_parts
    jwt = _mstock_token()   # get token once

    symbols = df['Symbol'].str.upper().str.strip().tolist()
    missing = []
    for s in symbols:
        price = df[df['Symbol'].str.upper() == s][price_col].iloc[0]
        if s not in st.session_state['margin_cache'] and token_map.get(s) and price > 0:
            missing.append(s)

    def fetch_margin(sym):
        token = token_map.get(sym)
        if not token:
            return sym, None
        headers = _mstock_headers(jwt)
        headers["Content-Type"] = "application/json"
        payload = {
            "orders": [{
                "product_type": "MIS",
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "0",
                "exchange": "NSE",
                "symbol_name": "",
                "token": token,
                "trigger_price": 0
            }]
        }
        try:
            resp = requests.post(f"{MSTOCK_BASE_URL}/margins/orders", json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                return sym, None
            data = resp.json()
            if not data.get('status'):
                return sym, None
            margin = data.get('data', {}).get('total', 0)
            return sym, float(margin) if margin > 0 else None
        except:
            return sym, None

    if missing:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_margin, s): s for s in missing}
            for future in as_completed(futures):
                sym, margin = future.result()
                if margin is not None and margin > 0:
                    st.session_state['margin_cache'][sym] = margin

    margins, leverages, qties = [], [], []
    for sym in symbols:
        margin = st.session_state['margin_cache'].get(sym)
        price = df[df['Symbol'].str.upper() == sym][price_col].iloc[0]
        if margin is None or margin <= 0 or price <= 0:
            margins.append(None)
            leverages.append(None)
            qties.append(0)
        else:
            margins.append(round(margin, 2))
            leverages.append(round(price / margin, 1))
            qties.append(math.floor(part_capital / margin))

    df['Margin/Share (₹)'] = margins
    df['Leverage (x)'] = leverages
    df['Max Qty'] = qties
    return df

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & STYLES (unchanged)
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
# AUTO‑REFRESH TIMER (every 2 minutes)
# ─────────────────────────────────────────────────────────────────────────────

def set_auto_refresh():
    if 'next_refresh' not in st.session_state:
        st.session_state.next_refresh = datetime.now() + timedelta(minutes=2)
    if datetime.now() >= st.session_state.next_refresh:
        st.session_state.next_refresh = datetime.now() + timedelta(minutes=2)
        st.experimental_rerun()

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONS (all original, unchanged)
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

@st.cache_data(ttl=120)
def get_tradingview_stocks(price_min, price_max, market_cap_min, limit=1000):
    try:
        count, df = (Query()
            .select(
                'name', 'close', 'change', 'volume',
                'relative_volume', 'market_cap_basic', 'sector'
            )
            .set_markets('india')
            .where(
                col('close') > price_min,
                col('close') <= price_max,
                col('market_cap_basic') > market_cap_min,
                col('exchange') == 'NSE'
            )
            .order_by('change', ascending=False)
            .limit(limit)
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

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR FILTERS (added margin inputs)
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.markdown("## 🔍 Filter Settings")

market_cap_options = {
    '≥ 41B (Large Cap)': 41_000_000_000,
    '≥ 100B (Mega Cap)': 100_000_000_000,
    '≥ 500B (Giant Cap)': 500_000_000_000,
    '≥ 1T (Super Cap)': 1_000_000_000_000
}
selected_cap = st.sidebar.selectbox("📊 Minimum Market Cap", options=list(market_cap_options.keys()), index=0)
market_cap_min = market_cap_options[selected_cap]

price_min = st.sidebar.slider("💰 Minimum Price (₹)", min_value=50, max_value=1000, value=200, step=50)
price_max = st.sidebar.slider("💰 Maximum Price (₹)", min_value=500, max_value=5000, value=2000, step=100)
stocks_to_show = st.sidebar.slider("📋 Number of top stocks to display & analyze", min_value=10, max_value=200, value=50, step=10)

st.sidebar.markdown("---")
st.sidebar.markdown("### Stage 1 Filter: **Gap ±2%** only (EMA removed)")

# ── NEW: Margin settings ──
st.sidebar.markdown("---")
st.sidebar.markdown("### 💰 Margin Settings")
total_capital = st.sidebar.number_input("Total Capital (₹)", min_value=1000, value=10000, step=1000)
num_parts = st.sidebar.number_input("Number of Parts", min_value=1, max_value=10, value=4, step=1)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE (unchanged except margin integration)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="main-header">📈 India Stock Screener (Auto‑Refresh Every 2 min)</div>', unsafe_allow_html=True)

ist = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(ist)
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
# STAGE 1: AUTO-LOAD & GAP FILTER (summary only, no table)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="stage-header">📊 STAGE 1: Loading & Filtering (Gap ±2%)</div>', unsafe_allow_html=True)

with st.status("Fetching stocks from TradingView...", expanded=False) as status:
    count, df = get_tradingview_stocks(price_min, price_max, market_cap_min)
    if count == 0:
        st.error("❌ No stocks found!")
        st.stop()
    status.update(label=f"✅ Found {count} stocks", state="complete")

with st.spinner("Applying gap filter (bulk)..."):
    filtered_tickers, rejected = get_gap_filtered_stocks(df)
    df = df[df['ticker'].isin(filtered_tickers)].copy()
    df = df.sort_values('change', ascending=False)
    df = df.head(stocks_to_show)
    filtered_count = len(df)

st.success(f"✅ Gap Filter: {count} → {filtered_count} stocks (Rejected {len(rejected)})")
if rejected:
    with st.expander(f"📊 Show Rejected ({len(rejected)})"):
        for s in rejected[:20]:
            st.write(f"- {s['ticker']}: {s['reason']}")

st.info(f"✅ {filtered_count} stocks match. Stage 2 (candle analysis) running automatically...")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: AUTO-ANALYZE CANDLES
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown('<div class="stage-header">📊 STAGE 2: Candle Analysis (Auto)</div>', unsafe_allow_html=True)

with st.spinner("Fetching 5‑minute intraday data and checking candle conditions..."):
    tickers_list = df['ticker'].tolist()
    df, valid, invalid, failed = check_candle_conditions(df, tickers_list)

# Metrics
col1, col2, col3 = st.columns(3)
with col1: st.metric("Analyzed", len(df))
with col2: st.metric("Pass All 4 Conditions", len(valid), delta="✓")
with col3: st.metric("Fail / No Data", len(invalid)+len(failed), delta="✗")

# ─────────────────────────────────────────────────────────────────────────────
# FILTER CHECKBOXES (inside 9:15 & breakout) – side by side
# ─────────────────────────────────────────────────────────────────────────────

filter_col1, filter_col2 = st.columns(2)

with filter_col1:
    if is_after_9_25:
        show_inside_only = st.checkbox(
            "📊 Show only stocks where 9:20 candle is INSIDE 9:15 range",
            value=False,
            help="Filters to show only stocks where 9:20 high ≤ 9:15 high AND 9:20 low ≥ 9:15 low"
        )
    else:
        st.info("⏳ 9:20 candle not yet complete – filter available after 9:25 AM.")
        show_inside_only = False

with filter_col2:
    if is_after_9_30:
        show_breakout_only = st.checkbox(
            "⚡ Show ONLY Breakout Stocks (9:30-9:45)",
            value=False,
            help="Filters to show only stocks that broke above 9:15 High between 9:30-9:45"
        )
    else:
        st.info("⏳ Breakout filter available after 9:30 AM.")
        show_breakout_only = False

# ─────────────────────────────────────────────────────────────────────────────
# APPLY FILTERS & PREPARE FINAL DATAFRAME
# ─────────────────────────────────────────────────────────────────────────────

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

    # 2. Select only the columns we want to show
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

    # ── NEW: Add margin columns ──
    # Temporarily rename Price column to 'Price' for the function
    display_df['Price'] = display_df['Price (₹)']
    display_df['Symbol'] = display_df['Stock']
    # Call margin calculator
    display_df = calculate_margin_and_qty(
        display_df,
        total_capital=total_capital,
        num_parts=num_parts,
        price_col='Price'
    )
    # Drop temporary columns (keep only the new margin columns)
    # The function adds 'Margin/Share (₹)', 'Leverage (x)', 'Max Qty'
    display_df = display_df.drop(columns=['Price', 'Symbol'], errors='ignore')

    # ── Display styled table ──
    if 'Change %' in display_df.columns:
        styled_df = display_df.style.applymap(color_change, subset=['Change %'])
    else:
        styled_df = display_df.style

    st.dataframe(styled_df, use_container_width=True, height=500)

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
# AUTO-REFRESH TRIGGER
# ─────────────────────────────────────────────────────────────────────────────

set_auto_refresh()

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 1rem;'>
        Made with ❤️ using Streamlit | Data from TradingView & Yahoo Finance
    </div>
    """,
    unsafe_allow_html=True
)
