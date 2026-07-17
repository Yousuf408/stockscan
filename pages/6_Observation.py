# ═══════════════════════════════════════════════════════════════════════════════
# TRADINGVIEW SCREENER - TWO STAGE APPROACH
# Stage 1: Auto-load stocks from TradingView (no button)
# Stage 2: Optional candle analysis (one button for all stocks)
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query
from tradingview_screener.column import col
from datetime import datetime, time, timedelta
import pytz
import plotly.graph_objects as go
import plotly.express as px
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="TradingView Screener India",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #00ff88;
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #1a1a2e, #16213e, #0f3460);
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .stage-header {
        font-size: 1.3rem;
        color: #00ff88;
        padding: 0.5rem;
        background: rgba(0, 255, 136, 0.1);
        border-left: 4px solid #00ff88;
        margin: 1rem 0;
    }
    .metric-card {
        background: #1e1e2e;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #00ff88;
        margin: 0.5rem 0;
    }
    .stock-card {
        background: #1e1e2e;
        padding: 0.8rem;
        border-radius: 8px;
        margin: 0.3rem 0;
        border: 1px solid #2d2d44;
    }
    .stock-card:hover {
        border-color: #00ff88;
        transition: 0.3s;
    }
    .success-text {
        color: #00ff88;
        font-weight: bold;
    }
    .fail-text {
        color: #ff4444;
        font-weight: bold;
    }
    .warning-text {
        color: #ffaa00;
        font-weight: bold;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────────────
# SECTION: GAP FILTER (BULK YAHOO FETCH)
# ──────────────────────────────────────────────────────────────────────────────

def get_gap_filtered_stocks(df):
    """
    Bulk fetch daily OHLC for all NSE tickers using yfinance.
    Uses the most recent trading day's open to compute gap, even if today is a holiday/weekend.
    Reject stocks with |gap%| >= 2%.
    """
    # Build mapping from Yahoo ticker (with .NS) to original TradingView ticker (NSE:...)
    yahoo_tickers = []
    ticker_map = {}
    for row in df.itertuples():
        base = row.ticker.replace('NSE:', '')
        yahoo_ticker = base + '.NS'      # Standard suffix for NSE on Yahoo
        yahoo_tickers.append(yahoo_ticker)
        ticker_map[yahoo_ticker] = row.ticker

    # Bulk download all daily data in one call
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
            # If no data, we cannot compute gap → keep the stock (fail‑safe)
            filtered.append(original_ticker)
            continue

        hist = data[yahoo_ticker]
        if hist.empty or len(hist) < 2:
            filtered.append(original_ticker)
            continue

        # Use the most recent available trading day
        latest_date = hist.index[-1].date()
        latest_data = hist[hist.index.date == latest_date]
        if latest_data.empty:
            filtered.append(original_ticker)
            continue

        today_open = float(latest_data.iloc[0]['Open'])

        # Get previous close – take the row immediately before latest_date
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
                'type': 'Gap UP' if gap_percent > 0 else 'Gap DOWN'
            })
        else:
            filtered.append(original_ticker)

    return filtered, rejected

# ──────────────────────────────────────────────────────────────────────────────
# SECTION: TRADINGVIEW SCREENER (STAGE 1)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
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

# ──────────────────────────────────────────────────────────────────────────────
# SECTION: INTRADAY DATA & CANDLE CONDITIONS (STAGE 2)
# ──────────────────────────────────────────────────────────────────────────────

def get_intraday_data_for_symbol(yahoo_ticker, period="5d", interval="5m"):
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

