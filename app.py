import streamlit as st
import pandas as pd
from datetime import datetime
import logging

# ================================================================
# 1. PAGE CONFIG – MUST BE FIRST STREAMLIT COMMAND
# ================================================================
st.set_page_config(page_title="Margin Calculator", layout="wide")

# ================================================================
# 2. MSTOCK SDK SETUP
# ================================================================
# Try importing the official mStock SDK (Type A)
# Install: pip install mStock-TradingApi-A
try:
    from tradingapi_a.mconnect import MConnect
    MSTOCK_SDK_AVAILABLE = True
except ImportError:
    MSTOCK_SDK_AVAILABLE = False

# ================================================================
# 3. AUTHENTICATION & API FUNCTIONS
# ================================================================
def authenticate_mstock(api_key: str, user_id: str, password: str, otp: str = None):
    """
    Authenticate with mStock and return an authenticated client object.
    
    Flow:
    1. Login with user_id and password -> get request_token
    2. Generate session with API key, request_token, and checksum/OTP
    3. Return the client with valid access token
    """
    if not MSTOCK_SDK_AVAILABLE:
        st.error("❌ mStock SDK not installed. Run: pip install mStock-TradingApi-A")
        return None
    
    try:
        # Initialize MConnect client
        client = MConnect()
        
        # Step 1: Login to get request token
        login_response = client.login(user_id, password)
        
        if login_response.get('status') != 'success':
            st.error(f"Login failed: {login_response.get('message', 'Unknown error')}")
            return None
        
        request_token = login_response.get('data', {}).get('request_token')
        if not request_token:
            st.error("Failed to get request_token from login response")
            return None
        
        # Step 2: Generate access token
        # For Type A: generate_session(api_key, request_token, checksum)
        # checksum is typically the OTP or a pre-generated checksum from mStock portal
        if otp:
            gen_response = client.generate_session(api_key, request_token, otp)
        else:
            # If no OTP provided, try with empty checksum (might work if 2FA is disabled)
            gen_response = client.generate_session(api_key, request_token, "")
        
        if gen_response.get('status') != 'success':
            st.error(f"Session generation failed: {gen_response.get('message', 'Unknown error')}")
            return None
        
        st.success("✅ Authentication successful!")
        return client
        
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

def get_margin_data(client, symbols: list, capital: float = None):
    """
    For each stock, fetch:
    - Current price (LTP)
    - Margin required for 1 share (MIS / intraday)
    - Calculate leverage, buying power, and max quantity
    """
    if client is None:
        return [], 0
    
    # If capital not provided, fetch from API
    if capital is None:
        try:
            fund_summary = client.get_fund_summary()
            if fund_summary and fund_summary.get('data'):
                capital = float(fund_summary['data'][0].get('MTF_AVAILABLE_BALANCE', 10000))
            else:
                capital = 10000.0
        except:
            capital = 10000.0
    
    results = []
    
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue
            
        try:
            # Get current price (LTP)
            # get_ltp expects list of symbols with exchange prefix
            ltp_response = client.get_ltp([f"NSE:{sym}"])
            
            if not ltp_response or ltp_response.get('status') != 'success':
                results.append({
                    'Symbol': sym,
                    'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': f'❌ Price fetch failed'
                })
                continue
            
            # Extract price from response
            price_data = ltp_response.get('data', {})
            price = float(price_data.get(f'NSE:{sym}', {}).get('ltp', 0))
            
            if price == 0:
                results.append({
                    'Symbol': sym,
                    'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': f'❌ No price data'
                })
                continue
            
            # Calculate margin for 1 share (MIS / Intraday)
            # calculate_order_margin(exchange, symbol, transaction_type, product_type, 
            #                        order_type, quantity, price, trigger_price)
            margin_response = client.calculate_order_margin(
                exchange="NSE",
                trading_symbol=sym,
                transaction_type="BUY",
                product_type="MIS",      # Intraday
                order_type="MARKET",
                quantity="1",
                price="0",
                trigger_price="0"
            )
            
            if not margin_response or margin_response.get('status') != 'success':
                results.append({
                    'Symbol': sym,
                    'Price (₹)': round(price, 2),
                    'Margin/Share (₹)': 'Error',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': f'❌ Margin calc failed'
                })
                continue
            
            margin_per_share = float(margin_response.get('data', {}).get('total', 0))
            
            if margin_per_share == 0:
                results.append({
                    'Symbol': sym,
                    'Price (₹)': round(price, 2),
                    'Margin/Share (₹)': 'Error',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': f'❌ Zero margin'
                })
                continue
            
            # Calculate derived values
            leverage = price / margin_per_share
            buying_power = capital * leverage
            max_qty = int(buying_power / price)
            
            results.append({
                'Symbol': sym,
                'Price (₹)': round(price, 2),
                'Margin/Share (₹)': round(margin_per_share, 2),
                'Leverage (x)': round(leverage, 1),
                'Buying Power (₹)': round(buying_power, 2),
                'Max Qty': max_qty,
                'Status': '✅ Ready'
            })
            
        except Exception as e:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': f'❌ {str(e)[:40]}'
            })
    
    return results, capital

