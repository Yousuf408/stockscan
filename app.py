import streamlit as st
import pandas as pd
import requests
import math
import pyotp
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Test mStock Margin", layout="wide")

# ================================================================
# 1. CONFIGURATION – Replace with your credentials or use secrets
# ================================================================
# For testing, you can hardcode them here (remove before committing)
MSTOCK_BASE_URL = "https://api.mstock.trade/openapi/typeb"
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_USER_ID = "MA1764118"
MSTOCK_PASSWORD = "P@ssw0rd"
MSTOCK_TOTP_SECRET = "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV"

# ================================================================
# 2. HELPERS WITH CORRECT HEADERS
# ================================================================
def _get_headers(jwt_token=None):
    """Return headers with required API version."""
    headers = {"X-Mirae-Version": "1"}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    return headers

def get_access_token():
    """Authenticate and return JWT token."""
    try:
        totp = pyotp.TOTP(MSTOCK_TOTP_SECRET).now()
        url = f"{MSTOCK_BASE_URL}/connect/login"
        payload = {
            "clientcode": MSTOCK_USER_ID,
            "password": MSTOCK_PASSWORD,
            "totp": totp,
            "state": ""
        }
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=10)
        if resp.status_code != 200:
            st.error(f"Login HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        if not data.get('status'):
            st.error(f"Login failed: {data.get('message')}")
            return None
        return data.get('data', {}).get('jwtToken')
    except Exception as e:
        st.error(f"Auth exception: {str(e)}")
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def get_symbol_token_map():
    """Build symbol → token map from instrument master (EQ only)."""
    token_map = {}
    jwt = get_access_token()
    if not jwt:
        return token_map
    headers = _get_headers(jwt)
    url = f"{MSTOCK_BASE_URL}/instruments/OpenAPIScripMaster"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        st.error(f"Instrument master HTTP {resp.status_code}: {resp.text[:200]}")
        return token_map
    data = resp.json()
    instruments = data.get('data', []) if isinstance(data, dict) else data
    for item in instruments:
        if item.get('instrumenttype', '').upper() not in ('EQ', 'EQUITY', 'E'):
            continue
        symbol = item.get('symbol') or item.get('trading_symbol')
        token = item.get('token') or item.get('instrument_token')
        if symbol and token:
            token_map[symbol.upper()] = str(token)
    st.success(f"✅ Loaded {len(token_map)} equity symbols")
    return token_map

def get_margin_per_share(token, price):
    """Get margin required for 1 share (MIS)."""
    jwt = get_access_token()
    if not jwt:
        return None
    headers = _get_headers(jwt)
    headers["Content-Type"] = "application/json"
    payload = {
        "orders": [{
            "product_type": "MIS",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "0",
            "exchange": "NSE",
            "symbol_name": "",
            "token": token,
            "trigger_price": 0
        }]
    }
    url = f"{MSTOCK_BASE_URL}/margins/orders"
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data.get('status'):
        return None
    margin = data.get('data', {}).get('total', 0)
    return float(margin) if margin > 0 else None

# ================================================================
# 3. MAX QUANTITY CALCULATION (Parallel)
# ================================================================
def calculate_max_qty(df, total_capital, num_parts=4):
    """
    Add 'Max Qty' column to DataFrame with 'Symbol' and 'Price'.
    """
    if df.empty or total_capital <= 0:
        df['Max Qty'] = 0
        return df

    if 'margin_cache' not in st.session_state:
        st.session_state['margin_cache'] = {}

    part_capital = total_capital / num_parts
    token_map = get_symbol_token_map()
    if not token_map:
        df['Max Qty'] = 0
        return df

    # Identify missing symbols
    symbols = df['Symbol'].str.upper().str.strip().tolist()
    missing = [s for s in symbols if s not in st.session_state['margin_cache'] and token_map.get(s)]
    price_lookup = dict(zip(df['Symbol'].str.upper(), df['Price']))

    def fetch_margin(symbol):
        token = token_map.get(symbol)
        price = price_lookup.get(symbol, 0)
        if not token or price <= 0:
            return symbol, None
        margin = get_margin_per_share(token, price)
        return symbol, margin

    # Parallel fetch
    if missing:
        with st.spinner(f"Fetching margins for {len(missing)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_margin, s): s for s in missing}
                for future in as_completed(futures):
                    sym, margin = future.result()
                    if margin is not None and margin > 0:
                        st.session_state['margin_cache'][sym] = margin

    # Compute max quantity
    def get_qty(sym):
        margin = st.session_state['margin_cache'].get(sym)
        if not margin or margin <= 0:
            return 0
        return math.floor(part_capital / margin)

    df['Max Qty'] = df['Symbol'].str.upper().apply(get_qty)
    return df

# ================================================================
# 4. STREAMLIT UI – TEST HARNESS
# ================================================================
st.title("🧪 Test mStock Margin Calculator")

with st.sidebar:
    st.header("🔐 Authentication")
    if get_access_token():
        st.success("✅ Authenticated")
    else:
        st.error("❌ Not authenticated – check credentials")

    st.header("💰 Settings")
    total_capital = st.number_input("Total Capital (₹)", min_value=1000, value=10000, step=1000)
    num_parts = st.number_input("Number of Parts", min_value=1, max_value=10, value=4, step=1)

    default_symbols = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    symbols_input = st.text_area("Symbols (comma/newline)", value=default_symbols, height=120)
    fetch_btn = st.button("🚀 Fetch Margins", type="primary")

if fetch_btn:
    symbols = [s.strip().upper() for s in symbols_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    # Build DataFrame with symbols and fetch prices
    df = pd.DataFrame({'Symbol': symbols})
    token_map = get_symbol_token_map()
    jwt = get_access_token()
    prices = []
    with st.spinner("Fetching live prices..."):
        for sym in symbols:
            token = token_map.get(sym)
            if not token:
                prices.append(0)
                continue
            try:
                headers = _get_headers(jwt)
                url = f"{MSTOCK_BASE_URL}/market/quote?mode=OHLC&exchange=NSE&token={token}"
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status'):
                        ohlc = data.get('data', {}).get('OHLC', {})
                        price_data = ohlc.get(token)
                        if price_data:
                            prices.append(float(price_data.get('ltp', 0)))
                            continue
                prices.append(0)
            except:
                prices.append(0)
    df['Price'] = prices

    # Calculate max quantity
    df = calculate_max_qty(df, total_capital, num_parts)

    st.metric("💰 Capital per part", f"₹{total_capital/num_parts:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Debug: show per‑symbol details
    with st.expander("🐞 Debug Info (per symbol)"):
        debug_data = []
        for sym in symbols:
            token = token_map.get(sym)
            margin = st.session_state['margin_cache'].get(sym)
            debug_data.append({
                'Symbol': sym,
                'Token': token,
                'Margin/Share': margin,
                'Price': df[df['Symbol']==sym]['Price'].values[0] if sym in df['Symbol'].values else 0
            })
        st.dataframe(pd.DataFrame(debug_data))

st.caption("Test module – works standalone. Integrate into your screener by calling calculate_max_qty(df, capital, parts).")