def get_candle_data_bulk(tickers_list):
    """
    Fetch 5‑minute data for a list of NSE tickers.
    (Sequential – Yahoo does not support bulk intraday)
    """
    results = {}
    symbol_formats = ['.NS', '-NS', '']

    for ticker in tickers_list:
        base_ticker = ticker.replace('NSE:', '')
        found = False
        for suffix in symbol_formats:
            yahoo_ticker = base_ticker + suffix
            data = get_intraday_data_for_symbol(yahoo_ticker)
            if data is not None and not data.empty:
                ist = pytz.timezone('Asia/Kolkata')
                today = datetime.now(ist).date()
                today_data = data[data.index.date == today]
                
                # Get previous day's close (for gap calculation)
                yesterday_data = data[data.index.date < today]
                if len(yesterday_data) > 0:
                    prev_close = float(yesterday_data.iloc[-1]['Close'])
                else:
                    prev_close = None
                
                if today_data.empty:
                    continue
                df_day = today_data

                # 9:15 candle
                mask_first = (df_day.index.hour == 9) & (df_day.index.minute >= 10) & (df_day.index.minute <= 20)
                if mask_first.sum() == 0:
                    mask_first = (df_day.index.hour == 9) & (df_day.index.minute < 30)
                    if mask_first.sum() == 0:
                        first_candle = df_day.iloc[0]
                    else:
                        first_candle = df_day[mask_first].iloc[0]
                else:
                    first_candle = df_day[mask_first].iloc[0]

                # 9:20 candle
                mask_second = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 25)
                if mask_second.sum() == 0:
                    if len(df_day) >= 2:
                        second_candle = df_day.iloc[1]
                    else:
                        continue
                else:
                    second_candle = df_day[mask_second].iloc[0]

                # Max high 9:20–10:15
                mask_morning = ((df_day.index.hour == 9) & (df_day.index.minute >= 20)) | \
                               ((df_day.index.hour == 10) & (df_day.index.minute <= 15))
                if mask_morning.sum() > 0:
                    max_high = float(df_day.loc[mask_morning, 'High'].max())
                else:
                    max_high = float(second_candle['High'])

                # Check 9:20-9:35 for touching 9:15 low
                low_9_15 = float(first_candle['Low'])
                mask_20_to_35 = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 35)
                hit_low_9_20_to_35 = False
                if mask_20_to_35.sum() > 0:
                    candles = df_day.loc[mask_20_to_35]
                    hit_low_9_20_to_35 = ((candles['Low'] <= low_9_15) | (candles['Close'] <= low_9_15)).any().item()

                # Check 9:30-9:45 for breakout above 9:15 high
                high_9_15 = float(first_candle['High'])
                mask_30_to_45 = (df_day.index.hour == 9) & (df_day.index.minute >= 30) & (df_day.index.minute <= 45)
                breakout_9_30_to_9_45 = False
                if mask_30_to_45.sum() > 0:
                    candles = df_day.loc[mask_30_to_45]
                    breakout_9_30_to_9_45 = (candles['High'] > high_9_15).any().item()

                # Calculate gap based on 9:20 High vs Previous Day Close
                if prev_close is not None and prev_close > 0:
                    high_9_20 = float(second_candle['High'])
                    gap_percent = ((high_9_20 - prev_close) / prev_close) * 100
                else:
                    gap_percent = 0
                    prev_close = float(first_candle['Close'])  # Fallback to today's close

                results[base_ticker] = {
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
                found = True
                break
    return results

def check_candle_conditions(df, tickers_list, max_open_percent=2.0):
    """
    Check all candle conditions:
    1. 9:20 Close ≤ 9:15 High
    2. 9:20 High and Low below 9:15 High
    3. 9:20 Candle bearish: Close < Open
    4. 9:20-9:35 does NOT touch 9:15 Low
    """
    with st.spinner('Fetching intraday data from Yahoo Finance...'):
        candle_data = get_candle_data_bulk(tickers_list)

    # Add columns
    df['candle_9_15_high'] = None
    df['candle_9_15_low'] = None
    df['candle_9_20_open'] = None
    df['candle_9_20_high'] = None
    df['candle_9_20_low'] = None
    df['candle_9_20_close'] = None
    df['max_high_up_to_10_15'] = None
    df['hit_low_9_20_to_35'] = None
    df['breakout_9_30_to_9_45'] = None
    df['data_date'] = None
    df['prev_close'] = None
    df['gap_percent'] = None
    df['open_gap_percent'] = None
    df['passes_candle_check'] = False
    df['candle_check_status'] = 'No Data'
    df['yahoo_ticker'] = ''

    valid_stocks = []
    invalid_stocks = []
    failed_to_fetch = []

    sample_data = []

    for idx, row in df.iterrows():
        ticker = row['ticker']
        base_ticker = ticker.replace('NSE:', '')

        if base_ticker in candle_data:
            data = candle_data[base_ticker]
            df.at[idx, 'candle_9_15_high'] = data['high_9_15']
            df.at[idx, 'candle_9_15_low'] = data['low_9_15']
            df.at[idx, 'candle_9_20_open'] = data['open_9_20']
            df.at[idx, 'candle_9_20_high'] = data['high_9_20']
            df.at[idx, 'candle_9_20_low'] = data['low_9_20']
            df.at[idx, 'candle_9_20_close'] = data['close_9_20']
            df.at[idx, 'max_high_up_to_10_15'] = data['max_high_up_to_10_15']
            df.at[idx, 'hit_low_9_20_to_35'] = data['hit_low_9_20_to_35']
            df.at[idx, 'breakout_9_30_to_9_45'] = data['breakout_9_30_to_9_45']
            df.at[idx, 'prev_close'] = data['prev_close']
            df.at[idx, 'gap_percent'] = data['gap_percent']
            df.at[idx, 'open_gap_percent'] = data['gap_percent']
            df.at[idx, 'yahoo_ticker'] = data['yahoo_ticker']
            df.at[idx, 'data_date'] = data['data_date']

            # Use gap_percent already calculated from prev_close
            gap_percent = data['gap_percent']

            # All conditions
            cond1 = data['close_9_20'] <= data['high_9_15']
            cond2 = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] <= data['high_9_15'])
            cond3 = abs(gap_percent) <= max_open_percent  # Ignore both gap up and gap down
            cond4 = data['close_9_20'] < data['open_9_20']
            cond5 = not data['hit_low_9_20_to_35']

            if cond1 and cond2 and cond3 and cond4 and cond5:
                df.at[idx, 'passes_candle_check'] = True
                df.at[idx, 'candle_check_status'] = 'PASS ✓'
                valid_stocks.append(ticker)
            else:
                reasons = []
                if not cond1:
                    reasons.append('9:20 close > 9:15 high')
                if not cond2:
                    reasons.append('9:20 high/low not below 9:15 high')
                if not cond3:
                    if gap_percent > max_open_percent:
                        reasons.append(f'Gap UP > {max_open_percent}% (vs prev close)')
                    else:
                        reasons.append(f'Gap DOWN > {max_open_percent}% (vs prev close)')
                if not cond4:
                    reasons.append('9:20 candle not bearish (close > open)')
                if not cond5:
                    reasons.append('Touched 9:15 low (9:20-9:35)')
                df.at[idx, 'candle_check_status'] = 'FAIL ✗ (' + ', '.join(reasons) + ')'
                invalid_stocks.append(ticker)

            if len(sample_data) < 5:
                sample_data.append({
                    'ticker': base_ticker,
                    'high_9_15': data['high_9_15'],
                    'open_9_20': data['open_9_20'],
                    'close_9_20': data['close_9_20'],
                    'gap%': gap_percent,
                    'cond1': cond1,
                    'cond2': cond2,
                    'cond3': cond3,
                    'cond4': cond4,
                    'cond5': cond5,
                    'breakout_9_30_45': data['breakout_9_30_to_9_45'],
                    'date': data['data_date']
                })
        else:
            failed_to_fetch.append(ticker)

    if len(sample_data) > 0:
        st.info("📊 Sample data for first 5 stocks that had data (conditions shown):")
        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df)
    else:
        st.warning("⚠️ No stock data could be fetched from Yahoo Finance.")

    return df, valid_stocks, invalid_stocks, failed_to_fetch

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR - FILTERS
# ═══════════════════════════════════════════════════════════════════════════════

