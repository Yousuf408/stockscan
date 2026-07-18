import streamlit as st
import pandas as pd
from datetime import datetime

# ============================================================
# 1. PAGE CONFIG – MUST BE FIRST
# ============================================================
st.set_page_config(page_title="Margin Calculator", layout="wide")

# ============================================================
# 2. SDK SETUP – Type B
# ============================================================
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ============================================================
# 3. AUTHENTICATION FUNCTION – TYPE B (FIXED)
# ============================================================
def authenticate_type_b(api_key: str, user_id: str, password: str, otp: str):
    """
    Authenticate with mStock using Type-B API.
    
    Type-B login response uses "status": true/false, not "success".
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed. Run: pip install mStock-TradingApi-B")
        return None

    try:
        client = MConnectB()

        # Step 1: Login – sends OTP to registered mobile
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        # Debug – remove after testing
        st.write("🔍 Login response:", login_data)

        # ✅ FIX: Type B uses "status" (boolean), not "success"
        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown error')}")
            return None

        # Get request_token from data
        request_token = login_data.get('data', {}).get('request_token')
        
        # If request_token is missing, the SDK might already be authenticated
        if not request_token:
            st.warning("No request_token received. Testing if SDK is already authenticated...")
            try:
                test_resp = client.get_fund_summary()
                test_data = test_resp.json()
                if test_data.get('status', False):
                    st.success("✅ Already authenticated (using stored token)!")
                    return client
            except:
                st.error("No request_token and test call failed. Please check your credentials.")
                return None

        # Step 2: Generate session using OTP (if request_token was received)
        if request_token:
            gen_response = client.generate_session(api_key, request_token, otp)
            gen_data = gen_response.json()
            st.write("🔍 Session response:", gen_data)

            # ✅ FIX: Check "status" (boolean), not "success"
            if not gen_data.get('status', False):
                st.error(f"Session generation failed: {gen_data.get('message', 'Unknown error')}")
                return None

        st.success("✅ Authentication successful!")
        return client

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

# ============================================================
# 4. MARGIN CALCULATION FUNCTION (UPDATED FOR TYPE B)
# ============================================================
def get_margin_data(client, symbols: list):
    """Fetch price, margin, leverage, and max quantity for each symbol."""
    if client is None:
        return [], 0.0

    # Get available capital
    try:
        fund_resp = client.get_fund_summary()
        fund_data = fund_resp.json()
        # Type B uses "status" here too
        if fund_data.get('status', False):
            capital = float(fund_data['data'][0]['MTF_AVAILABLE_BALANCE'])
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
            # Get LTP – Type B uses get_market_quote
            ltp_resp = client.get_market_quote("OHLC", {"NSE": [sym]})
            ltp_data = ltp_resp.json()

            if not ltp_data.get('status', False):
                results.append({
                    'Symbol': sym, 'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                    'Buying Power (₹)': '-', 'Max Qty': '-',
                    'Status': '❌ LTP fetch failed'
                })
                continue

            # Extract price – structure may be data.OHLC[symbol].ltp
            price_data = ltp_data.get('data', {}).get('OHLC', {}).get(sym, {})
            price = float(price_data.get('ltp', 0))

            if price == 0:
                results.append({
                    'Symbol': sym, 'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                    'Buying Power (₹)': '-', 'Max Qty': '-',
                    'Status': '❌ Price is zero'
                })
                continue

            # Calculate margin for 1 share (MIS / Intraday)
            margin_resp = client.calculate_order_margin(
                "MIS",          # product_type
                "BUY",          # transaction_type
                "1",            # quantity
                "0",            # price (0 for market)
                "NSE",          # exchange
                sym,            # trading_symbol
                "",             # symbol_token (optional)
                "0"             # trigger_price
            )
            margin_data = margin_resp.json()

            if not margin_data.get('status', False):
                results.append({
                    'Symbol': sym, 'Price (₹)': round(price, 2),
                    'Margin/Share (₹)': 'Error', 'Leverage (x)': '-',
                    'Buying Power (₹)': '-', 'Max Qty': '-',
                    'Status': '❌ Margin calc failed'
                })
                continue

            margin_per_share = float(margin_data.get('data', {}).get('total', 0))
            if margin_per_share == 0:
                results.append({
                    'Symbol': sym, 'Price (₹)': round(price, 2),
                    'Margin/Share (₹)': 'Error', 'Leverage (x)': '-',
                    'Buying Power (₹)': '-', 'Max Qty': '-',
                    'Status': '❌ Zero margin'
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

# ============================================================
# 5. STREAMLIT UI
# ============================================================
st.title("🚀 Live Margin Calculator")
st.markdown("Get real‑time margin, leverage, and maximum quantity for any stock")

# --- Sidebar ---
with st.sidebar:
    st.header("🔐 Authentication")

    if SDK_AVAILABLE:
        st.success("✅ mStock Type-B SDK loaded")
    else:
        st.error("❌ Type-B SDK not installed")
        st.code("pip install mStock-TradingApi-B", language="bash")
        st.stop()

    api_key = st.text_input("API Key", type="password",
                            help="Generated from mStock dashboard → Products → Trading APIs (Type B)")
    user_id = st.text_input("User ID", help="Your mStock trading username")
    password = st.text_input("Password", type="password", help="Your mStock trading password")
    otp = st.text_input("OTP (6-digit from authenticator app)", type="password",
                        help="Generate from Google Authenticator / Authy using your TOTP secret")

    if st.button("🔑 Authenticate", type="primary"):
        if not api_key or not user_id or not password or not otp:
            st.error("Please fill in ALL fields including OTP")
        else:
            with st.spinner("Authenticating with mStock Type-B..."):
                client = authenticate_type_b(api_key, user_id, password, otp)
                if client:
                    st.session_state['mstock_client'] = client
                    st.session_state['authenticated'] = True
                    st.success("✅ Connected!")

    st.markdown("---")

    st.header("📊 Stock Selection")
    default_stocks = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stock_input = st.text_area(
        "Enter symbols (comma or newline separated):",
        value=default_stocks,
        height=120,
        help="Example: TCS, INFY, RELIANCE"
    )

    fetch_btn = st.button("🔄 Fetch Margins", type="primary")

# --- Main Area ---
if not st.session_state.get('authenticated', False):
    st.info("👈 Please authenticate first by entering your credentials and OTP, then click 'Authenticate'")
    st.dataframe(pd.DataFrame(columns=[
        'Symbol', 'Price (₹)', 'Margin/Share (₹)',
        'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
    ]))
    st.stop()

client = st.session_state.get('mstock_client')
if not client:
    st.warning("⚠️ Client not available. Please authenticate again.")
    st.stop()

capital_placeholder = st.empty()

if fetch_btn:
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    if not symbols:
        st.warning("Please enter at least one stock symbol.")
        st.stop()

    with st.spinner("Fetching real‑time margin data..."):
        data, capital = get_margin_data(client, symbols)

    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")

    df = pd.DataFrame(data)

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

    # --- Simulated Buy ---
    st.markdown("---")
    st.subheader("📦 Place Order (Simulation)")

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

st.markdown("---")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("Powered by mStock Type-B Trading API")
