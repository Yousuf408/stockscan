# ═══════════════════════════════════════════════════════════════════════════════
# TRADINGVIEW SCREENER WITH CANDLE FILTER - FIXED VERSION
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
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="TradingView Screener India",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
    </style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def get_tradingview_stocks(price_min, price_max, market_cap_min, limit=1000):
    """
    Fetch stocks from TradingView with specified filters
    """
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

@st.cache_data(ttl=300)
def get_intraday_data_bulk_fixed(tickers_list, use_alternate_symbols=True):
    """
    Fetch 5-minute intraday data with multiple symbol formats
    """
    results = {}
    
    # Try different symbol formats
    symbol_formats = ['.NS', '-NS', '']
    
    for ticker in tickers_list:
        base_ticker = ticker.replace('NSE:', '')
        
        for suffix in symbol_formats:
            try:
                yahoo_ticker = base_ticker + suffix
                
                # Fetch with shorter period for speed
                data = yf.download(
                    yahoo_ticker, 
                    period="5d", 
                    interval="5m", 
                    progress=False, 
                    auto_adjust=False,
                    threads=False
                )
                
                if not data.empty:
                    # Set timezone to IST
                    ist = pytz.timezone('Asia/Kolkata')
                    if data.index.tz is None:
                        data.index = data.index.tz_localize('UTC').tz_convert(ist)
                    else:
                        data.index = data.index.tz_convert(ist)
                    
                    # Check if we have today's data
                    today = datetime.now(ist).date()
                    today_data = data[data.index.date == today]
                    
                    if not today_data.empty:
                        # Look for 9:15 and 9:20 candles (with some flexibility)
                        for hour in [9, 10]:  # Check both 9 and 10 AM
                            mask_9_15 = (today_data.index.hour == hour) & (today_data.index.minute == 15)
                            mask_9_20 = (today_data.index.hour == hour) & (today_data.index.minute == 20)
                            
                            if not today_data[mask_9_15].empty and not today_data[mask_9_20].empty:
                                high_9_15 = float(today_data.loc[mask_9_15, 'High'].iloc[0])
                                close_9_20 = float(today_data.loc[mask_9_20, 'Close'].iloc[0])
                                results[base_ticker] = (high_9_15, close_9_20, yahoo_ticker)
                                break
                        
                        # If no 9:15/9:20 data, try to use first two candles of the day
                        if base_ticker not in results and len(today_data) >= 2:
                            try:
                                first_candle = today_data.iloc[0]
                                second_candle = today_data.iloc[1]
                                high_9_15 = float(first_candle['High'])
                                close_9_20 = float(second_candle['Close'])
                                results[base_ticker] = (high_9_15, close_9_20, yahoo_ticker + " (first two candles)")
                            except:
                                pass
                    
                    break  # If we got data, break the suffix loop
                    
            except Exception as e:
                continue
    
    return results

@st.cache_data(ttl=300)
def get_previous_day_candle_data(tickers_list):
    """
    Get previous day's data if today's data is not available
    """
    results = {}
    
    for ticker in tickers_list:
        base_ticker = ticker.replace('NSE:', '')
        try:
            yahoo_ticker = base_ticker + '.NS'
            
            data = yf.download(
                yahoo_ticker, 
                period="7d", 
                interval="5m", 
                progress=False, 
                auto_adjust=False,
                threads=False
            )
            
            if not data.empty:
                ist = pytz.timezone('Asia/Kolkata')
                if data.index.tz is None:
                    data.index = data.index.tz_localize('UTC').tz_convert(ist)
                else:
                    data.index = data.index.tz_convert(ist)
                
                # Get most recent trading day
                dates = data.index.date.unique()
                if len(dates) > 0:
                    latest_date = dates[-1]
                    latest_data = data[data.index.date == latest_date]
                    
                    if len(latest_data) >= 2:
                        first_candle = latest_data.iloc[0]
                        second_candle = latest_data.iloc[1]
                        high_9_15 = float(first_candle['High'])
                        close_9_20 = float(second_candle['Close'])
                        results[base_ticker] = (high_9_15, close_9_20, yahoo_ticker + " (prev day)")
                        
        except Exception as e:
            continue
    
    return results

