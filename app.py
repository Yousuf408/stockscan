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

def set_client_token(client, jwt_token):
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

def authenticate_type_b(api_key, user_id, password, otp):
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
            st.error("No JWT token received.")
            return None, None
        set_client_token(client, jwt_token)
        st.success("✅ Authentication successful!")
        return client, jwt_token
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None, None

def get_symbol_token_map(jwt_token, debug=False):
    base_url = "https://api.mstock.trade/openapi/typeb"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    symbol_to_token = {}
    symbol_to_price = {}

    endpoint = "/instruments/OpenAPIScripMaster"
    try:
        resp = requests.get(f"{base_url}{endpoint}", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            instruments = data.get('data', []) if isinstance(data, dict) else data
            
            # Filter for equity instruments only
            equity_instruments = []
            for item in instruments:
                inst_type = item.get('instrumenttype', '').upper()
                # Accept 'EQ', 'EQUITY', 'E' (some APIs use different codes)
                if inst_type in ['EQ', 'EQUITY', 'E']:
                    equity_instruments.append(item)
            
            if debug:
                st.write(f"🔍 Total instruments: {len(instruments)}")
                st.write(f"🔍 Equity instruments: {len(equity_instruments)}")
                if equity_instruments:
                    st.write("🔍 Sample equity symbols:", [item.get('symbol') for item in equity_instruments[:5]])
            
            for item in equity_instruments:
                symbol = item.get('symbol') or item.get('trading_symbol')
                token = item.get('token') or item.get('instrument_token')
                if symbol and token:
                    symbol_to_token[symbol.upper()] = str(token)
                    # Try multiple possible price fields
                    price = None
                    for field in ['last_price', 'close_price', 'ltp', 'close', 
                                  'prev_close', 'day_close', 'previous_close']:
                        if field in item and item[field]:
                            price = float(item[field])
                            break
                    if price:
                        symbol_to_price[symbol.upper()] = price

            if symbol_to_token:
                st.success(f"✅ Loaded {len(symbol_to_token)} equity instruments.")
            else:
                st.warning("⚠️ No equity symbols found in master list.")
        else:
            st.error(f"❌ Failed to fetch master list. Status: {resp.status_code}")
    except Exception as e:
        st.error(f"❌ Error: {e}")
    return symbol_to_token, symbol_to_price

def get_margin_data(client, jwt_token, symbols, debug=False):
    if client is None and not jwt_token:
        return [], 0.0

    symbol_to_token, symbol_to_price = get_symbol_token_map(jwt_token, debug=debug)
    if not symbol_to_token:
        return [], 0.0

    # Get capital
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

        token = symbol_to_token.get(sym)
        if not token:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Margin %': '-',
                'Status': f'❌ Token not found (not an equity symbol on NSE)'
            })
            continue

        # ---- 1. Get Price ----
        price = 0
        # Try quote API first (live LTP)
        try:
            headers = {'Authorization': f'Bearer {jwt_token}'}
            url_quote = f"https://api.mstock.trade/openapi/typeb/market/quote?mode=OHLC&exchange=NSE&token={token}"
            resp = requests.get(url_quote, headers=headers)
            if resp.status_code == 200:
                quote_data = resp.json()
                if quote_data.get('status', False):
                    ohlc = quote_data.get('data', {}).get('OHLC', {})
                    price_data = ohlc.get(token) or ohlc.get(f"NSE:{token}")
                    if price_data:
                        price = float(price_data.get('ltp', 0))
                    else:
                        # Try any price
                        for key, val in ohlc.items():
                            if isinstance(val, dict) and val.get('ltp'):
                                price = float(val['ltp'])
                                break
        except:
            pass

        # If live quote fails, use master list price (last close)
        if price == 0 and sym in symbol_to_price:
            price = symbol_to_price[sym]

        if price == 0:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'No Data',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Margin %': '-',
                'Status': '⏸ Price unavailable (market closed or symbol not traded)'
            })
            continue

        # ---- 2. Get Margin per Share (MIS) ----
        margin_per_share = 0
        try:
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
            if resp.status_code == 200:
                margin_data = resp.json()
                if margin_data.get('status', False):
                    margin_per_share = float(margin_data.get('data', {}).get('total', 0))
        except:
            pass

        if margin_per_share == 0:
            results.append({
                'Symbol': sym,
                'Price (₹)': round(price, 2),
                'Margin/Share (₹)': 'Error',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Margin %': '-',
                'Status': '❌ Margin calc failed'
            })
            continue

        # ---- 3. Calculate ----
        leverage = price / margin_per_share
        buying_power = capital * leverage
        max_qty = int(buying_power / price)
        margin_percent = (margin_per_share / price) * 100

        results.append({
            'Symbol': sym,
            'Price (₹)': round(price, 2),
            'Margin/Share (₹)': round(margin_per_share, 2),
            'Leverage (x)': round(leverage, 1),
            'Buying Power (₹)': round(buying_power, 2),
            'Max Qty': max_qty,
            'Margin %': f"{margin_percent:.1f}%",
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
                    st.session_state['authenticated'] = True

    st.markdown("---")
    st.header("📊 Stocks")
    default = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stocks_input = st.text_area("Symbols (comma/newline)", value=default, height=120)
    debug_mode = st.checkbox("🐞 Show debug info", value=False)
    fetch_btn = st.button("🔄 Fetch Margins")

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
        data, capital = get_margin_data(client, jwt_token, symbols, debug=debug_mode)

    st.metric("💰 Available Capital", f"₹{capital:,.2f}")
    if not data:
        st.warning("No data returned.")
        df = pd.DataFrame(columns=['Symbol', 'Price (₹)', 'Margin/Share (₹)', 'Leverage (x)',
                                   'Buying Power (₹)', 'Max Qty', 'Margin %', 'Status'])
    else:
        df = pd.DataFrame(data)

    col_order = ['Symbol', 'Price (₹)', 'Margin/Share (₹)', 'Leverage (x)',
                 'Margin %', 'Buying Power (₹)', 'Max Qty', 'Status']
    if all(c in df.columns for c in col_order):
        df = df[col_order]

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Simulated Buy section
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
