import streamlit as st
import pandas as pd
import threading
import time
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

st.set_page_config(page_title="Nifty 50 WebSocket", page_icon="⚡", layout="wide")
st.title("⚡ Nifty 50 High-Speed WebSocket Stream")

# =====================================================================
# 1. FIXED API CREDENTIALS
# =====================================================================
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"

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

# =====================================================================
# 2. PURE WEBSOCKET PIPELINE
# =====================================================================
def start_websocket_stream(auth_token, feed_token):
    try:
        clean_auth_token = auth_token.replace("Bearer ", "").strip()
        sws = SmartWebSocketV2(clean_auth_token, API_KEY, CLIENT_CODE, feed_token)

        def on_open(wsapp):
            st.session_state.ws_connected = True
            log_message("✅ Pure WebSocket Active! Subscribing to script streams...")
            token_list = [{"exchangeType": 1, "tokens": list(TRACKED_STOCKS.keys())}]
            sws.subscribe("manual_otp_stream", 2, token_list)
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

        def on_close(wsapp, *args, **kwargs):
            st.session_state.ws_connected = False
            log_message("🔌 Connection closed down by remote server.")

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        sws.connect()
        
    except Exception as thread_err:
        log_message(f"💥 Fatal exception in WebSocket Thread Engine: {str(thread_err)}")

# =====================================================================
# 3. MANUAL OTP UI INPUT PANEL
# =====================================================================
if not st.session_state.ws_connected:
    st.subheader("🔑 Secure Gateway Login")
    
    # Text input field on the UI for your 6-digit dynamic OTP
    user_otp = st.text_input(
        label="Enter the 6-Digit TOTP from your Authenticator App:", 
        max_chars=6, 
        placeholder="e.g. 123456",
        type="password"  # Hides the numbers as you type for security
    )
    
    if st.button("🔌 Connect to Live WebSocket Stream"):
        if len(user_otp) != 6 or not user_otp.isdigit():
            st.warning("Please enter a valid 6-digit numeric OTP.")
        else:
            st.session_state.ws_logs = []
            log_message("📡 Initiating handshake with manual security verification...")
            
            try:
                obj = SmartConnect(api_key=API_KEY)
                session_data = obj.generateSession(CLIENT_CODE, PASSWORD, user_otp)
                
                if session_data.get('status'):
                    log_message("✅ Dynamic Handshake Passed! Fetching pipeline authentication tickets...")
                    auth_token = session_data['data']['jwtToken']
                    feed_token = obj.getfeedToken()
                    
                    log_message("⏳ Spawning standalone background thread for WebSocket listener...")
                    ws_thread = threading.Thread(
                        target=start_websocket_stream, 
                        args=(auth_token, feed_token), 
                        daemon=True
                )
                    ws_thread.start()
                    
                    time.sleep(2.5)
                    st.rerun()
                else:
                    msg = session_data.get('message')
                    log_message(f"❌ Session Rejected: {msg}")
                    st.error(f"Authentication Failed: {msg}. Ensure your phone app clock is synced.")
            except Exception as e:
                log_message(f"💥 Integration Crash: {str(e)}")

# =====================================================================
# 4. MONITOR RENDERING ZONE
# =====================================================================
@st.fragment(run_every=1)
def monitoring_ui_dashboard():
    if st.session_state.ws_logs:
        st.subheader("📋 Pipeline Infrastructure Log Stream")
        for log in st.session_state.ws_logs[::-1]:
            st.code(log)
            
    if st.session_state.ws_connected:
        st.subheader("🟢 Live Data Matrix (Pure WebSocket Active)")
        ui_df = pd.DataFrame.from_dict(st.session_state.live_market_data, orient='index')
        ui_df.index.name = "Token"
        ui_df.reset_index(inplace=True)
        st.dataframe(ui_df, use_container_width=True, hide_index=True)

monitoring_ui_dashboard()