st.sidebar.markdown("## 🔍 Filter Settings")

market_cap_options = {
    '≥ 41B (Large Cap)': 41_000_000_000,
    '≥ 100B (Mega Cap)': 100_000_000_000,
    '≥ 500B (Giant Cap)': 500_000_000_000,
    '≥ 1T (Super Cap)': 1_000_000_000_000
}
selected_cap = st.sidebar.selectbox(
    "📊 Minimum Market Cap",
    options=list(market_cap_options.keys()),
    index=0
)
market_cap_min = market_cap_options[selected_cap]

price_min = st.sidebar.slider(
    "💰 Minimum Price (₹)",
    min_value=50,
    max_value=1000,
    value=200,
    step=50
)

price_max = st.sidebar.slider(
    "💰 Maximum Price (₹)",
    min_value=500,
    max_value=5000,
    value=2000,
    step=100
)

stocks_to_show = st.sidebar.slider(
    "📋 Number of stocks to display",
    min_value=10,
    max_value=200,
    value=50,
    step=10
)

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚡ Candle Filters")

st.sidebar.markdown("""
**Default Settings:**
- 🚫 Max Gap: **2.0%** (fixed)
- 📊 **Ignores both Gap UP and Gap DOWN**
- ✅ Applied during stock fetch
- **Buy-Side Logic**: Avoids high-impact opening gaps
""")