def check_candle_condition_fixed(df, tickers_list):
    """
    Check the candle condition with multiple fallback methods
    """
    # First try: Get today's data
    with st.spinner('Fetching today\'s intraday data from Yahoo Finance...'):
        candle_data = get_intraday_data_bulk_fixed(tickers_list)
    
    # If not enough data, try previous day
    if len(candle_data) < len(tickers_list) * 0.1:  # Less than 10% of stocks have data
        with st.spinner('Today\'s data limited. Trying previous trading day...'):
            prev_data = get_previous_day_candle_data(tickers_list)
            candle_data.update(prev_data)
    
    # Add columns
    df['candle_9_15_high'] = None
    df['candle_9_20_close'] = None
    df['passes_candle_check'] = False
    df['candle_check_status'] = 'No Data'
    df['yahoo_ticker'] = ''
    
    valid_stocks = []
    invalid_stocks = []
    failed_to_fetch = []
    
    for idx, row in df.iterrows():
        ticker = row['ticker']
        base_ticker = ticker.replace('NSE:', '')
        
        if base_ticker in candle_data:
            high_9_15, close_9_20, yahoo_ticker = candle_data[base_ticker]
            df.at[idx, 'candle_9_15_high'] = high_9_15
            df.at[idx, 'candle_9_20_close'] = close_9_20
            df.at[idx, 'yahoo_ticker'] = yahoo_ticker
            
            # Check condition: 9:20 Close <= 9:15 High
            if close_9_20 <= high_9_15:
                df.at[idx, 'passes_candle_check'] = True
                df.at[idx, 'candle_check_status'] = 'PASS ✓'
                valid_stocks.append(ticker)
            else:
                df.at[idx, 'candle_check_status'] = 'FAIL ✗'
                invalid_stocks.append(ticker)
        else:
            failed_to_fetch.append(ticker)
    
    return df, valid_stocks, invalid_stocks, failed_to_fetch

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR - FILTERS
# ═══════════════════════════════════════════════════════════════════════════════

st.sidebar.markdown("## 🔍 Filter Settings")

# Market Cap filter
market_cap_options = {
    '> 41B (Large Cap)': 41_000_000_000,
    '> 100B (Mega Cap)': 100_000_000_000,
    '> 500B (Giant Cap)': 500_000_000_000,
    '> 1T (Super Cap)': 1_000_000_000_000
}
selected_cap = st.sidebar.selectbox(
    "📊 Market Cap",
    options=list(market_cap_options.keys()),
    index=0
)
market_cap_min = market_cap_options[selected_cap]

# Price range
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
    value=3000,
    step=100
)

# Candle filter toggle
enable_candle_filter = st.sidebar.checkbox(
    "🕯️ Enable 9:15/9:20 Candle Filter",
    value=True,
    help="Filter stocks where 9:20 AM close <= 9:15 AM high"
)

# Number of stocks to display
stocks_to_show = st.sidebar.slider(
    "📋 Number of stocks to display",
    min_value=10,
    max_value=200,
    value=50,
    step=10
)

