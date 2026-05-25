import streamlit as st
import pyotp
import time
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pandas as pd

# Page Configuration
st.set_page_config(page_title="AngelOne Live Screener", layout="wide")


st.markdown("""
<style>
/* ── Always show sidebar toggle button ── */
[data-testid="collapsedControl"] {
    display: block !important;
    visibility: visible !important;
    background: #111118 !important;
    border: 1px solid #00e676 !important;
    border-radius: 6px !important;
    color: #00e676 !important;
}

/* ── Sidebar dark theme ── */
[data-testid="stSidebar"] {
    background: #111118 !important;
    border-right: 1px solid #ffffff12 !important;
}

/* ── Sidebar nav links ── */
[data-testid="stSidebar"] a {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    color: #c8c8d8 !important;
    letter-spacing: 0.06em !important;
}

[data-testid="stSidebar"] a:hover {
    color: #00e676 !important;
}
</style>
""", unsafe_allow_html=True)
st.title("⚡ Angel One Live WebSocket Dashboard")

# UI Elements for Controlling the App
start_btn = st.button("🚀 Connect To Live Market")
data_placeholder = st.empty()

# --- CALLBACK FUNCTIONS (WebSocket isme live data bhejega) ---

def on_data(wsapp, message):
    """
    Jab bhi Exchange se naya live tick (LTP/Volume) aayega, 
    yeh function automatically trigger hoga.
    """
    print("Live Ticks Received: ", message)
    
    # Dashboard par live data ko render karna
    with data_placeholder.container():
        st.subheader("📈 Live Market Feed (Tick-by-Tick)")
        st.write("Data incoming from Angel One servers:")
        st.json(message)

def on_open(wsapp):
    """
    Jaise hi WebSocket connection successfully open hoga,
    yeh function chalega aur stocks ko subscribe karega.
    """
    print("WebSocket Connected Successfully!")
    
    correlation_id = "screener_01"
    mode = 3 # 3 matlab SnapQuote (Isme LTP, Volume, OHLC sab milta hai)
    
    # Example Subscription List (ExchangeType 1 = NSE)
    # Tokens Example: "3045" is SBIN, "2885" is RELIANCE
    # Aap isme apni pasand ke NSE tokens add kar sakte hain
    token_list = [
        {
            "exchangeType": 1,
            "tokens": ["3045", "2885"]
        }
    ]
    
    # Stocks ko live stream ke liye subscribe karein
    wsapp.subscribe(correlation_id, mode, token_list)

# --- MAIN APP EXECUTION ---

if start_btn:
    st.info("🔄 Connecting to Angel One & Generating Session...")
    
    try:
        # 1. Streamlit Secrets se credentials securely call karna
        api_key = st.secrets["API_KEY"]
        username = st.secrets["CLIENT_CODE"]
        password = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"] # Google Authenticator ka Secret Key

        # 2. SmartConnect Session Initialize karna
        smartApi = SmartConnect(api_key=api_key)
        
        # PyOTP automatic har 30 seconds mein naya TOTP generate karega
        current_totp = pyotp.TOTP(totp_secret).now()
        
        # Angel One login request
        session_data = smartApi.generateSession(username, password, current_totp)
        
        if session_data['status']:
            auth_token = session_data['data']['jwtToken']
            feed_token = smartApi.getfeedToken()
            
            st.success("✅ Login Successful! Session Created.")
            
            # 3. WebSocket 2.0 Initialize Karna
            sws = SmartWebSocketV2(auth_token, api_key, username, feed_token)
            
            # Handshake functions assign karna
            sws.on_open = on_open
            sws.on_data = on_data
            
            st.warning("🤖 Starting Live WebSocket Stream Thread...")
            
            # Connection open karna (Yeh connection ko active rakhega)
            sws.connect()
            
        else:
            st.error(f"❌ Login Failed: {session_data['message']}")
            
    except Exception as e:
        st.error(f"⚠️ Critical Error: {str(e)}")
        st.info("Please check if your Streamlit Secrets are configured correctly.")