# Fixed gap value
max_gap = 2.0

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚡ Breakout Filter (After 9:30 AM)")

# Breakout checkbox (only shows after 9:30 AM)
ist = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(ist)
breakout_start_time = current_time.replace(hour=9, minute=30, second=0)
is_after_9_30 = current_time >= breakout_start_time

if is_after_9_30:
    show_breakout_only = st.sidebar.checkbox(
        "⚡ Show ONLY Breakout Stocks (9:30-9:45)",
        value=False,
        help="Filters to show only stocks that broke above 9:15 High between 9:30-9:45"
    )
else:
    show_breakout_only = False
    st.sidebar.info("⏰ **Available after 9:30 AM**")
    st.sidebar.write("Track stocks breaking above 9:15 High between 9:30-9:45")

run_button = st.sidebar.button(
    "🚀 Analyze Candles for All Stocks",
    type="primary",
    use_container_width=True,
    help="Click to analyze candle conditions for all loaded stocks"
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 📋 Stock Filters (Stage 1 - Buy Side Logic):
1. **Price**: ₹200–₹2000 (configurable)
2. **Market Cap**: ≥ 41B (configurable)
3. **Exchange**: NSE
4. **Max Gap**: ±2% (fixed) - Ignores BOTH gap UP & gap DOWN

### ✅ Candle Conditions (Stage 2):
1. 9:20 Close ≤ 9:15 High
2. 9:20 High/Low below 9:15 High
3. 9:20 Candle bearish (Close < Open) - Seller control
4. 9:20-9:35 does NOT touch 9:15 Low - Holds support

### ⚡ Breakout Tracker (Optional):
- Enable after 9:30 AM
- Shows only breakout stocks (momentum confirmation)
- **Best for Buy entries after breakout confirmation**
""")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="main-header">📈 India Stock Screener</div>', unsafe_allow_html=True)

ist = pytz.timezone('Asia/Kolkata')
now = datetime.now(ist)
market_open = now.replace(hour=9, minute=15, second=0)
market_close = now.replace(hour=15, minute=30, second=0)
is_market_open = market_open <= now <= market_close

col1, col2, col3 = st.columns(3)
with col1:
    status = "🟢 Open" if is_market_open else "🔴 Closed"
    st.metric("🇮🇳 Market", status, delta="NSE India")
with col2:
    st.metric("🕐 Time", now.strftime("%H:%M IST"), delta="")
with col3:
    st.metric("📅 Date", now.strftime("%d %b %Y"), delta="")

if not is_market_open:
    st.warning("⚠️ Market is currently closed. Candle data will be from the most recent trading day (if any).")

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: AUTO-LOAD STOCKS
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="stage-header">📊 STAGE 1: Loading Qualified Stocks from TradingView</div>', unsafe_allow_html=True)

with st.status("Fetching stocks from TradingView...", expanded=False) as status:
    st.write("Applying filters:")
    st.write(f"- Price: ₹{price_min} to ₹{price_max}")
    st.write(f"- Market Cap: {selected_cap}")
    st.write("- Exchange: NSE")
    st.write("- Max Gap: 2% (fixed)")
    
    count, df = get_tradingview_stocks(price_min, price_max, market_cap_min)
    
    if count == 0:
        st.error("❌ No stocks found with these filters!")
        st.stop()
    
    status.update(label=f"✅ Found {count} stocks from TradingView", state="complete")

# Apply gap filtering (bulk Yahoo fetch)
st.markdown("---")
st.markdown("⚡ **Applying Gap Filter (±2% from Previous Close)...**")

with st.spinner("Filtering stocks by gap up/down (bulk download)..."):
    filtered_tickers, rejected_gap_stocks = get_gap_filtered_stocks(df)
    df = df[df['ticker'].isin(filtered_tickers)].copy()
    
    filtered_count = len(df)
    rejected_count = len(rejected_gap_stocks)

if rejected_count > 0:
    st.success(f"✅ Gap Filter Applied: {count} → {filtered_count} stocks (Rejected {rejected_count} with ±2% gap)")
    with st.expander(f"📊 Show Rejected Stocks ({rejected_count})"):
        for stock in rejected_gap_stocks[:20]:  # Show first 20
            gap_type = f"<span style='color:#ff4444'>{stock['type']}</span>"
            st.write(f"- {stock['ticker']}: {stock['gap_percent']:.2f}% {stock['type']}")
else:
    st.success(f"✅ Gap Filter Applied: All {filtered_count} stocks passed ±2% check")

count = filtered_count  # Update count to filtered count

# Display stock table
st.subheader(f"📋 Qualified Stocks List ({count} stocks - After Gap Filter)")

display_tv_df = df.copy()
display_tv_df['name'] = display_tv_df['ticker'].str.replace('NSE:', '')
display_tv_df['market_cap_b'] = (display_tv_df['market_cap_basic'] / 1e9).round(1)

tv_display_cols = ['name', 'close', 'change', 'volume', 'relative_volume', 'market_cap_b', 'sector']
available_cols = [col for col in tv_display_cols if col in display_tv_df.columns]
display_tv_df = display_tv_df[available_cols].copy()

rename_tv_dict = {
    'name': 'Stock',
    'close': 'Price (₹)',
    'change': 'Change %',
    'volume': 'Volume',
    'relative_volume': 'Rel Vol',
    'market_cap_b': 'Mkt Cap (B₹)',
    'sector': 'Sector'
}
rename_tv_dict = {k: v for k, v in rename_tv_dict.items() if k in display_tv_df.columns}
display_tv_df = display_tv_df.rename(columns=rename_tv_dict)

for col in display_tv_df.columns:
    if pd.api.types.is_numeric_dtype(display_tv_df[col]):
        display_tv_df[col] = display_tv_df[col].round(2)

def color_change(val):
    try:
        if isinstance(val, (int, float)):
            color = '#00ff88' if val > 0 else '#ff4444'
            return f'color: {color}'
        return ''
    except:
        return ''

if 'Change %' in display_tv_df.columns:
    styled_tv_df = display_tv_df.style.applymap(color_change, subset=['Change %'])
else:
    styled_tv_df = display_tv_df.style

st.dataframe(styled_tv_df, use_container_width=True, height=400)

st.info(f"✅ **{count} stocks match your filters.** \n\n👉 Click '🚀 Analyze Candles for All Stocks' button in the sidebar to check candle conditions.")

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: CANDLE ANALYSIS (OPTIONAL)
# ═══════════════════════════════════════════════════════════════════════════════

if run_button:
    st.markdown("---")
    st.markdown('<div class="stage-header">✅ STAGE 2: Analyzing Candle Conditions for All Stocks</div>', unsafe_allow_html=True)
    
    with st.status("Checking candle conditions...", expanded=True) as status:
        st.write("Applying conditions (Buy-Side Logic):")
        st.write("1️⃣ 9:20 Close ≤ 9:15 High")
        st.write("2️⃣ 9:20 High/Low below 9:15 High")
        st.write("3️⃣ 9:20 candle bearish (Close < Open) - Seller Control")
        st.write("4️⃣ 9:20-9:35 does NOT touch 9:15 Low - Holds Support")
        st.write("🚫 **Gap Filter**: ±2% (ignores both Gap UP and Gap DOWN)")
        
        # Process all stocks for candle analysis
        tickers_list = df['ticker'].tolist()[:200]
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list, max_gap)
        
        status.update(
            label=f"✅ Candle check complete: {len(valid)} pass, {len(invalid)} fail, {len(failed)} no data",
            state="complete"
        )
    
    df_filtered = df[df['passes_candle_check'] == True].copy()
    
    # Apply breakout filter if checkbox is selected
    if show_breakout_only:
        df_filtered = df_filtered[df_filtered['breakout_9_30_to_9_45'] == True].copy()
    
    df_filtered = df_filtered.head(stocks_to_show)
    total_passing = len(df_filtered)
    
    st.markdown("---")
    st.subheader("📊 Candle Analysis Results")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Analyzed", count)
    with col2:
        st.metric("Passing All Conditions", len(valid), delta="✓")
    with col3:
        if show_breakout_only:
            breakout_count = len(df[df['breakout_9_30_to_9_45'] == True])
            st.metric("Breakout Stocks", breakout_count, delta="⚡")
        else:
            st.metric("Showing", total_passing)
    with col4:
        if total_passing > 0:
            avg_change = df_filtered['change'].mean()
            st.metric("Avg Change %", f"{avg_change:.2f}%", 
                     delta="Gain" if avg_change > 0 else "Loss", 
                     delta_color="normal" if avg_change > 0 else "inverse")
    
    if total_passing > 0:
        st.subheader("📋 Stocks Passing All Candle Conditions")
        display_df = df_filtered.copy()
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)
        
        display_cols = [
            'name', 'close', 'change', 'volume', 'relative_volume', 
            'market_cap_b', 'sector',
            'candle_9_15_high', 'candle_9_20_open', 'candle_9_20_high', 
            'candle_9_20_low', 'candle_9_20_close', 'max_high_up_to_10_15', 
            'open_gap_percent', 'hit_low_9_20_to_35', 'breakout_9_30_to_9_45'
        ]
        available_cols = [col for col in display_cols if col in display_df.columns]
        display_df = display_df[available_cols].copy()
        
        rename_dict = {
            'name': 'Stock',
            'close': 'Price (₹)',
            'change': 'Change %',
            'volume': 'Volume',
            'relative_volume': 'Rel Vol',
            'market_cap_b': 'Mkt Cap (B₹)',
            'sector': 'Sector',
            'candle_9_15_high': '9:15 High',
            'candle_9_20_open': '9:20 Open',
            'candle_9_20_high': '9:20 High',
            'candle_9_20_low': '9:20 Low',
            'candle_9_20_close': '9:20 Close',
            'max_high_up_to_10_15': 'Max High till 10:15',
            'open_gap_percent': 'Gap %',
            'hit_low_9_20_to_35': 'Hit Low (9:20-9:35)?',
            'breakout_9_30_to_9_45': 'Breakout (9:30-9:45)?'
        }
        rename_dict = {k: v for k, v in rename_dict.items() if k in display_df.columns}
        display_df = display_df.rename(columns=rename_dict)
        
        for col in display_df.columns:
            if pd.api.types.is_numeric_dtype(display_df[col]):
                display_df[col] = display_df[col].round(2)
        
        if 'Change %' in display_df.columns:
            styled_df = display_df.style.applymap(color_change, subset=['Change %'])
        else:
            styled_df = display_df.style
        
        st.dataframe(styled_df, use_container_width=True, height=500)
        
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name=f'candle_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )
        st.success(f"✅ Found {total_passing} stocks" + (" with breakout (9:30-9:45)!" if show_breakout_only else " passing all candle conditions!"))
    else:
        st.warning("⚠️ No stocks passed all candle conditions!")
        col1, col2 = st.columns(2)
        with col1:
            st.info("💡 **Why no results?**")
            st.write("1. 📅 **Market is closed** - check during trading hours (9:15 AM - 3:30 PM IST)")
            st.write("2. ⏰ **Before 9:35 AM** - candle data not complete yet")
            st.write("3. 📊 **Very strict conditions** - all 4 conditions must pass")
        with col2:
            st.info("📊 **Status Distribution:**")
            status_counts = df['candle_check_status'].value_counts()
            for status, count in status_counts.items():
                st.write(f"- {status}: {count} stocks")

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 1rem;'>
        Made with ❤️ using Streamlit | Data from TradingView & Yahoo Finance
    </div>
    """,
    unsafe_allow_html=True
)