# Action button
run_button = st.sidebar.button(
    "🚀 Run Screener",
    type="primary",
    use_container_width=True
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### ℹ️ How it works:
1. Fetches stocks from TradingView with your filters
2. Optionally checks 9:15/9:20 candle condition via Yahoo Finance
3. Displays results with interactive charts

### ⚠️ Note:
- Data may be limited during market hours
- Uses multiple symbol formats (.NS, -NS, etc.)
- Falls back to previous day data if needed
""")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════════════════════════════════

# Header
st.markdown('<div class="main-header">📈 India Stock Screener</div>', unsafe_allow_html=True)

# Market status
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

# Show warning if market is closed
if not is_market_open:
    st.warning("⚠️ Market is currently closed. Candle data will be from the most recent trading day.")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

if run_button:
    # Step 1: Fetch from TradingView
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
    
    # Step 2: Candle check if enabled
    if enable_candle_filter and count > 0:
        with st.status("Checking candle condition...", expanded=True) as status:
            st.write("Fetching 9:15 and 9:20 candle data from Yahoo Finance...")
            st.write("Trying multiple symbol formats and fallback options...")
            
            tickers_list = df['ticker'].tolist()[:100]  # Limit to first 100 for speed
            df, valid, invalid, failed = check_candle_condition_fixed(df, tickers_list)
            
            status.update(
                label=f"✅ Candle check complete: {len(valid)} pass, {len(invalid)} fail, {len(failed)} no data",
                state="complete"
            )
        
        # Filter stocks that pass
        df_filtered = df[df['passes_candle_check'] == True].copy()
        df_filtered = df_filtered.head(stocks_to_show)
        total_passing = len(df_filtered)
        
        # Show sample of stocks with data
        df_with_data = df[df['candle_check_status'] != 'No Data'].copy()
        
    else:
        df_filtered = df.head(stocks_to_show).copy()
        total_passing = count
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RESULTS DISPLAY
    # ═══════════════════════════════════════════════════════════════════════════
    
    st.markdown("---")
    
    # Metrics row
    st.subheader("📊 Results Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Stocks Found", count, delta="From TradingView")
    with col2:
        if enable_candle_filter:
            st.metric("Passing Candle Check", len(valid) if enable_candle_filter else "N/A", 
                     delta="✓" if enable_candle_filter else "Filter disabled")
        else:
            st.metric("Candle Filter", "Disabled", delta="⏭️")
    with col3:
        st.metric("Displaying", total_passing, delta="Top gainers")
    with col4:
        if total_passing > 0:
            avg_change = df_filtered['change'].mean()
            st.metric("Avg Change %", f"{avg_change:.2f}%", 
                     delta="Gain" if avg_change > 0 else "Loss", 
                     delta_color="normal" if avg_change > 0 else "inverse")
    
    # Show data availability
    if enable_candle_filter:
        with st.expander("📊 Data Availability Details"):
            st.write(f"**Stocks with Yahoo Finance data:** {len(df_with_data)} out of {count}")
            if len(df_with_data) > 0:
                sample_tickers = df_with_data['ticker'].str.replace('NSE:', '').tolist()[:10]
                st.write(f"**Sample tickers with data:** {', '.join(sample_tickers)}")
            else:
                st.warning("No Yahoo Finance data available for any stock. This could be because:")
                st.write("1. Market is closed (try during market hours)")
                st.write("2. Yahoo Finance is temporarily unavailable")
                st.write("3. Symbol format issues (try alternative ticker formats)")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CHARTS AND TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    
    if total_passing > 0:
        st.subheader("📈 Visualizations")
        
        # Top gainers chart
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df_filtered['ticker'].str.replace('NSE:', ''),
            y=df_filtered['change'],
            marker_color=df_filtered['change'].apply(lambda x: '#00ff88' if x > 0 else '#ff4444'),
            text=df_filtered['change'].round(2),
            textposition='outside',
            name='Change %'
        ))
        fig1.update_layout(
            title='Top Gainers by Percentage Change',
            xaxis_title='Stock',
            yaxis_title='Change %',
            height=400,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white')
        )
        st.plotly_chart(fig1, use_container_width=True)
        
        # Price distribution
        col1, col2 = st.columns(2)
        
        with col1:
            fig2 = px.histogram(
                df_filtered, 
                x='close', 
                nbins=20,
                title='Price Distribution',
                labels={'close': 'Price (₹)'},
                color_discrete_sequence=['#00ff88']
            )
            fig2.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white')
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        with col2:
            df_filtered['market_cap_b'] = df_filtered['market_cap_basic'] / 1e9
            fig3 = px.scatter(
                df_filtered,
                x='change',
                y='close',
                size='market_cap_b',
                color='sector',
                title='Change vs Price (Bubble size = Market Cap)',
                labels={'change': 'Change %', 'close': 'Price (₹)'}
            )
            fig3.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'),
                height=400
            )
            st.plotly_chart(fig3, use_container_width=True)
        
        # ═══════════════════════════════════════════════════════════════════════
        # STOCK TABLE
        # ═══════════════════════════════════════════════════════════════════════
        
        st.subheader("📋 Stock Details")
        
        # Prepare display dataframe
        display_df = df_filtered.copy()
        display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
        display_df['market_cap_b'] = (display_df['market_cap_basic'] / 1e9).round(1)
        
        # Select columns for display
        display_cols = ['name', 'close', 'change', 'volume', 'relative_volume', 
                       'market_cap_b', 'sector']
        
        if enable_candle_filter:
            display_cols.extend(['candle_9_15_high', 'candle_9_20_close', 'candle_check_status'])
        
        display_df = display_df[display_cols].copy()
        
        # Rename columns
        display_df.columns = ['Stock', 'Price (₹)', 'Change %', 'Volume', 'Rel Volume', 
                             'Mkt Cap (B₹)', 'Sector']
        
        if enable_candle_filter:
            display_df.columns = list(display_df.columns) + ['9:15 High', '9:20 Close', 'Status']
        
        # Color code the change column
        def color_change(val):
            color = '#00ff88' if val > 0 else '#ff4444'
            return f'color: {color}'
        
        # Apply styling
        styled_df = display_df.style.applymap(
            color_change, 
            subset=['Change %']
        )
        
        # Display table
        st.dataframe(
            styled_df,
            use_container_width=True,
            height=400
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # DOWNLOAD BUTTON
        # ═══════════════════════════════════════════════════════════════════════
        
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name=f'screener_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            mime='text/csv',
            use_container_width=True
        )
        
    else:
        st.warning("⚠️ No stocks passed the candle check filter!")
        
        if enable_candle_filter:
            col1, col2 = st.columns(2)
            
            with col1:
                st.info("💡 **Try these fixes:**")
                st.write("1. ✅ **Disable the candle filter** to see all stocks")
                st.write("2. 📅 **Check during market hours** (9:15 AM - 3:30 PM IST)")
                st.write("3. 🔄 **Refresh the data** after market opens")
                st.write("4. 📊 **Adjust your filters** to include more stocks")
            
            with col2:
                st.info("📊 **Status Distribution:**")
                status_counts = df['candle_check_status'].value_counts()
                for status, count in status_counts.items():
                    st.write(f"- {status}: {count} stocks")
                
                # Show sample of stocks with data
                df_with_data = df[df['candle_check_status'] != 'No Data'].head(10)
                if len(df_with_data) > 0:
                    st.write("**Sample stocks with data:**")
                    sample = df_with_data['ticker'].str.replace('NSE:', '').tolist()
                    st.write(", ".join(sample[:5]))

else:
    # Initial state - show instructions
    st.info("👈 **Configure your filters in the sidebar and click 'Run Screener' to start**")
    
    st.markdown("""
    ### 🎯 What this screener does:
    1. **Fetches stocks** from NSE India based on your filters
    2. **Optional candle filter**: Checks if 9:20 AM close ≤ 9:15 AM high
    3. **Displays results** with interactive charts and detailed data
    
    ### 🔧 Available filters:
    - **Market Cap**: Choose from Large, Mega, Giant, or Super Cap
    - **Price Range**: Set your desired price range
    - **Candle Filter**: Toggle the 9:15/9:20 candle condition check
    - **Number of stocks**: Control how many stocks to display
    
    ### 📊 Features:
    - Real-time data from TradingView and Yahoo Finance
    - Interactive charts (Plotly)
    - Export results to CSV
    - Color-coded performance indicators
    
    ### ⚠️ Important Notes:
    - Yahoo Finance data works best during market hours
    - Only NSE stocks are included
    - First 100 stocks are checked for candle data (for performance)
    """)

# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 1rem;'>
        Made with ❤️ using Streamlit | Data from TradingView & Yahoo Finance
    </div>
    """,
    unsafe_allow_html=True
)
