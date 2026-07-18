import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from pathlib import Path
import json

st.set_page_config(page_title="Margin Calculator v2", layout="wide")

# ------------------- SDK Setup -------------------
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ------------------- Helper: Load Cached Symbols -------------------
def load_symbol_tokens(cache_file='mstock_symbols.json'):
    """Load symbol→token mapping from cache"""
    try:
        cache_path = Path(cache_file)
        if cache_path.exists():
            symbol_map = json.loads(cache_path.read_text())
            return symbol_map
        else:
            return None
    except Exception as e:
        st.error(f"❌ Cache load error: {str(e)}")
        return None


def get_token_for_symbol(symbol, symbol_map):
    """Get token for a symbol from cache"""
    symbol = symbol.strip().upper()
    if symbol_map and symbol in symbol_map:
        return symbol_map[symbol].get('token')
    return None


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
    Type-B authentication
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None, None

    try:
        client = MConnectB()
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None, None

        jwt_token = login_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received. Check credentials.")
            return None, None

        set_client_token(client, jwt_token)
        st.success("✅ Authentication successful!")
        return client, jwt_token

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None, None

# ------------------- Margin & Price Fetch (WITH TOKENS) -------------------
def get_margin_data(client, jwt_token, api_key, symbols, symbol_map):
    """
    Fetch price and margin using tokens from symbol_map
    """
    if client is None and not jwt_token:
        return [], 0.0

    # Get capital
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

        # ✅ KEY CHANGE: Get token from cached symbol_map
        token = get_token_for_symbol(sym, symbol_map)
        
        if not token:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': f'❌ Token not found in cache'
            })
            st.warning(f"⚠️ {sym}: Token not found. Download instrument master first!")
            continue

        price = 0
        margin_per_share = 0

        # ---- Get LTP (using token) ----
        ltp_data = {}
        try:
            if client:
                # Use token for LTP query
                ltp_resp = client.get_market_quote("OHLC", {"NSE": [token]})
                ltp_data = ltp_resp.json()
                st.write(f"🔍 {sym} LTP response (SDK):", ltp_data)
            else:
                # Raw HTTP request with token
                headers = {
                    'X-Mirae-Version': '1',
                    'Authorization': f'Bearer {jwt_token}',
                    'X-PrivateKey': api_key,
                    'Content-Type': 'application/json'
                }
                payload = {
                    'mode': 'OHLC',
                    'exchangeTokens': {
                        'NSE': [token]
                    }
                }
                resp = requests.post(
                    'https://api.mstock.trade/openapi/typeb/instruments/quote',
                    json=payload,
                    headers=headers
                )
                ltp_data = resp.json()
                st.write(f"🔍 {sym} LTP response (HTTP):", ltp_data)
        except Exception as e:
            st.error(f"❌ {sym} LTP fetch error: {str(e)}")
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Network Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': f'❌ {str(e)}'
            })
            continue

        if ltp_data.get('status', False):
            fetched = ltp_data.get('data', {}).get('fetched', [])
            if fetched:
                price_data = fetched[0]
                price = float(price_data.get('ltp', 0))
                st.success(f"✅ {sym} LTP: ₹{price}")
        else:
            error_msg = ltp_data.get('message', 'Unknown error')
            st.warning(f"⚠️ {sym}: {error_msg}")

        if price == 0:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': '❌ LTP not found'
            })
            continue

        # ---- Get Margin (using token) ----
        margin_data = {}
        try:
            if client:
                # Use token for margin calculation
                margin_resp = client.calculate_order_margin(
                    "MIS", "BUY", "1", "0", "NSE", token, "", "0"
                )
                margin_data = margin_resp.json()
                st.write(f"🔍 {sym} Margin response (SDK):", margin_data)
            else:
                # Raw HTTP request with token
                headers = {
                    'X-Mirae-Version': '1',
                    'Authorization': f'Bearer {jwt_token}',
                    'X-PrivateKey': api_key,
                    'Content-Type': 'application/json'
                }
                payload = {
                    'orders': [
                        {
                            'product_type': 'MIS',
                            'transaction_type': 'BUY',
                            'quantity': '1',
                            'price': '0',
                            'exchange': 'NSE',
                            'symbol_name': sym,
                            'token': token,
                            'trigger_price': '0'
                        }
                    ]
                }
                resp = requests.post(
                    'https://api.mstock.trade/openapi/typeb/margins/orders',
                    json=payload,
                    headers=headers
                )
                margin_data = resp.json()
                st.write(f"🔍 {sym} Margin response (HTTP):", margin_data)
        except Exception as e:
            st.error(f"❌ {sym} Margin calc error: {str(e)}")

        if margin_data.get('status', False):
            # Parse margin from response
            charges = margin_data.get('data', {}).get('charges', [])
            if charges:
                margin_per_share = float(charges[0].get('total_charges', 0))
                st.success(f"✅ {sym} Margin: ₹{margin_per_share}")
        else:
            error_msg = margin_data.get('message', 'Unknown error')
            st.warning(f"⚠️ {sym}: Margin API - {error_msg}")

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
st.title("🚀 Live Margin Calculator v2 (With Tokens)")

# Load symbol cache
symbol_map = load_symbol_tokens('mstock_symbols.json')

if not symbol_map:
    st.error("❌ Symbol cache not found!")
    st.info("📌 First, download instrument master from the test page")
    st.stop()
else:
    st.success(f"✅ Symbol cache loaded: {len(symbol_map)} symbols")

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
    otp = st.text_input("OTP (6-digit)", type="password")

    if st.button("🔑 Authenticate"):
        if not all([api_key, user_id, password]):
            st.error("API Key, User ID, and Password are required")
        else:
            with st.spinner("Authenticating..."):
                client, token = authenticate_type_b(api_key, user_id, password, otp)
                if client or token:
                    st.session_state['mstock_client'] = client
                    st.session_state['jwt_token'] = token
                    st.session_state['api_key'] = api_key
                    st.session_state['authenticated'] = True

    st.markdown("---")
    st.header("📊 Stocks")
    default = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC, RUBICON"
    stocks_input = st.text_area("Symbols (comma/newline)", value=default, height=120)
    fetch_btn = st.button("🔄 Fetch Margins")

# Main area
if not st.session_state.get('authenticated'):
    st.info("🔐 Please authenticate first using the sidebar")
    st.stop()

client = st.session_state.get('mstock_client')
jwt_token = st.session_state.get('jwt_token')
api_key = st.session_state.get('api_key')

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("⚠️ No symbols entered")
        st.stop()

    with st.spinner("Fetching data..."):
        data, capital = get_margin_data(client, jwt_token, api_key, symbols, symbol_map)

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
