import streamlit as st
import pandas as pd
import requests
import math
import pyotp
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Margin Calculator", layout="wide")

# ================================================================
# 1. MSTOCK CREDENTIALS (FILLED)
# ================================================================
MSTOCK_BASE_URL = "https://api.mstock.trade/openapi/typeb"
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_USER_ID = "MA1764118"
MSTOCK_PASSWORD = "P@ssw0rd"
MSTOCK_TOTP_SECRET = "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV"

# ================================================================
# 2. DEBUG TRACKING
# ================================================================
def _init_debug():
    if 'qty_calc_debug' not in st.session_state:
        st.session_state['qty_calc_debug'] = {
            'token_map_size': 0,
            'token_error': None,
            'token_last_generated': None,
            'per_symbol': {},
        }

def _log_debug(key, value):
    _init_debug()
    st.session_state['qty_calc_debug'][key] = value

def _log_symbol_debug(symbol, **kwargs):
    _init_debug()
    if symbol not in st.session_state['qty_calc_debug']['per_symbol']:
        st.session_state['qty_calc_debug']['per_symbol'][symbol] = {}
    st.session_state['qty_calc_debug']['per_symbol'][symbol].update(kwargs)

def get_qty_calc_debug():
    _init_debug()
    return st.session_state['qty_calc_debug']

# ================================================================
# 3. AUTHENTICATION – RAW HTTP with OTP
# ================================================================
def get_access_token():
    """Generate JWT token using TOTP."""
    try:
        totp = pyotp.TOTP(MSTOCK_TOTP_SECRET).now()
        url = f"{MSTOCK_BASE_URL}/connect/login"
        payload = {
            "clientcode": MSTOCK_USER_ID,
            "password": MSTOCK_PASSWORD,
            "totp": totp,
            "state": ""
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            _log_debug('token_error', f"HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        if not data.get('status'):
            _log_debug('token_error', data.get('message', 'Login failed'))
            return None
        jwt_token = data.get('data', {}).get('jwtToken')
        if not jwt_token:
            _log_debug('token_error', 'No JWT token in response')
            return None
        _log_debug('token_error', None)
        _log_debug('token_last_generated', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return jwt_token
    except Exception as e:
        _log_debug('token_error', f"Exception: {str(e)}")
        return None

# ================================================================
# 4. SYMBOL → TOKEN MAP (from instrument master)
# ================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def get_symbol_token_map():
    token_map = {}
    try:
        jwt_token = get_access_token()
        if not jwt_token:
            _log_debug('token_map_error', 'Could not get access token')
            return {}
        headers = {"Authorization": f"Bearer {jwt_token}"}
        url = f"{MSTOCK_BASE_URL}/instruments/OpenAPIScripMaster"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            _log_debug('token_map_error', f"HTTP {resp.status_code}")
            return {}
        data = resp.json()
        instruments = data.get('data', []) if isinstance(data, dict) else data
        for item in instruments:
            inst_type = item.get('instrumenttype', '').upper()
            if inst_type not in ['EQ', 'EQUITY', 'E']:
                continue
            symbol = item.get('symbol') or item.get('trading_symbol')
            token = item.get('token') or item.get('instrument_token')
            if symbol and token:
                token_map[symbol.upper()] = str(token)
        _log_debug('token_map_size', len(token_map))
        return token_map
    except Exception as e:
        _log_debug('token_map_error', f"Exception: {str(e)}")
        return {}

# ================================================================
# 5. MARGIN PER SHARE
# ================================================================
def get_margin_per_share(token, price, product_type="MIS"):
    jwt_token = get_access_token()
    if not jwt_token:
        return None, "Could not obtain access token"
    try:
        headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
        payload = {
            "orders": [{
                "product_type": product_type,
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
        if resp.status_code == 401:
            jwt_token = get_access_token()
            if not jwt_token:
                return None, "401 Unauthorized, token refresh failed"
            headers["Authorization"] = f"Bearer {jwt_token}"
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        if not data.get('status'):
            return None, data.get('message', 'Margin API error')
        margin = data.get('data', {}).get('total', 0)
        if margin == 0:
            return None, "Zero margin returned"
        return float(margin), None
    except Exception as e:
        return None, f"Exception: {str(e)}"

# ================================================================
# 6. MAX QUANTITY CALCULATION (Parallel)
# ================================================================
def calculate_max_quantity_column(df, total_capital, num_parts=4):
    _init_debug()
    if 'margin_cache' not in st.session_state:
        st.session_state['margin_cache'] = {}
    if total_capital is None or total_capital <= 0 or df.empty:
        return pd.Series([0] * len(df), index=df.index)
    part_capital = total_capital / num_parts
    token_map = get_symbol_token_map()
    symbols_in_df = [str(r.get("Symbol", "")).strip().upper() for _, r in df.iterrows()]
    missing = [s for s in symbols_in_df if s not in st.session_state['margin_cache'] and token_map.get(s)]
    price_lookup = {str(r.get("Symbol", "")).strip().upper(): r.get("Price", 0) for _, r in df.iterrows()}

    def fetch_margin(symbol):
        token = token_map.get(symbol)
        price = price_lookup.get(symbol, 0)
        if not token or price <= 0:
            return symbol, None, "No token or price"
        margin, error = get_margin_per_share(token, price)
        return symbol, margin, error

    if missing:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_margin, sym): sym for sym in missing}
            for future in as_completed(futures):
                sym, margin_val, error = future.result()
                _log_symbol_debug(sym, token=token_map.get(sym), margin_error=error, margin_value=margin_val)
                if margin_val is not None and margin_val > 0:
                    st.session_state['margin_cache'][sym] = margin_val

    max_qty_list = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        margin_per_share = st.session_state['margin_cache'].get(symbol)
        if margin_per_share is None or margin_per_share <= 0:
            max_qty_list.append(0)
            continue
        max_qty = math.floor(part_capital / margin_per_share)
        max_qty_list.append(max(max_qty, 0))
    return pd.Series(max_qty_list, index=df.index)

# ================================================================
# 7. STREAMLIT UI
# ================================================================
st.title("🚀 Live Margin Calculator")

with st.sidebar:
    st.header("🔐 Authentication")
    jwt_token = get_access_token()
    if jwt_token:
        st.success("✅ Authenticated")
    else:
        st.warning("⚠️ Not authenticated – check credentials")

    st.markdown("---")
    st.header("📊 Capital & Stocks")
    total_capital = st.number_input("Total Capital (₹)", min_value=1000, value=10000, step=1000)
    num_parts = st.number_input("Number of Parts", min_value=1, max_value=10, value=4, step=1)
    default_stocks = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stocks_input = st.text_area("Stock Symbols (comma/newline)", value=default_stocks, height=120)
    fetch_btn = st.button("🔄 Fetch Margins", type="primary")

if fetch_btn:
    symbols = [s.strip().upper() for s in stocks_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    # Build DataFrame with symbols and fetch prices
    df = pd.DataFrame({'Symbol': symbols})
    token_map = get_symbol_token_map()
    jwt_token = get_access_token()
    prices = []
    for sym in symbols:
        token = token_map.get(sym)
        if not token:
            prices.append(0)
            continue
        try:
            headers = {"Authorization": f"Bearer {jwt_token}"}
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

    with st.spinner("Calculating margins..."):
        df['Max Qty'] = calculate_max_quantity_column(df, total_capital, num_parts)

    st.metric("💰 Capital per part", f"₹{total_capital/num_parts:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("🐞 Debug Info"):
        debug = get_qty_calc_debug()
        st.json(debug)

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
