# ═══════════════════════════════════════════════════════════════════════════════
# TRADINGVIEW SCREENER - FINAL WITH ALL CONDITIONS + 9:20-9:35 LOW TOUCH CHECK
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
    Returns dict with base_ticker -> candle_info containing:
      - high_9_15, low_9_15, close_9_15
      - open_9_20, high_9_20, low_9_20, close_9_20
      - max_high_up_to_10_15
      - hit_low_9_20_to_35 (True if any candle 9:20-9:35 touches low_9_15)
      - yahoo_ticker, data_date
    Only today's data is used.
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
                if today_data.empty:
                    continue
                df_day = today_data

                # 9:15 candle (first candle around 9:15)
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

                # ✅ NEW: Check 9:20-9:35 for touching 9:15 low
                low_9_15 = float(first_candle['Low'])
                mask_20_to_35 = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 35)
                hit_low_9_20_to_35 = False
                if mask_20_to_35.sum() > 0:
                    candles = df_day.loc[mask_20_to_35]
                    hit_low_9_20_to_35 = ((candles['Low'] <= low_9_15) | (candles['Close'] <= low_9_15)).any().item()

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
                    'yahoo_ticker': yahoo_ticker,
                    'data_date': today.strftime("%Y-%m-%d")
                }
                found = True
                break
        # if not found, skip
    return results

