import streamlit as st
import pyotp
import pandas as pd
import threading
import time
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

st.set_page_config(page_title="Nifty 50 Real-Time Feed", page_icon="⚡", layout="wide")
st.title("⚡ Nifty 50 High-Speed WebSocket Stream")
st.markdown("Stress testing 50 highly liquid constituents simultaneously using a dedicated background worker pipeline.")

# =====================================================================
# 1. API CREDENTIALS
# =====================================================================
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"  # Alphanumeric secret key string


# =====================================================================
# 2. COMPLETE NIFTY 50 INDEX TOKENS (HARDCODED FOR ZERO LATENCY)
# =====================================================================
TRACKED_STOCKS = {
    "1398": "RELIANCE-EQ", "1333": "HDFCBANK-EQ", "11536": "TCS-EQ", "1594": "INFY-EQ",
    "4124": "ICICIBANK-EQ", "3045": "SBIN-EQ", "10604": "BHARTIARTL-EQ", "1660": "ITC-EQ",
    "3456": "TATAMOTORS-EQ", "11630": "NIFTY-BEES", "236": "ASIANPAINT-EQ", "3351": "LT-EQ",
    "5258": "INDUSINDBK-EQ", "547": "BPCL-EQ", "2031": "M&M-EQ", "11723": "HCLTECH-EQ",
    "3506": "TITAN-EQ", "1363": "MARUTI-EQ", "11483": "TECHM-EQ", "17963": "NESTLEIND-EQ",
    "1406": "SUNPHARMA-EQ", "11523": "ULTRACEMCO-EQ", "1232": "KOTAKBANK-EQ", "1348": "JSWSTEEL-EQ",
    "694": "CIPLA-EQ", "0": "ADANIENT-EQ", "15083": "ADANIPORTS-EQ", "2475": "BAJAJ-AUTO-EQ",
    "16675": "BAJAJFINSV-EQ", "317": "BAJFINANCE-EQ", "4204": "BRITANNIA-EQ", "4717": "COALINDIA-EQ",
    "10940": "DIVISLAB-EQ", "881": "DRREDDY-EQ", "910": "EICHERMOT-EQ", "14366": "GRASIM-EQ",
    "1224": "HINDALCO-EQ", "1330": "HINDUNILVR-EQ", "5097": "POWERGRID-EQ", "2412": "NTPC-EQ",
    "2885": "ONGC-EQ", "11805": "TATACONSUM-EQ", "3432": "TATASTEEL-EQ", "11532": "WIPRO-EQ",
    "7229": "APOLLOHOSP-EQ", "1913": "HDFCLIFE-EQ", "18391": "SBI LIFE-EQ", "4963": "ICICIGI-EQ",
    "21770": "LTIM-EQ", "14977": "SHRIRAMFIN-EQ"
}

# Session Initialization
if "live_market_data" not in st.session_state:
    st.session_state.live_market_data = {
        token: {"Symbol": sym, "Price": 0.0, "Volume": 0}
        for token, sym in TRACKED_STOCKS.items()
    }
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False
if "ws_logs" not in st.session_state:
    st.session_state.ws_logs = []

def log_message(msg):
    st.session_state.ws_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

# =====================================================================
# 3. HIGH-SPEED WEBSOCKET CLIENT RUNNER
# =====================================================================
def start_websocket_stream(auth_token, feed_token):
    clean_auth_token = auth_token.replace("Bearer ", "").strip()
    sws = SmartWebSocketV2(clean_auth_token, API_KEY, CLIENT_CODE, feed_token)

    def on_open(wsapp):
        st.session_state.ws_connected = True
        log_message("✅ Connected to SmartWebSocketV2 Platform.")
        
        # Subscribe all 50 tokens at once
        token_list = [{"exchangeType": 1, "tokens": list(TRACKED_STOCKS.keys())}]
        sws.subscribe("nifty50_load_test", 2, token_list)
        log_message(f"📡 Dispatched subscription mapping packet for {len(TRACKED_STOCKS)} stocks.")

    def on_data(wsapp, message):
        token = message.get("token")
        if token in st.session_state.live_market_data:
            # Memory injection updates happen concurrently here
            st.session_state.live_market_data[token].update({
                "Price": message.get("last_traded_price", 0.0) / 100.0 if "last_traded_price" in message else st.session_state.live_market_data[token]["Price"],
                "Volume": message.get("volume_trade_for_the_day", 0) if "volume_trade_for_the_day" in message else st.session_state.live_market_data[token]["Volume"]
            })

    def on_error(wsapp, error):
        log_message(f"❌ Socket Interface Exception: {str(error)}")

    def on_close(wsapp, close_status_code, close_msg):
        st.session_state.ws_connected = False
        log_message(f"🔌 Pipe Closed. Code: {close_status_code} | Msg: {close_msg}")

    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close
    
    sws.connect()

# =====================================================================
# 4. HANDSHAKE FLOW INITIALIZATION
# =====================================================================
if not st.session_state.ws_connected:
    if st.button("🔌 Boot Nifty 50 Live Stream"):
        st.session_state.ws_logs = []
        obj = SmartConnect(api_key=API_KEY)
        try:
            totp_auth = pyotp.TOTP(TOTP_SECRET).now()
            log_message("🔑 Triggering authentication request credentials...")
            session_data = obj.generateSession(CLIENT_CODE, PASSWORD, totp_auth)
            
            if session_data.get('status'):
                auth_token = session_data['data']['jwtToken']
                feed_token = obj.getfeedToken()
                
                ws_thread = threading.Thread(
                    target=start_websocket_stream, 
                    args=(auth_token, feed_token), 
                    daemon=True
                )
                ws_thread.start()
                time.sleep(2)
                st.rerun()
            else:
                log_message(f"❌ Session Generation Failure: {session_data.get('message')}")
        except Exception as e:
            log_message(f"💥 Worker Thread Allocation Error: {str(e)}")

# =====================================================================
# 5. STREAMING DASHBOARD RENDERING UNIT
# =====================================================================
st.subheader("📋 Pipeline Infrastructure Log Stream")
for log in st.session_state.ws_logs[::-1]:
    st.code(log)

if st.session_state.ws_connected:
    # Fragment forces the UI component to redraw at 1-second intervals
    @st.fragment(run_every=1)
    def render_live_view():
        ui_df = pd.DataFrame.from_dict(st.session_state.live_market_data, orient='index')
        ui_df.index.name = "Token"
        ui_df.reset_index(inplace=True)
        
        st.subheader("🟢 Live Data Matrix (50 / 50 Tracks Processing)")
        st.dataframe(ui_df, use_container_width=True, hide_index=True)
    render_live_view()
