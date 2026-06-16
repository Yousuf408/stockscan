import streamlit as st
import requests
import pyotp
import pandas as pd
import time

# ========== CREDENTIALS ==========
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"

# ========== 50 NSE STOCKS ==========
STOCKS = {
    "RELIANCE": "2885", "TCS": "11536", "HDFCBANK": "1333", "INFY": "1594",
    "ICICIBANK": "4963", "BHARTIARTL": "10604", "SBIN": "3045", "ITC": "1660",
    "KOTAKBANK": "492", "LT": "1788", "AXISBANK": "590", "HINDUNILVR": "356",
    "BAJFINANCE": "317", "WIPRO": "3787", "ASIANPAINT": "236", "MARUTI": "2489",
    "SUNPHARMA": "335", "TITAN": "3506", "ULTRACEMCO": "11543", "NESTLEIND": "1749",
    "HCLTECH": "722", "TECHM": "3466", "POWERGRID": "14977", "NTPC": "11630",
    "ONGC": "2475", "COALINDIA": "4834", "ADANIPORTS": "9697", "ADANIENT": "13488",
    "JSWSTEEL": "11723", "TATASTEEL": "3499", "HINDALCO": "1344", "TATAMOTORS": "3456",
    "M&M": "2031", "BAJAJFINSV": "318", "BAJAJ-AUTO": "319", "EICHERMOT": "910",
    "HEROMOTOCO": "1348", "DRREDDY": "881", "CIPLA": "694", "DIVISLAB": "10940",
    "APOLLOHOSP": "157", "GRASIM": "1232", "BRITANNIA": "547", "INDUSINDBK": "525",
    "SBILIFE": "13174", "HDFCLIFE": "467", "BPCL": "526", "UPL": "11287",
    "SHREECEM": "3103", "DABUR": "772"
}

# ========== PAGE SETUP ==========
st.set_page_config(page_title="NSE Live", layout="wide")

# Auto-refresh every 5 seconds (clean, no loop)
st.markdown(
    """
    <meta http-equiv="refresh" content="5">
    """,
    unsafe_allow_html=True
)

st.title("📡 NSE Live Data (Angel One)")
st.caption(f"Last updated: {time.strftime('%H:%M:%S')}")

# ========== LOGIN ==========
@st.cache_resource
def angel_login():
    totp = pyotp.TOTP(TOTP_SECRET).now()
    url = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword"
    headers = {
        "Content-Type": "application/json", "Accept": "application/json",
        "X-UserType": "USER", "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": API_KEY
    }
    payload = {"clientcode": CLIENT_CODE, "password": PASSWORD, "totp": totp}
    resp = requests.post(url, json=payload, headers=headers).json()
    if resp.get("status"):
        return resp["data"]["jwtToken"]
    return None

jwt_token = angel_login()

if not jwt_token:
    st.error("❌ Login failed")
    st.stop()

# ========== FETCH DATA ==========
def fetch_quotes(tokens):
    url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/market/v1/quote/"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
        "X-PrivateKey": API_KEY
    }
    payload = {"mode": "FULL", "exchangeTokens": {"NSE": tokens}}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.json()
    except:
        return None

# ========== DISPLAY ==========
tokens = list(STOCKS.values())
symbol_map = {v: k for k, v in STOCKS.items()}

data = fetch_quotes(tokens)

if data and data.get("status"):
    rows = []
    for item in data.get("data", {}).get("fetched", []):
        token = str(item.get("symbolToken", ""))
        sym = symbol_map.get(token, "?")
        rows.append({
            "Symbol": sym,
            "LTP": f"₹{item.get('ltp', 0):.2f}",
            "Volume": item.get("volume", 0),
            "Change %": f"{item.get('change', 0):.2f}%"
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.success(f"✅ Showing {len(rows)} stocks")
else:
    st.warning("⏳ Loading data... Page auto-refreshes every 5 seconds.")
