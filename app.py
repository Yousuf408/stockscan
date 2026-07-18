import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Margin Calculator", layout="wide")

# ------------------- SDK Setup -------------------
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ------------------- Authentication (Fixed) -------------------
def authenticate_type_b(api_key: str, user_id: str, password: str, otp: str):
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None

    try:
        client = MConnectB()

        # Step 1: Login – get request_token
        login_response = client.login(user_id, password)
        login_data = login_response.json()
        st.write("🔍 Login response:", login_data)

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None

        request_token = login_data.get('data', {}).get('request_token')
        if not request_token:
            st.error("No request_token received.")
            return None

        # Step 2: Generate session – token is set internally
        gen_response = client.generate_session(api_key, request_token, otp)
        gen_data = gen_response.json()
        st.write("🔍 Session response:", gen_data)

        if not gen_data.get('status', False):
            st.error(f"Session generation failed: {gen_data.get('message', 'Unknown')}")
            return None

        st.success("✅ Authentication successful!")
        return client

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

# ------------------- Margin Calculator -------------------
def get_margin_data(client, symbols: list):
    if client is None:
        return [], 0.0

    try:
        fund_resp = client.get_fund_summary()
        fund_data = fund_resp.json()
        st.write("🔍 Fund summary:", fund_data)
        if fund_data.get('status', False):
            capital = float(fund_data['data'][0]['MTF_AVAILABLE_BALANCE'])
        else:
            capital = 10000.0
    except Exception as e:
        st.warning(f"Could not fetch capital: {e}. Using ₹10,000 mock.")
        capital = 10000.0

    results = []
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue

        try:
            # Fetch LTP
            ltp_resp = client.get_market_quote("OHLC", {"NSE": [sym]})
            ltp_data = ltp_resp.json()
            st.write(f"🔍 LTP response for {sym}:", ltp_data)

            if ltp_data.get('status', False):
                ohlc = ltp_data.get('data', {}).get('OHLC', {})
                price_data = ohlc.get(sym) or ohlc.get(f"NSE:{sym}")
                if price_data:
                    price = float(price_data.get('ltp', 0))
                else:
                    price = 0
            else:
                price = 0

            if price == 0:
                results.append({
                    'Symbol': sym, 'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                    'Buying Power (₹)': '-', 'Max Qty': '-',
                    'Status': '❌ LTP fetch failed'
                })
                continue

            # Calculate Margin (MIS / Intraday)
            margin_resp = client.calculate_order_margin(
                "MIS", "BUY", "1", "0", "NSE", sym, "", "0"
            )
            margin_data = margin_resp.json()
            st.write(f"🔍 Margin for {sym}:", margin_data)

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
                'Symbol': sym, 'Price (₹)': 'Error',
                'Margin/Share (₹)': '-', 'Leverage (x)': '-',
                'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': f'❌ {str(e)[:40]}'
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
    otp = st.text_input("OTP (6-digit from authenticator)", type="password")

    if st.button("🔑 Authenticate"):
        if not all([api_key, user_id, password, otp]):
            st.error("All fields required")
        else:
            with st.spinner("Authenticating..."):
                client = authenticate_type_b(api_key, user_id, password, otp)
                if client:
                    st.session_state['mstock_client'] = client
                    st.session_state['authenticated'] = True

    st.markdown("---")
    st.header("📊 Stocks")
    default = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stocks_input = st.text_area("Symbols (comma/newline)", value=default, height=120)
    fetch_btn = st.button("🔄 Fetch Margins")

# Main
if not st.session_state.get('authenticated'):
    st.info("Authenticate first")
    st.stop()

client = st.session_state.get('mstock_client')
if not client:
    st.warning("Client missing – re-authenticate")
    st.stop()

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols")
        st.stop()

    with st.spinner("Fetching..."):
        data, capital = get_margin_data(client, symbols)

    st.metric("💰 Capital", f"₹{capital:,.2f}")
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    ready = df[df['Status'] == '✅ Ready']
    if not ready.empty:
        st.markdown("---")
        st.subheader("📦 Simulated Buy")
        for idx, row in ready.iterrows():
            cols = st.columns([1, 1, 1, 2])
            with cols[0]:
                st.write(f"**{row['Symbol']}**")
            with cols[1]:
                st.write(f"₹{row['Price (₹)']:.2f}")
            with cols[2]:
                qty = st.number_input(
                    "Qty", min_value=1, max_value=row['Max Qty'],
                    value=min(row['Max Qty'], 10), key=f"qty_{idx}"
                )
            with cols[3]:
                if st.button(f"Buy {row['Symbol']}", key=f"buy_{idx}"):
                    st.success(f"Simulated: {row['Symbol']} {qty} shares")
    else:
        st.info("No ready stocks")

st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
