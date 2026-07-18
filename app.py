import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# ================================================================
# 1. PAGE CONFIG – MUST BE FIRST
# ================================================================
st.set_page_config(page_title="Margin Calculator", layout="wide")

# ================================================================
# 2. SDK SETUP – Type B
# ================================================================
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ================================================================
# 3. AUTHENTICATION FUNCTION – TYPE B
# ================================================================
def authenticate_type_b(api_key: str, user_id: str, password: str, otp: str):
    """
    Authenticate with mStock using Type-B API.
    Returns JWT token on success, None on failure.
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed. Run: pip install mStock-TradingApi-B")
        return None

    try:
        client = MConnectB()

        # Step 1: Login – sends OTP to registered mobile
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown error')}")
            return None

        # Step 2: Get request_token from login response
        request_token = login_data.get('data', {}).get('request_token')
        if not request_token:
            st.error("No request_token received. Please check your credentials.")
            return None

        # Step 3: Generate session using OTP
        gen_response = client.generate_session(api_key, request_token, otp)
        gen_data = gen_response.json()

        if not gen_data.get('status', False):
            st.error(f"Session generation failed: {gen_data.get('message', 'Unknown error')}")
            return None

        # Step 4: Extract JWT token from session response
        jwt_token = gen_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received.")
            return None

        st.success("✅ Authentication successful!")
        return jwt_token

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

# ================================================================
# 4. GET INSTRUMENT MASTER & BUILD SYMBOL→TOKEN MAPPING
# ================================================================
def get_symbol_token_map(jwt_token: str):
    """
    Fetch instrument master and build a mapping from symbol name to token.
    Uses raw HTTP with the JWT token.
    """
    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    symbol_to_token = {}

    try:
        # Try /market/instruments endpoint
        resp = requests.get(f"{base_url}/market/instruments", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status'):
                for item in data.get('data', []):
                    symbol = item.get('symbol') or item.get('trading_symbol')
                    token = item.get('token') or item.get('instrument_token')
                    if symbol and token:
                        symbol_to_token[symbol.upper()] = str(token)
                return symbol_to_token
    except Exception as e:
        st.write(f"Error fetching instrument master: {e}")

    # Fallback: Try /instruments endpoint
    try:
        resp = requests.get(f"{base_url}/instruments", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status'):
                for item in data.get('data', []):
                    symbol = item.get('symbol') or item.get('trading_symbol')
                    token = item.get('token') or item.get('instrument_token')
                    if symbol and token:
                        symbol_to_token[symbol.upper()] = str(token)
                return symbol_to_token
    except Exception as e:
        st.write(f"Error fetching instruments (fallback): {e}")

    return symbol_to_token

# ================================================================
# 5. MARGIN & PRICE FETCH FUNCTION
# ================================================================
def get_margin_data(jwt_token: str, symbols: list):
    """
    Fetch LTP and margin for each symbol using raw HTTP requests.
    """
    if not jwt_token:
        return [], 0.0

    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # 1. Build symbol → token mapping
    symbol_to_token = get_symbol_token_map(jwt_token)

    if not symbol_to_token:
        st.error("❌ Could not fetch instrument mapping. Please check API connectivity.")
        # Return empty results with correct column structure
        return [], 0.0

    # 2. Get available capital
    capital = 10000.0
    try:
        resp = requests.get(f"{base_url}/user/fundsummary", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status'):
                capital = float(data['data'][0]['MTF_AVAILABLE_BALANCE'])
    except Exception as e:
        st.write(f"Error fetching capital: {e}")

    results = []

    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue

        # 3. Get token for this symbol
        token = symbol_to_token.get(sym)
        if not token:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': f'❌ Token not found for {sym}'
            })
            continue

        # 4. Get LTP using token (CORRECT way)
        price = 0
        try:
            url_quote = f"{base_url}/market/quote?mode=OHLC&exchange=NSE&token={token}"
            resp = requests.get(url_quote, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    ohlc = data.get('data', {}).get('OHLC', {})
                    # The key is the token itself
                    price_data = ohlc.get(token)
                    if price_data:
                        price = float(price_data.get('ltp', 0))
        except Exception as e:
            st.write(f"Error fetching LTP for {sym}: {e}")

        if price == 0:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': '❌ LTP fetch failed'
            })
            continue

        # 5. Get margin (MIS) – using token
        margin_per_share = 0
        try:
            # Using the correct margin endpoint with orders array
            margin_payload = {
                "orders": [{
                    "product_type": "MIS",
                    "transaction_type": "BUY",
                    "quantity": "1",
                    "price": "0",
                    "exchange": "NSE",
                    "symbol_name": sym,
                    "token": token,
                    "trigger_price": 0
                }]
            }
            resp = requests.post(f"{base_url}/margins/orders", json=margin_payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    margin_per_share = float(data.get('data', {}).get('total', 0))
        except Exception as e:
            st.write(f"Error fetching margin for {sym}: {e}")

        if margin_per_share == 0:
            results.append({
                'Symbol': sym,
                'Price (₹)': round(price, 2),
                'Margin/Share (₹)': 'Error',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': '❌ Margin calc failed'
            })
            continue

        # 6. Calculate derived values
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

    return results, capital

# ================================================================
# 6. STREAMLIT UI
# ================================================================
st.title("🚀 Live Margin Calculator")
st.markdown("Get real‑time margin, leverage, and maximum quantity for any stock")

# --- Sidebar: Authentication ---
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
                token = authenticate_type_b(api_key, user_id, password, otp)
                if token:
                    st.session_state['jwt_token'] = token
                    st.session_state['authenticated'] = True
                    st.success("✅ Connected!")

    st.markdown("---")

    # --- Stock Selection ---
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
    # Show empty table with correct columns
    st.dataframe(pd.DataFrame(columns=[
        'Symbol', 'Price (₹)', 'Margin/Share (₹)',
        'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
    ]))
    st.stop()

jwt_token = st.session_state.get('jwt_token')
if not jwt_token:
    st.warning("⚠️ No JWT token found. Please authenticate again.")
    st.stop()

capital_placeholder = st.empty()

if fetch_btn:
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    if not symbols:
        st.warning("Please enter at least one stock symbol.")
        st.stop()

    with st.spinner("Fetching real‑time margin data..."):
        data, capital = get_margin_data(jwt_token, symbols)

    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")

    if not data:
        st.warning("No data returned. Please check your symbols and try again.")
        st.dataframe(pd.DataFrame(columns=[
            'Symbol', 'Price (₹)', 'Margin/Share (₹)',
            'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
        ]))
    else:
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
        ready_stocks = df[df['Status'] == '✅ Ready']
        if not ready_stocks.empty:
            st.markdown("---")
            st.subheader("📦 Place Order (Simulation)")

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
