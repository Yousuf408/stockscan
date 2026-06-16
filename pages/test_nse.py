import streamlit as st
import pyotp
import pandas as pd
import threading
import time
import base64
import sys
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

st.set_page_config(page_title="Nifty 50 Real-Time Feed", page_icon="⚡", layout="wide")
st.title("⚡ Nifty 50 High-Speed WebSocket Stream")

# =====================================================================
# 1. API CREDENTIALS
# =====================================================================
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"  # Alphanumeric secret key string


TRACKED_STOCKS = {
    "1398": "RELIANCE-EQ", "1333": "HDFCBANK-EQ", "11536": "TCS-EQ", "1594": "INFY-EQ",
    "4124": "ICICIBANK-EQ", "3045": "SBIN-EQ", "10604": "BHARTIARTL-EQ", "1660": "ITC-EQ",
    "3456": "TATAMOTORS-EQ", "11630": "NIFTY-BEES"
}

# State Variables
if "live_market_data" not in st.session_state:
    st.session_state.live_market_data = {t: {"Symbol": s, "Price": 0.0, "Volume": 0} for t, s in TRACKED_STOCKS.items()}
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False
if "ws_logs" not in st.session_state:
    st.session_state.ws_logs = []

def log_message(msg):
    st.session_state.ws_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def fix_secret_string(raw_secret):
    clean = raw_secret.replace(" ", "").strip()
    try:
        base64.b32decode(clean, casefold=True)
        return clean
    except Exception:
        padded = clean + '=' * ((4 - len(clean) % 4) % 4)
        return base64.b64encode(base64.b64decode(padded)).decode('utf-8')

# =====================================================================
# 2. FIXED WEBSOCKET PIPELINE WITH MULTI-ARGUMENT CALLBACK SUPPORT
# =====================================================================
def start_websocket_stream(auth_token, feed_token):
    try:
        clean_auth_token = auth_token.replace("Bearer ", "").strip()
        sws = SmartWebSocketV2(clean_auth_token, API_KEY, CLIENT_CODE, feed_token)

        def on_open(wsapp):
            st.session_state.ws_connected = True
            log_message("✅ Pure WebSocket Active! Subscribing to script streams...")
            token_list = [{"exchangeType": 1, "tokens": list(TRACKED_STOCKS.keys())}]
            sws.subscribe("load_test_800", 2, token_list)
            log_message("📡 Subscription payload successfully processed.")

        def on_data(wsapp, message):
            if isinstance(message, dict):
                token = message.get("token")
                if token in st.session_state.live_market_data:
                    st.session_state.live_market_data[token].update({
                        "Price": message.get("last_traded_price", 0.0) / 100.0 if "last_traded_price" in message else st.session_state.live_market_data[token]["Price"],
                        "Volume": message.get("volume_trade_for_the_day", 0) if "volume_trade_for_the_day" in message else st.session_state.live_market_data[token]["Volume"]
                    })

        def on_error(wsapp, error):
            log_message(f"❌ Socket Pipeline Error: {str(error)}")

        # Catching both old and new SDK call variants to prevent silent core drops
        def on_close(wsapp, *args, **kwargs):
            st.session_state.ws_connected = False
            # Safely parse exit parameters based on argument distribution lengths
            msg = f"Args: {args} {kwargs}" if args else "Normal Closure"
            log_message(f"🔌 Connection closed down by remote server. Details: {msg}")

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        
        log_message("🔌 Connecting network to wss://smartapisocket.angelone.in...")
        sws.connect()
        
    except Exception as thread_err:
        log_message(f"💥 Fatal exception in WebSocket Thread Engine: {str(thread_err)}")

# =====================================================================
# 3. VERIFICATION RUNNER
# =====================================================================
if not st.session_state.ws_connected:
    if st.button("🔌 Boot Nifty 50 Live Stream"):
        st.session_state.ws_logs = []
        log_message("🔑 Normalizing TOTP Secret Key structure...")
        
        try:
            safe_secret = fix_secret_string(TOTP_SECRET)
            totp_auth = pyotp.TOTP(safe_secret).now()
            
            log_message("📡 Connecting to Angel One REST Validation Endpoint...")
            obj = SmartConnect(api_key=API_KEY)
            session_data = obj.generateSession(CLIENT_CODE, PASSWORD, totp_auth)
            
            if session_data.get('status'):
                log_message("✅ REST Authentication verified! Fetching tokens...")
                auth_token = session_data['data']['jwtToken']
                feed_token = obj.getfeedToken()
                
                log_message("⏳ Spawning standalone background thread for WebSocket listener...")
                ws_thread = threading.Thread(
                    target=start_websocket_stream, 
                    args=(auth_token, feed_token), 
                    daemon=True
                )
                ws_thread.start()
                
                # Monitor initialization progress across threads
                time.sleep(2.5)
                st.rerun()
            else:
                log_message(f"❌ Session Rejected by Angel One: {session_data.get('message')}")
        except Exception as e:
            log_message(f"💥 Session Generation Crash: {str(e)}")

# =====================================================================
# 4. MONITOR RENDERING ZONE
# =====================================================================
@st.fragment(run_every=1)
def monitoring_ui_dashboard():
    st.subheader("📋 Pipeline Infrastructure Log Stream")
    if st.session_state.ws_logs:
        for log in st.session_state.ws_logs[::-1]:
            st.code(log)
            
    if st.session_state.ws_connected:
        st.subheader("🟢 Live Data Matrix")
        ui_df = pd.DataFrame.from_dict(st.session_state.live_market_data, orient='index')
        ui_df.index.name = "Token"
        ui_df.reset_index(inplace=True)
        st.dataframe(ui_df, use_container_width=True, hide_index=True)

monitoring_ui_dashboard()
