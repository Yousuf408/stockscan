import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="Margin Calculator", layout="wide")

# ================================================================
# 1. AUTHENTICATION – RAW HTTP (includes OTP)
# ================================================================
def authenticate(user_id: str, password: str, otp: str):
    """
    Authenticate with mStock Type‑B using raw HTTP.
    Sends OTP in the login payload.
    Returns JWT token on success, None on failure.
    """
    url = "https://api.mstock.trade/openapi/typeb/connect/login"
    headers = {"Content-Type": "application/json"}
    payload = {
        "clientcode": user_id,
        "password": password,
        "totp": otp,          # 6‑digit OTP from authenticator
        "state": ""
    }
    try:
        resp = requests.post(url, json=payload, headers=headers)
        data = resp.json()
        st.write("🔍 Login response:", data)  # Debug – remove later

        if data.get('status'):
            jwt_token = data.get('data', {}).get('jwtToken')
            if jwt_token:
                st.success("✅ Authentication successful!")
                return jwt_token
            else:
                st.error("Login successful but no JWT token received.")
        else:
            st.error(f"Login failed: {data.get('message', 'Unknown error')}")
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
    return None

# ================================================================
# 2. GET INSTRUMENT MASTER (SYMBOL → TOKEN MAPPING)
# ================================================================
def get_symbol_token_map(jwt_token: str):
    """Fetch instrument master and build symbol→token mapping."""
    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    symbol_to_token = {}

    # Try both endpoints
    for endpoint in ["/market/instruments", "/instruments"]:
        try:
            resp = requests.get(f"{base_url}{endpoint}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    for item in data.get('data', []):
                        symbol = item.get('symbol') or item.get('trading_symbol')
                        token = item.get('token') or item.get('instrument_token')
                        if symbol and token:
                            symbol_to_token[symbol.upper()] = str(token)
                    if symbol_to_token:
                        break
        except:
            continue
    return symbol_to_token

# ================================================================
# 3. FETCH MARGIN & PRICE DATA
# ================================================================
def get_margin_data(jwt_token: str, symbols: list):
    """Fetch LTP and margin for each symbol using raw HTTP."""
    if not jwt_token:
        return [], 0.0

    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # Build symbol→token mapping
    symbol_to_token = get_symbol_token_map(jwt_token)
    if not symbol_to_token:
        st.error("❌ Could not fetch instrument mapping. Check connectivity.")
        return [], 0.0

    # Get available capital
    capital = 10000.0
    try:
        resp = requests.get(f"{base_url}/user/fundsummary", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status'):
                capital = float(data['data'][0]['MTF_AVAILABLE_BALANCE'])
    except:
        pass

    results = []

    for sym in symbols:
        sym = sym.strip().upper()
        token = symbol_to_token.get(sym)

        if not token:
            results.append({
                'Symbol': sym, 'Price (₹)': 'Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': f'❌ Token not found'
            })
            continue

        # Fetch LTP using token
        price = 0
        try:
            url_quote = f"{base_url}/market/quote?mode=OHLC&exchange=NSE&token={token}"
            resp = requests.get(url_quote, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    ohlc = data.get('data', {}).get('OHLC', {})
                    price_data = ohlc.get(token)
                    if price_data:
                        price = float(price_data.get('ltp', 0))
        except:
            pass

        if price == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': 'Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ LTP fetch failed'
            })
            continue

        # Fetch margin (MIS) using token
        margin_per_share = 0
        try:
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
            resp = requests.post(f"{base_url}/margins/orders", json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    margin_per_share = float(data.get('data', {}).get('total', 0))
        except:
            pass

        if margin_per_share == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': round(price, 2),
                'Margin/Share (₹)': 'Error', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ Margin calc failed'
            })
            continue

        # Calculate
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
# 4. STREAMLIT UI
# ================================================================
st.title("🚀 Live Margin Calculator")

with st.sidebar:
    st.header("🔐 Authentication")
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type="password")
    otp = st.text_input("OTP (6‑digit from authenticator)", type="password")

    if st.button("Authenticate"):
        if not user_id or not password or not otp:
            st.error("All fields are required")
        else:
            with st.spinner("Authenticating..."):
                token = authenticate(user_id, password, otp)
                if token:
                    st.session_state['jwt_token'] = token
                    st.session_state['authenticated'] = True

    st.markdown("---")
    st.header("📊 Stocks")
    default = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stock_input = st.text_area("Symbols (comma/newline)", value=default, height=120)
    fetch_btn = st.button("🔄 Fetch Margins")

# Main area
if not st.session_state.get('authenticated'):
    st.info("Please authenticate first")
    st.dataframe(pd.DataFrame(columns=[
        'Symbol', 'Price (₹)', 'Margin/Share (₹)',
        'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
    ]))
    st.stop()

jwt_token = st.session_state.get('jwt_token')

if fetch_btn:
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    with st.spinner("Fetching data..."):
        data, capital = get_margin_data(jwt_token, symbols)

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
    ready = df[df['Status'] == '✅ Ready'] if 'Status' in df.columns else pd.DataFrame()
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
                    st.success(f"Simulated: {row['Symbol']} {qty} shares")

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