# ================================================================
# 4. STREAMLIT UI
# ================================================================
st.title("🚀 Live Margin Calculator")
st.markdown("Get real-time margin, leverage, and max quantity for any stock")

# --- Sidebar: Authentication ---
with st.sidebar:
    st.header("🔐 Authentication")
    
    # Show SDK status
    if MSTOCK_SDK_AVAILABLE:
        st.success("✅ mStock SDK loaded")
    else:
        st.error("❌ mStock SDK not installed")
        st.code("pip install mStock-TradingApi-A", language="bash")
        st.stop()
    
    # Credentials input
    api_key = st.text_input("API Key", type="password", 
                            help="Generate from mStock dashboard → Products → Trading APIs")
    user_id = st.text_input("User ID", help="Your mStock trading username")
    password = st.text_input("Password", type="password", help="Your mStock trading password")
    otp = st.text_input("OTP / Checksum (if 2FA enabled)", type="password",
                        help="OTP received on registered mobile or checksum from mStock portal")
    
    auth_btn = st.button("🔑 Authenticate", type="primary")
    
    if auth_btn:
        if not api_key or not user_id or not password:
            st.error("Please fill in API Key, User ID, and Password")
        else:
            with st.spinner("Authenticating with mStock..."):
                client = authenticate_mstock(api_key, user_id, password, otp if otp else None)
                if client:
                    st.session_state['mstock_client'] = client
                    st.session_state['authenticated'] = True
                    st.success("✅ Connected!")
    
    st.markdown("---")
    
    # --- Stock Selection ---
    st.header("📊 Stock Selection")
    
    # Default stock list (from your screenshot)
    default_stocks = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    
    stock_input = st.text_area(
        "Enter stock symbols (comma or newline separated):",
        value=default_stocks,
        height=120,
        help="Enter NSE stock symbols. Example: TCS, INFY, RELIANCE"
    )
    
    fetch_btn = st.button("🔄 Fetch Margins", type="primary")

# --- Main Area ---
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📈 Margin & Leverage")
with col2:
    capital_placeholder = st.empty()

# Check authentication status
if not st.session_state.get('authenticated', False):
    st.info("👈 Please authenticate first by entering your credentials and clicking 'Authenticate'")
    # Show empty table
    st.dataframe(pd.DataFrame(columns=['Symbol', 'Price (₹)', 'Margin/Share (₹)', 
                                        'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status']))
    st.stop()

client = st.session_state.get('mstock_client')

if fetch_btn and client:
    # Parse stock symbols
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    
    if not symbols:
        st.warning("Please enter at least one stock symbol.")
        st.stop()
    
    with st.spinner("Fetching real-time margin data..."):
        data, capital = get_margin_data(client, symbols)
    
    # Update capital display
    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")
    
    # Create and display DataFrame
    df = pd.DataFrame(data)
    
    # Style the dataframe
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", width="small"),
            "Price (₹)": st.column_config.NumberColumn("Price", format="₹%.2f"),
            "Margin/Share (₹)": st.column_config.NumberColumn("Margin/Share", format="₹%.2f"),
            "Leverage (x)": st.column_config.NumberColumn("Leverage", format="%.1fx"),
            "Buying Power (₹)": st.column_config.NumberColumn("Buying Power", format="₹%.2f"),
            "Max Qty": st.column_config.NumberColumn("Max Qty", format="%d"),
            "Status": st.column_config.TextColumn("Status"),
        },
        hide_index=True,
    )
    
    # --- Order Simulation ---
    st.markdown("---")
    st.subheader("📦 Place Order (Simulation)")
    
    # Filter only ready stocks
    ready_stocks = df[df['Status'] == '✅ Ready']
    
    if not ready_stocks.empty:
        for idx, row in ready_stocks.iterrows():
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            with col1:
                st.write(f"**{row['Symbol']}**")
            with col2:
                st.write(f"₹{row['Price (₹)']:.2f}")
            with col3:
                qty = st.number_input(
                    "Qty",
                    min_value=1,
                    max_value=row['Max Qty'],
                    value=min(row['Max Qty'], 10),
                    key=f"qty_{idx}_{row['Symbol']}"
                )
            with col4:
                if st.button(f"Buy {row['Symbol']}", key=f"buy_{idx}_{row['Symbol']}"):
                    st.success(f"✅ Order placed: {row['Symbol']} - {qty} shares at ₹{row['Price (₹)']:.2f} (Simulation)")
    else:
        st.info("No stocks with 'Ready' status to place orders.")

elif fetch_btn and not client:
    st.error("❌ Not authenticated. Please authenticate first.")

# --- Footer ---
st.markdown("---")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("Powered by mStock Trading API | Data refreshes on each fetch")
