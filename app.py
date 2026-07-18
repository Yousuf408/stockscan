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
        setattr(client, '_jwt_token', jwt_token)
        return False

# ------------------- Authentication -------------------
def authenticate_type_b(api_key, user_id, password, otp):
    """
    Type-B authentication using SDK.
    Returns client and JWT token.
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None, None

    try:
        client = MConnectB()
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        st.write("🔍 Login response:", login_data)  # Debug – remove later

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None, None

        jwt_token = login_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received. Check credentials.")
            return None, None

        set_client_token(client, jwt_token)

        st.success("✅ Authentication successful (JWT set)!")
        return client, jwt_token

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None, None

# ------------------- Instrument Master (Symbol → Token) -------------------
def get_symbol_token_map(jwt_token):
    """
    Fetch the master instrument list from the correct endpoint
    and build a dictionary mapping symbol name (e.g. 'GABRIEL') to numeric token.
    """
    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    symbol_to_token = {}

    # Correct endpoint
    endpoint = "/instruments/OpenAPIScripMaster"
    try:
        resp = requests.get(f"{base_url}{endpoint}", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            # The response may be a list directly or under a 'data' key
            instruments = data.get('data', []) if isinstance(data, dict) else data

            for item in instruments:
                # Adjust these keys based on actual response structure
                symbol = item.get('symbol') or item.get('trading_symbol')
                token = item.get('token') or item.get('instrument_token')
                if symbol and token:
                    symbol_to_token[symbol.upper()] = str(token)

            if symbol_to_token:
                st.success(f"✅ Loaded {len(symbol_to_token)} instruments from master list.")
            else:
                st.warning("⚠️ Master list fetched but no symbols found. Check response structure.")
        else:
            st.error(f"❌ Failed to fetch master list. Status: {resp.status_code}")
    except Exception as e:
        st.error(f"❌ Error fetching instrument master: {e}")

    return symbol_to_token

# ------------------- Margin & Price Fetch (Using Tokens) -------------------
def get_margin_data(client, jwt_token, symbols):
    """
    Fetch LTP and margin using numeric tokens obtained from the master list.
    Tries SDK first, falls back to raw HTTP if needed.
    """
    if client is None and not jwt_token:
        return [], 0.0

    # 1. Get symbol → token mapping
    symbol_to_token = get_symbol_token_map(jwt_token)
    if not symbol_to_token:
        st.error("❌ Could not obtain instrument mapping. Aborting data fetch.")
        return [], 0.0

    # 2. Get available capital
    capital = 10000.0
    try:
        if client:
            fund_resp = client.get_fund_summary()
            fund_data = fund_resp.json()
            if fund_data.get('status', False):
                capital = float(fund_data['data'][0]['MTF_AVAILABLE_BALANCE'])
        else:
            headers = {'Authorization': f'Bearer {jwt_token}'}
            resp = requests.get('https://api.mstock.trade/openapi/typeb/user/fundsummary', headers=headers)
            fund_data = resp.json()
            if fund_data.get('status', False):
                capital = float(fund_data['data'][0]['MTF_AVAILABLE_BALANCE'])
    except:
        pass

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

        # 4. Get LTP using token
        price = 0
        try:
            if client:
                # SDK method – may require token instead of symbol
                # Some SDK versions support get_market_quote with token
                # If not, fallback to raw
                try:
                    ltp_resp = client.get_market_quote("OHLC", {"NSE": [token]})
                    ltp_data = ltp_resp.json()
                except:
                    ltp_data = {}
            else:
                # Raw HTTP – use token
                headers = {'Authorization': f'Bearer {jwt_token}'}
                url_quote = f"https://api.mstock.trade/openapi/typeb/market/quote?mode=OHLC&exchange=NSE&token={token}"
                resp = requests.get(url_quote, headers=headers)
                ltp_data = resp.json() if resp.status_code == 200 else {}
        except:
            ltp_data = {}

        if ltp_data.get('status', False):
            ohlc = ltp_data.get('data', {}).get('OHLC', {})
            # The key is the token itself
            price_data = ohlc.get(token)
            if price_data:
                price = float(price_data.get('ltp', 0))

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

        # 5. Get margin (MIS) using token
        margin_per_share = 0
        try:
            if client:
                # SDK may have a method that accepts token
                try:
                    margin_resp = client.calculate_order_margin(
                        "MIS", "BUY", "1", "0", "NSE", sym, token, "0"
                    )
                    margin_data = margin_resp.json()
                except:
                    margin_data = {}
            else:
                headers = {'Authorization': f'Bearer {jwt_token}', 'Content-Type': 'application/json'}
                payload = {
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
                resp = requests.post(
                    "https://api.mstock.trade/openapi/typeb/margins/orders",
                    json=payload,
                    headers=headers
                )
                margin_data = resp.json() if resp.status_code == 200 else {}
        except:
            margin_data = {}

        if margin_data.get('status', False):
            margin_per_share = float(margin_data.get('data', {}).get('total', 0))

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

        # 6. Calculate
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
    st.info("Please authenticate first")
    st.stop()

client = st.session_state.get('mstock_client')
jwt_token = st.session_state.get('jwt_token')

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    with st.spinner("Fetching data..."):
        data, capital = get_margin_data(client, jwt_token, symbols)

    st.metric("💰 Available Capital", f"₹{capital:,.2f}")
    if not data:
        st.warning("No data returned. Check symbols or connectivity.")
        df = pd.DataFrame(columns=[
            'Symbol', 'Price (₹)', 'Margin/Share (₹)',
            'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
        ])
    else:
        df = pd.DataFrame(data)

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Simulated Buy
    if 'Status' in df.columns:
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
                        st.success(f"Simulated order: {row['Symbol']} - {qty} shares")

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
