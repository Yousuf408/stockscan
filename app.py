import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="Margin Calculator", layout="wide")

# ------------------- SDK Setup -------------------
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ------------------- Helper: set token on client -------------------
def set_client_token(client, jwt_token):
    """Try multiple ways to set the JWT token on the client."""
    if hasattr(client, 'set_jwt_token'):
        client.set_jwt_token(jwt_token)
        return True
    elif hasattr(client, 'set_access_token'):
        client.set_access_token(jwt_token)
        return True
    elif hasattr(client, 'set_bearer_token'):
        client.set_bearer_token(jwt_token)
        return True
    elif hasattr(client, 'headers'):
        client.headers['Authorization'] = f'Bearer {jwt_token}'
        return True
    else:
        # Fallback: store token in a private attribute
        setattr(client, '_jwt_token', jwt_token)
        return False

# ------------------- Authentication -------------------
def authenticate_type_b(api_key, user_id, password, otp):
    """
    Type-B authentication:
    - login() returns a JWT directly (no request_token)
    - We extract jwtToken and set it on the client.
    - No need for generate_session().
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None, None

    try:
        client = MConnectB()

        # 1. Login – sends OTP to phone (if 2FA is enabled)
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        # Debug (remove later)
        st.write("🔍 Login response:", login_data)

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None, None

        # 2. Extract JWT token (no request_token needed)
        jwt_token = login_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received. Check credentials.")
            return None, None

        # 3. Set token on the client
        set_client_token(client, jwt_token)

        st.success("✅ Authentication successful (JWT set)!")
        return client, jwt_token

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None, None

# ------------------- Margin & Price Fetch -------------------
def get_margin_data(client, jwt_token, symbols):
    """
    Fetch price and margin using either SDK or raw requests.
    KEY FIX: SDK dict uses raw symbol (GABRIEL), HTTP uses NSE: prefix (NSE:GABRIEL)
    """
    if client is None and not jwt_token:
        return [], 0.0

    # Get capital – try SDK first, fallback to raw
    capital = 10000.0
    try:
        if client:
            fund_resp = client.get_fund_summary()
            fund_data = fund_resp.json()
            if fund_data.get('status', False):
                capital = float(fund_data['data'][0]['MTF_AVAILABLE_BALANCE'])
                st.success(f"✅ Capital fetched: ₹{capital:,.2f}")
    except Exception as e:
        st.warning(f"⚠️ Fund fetch failed: {str(e)}")

    results = []
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue

        # ✅ SYMBOL FORMAT FIX:
        # SDK dict wants raw symbol: "GABRIEL"
        # HTTP URL wants NSE: prefix: "NSE:GABRIEL"
        api_symbol_for_sdk = sym
        api_symbol_for_http = f"NSE:{sym}"
        
        price = 0
        margin_per_share = 0

        # ---- Get LTP ----
        ltp_data = {}
        try:
            if client:
                # ✅ SDK: Use raw symbol in dict
                ltp_resp = client.get_market_quote("OHLC", {"NSE": [api_symbol_for_sdk]})
                ltp_data = ltp_resp.json()
                st.write(f"🔍 {sym} LTP response (SDK):", ltp_data)
            else:
                # ✅ HTTP: Use NSE: prefix in URL
                headers = {'Authorization': f'Bearer {jwt_token}'}
                resp = requests.get(
                    f'https://api.mstock.trade/openapi/typeb/market/quote?mode=OHLC&exchange=NSE&symbol={api_symbol_for_http}',
                    headers=headers
                )
                ltp_data = resp.json()
                st.write(f"🔍 {sym} LTP response (HTTP):", ltp_data)
        except Exception as e:
            st.error(f"❌ {sym} LTP fetch error: {str(e)}")
            results.append({
                'Symbol': sym, 'Price (₹)': 'Network Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': f'❌ {str(e)}'
            })
            continue

        if ltp_data.get('status', False):
            ohlc = ltp_data.get('data', {}).get('OHLC', {})
            # Try multiple key formats in response
            price_data = ohlc.get(api_symbol_for_sdk) or ohlc.get(api_symbol_for_http) or ohlc.get(sym)
            if price_data:
                price = float(price_data.get('ltp', 0))
                st.success(f"✅ {sym} LTP: ₹{price}")
        else:
            error_msg = ltp_data.get('message', 'Unknown error')
            st.warning(f"⚠️ {sym}: API returned status=False: {error_msg}")

        if price == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': 'Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ LTP not found in response'
            })
            continue

        # ---- Get Margin (MIS) ----
        margin_data = {}
        try:
            if client:
                # ✅ SDK: Use raw symbol
                margin_resp = client.calculate_order_margin(
                    "MIS", "BUY", "1", "0", "NSE", api_symbol_for_sdk, "", "0"
                )
                margin_data = margin_resp.json()
                st.write(f"🔍 {sym} Margin response (SDK):", margin_data)
            else:
                # ✅ HTTP: Use NSE: prefix
                headers = {'Authorization': f'Bearer {jwt_token}'}
                url = f'https://api.mstock.trade/openapi/typeb/order/margin'
                payload = {
                    "product_type": "MIS",
                    "transaction_type": "BUY",
                    "quantity": "1",
                    "price": "0",
                    "exchange": "NSE",
                    "trading_symbol": api_symbol_for_http,
                    "symbol_token": "",
                    "trigger_price": "0"
                }
                resp = requests.post(url, json=payload, headers=headers)
                margin_data = resp.json()
                st.write(f"🔍 {sym} Margin response (HTTP):", margin_data)
        except Exception as e:
            st.error(f"❌ {sym} Margin calc error: {str(e)}")

        if margin_data.get('status', False):
            margin_per_share = float(margin_data.get('data', {}).get('total', 0))
            st.success(f"✅ {sym} Margin/Share: ₹{margin_per_share}")
        else:
            error_msg = margin_data.get('message', 'Unknown error')
            st.warning(f"⚠️ {sym}: Margin API returned status=False: {error_msg}")

        if margin_per_share == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': round(price, 2),
                'Margin/Share (₹)': 'Error', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ Margin calc failed'
            })
            continue

        # ---- Calculate ----
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

# ------------------- Streamlit UI -------------------
st.title("🚀 Live Margin Calculator")

with st.sidebar:
    st.header("🔐 Authentication")
    if not SDK_AVAILABLE:
        st.error("❌ Type-B SDK not installed")
        st.code("pip install mStock-TradingApi-B")
        st.stop()
    else:
        st.success("✅ SDK loaded")

    api_key = st.text_input("API Key", type="password")
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type="password")
    otp = st.text_input("OTP (6-digit)", type="password", help="If 2FA enabled, enter the OTP received")

    if st.button("🔑 Authenticate"):
        if not all([api_key, user_id, password]):
            st.error("API Key, User ID, and Password are required")
        else:
            with st.spinner("Authenticating..."):
                client, token = authenticate_type_b(api_key, user_id, password, otp)
                if client or token:
                    st.session_state['mstock_client'] = client
                    st.session_state['jwt_token'] = token
                    st.session_state['authenticated'] = True

    st.markdown("---")
    st.header("📊 Stocks")
    default = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stocks_input = st.text_area("Symbols (comma/newline)", value=default, height=120)
    fetch_btn = st.button("🔄 Fetch Margins")

# Main area
if not st.session_state.get('authenticated'):
    st.info("🔐 Please authenticate first using the sidebar")
    st.stop()

client = st.session_state.get('mstock_client')
jwt_token = st.session_state.get('jwt_token')

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("⚠️ No symbols entered")
        st.stop()

    with st.spinner("Fetching data..."):
        data, capital = get_margin_data(client, jwt_token, symbols)

    st.metric("💰 Available Capital", f"₹{capital:,.2f}")
    
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Simulated Buy
        ready = df[df['Status'] == '✅ Ready']
        if not ready.empty:
            st.markdown("---")
            st.subheader("📦 Simulated Order")
            for idx, row in ready.iterrows():
                cols = st.columns([1, 1, 1, 2])
                with cols[0]:
                    st.write(f"**{row['Symbol']}**")
                with cols[1]:
                    st.write(f"₹{row['Price (₹)']:.2f}")
                with cols[2]:
                    qty = st.number_input("Qty", min_value=1, max_value=row['Max Qty'],
                                          value=min(row['Max Qty'], 10), key=f"qty_{idx}")
                with cols[3]:
                    if st.button(f"Buy {row['Symbol']}", key=f"buy_{idx}"):
                        st.success(f"Simulated order: {row['Symbol']} - {qty} shares @ ₹{row['Price (₹)']:.2f}")
    else:
        st.error("❌ No data fetched. Check errors above.")

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
