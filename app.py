import streamlit as st
import pandas as pd
from datetime import datetime

# ============================================================
# 1. PAGE CONFIG – MUST BE FIRST STREAMLIT COMMAND
# ============================================================
st.set_page_config(page_title="Margin Calculator", layout="wide")

# ============================================================
# 2. SDK SETUP & IMPORTS
# ============================================================
# Check if the mStock SDK is installed.
try:
    from tradingapi_a.mconnect import MConnect
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ============================================================
# 3. AUTHENTICATION FUNCTION
# ============================================================
def authenticate(api_key: str, user_id: str, password: str, otp: str = ""):
    """
    Authenticate with mStock using Type‑A API.
    Returns an authenticated MConnect client object, or None on failure.
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock SDK not installed. Please install mStock-TradingApi-A.")
        return None

    try:
        client = MConnect()

        # Step 1: Login to get request token
        login_resp = client.login(user_id, password)
        login_data = login_resp.json()          # Parse the Response object

        if login_data.get('status') != 'success':
            st.error(f"Login failed: {login_data.get('message', 'Unknown error')}")
            return None

        request_token = login_data.get('data', {}).get('request_token')
        if not request_token:
            st.error("No request_token received from login.")
            return None

        # Step 2: Exchange request_token for access_token
        # If 2FA is disabled, pass an empty string as the checksum.
        gen_resp = client.generate_session(api_key, request_token, otp)
        gen_data = gen_resp.json()              # Parse the Response object

        if gen_data.get('status') != 'success':
            st.error(f"Session generation failed: {gen_data.get('message', 'Unknown error')}")
            return None

        st.success("✅ Authentication successful!")
        return client

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None

# ============================================================
# 4. MARGIN CALCULATION FUNCTION
# ============================================================
def get_margin_data(client, symbols: list):
    """
    For each symbol, fetch:
      - Current LTP
      - Margin required for 1 share (MIS / intraday)
      - Leverage, buying power, max quantity
    Returns a list of dicts and the available capital.
    """
    if client is None:
        return [], 0.0

    # Get available capital
    try:
        fund_resp = client.get_fund_summary()
        fund_data = fund_resp.json()
        if fund_data.get('status') == 'success':
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
            # --- Get LTP ---
            ltp_resp = client.get_ltp([f"NSE:{sym}"])
            ltp_data = ltp_resp.json()
            if ltp_data.get('status') != 'success':
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

            price = float(ltp_data.get('data', {}).get(f'NSE:{sym}', {}).get('ltp', 0))
            if price == 0:
                results.append({
                    'Symbol': sym,
                    'Price (₹)': 'Error',
                    'Margin/Share (₹)': '-',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': '❌ Price is zero'
                })
                continue

            # --- Calculate margin for 1 share (MIS) ---
            margin_resp = client.calculate_order_margin(
                exchange="NSE",
                trading_symbol=sym,
                transaction_type="BUY",
                product_type="MIS",
                order_type="MARKET",
                quantity="1",
                price="0",
                trigger_price="0"
            )
            margin_data = margin_resp.json()
            if margin_data.get('status') != 'success':
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

            margin_per_share = float(margin_data.get('data', {}).get('total', 0))
            if margin_per_share == 0:
                results.append({
                    'Symbol': sym,
                    'Price (₹)': round(price, 2),
                    'Margin/Share (₹)': 'Error',
                    'Leverage (x)': '-',
                    'Buying Power (₹)': '-',
                    'Max Qty': '-',
                    'Status': '❌ Zero margin'
                })
                continue

            # --- Calculate derived values ---
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

    # Show SDK status
    if SDK_AVAILABLE:
        st.success("✅ mStock SDK loaded")
    else:
        st.error("❌ SDK not installed")
        st.code("pip install mStock-TradingApi-A", language="bash")
        st.stop()

    # Credentials input
    api_key = st.text_input("API Key", type="password",
                            help="Generated from mStock dashboard → Products → Trading APIs")
    user_id = st.text_input("User ID", help="Your mStock trading username")
    password = st.text_input("Password", type="password", help="Your mStock trading password")
    otp = st.text_input("OTP / Checksum (optional)", type="password",
                        help="If 2FA is enabled, enter the OTP; otherwise leave blank")

    if st.button("🔑 Authenticate", type="primary"):
        if not api_key or not user_id or not password:
            st.error("Please fill in API Key, User ID, and Password")
        else:
            with st.spinner("Authenticating with mStock..."):
                client = authenticate(api_key, user_id, password, otp)
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
    st.info("👈 Please authenticate first by entering your credentials and clicking 'Authenticate'")
    # Show empty table
    st.dataframe(pd.DataFrame(columns=[
        'Symbol', 'Price (₹)', 'Margin/Share (₹)',
        'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status'
    ]))
    st.stop()

client = st.session_state.get('mstock_client')
if not client:
    st.warning("⚠️ Client not available. Please authenticate again.")
    st.stop()

# Show capital if already available
capital_placeholder = st.empty()

if fetch_btn:
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    if not symbols:
        st.warning("Please enter at least one stock symbol.")
        st.stop()

    with st.spinner("Fetching real‑time margin data..."):
        data, capital = get_margin_data(client, symbols)

    # Update capital display
    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")

    # Create DataFrame
    df = pd.DataFrame(data)

    # Display table with formatting
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

    # --- Simulated Buy Section ---
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

# --- Footer ---
st.markdown("---")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("Powered by mStock Trading API | Real‑time data fetched on each request")
