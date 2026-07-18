import streamlit as st
import pandas as pd
import requests
import math
import pyotp
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

st.set_page_config(page_title="Live Margin Calculator", layout="wide")

# ================================================================
# 1. CREDENTIALS (use st.secrets in production)
# ================================================================
# For testing – replace with your actual credentials
MSTOCK_BASE_URL = "https://api.mstock.trade/openapi/typeb"
MSTOCK_API_KEY = st.secrets.get("MSTOCK_API_KEY", "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g=")
MSTOCK_USER_ID = st.secrets.get("MSTOCK_USER_ID", "MA1764118")
MSTOCK_PASSWORD = st.secrets.get("MSTOCK_PASSWORD", "P@ssw0rd")
MSTOCK_TOTP_SECRET = st.secrets.get("MSTOCK_TOTP_SECRET", "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV")

# ================================================================
# 2. MSTOCK HELPER FUNCTIONS
# ================================================================
def _mstock_headers(jwt=None):
    headers = {"X-Mirae-Version": "1"}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers

def _mstock_token():
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
        resp = requests.post(url, json=payload, headers=_mstock_headers(), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get('status'):
            return None
        return data.get('data', {}).get('jwtToken')
    except:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def _mstock_map():
    """Fetch instrument master and return symbol→token and symbol→price maps."""
    token_map = {}
    price_map = {}
    jwt = _mstock_token()
    if not jwt:
        return token_map, price_map
    try:
        url = f"{MSTOCK_BASE_URL}/instruments/OpenAPIScripMaster"
        resp = requests.get(url, headers=_mstock_headers(jwt), timeout=30)
        if resp.status_code != 200:
            return token_map, price_map
        data = resp.json()
        instruments = data.get('data', []) if isinstance(data, dict) else data
        for item in instruments:
            # Keep only Equity
            if item.get('instrumenttype', '').upper() not in ('EQ', 'EQUITY', 'E'):
                continue
            sym = item.get('symbol') or item.get('trading_symbol')
            tok = item.get('token') or item.get('instrument_token')
            if sym and tok:
                token_map[sym.upper()] = str(tok)
                # Try to get a fallback price
                price = None
                for field in ['last_price', 'close_price', 'ltp', 'close', 'prev_close', 'day_close']:
                    if field in item and item[field]:
                        try:
                            price = float(item[field])
                            break
                        except:
                            continue
                if price is not None:
                    price_map[sym.upper()] = price
        return token_map, price_map
    except:
        return token_map, price_map

def calculate_max_qty(df, total_capital, num_parts=4):
    """
    Adds 'Price' and 'Max Qty' columns to the input DataFrame.
    The DataFrame must have a 'Symbol' column.
    """
    if df.empty or total_capital <= 0:
        df['Price'] = 0
        df['Max Qty'] = 0
        return df

    token_map, price_map = _mstock_map()
    if not token_map:
        df['Price'] = 0
        df['Max Qty'] = 0
        return df

    # Get live prices (fallback to master price)
    jwt = _mstock_token()
    price_dict = {}
    symbols = df['Symbol'].str.upper().str.strip().tolist()
    for sym in symbols:
        tok = token_map.get(sym)
        if not tok:
            price_dict[sym] = price_map.get(sym, 0)
            continue
        # Try LTP
        try:
            url = f"{MSTOCK_BASE_URL}/market/quote?mode=OHLC&exchange=NSE&token={tok}"
            resp = requests.get(url, headers=_mstock_headers(jwt), timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status'):
                    ohlc = data.get('data', {}).get('OHLC', {})
                    price_data = ohlc.get(tok)
                    if price_data and price_data.get('ltp'):
                        price_dict[sym] = float(price_data['ltp'])
                        continue
        except:
            pass
        # Fallback
        price_dict[sym] = price_map.get(sym, 0)

    # Update df with prices
    df['Price'] = df['Symbol'].str.upper().map(price_dict).fillna(0)

    # Margin cache in session state
    if 'margin_cache' not in st.session_state:
        st.session_state['margin_cache'] = {}

    part_capital = total_capital / num_parts

    # Determine which symbols need margin fetch
    missing = [
        s for s in symbols
        if s not in st.session_state['margin_cache']
        and token_map.get(s)
        and price_dict.get(s, 0) > 0
    ]

    def fetch_margin(sym):
        tok = token_map.get(sym)
        price = price_dict.get(sym, 0)
        if not tok or price <= 0:
            return sym, None
        # Call margin API
        headers = _mstock_headers(jwt)
        headers["Content-Type"] = "application/json"
        payload = {
            "orders": [{
                "product_type": "MIS",
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "0",
                "exchange": "NSE",
                "symbol_name": "",
                "token": tok,
                "trigger_price": 0
            }]
        }
        try:
            resp = requests.post(f"{MSTOCK_BASE_URL}/margins/orders", json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                return sym, None
            data = resp.json()
            if not data.get('status'):
                return sym, None
            margin = data.get('data', {}).get('total', 0)
            return sym, float(margin) if margin > 0 else None
        except:
            return sym, None

    # Parallel fetch
    if missing:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_margin, s): s for s in missing}
            for future in as_completed(futures):
                sym, margin = future.result()
                if margin is not None and margin > 0:
                    st.session_state['margin_cache'][sym] = margin

    # Compute Max Qty
    def get_qty(sym):
        margin = st.session_state['margin_cache'].get(sym)
        if not margin or margin <= 0:
            return 0
        return math.floor(part_capital / margin)

    df['Max Qty'] = df['Symbol'].str.upper().apply(get_qty)
    return df

# ================================================================
# 3. STREAMLIT UI (with screener placeholder)
# ================================================================
st.title("🚀 Live Margin Calculator")
st.markdown("Enter stock symbols and your capital to see maximum tradable quantity.")

with st.sidebar:
    st.header("🔐 Authentication")
    if _mstock_token():
        st.success("✅ Authenticated")
    else:
        st.error("❌ Authentication failed – check credentials")

    st.header("💰 Capital & Settings")
    total_capital = st.number_input("Total Capital (₹)", min_value=1000, value=10000, step=1000)
    num_parts = st.number_input("Number of Parts", min_value=1, max_value=10, value=4, step=1)

    st.header("📊 Stock Selection")
    default_symbols = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    symbols_input = st.text_area("Symbols (comma or newline)", value=default_symbols, height=120)
    fetch_btn = st.button("🔄 Fetch Margins", type="primary")

# ─── Main area ───
if fetch_btn:
    symbols = [s.strip().upper() for s in symbols_input.replace(',', ' ').split() if s]
    if not symbols:
        st.warning("No symbols entered")
        st.stop()

    # Create initial DataFrame
    df = pd.DataFrame({'Symbol': symbols})

    with st.spinner("Fetching margins and calculating max quantity..."):
        df = calculate_max_qty(df, total_capital, num_parts)

    # Display results
    st.metric("💰 Capital per part", f"₹{total_capital/num_parts:,.2f}")

    # Reorder columns for clarity
    display_cols = ['Symbol', 'Price', 'Max Qty']
    if all(c in df.columns for c in display_cols):
        df_display = df[display_cols].copy()
    else:
        df_display = df

    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # Debug expander
    with st.expander("🐞 Debug Info (per symbol)"):
        debug_data = []
        token_map, _ = _mstock_map()
        for sym in symbols:
            tok = token_map.get(sym)
            margin = st.session_state.get('margin_cache', {}).get(sym)
            price = df[df['Symbol'] == sym]['Price'].iloc[0] if sym in df['Symbol'].values else 0
            debug_data.append({
                'Symbol': sym,
                'Token': tok,
                'Margin/Share (₹)': margin,
                'Price (₹)': price
            })
        st.dataframe(pd.DataFrame(debug_data))

st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
