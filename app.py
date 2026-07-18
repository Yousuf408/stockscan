import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="Margin Calculator", layout="wide")

# ------------------- SDK Setup (only for authentication) -------------------
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ------------------- Authentication -------------------
def authenticate_type_b(api_key, user_id, password, otp):
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None

    try:
        client = MConnectB()
        login_response = client.login(user_id, password)
        login_data = login_response.json()
        st.write("🔍 Login response:", login_data)

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None

        jwt_token = login_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received.")
            return None

        # No need to set token on client – we'll use raw requests
        st.success("✅ Authentication successful!")
        return jwt_token

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

# ------------------- Margin & Price Fetch (raw HTTP) -------------------
def get_margin_data(jwt_token, symbols):
    if not jwt_token:
        return [], 0.0

    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # 1. Get capital
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
        if not sym:
            continue

        # 2. Get LTP
        price = 0
        try:
            # Try format: symbol=NSE:GABRIEL
            url_quote = f"{base_url}/market/quote?mode=OHLC&symbol=NSE:{sym}"
            resp = requests.get(url_quote, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                st.write(f"🔍 LTP response for {sym}:", data)   # Debug
                if data.get('status'):
                    ohlc = data.get('data', {}).get('OHLC', {})
                    price_data = ohlc.get(sym) or ohlc.get(f"NSE:{sym}")
                    if price_data:
                        price = float(price_data.get('ltp', 0))
            # Fallback: exchange + symbol
            if price == 0:
                url_quote2 = f"{base_url}/market/quote?mode=OHLC&exchange=NSE&symbol={sym}"
                resp = requests.get(url_quote2, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    st.write(f"🔍 LTP response (alt) for {sym}:", data)
                    if data.get('status'):
                        ohlc = data.get('data', {}).get('OHLC', {})
                        price_data = ohlc.get(sym) or ohlc.get(f"NSE:{sym}")
                        if price_data:
                            price = float(price_data.get('ltp', 0))
        except Exception as e:
            st.write(f"Error fetching LTP for {sym}: {e}")

        if price == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': 'Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ LTP fetch failed'
            })
            continue

        # 3. Get margin (MIS)
        margin_per_share = 0
        try:
            margin_payload = {
                "product_type": "MIS",
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "0",
                "exchange": "NSE",
                "trading_symbol": sym,
                "symbol_token": "",
                "trigger_price": "0"
            }
            resp = requests.post(f"{base_url}/order/margin", json=margin_payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                st.write(f"🔍 Margin response for {sym}:", data)
                if data.get('status'):
                    margin_per_share = float(data.get('data', {}).get('total', 0))
        except Exception as e:
            st.write(f"Error fetching margin for {sym}: {e}")

        if margin_per_share == 0:
            results.append({
                'Symbol': sym, 'Price (₹)': round(price, 2),
                'Margin/Share (₹)': 'Error', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': '❌ Margin calc failed'
            })
            continue

        # 4. Calculate
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
                token = authenticate_type_b(api_key, user_id, password, otp)
                if token:
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

jwt_token = st.session_state.get('jwt_token')

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    with st.spinner("Fetching data..."):
        data, capital = get_margin_data(jwt_token, symbols)

    st.metric("💰 Available Capital", f"₹{capital:,.2f}")
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
                    st.success(f"Simulated order: {row['Symbol']} - {qty} shares")

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