def check_candle_conditions(df, tickers_list, max_open_percent=2.0):
    """
    Check all conditions:
    1. 9:20 Close ≤ 9:15 High
    2. 9:20 High and Low below 9:15 High
    3. Opening gap ≤ max_open_percent
    4. 9:20 Candle bearish: Close < Open
    5. 9:20-9:35 does NOT touch 9:15 Low
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
    df['data_date'] = None
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
            df.at[idx, 'yahoo_ticker'] = data['yahoo_ticker']
            df.at[idx, 'data_date'] = data['data_date']

            prev_close = data['close_9_15']
            if prev_close > 0:
                gap_percent = ((data['high_9_20'] - prev_close) / prev_close) * 100
                df.at[idx, 'open_gap_percent'] = gap_percent
            else:
                gap_percent = 0

            # All conditions
            cond1 = data['close_9_20'] <= data['high_9_15']
            cond2 = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] <= data['high_9_15'])
            cond3 = abs(gap_percent) <= max_open_percent
            cond4 = data['close_9_20'] < data['open_9_20']
            cond5 = not data['hit_low_9_20_to_35']  # NEW: Does NOT touch 9:15 low between 9:20-9:35

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
                    reasons.append(f'Gap > {max_open_percent}%')
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
                    'date': data['data_date']
                })
        else:
            failed_to_fetch.append(ticker)

    if len(sample_data) > 0:
        st.info("📊 Sample data for first 5 stocks that had data (conditions shown):")
        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df)
    else:
        st.warning("⚠️ No stock data could be fetched from Yahoo Finance. Possible reasons: market closed, network issues, or ticker format mismatches.")

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

max_gap = st.sidebar.slider(
    "🚫 Max Opening Gap %",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5,
    help="Ignore stocks that open with a gap greater than this percentage"
)

stocks_to_show = st.sidebar.slider(
    "📋 Number of stocks to display",
    min_value=10,
    max_value=200,
    value=50,
    step=10
)

run_button = st.sidebar.button(
    "🚀 Run Screener",
    type="primary",
    use_container_width=True
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 📋 Filter Conditions:
1. **9:20 Close ≤ 9:15 High**
2. **9:20 High/Low below 9:15 High**
3. **Opening gap ≤ 2%** (configurable)
4. **9:20 Candle bearish (Close < Open)**
5. **9:20-9:35 does NOT touch 9:15 Low** ✅
6. **Price ₹200–₹2000**
7. **Market Cap ≥ 41B**
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
# MAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

if run_button:
    with st.status("Fetching data from TradingView...", expanded=True) as status:
        st.write("Applying filters:")
        st.write(f"- Price: ₹{price_min} to ₹{price_max}")
        st.write(f"- Market Cap: {selected_cap}")
        st.write("- Exchange: NSE")
        
        count, df = get_tradingview_stocks(price_min, price_max, market_cap_min)
        
        if count == 0:
            st.error("❌ No stocks found with these filters!")
            st.stop()
        
        status.update(label=f"✅ Found {count} stocks from TradingView", state="complete")
    
    with st.status("Checking candle conditions...", expanded=True) as status:
        st.write("Applying conditions:")
        st.write("1️⃣ 9:20 Close ≤ 9:15 High")
        st.write("2️⃣ 9:20 High/Low below 9:15 High")
        st.write(f"3️⃣ Opening gap ≤ {max_gap}%")
        st.write("4️⃣ 9:20 candle bearish (Close < Open)")
        st.write("5️⃣ 9:20-9:35 does NOT touch 9:15 Low")
        
        # Process first 200 stocks for performance
        tickers_list = df['ticker'].tolist()[:200]
        df, valid, invalid, failed = check_candle_conditions(df, tickers_list, max_gap)
        
        status.update(
            label=f"✅ Candle check complete: {len(valid)} pass, {len(invalid)} fail, {len(failed)} no data",
            state="complete"
        )
    
    df_filtered = df[df['passes_candle_check'] == True].copy()
    df_filtered = df_filtered.head(stocks_to_show)
    total_passing = len(df_filtered)
    
    st.markdown("---")
    st.subheader("📊 Results Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Stocks Found", count)
    with col2:
        st.metric("Passing All Conditions", len(valid), delta="✓")
    with col3:
        st.metric("Displaying", total_passing)
    with col4:
        if total_passing > 0:
            avg_change = df_filtered['change'].mean()
            st.metric("Avg Change %", f"{avg_change:.2f}%", 
                     delta="Gain" if avg_change > 0 else "Loss", 
                     delta_color="normal" if avg_change > 0 else "inverse")
    
    if total_passing > 0:
        st.subheader("📋 Stock Details")
        display_df = df_filtered.copy()
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)
        
        display_cols = [
            'name', 'close', 'change', 'volume', 'relative_volume', 
            'market_cap_b', 'sector',
            'candle_9_15_high', 'candle_9_20_open', 'candle_9_20_high', 
            'candle_9_20_low', 'candle_9_20_close', 'max_high_up_to_10_15', 
            'open_gap_percent', 'hit_low_9_20_to_35'
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
            'hit_low_9_20_to_35': 'Hit Low (9:20-9:35)?'
        }
        rename_dict = {k: v for k, v in rename_dict.items() if k in display_df.columns}
        display_df = display_df.rename(columns=rename_dict)
        
        for col in display_df.columns:
            if pd.api.types.is_numeric_dtype(display_df[col]):
                display_df[col] = display_df[col].round(2)
        
        def color_change(val):
            try:
                if isinstance(val, (int, float)):
                    color = '#00ff88' if val > 0 else '#ff4444'
                    return f'color: {color}'
                return ''
            except:
                return ''
        
        if 'Change %' in display_df.columns:
            styled_df = display_df.style.applymap(color_change, subset=['Change %'])
        else:
            styled_df = display_df.style
        
        st.dataframe(styled_df, use_container_width=True, height=500)
        
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name=f'screener_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )
        st.success(f"✅ Found {total_passing} stocks meeting all conditions!")
    else:
        st.warning("⚠️ No stocks passed all conditions!")
        col1, col2 = st.columns(2)
        with col1:
            st.info("💡 **Try these fixes:**")
            st.write(f"1. 📊 **Increase max gap %** (currently {max_gap}%)")
            st.write("2. 📅 **Check during market hours** (9:15 AM - 3:30 PM IST)")
            st.write("3. 🔄 **Refresh the data** after market opens")
            st.write("4. 📊 **Adjust your filters** to include more stocks")
        with col2:
            st.info("📊 **Status Distribution:**")
            status_counts = df['candle_check_status'].value_counts()
            for status, count in status_counts.items():
                st.write(f"- {status}: {count} stocks")

else:
    st.info("👈 **Configure your filters in the sidebar and click 'Run Screener' to start**")
    st.markdown("""
    ### 🎯 What this screener does:
    1. **Fetches stocks** from NSE India based on your filters (Price, Market Cap, Exchange)
    2. **Checks five candle conditions**:
       - 9:20 Close ≤ 9:15 High
       - 9:20 High/Low below 9:15 High
       - Opening gap ≤ 2% (configurable)
       - 9:20 candle bearish (Close < Open)
       - 9:20-9:35 does NOT touch 9:15 Low ✅
    3. **Displays results** with detailed candle data
    
    ### 🔧 Available filters:
    - **Minimum Market Cap**: ≥ 41B, 100B, 500B, or 1T
    - **Price Range**: ₹50–₹5000 (slider)
    - **Max Gap %**: Control the maximum allowed opening gap
    - **Number of stocks**: Control how many stocks to display
    """)

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 1rem;'>
        Made with ❤️ using Streamlit | Data from TradingView & Yahoo Finance
    </div>
    """,
    unsafe_allow_html=True
)
