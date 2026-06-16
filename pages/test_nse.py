import streamlit as st
import websocket
import json
import threading
import time
import requests
import pyotp

# ========== CREDENTIALS (HARDCODED) ==========
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
st.set_page_config(page_title="NSE Live Test", layout="wide")
st.title("📡 NSE Live Data")
st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)

# ========== SESSION STATE ==========
if "live_data" not in st.session_state:
    st.session_state.live_data = {}
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False

placeholder = st.empty()
status = st.empty()

# ========== WEBSOCKET ==========
def run_websocket(feed_token, jwt_token):
    symbol_map = {v: k for k, v in STOCKS.items()}
    tokens = list(STOCKS.values())
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if 'last_traded_price' in data:
                token = str(data.get('token', ''))
                sym = symbol_map.get(token, '?')
                st.session_state.live_data[sym] = {
                    "ltp": data.get('last_traded_price', 0),
                    "volume": data.get('volume_trade_for_the_day', 0),
                    "change": data.get('change_percentage', 0)
                }
        except:
            pass
    
    def on_open(ws):
        st.session_state.ws_connected = True
        sub_msg = json.dumps({
            "action": "subscribe",
            "params": {
                "mode": 2,
                "tokenList": [{"exchangeType": 1, "tokens": tokens}]
            }
        })
        ws.send(sub_msg)
    
    def on_error(ws, error):
        st.session_state.ws_connected = False
    
    ws = websocket.WebSocketApp(
        f"wss://ws.angelbroking.com/NestHtml5Mobile/smart/websocket?feed_token={feed_token}&client_code={CLIENT_CODE}&jwttoken={jwt_token}",
        on_message=on_message,
        on_open=on_open,
        on_error=on_error
    )
    ws.run_forever()

# ========== AUTO LOGIN & CONNECT ==========
@st.cache_resource
def connect_angel():
    totp = pyotp.TOTP(TOTP_SECRET).now()
    
    login_url = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
        "X-PrivateKey": API_KEY
    }
    payload = {"clientcode": CLIENT_CODE, "password": PASSWORD, "totp": totp}
    
    response = requests.post(login_url, json=payload, headers=headers)
    data = response.json()
    
    if data.get("status"):
        return data["data"]["feedToken"], data["data"]["jwtToken"]
    else:
        return None, data.get("message", "Unknown error")

feed_token, jwt_token = connect_angel()

if feed_token:
    status.success("✅ Connected! Streaming 50 stocks...")
    thread = threading.Thread(target=run_websocket, args=(feed_token, jwt_token), daemon=True)
    thread.start()
else:
    status.error(f"❌ Login failed: {jwt_token}")
    st.stop()

# ========== DISPLAY LIVE DATA ==========
if st.session_state.ws_connected:
    while True:
        if st.session_state.live_data:
            import pandas as pd
            rows = []
            for sym, vals in sorted(st.session_state.live_data.items()):
                rows.append({
                    "Symbol": sym,
                    "LTP": f"₹{vals['ltp']:.2f}",
                    "Volume": vals['volume'],
                    "Change %": f"{vals['change']:.2f}%"
                })
            df = pd.DataFrame(rows)
            placeholder.dataframe(df, use_container_width=True, hide_index=True)
        else:
            placeholder.info("⏳ Waiting for tick data...")
        time.sleep(1)
        st.rerun()
