import streamlit as st
import websocket
import json
import threading
import requests
import pyotp

# ========== CREDENTIALS ==========
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"

st.set_page_config(page_title="WS Debug", layout="wide")
st.title("🔍 WebSocket Debugger")

# Login
totp = pyotp.TOTP(TOTP_SECRET).now()
url = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword"
headers = {
    "Content-Type": "application/json", "Accept": "application/json",
    "X-UserType": "USER", "X-SourceID": "WEB",
    "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
    "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": API_KEY
}
resp = requests.post(url, json={"clientcode": CLIENT_CODE, "password": PASSWORD, "totp": totp}, headers=headers).json()
st.json(resp)

if resp.get("status"):
    feed_token = resp["data"]["feedToken"]
    jwt_token = resp["data"]["jwtToken"]
    
    st.success("✅ Login OK")
    st.write(f"Feed Token: {feed_token[:20]}...")
    st.write(f"JWT: {jwt_token[:50]}...")
    
    log_area = st.empty()
    logs = []
    
    def on_message(ws, message):
        logs.append(f"📩 MSG: {message[:200]}")
        if len(logs) > 20:
            logs.pop(0)
        log_area.text("\n".join(logs))
    
    def on_open(ws):
        logs.append("🔗 WS OPENED")
        sub = json.dumps({
            "action": "subscribe",
            "params": {"mode": 2, "tokenList": [{"exchangeType": 1, "tokens": ["2885"]}]}
        })
        ws.send(sub)
        logs.append(f"📤 SENT: {sub}")
    
    def on_error(ws, error):
        logs.append(f"❌ ERROR: {error}")
    
    def on_close(ws, code, msg):
        logs.append(f"🔒 CLOSED: {code} - {msg}")
    
    ws_url = f"wss://ws.angelbroking.com/NestHtml5Mobile/smart/websocket?feed_token={feed_token}&client_code={CLIENT_CODE}&jwttoken={jwt_token}"
    st.write(f"WS URL: {ws_url[:100]}...")
    
    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_open=on_open, on_error=on_error, on_close=on_close)
    threading.Thread(target=ws.run_forever, daemon=True).start()
    st.info("WebSocket thread started. Watch logs below...")
else:
    st.error("❌ Login failed")
