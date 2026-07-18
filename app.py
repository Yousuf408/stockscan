import requests, math, pyotp
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CREDENTIALS (replace with your own or use st.secrets) ───
MSTOCK_BASE_URL = "https://api.mstock.trade/openapi/typeb"
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_USER_ID = "MA1764118"
MSTOCK_PASSWORD = "P@ssw0rd"
MSTOCK_TOTP_SECRET = "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV"

def _mstock_headers(jwt=None):
    headers = {"X-Mirae-Version": "1"}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers

def _mstock_token():
    totp = pyotp.TOTP(MSTOCK_TOTP_SECRET).now()
    resp = requests.post(f"{MSTOCK_BASE_URL}/connect/login", json={"clientcode": MSTOCK_USER_ID, "password": MSTOCK_PASSWORD, "totp": totp, "state": ""}, headers=_mstock_headers(), timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get('data', {}).get('jwtToken') if data.get('status') else None

@st.cache_data(ttl=86400)
def _mstock_token_map():
    """Returns {symbol: token} for NSE Equity only."""
    token_map = {}
    jwt = _mstock_token()
    if not jwt:
        return token_map
    resp = requests.get(f"{MSTOCK_BASE_URL}/instruments/OpenAPIScripMaster", headers=_mstock_headers(jwt), timeout=30)
    if resp.status_code != 200:
        return token_map
    data = resp.json()
    instruments = data.get('data', []) if isinstance(data, dict) else data
    for item in instruments:
        if item.get('instrumenttype', '').upper() not in ('EQ', 'EQUITY', 'E'):
            continue
        sym = item.get('symbol') or item.get('trading_symbol')
        tok = item.get('token') or item.get('instrument_token')
        if sym and tok:
            token_map[sym.upper()] = str(tok)
    return token_map

def calculate_margin_and_qty(df, total_capital, num_parts=4):
    """
    Adds three columns to the input DataFrame (must have 'Symbol' and 'Price'):
        - Margin/Share (₹)  : margin required for 1 share (MIS)
        - Leverage (x)      : price / margin
        - Max Qty           : floor( (capital/parts) / margin )
    """
    if df.empty or total_capital <= 0:
        df['Margin/Share (₹)'] = 0
        df['Leverage (x)'] = 0
        df['Max Qty'] = 0
        return df

    token_map = _mstock_token_map()
    if not token_map:
        df['Margin/Share (₹)'] = 0
        df['Leverage (x)'] = 0
        df['Max Qty'] = 0
        return df

    # Ensure Price is numeric
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)

    # Cache margins in session
    if 'margin_cache' not in st.session_state:
        st.session_state['margin_cache'] = {}

    part_capital = total_capital / num_parts

    # Identify symbols that need margin fetch (not in cache and have token and positive price)
    symbols = df['Symbol'].str.upper().str.strip().tolist()
    missing = [s for s in symbols if s not in st.session_state['margin_cache'] and token_map.get(s) and df[df['Symbol'].str.upper()==s]['Price'].iloc[0] > 0]

    def fetch_margin(sym):
        token = token_map.get(sym)
        price = df[df['Symbol'].str.upper()==sym]['Price'].iloc[0]
        if not token or price <= 0:
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
                "token": token,
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

    if missing:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_margin, s): s for s in missing}
            for future in as_completed(futures):
                sym, margin = future.result()
                if margin is not None and margin > 0:
                    st.session_state['margin_cache'][sym] = margin

    # Compute new columns
    margins = []
    leverages = []
    qties = []
    for sym in symbols:
        margin = st.session_state['margin_cache'].get(sym)
        if margin is None or margin <= 0:
            margins.append(None)
            leverages.append(None)
            qties.append(0)
        else:
            price = df[df['Symbol'].str.upper()==sym]['Price'].iloc[0]
            if price <= 0:
                margins.append(None)
                leverages.append(None)
                qties.append(0)
            else:
                margins.append(round(margin, 2))
                leverages.append(round(price / margin, 1))
                qties.append(math.floor(part_capital / margin))

    df['Margin/Share (₹)'] = margins
    df['Leverage (x)'] = leverages
    df['Max Qty'] = qties

    return df
