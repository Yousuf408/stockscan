import streamlit as st
import pyotp
import time
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pandas as pd

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');

/* App background */
.stApp { background: #0a0a0f !important; }
.block-container { padding: 1rem !important; }

/* Hide only footer and menu, NOT header (header has sidebar toggle) */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: #111118 !important;
    border-right: 1px solid #ffffff15 !important;
}
[data-testid="stSidebar"] a {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    color: #c8c8d8 !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stSidebar"] a:hover {
    color: #00e676 !important;
}
[data-testid="stSidebar"] [aria-current="page"] {
    color: #00e676 !important;
    background: #00e67618 !important;
}

/* Sidebar toggle button — always green and visible */
button[kind="header"] {
    background: #111118 !important;
    border: 1px solid #00e676 !important;
    border-radius: 6px !important;
    color: #00e676 !important;
}

/* Collapsed control — the reopen arrow */
[data-testid="collapsedControl"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    background: #111118 !important;
    border: 1px solid #00e676 !important;
    border-radius: 6px !important;
    color: #00e676 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #ffffff25; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #00e676; }
</style>
""", unsafe_allow_html=True)

# Sidebar branding
with st.sidebar:
    st.markdown("""
    <div style="padding:8px 4px 12px 4px;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:14px;
      font-weight:700;color:#e8e8f0;">
        TRADE<span style="color:#00e676;">SENTRY</span>
      </div>
      <div style="font-size:9px;color:#888899;font-family:'JetBrains Mono',
      monospace;margin-top:2px;">NSE LIVE DASHBOARD</div>
    </div>
    <hr style="border:none;border-top:1px solid #ffffff12;margin-bottom:8px;">
    """, unsafe_allow_html=True)

# Main page
st.markdown("""
<div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;
color:#e8e8f0;padding:4px 0 20px 0;">
TRADE<span style="color:#00e676;">SENTRY</span>
<span style="font-size:12px;color:#888899;margin-left:10px;font-weight:400;">
⚡ Live Market Dashboard</span>
</div>
""", unsafe_allow_html=True)

start_btn = st.button("🚀 Connect To Live Market")
data_placeholder = st.empty()

def on_data(wsapp, message):
    print("Live Ticks Received: ", message)
    with data_placeholder.container():
        st.subheader("📈 Live Market Feed (Tick-by-Tick)")
        st.write("Data incoming from Angel One servers:")
        st.json(message)

def on_open(wsapp):
    print("WebSocket Connected Successfully!")
    correlation_id = "screener_01"
    mode = 3
    token_list = [{"exchangeType": 1, "tokens": ["3045", "2885"]}]
    wsapp.subscribe(correlation_id, mode, token_list)

if start_btn:
    st.info("🔄 Connecting to Angel One & Generating Session...")
    try:
        api_key     = st.secrets["API_KEY"]
        username    = st.secrets["CLIENT_CODE"]
        password    = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"]

        smartApi     = SmartConnect(api_key=api_key)
        current_totp = pyotp.TOTP(totp_secret).now()
        session_data = smartApi.generateSession(username, password, current_totp)

        if session_data['status']:
            auth_token = session_data['data']['jwtToken']
            feed_token = smartApi.getfeedToken()
            st.success("✅ Login Successful! Session Created.")
            sws = SmartWebSocketV2(auth_token, api_key, username, feed_token)
            sws.on_open = on_open
            sws.on_data = on_data
            st.warning("🤖 Starting Live WebSocket Stream Thread...")
            sws.connect()
        else:
            st.error(f"❌ Login Failed: {session_data['message']}")
    except Exception as e:
        st.error(f"⚠️ Critical Error: {str(e)}")
        st.info("Please check your Streamlit Secrets are configured correctly.")
