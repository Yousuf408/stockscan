import streamlit as st
import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import sys, os
sys.path.append(os.path.dirname(__file__))
from styles import apply_styles, render_navbar, page_content

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

apply_styles()

# Define all pages
PAGES = [
    ("Dashboard", "app"),
    ("Sectors", "2_Sectors"),
    ("Watchlist", "3_Watchlist"),
    ("Pre-Watch", "4_PreWatch"),
    ("Scan", "5_Scan"),
    ("History", "6_History"),
    ("API", "7_API"),
    ("Settings", "8_Settings"),
]

# Render navbar
render_navbar("Dashboard", PAGES)

# Page content
page_content("Live Market Dashboard")

st.markdown("### 🚀 AngelOne WebSocket Connection")

start_btn = st.button("Connect To Live Market", key="connect_btn")
data_placeholder = st.empty()

def on_data(wsapp, message):
    with data_placeholder.container():
        st.subheader("📈 Live Market Feed")
        st.json(message)

def on_open(wsapp):
    token_list = [{"exchangeType": 1, "tokens": ["3045", "2885"]}]
    wsapp.subscribe("screener_01", 3, token_list)

if start_btn:
    st.info("🔄 Connecting to Angel One...")
    try:
        api_key     = st.secrets["API_KEY"]
        username    = st.secrets["CLIENT_CODE"]
        password    = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"]
        smartApi = SmartConnect(api_key=api_key)
        current_totp = pyotp.TOTP(totp_secret).now()
        session_data = smartApi.generateSession(username, password, current_totp)
        if session_data['status']:
            auth_token = session_data['data']['jwtToken']
            feed_token = smartApi.getfeedToken()
            st.success("✅ Login Successful!")
            sws = SmartWebSocketV2(auth_token, api_key, username, feed_token)
            sws.on_open = on_open
            sws.on_data = on_data
            sws.connect()
        else:
            st.error(f"❌ Login Failed: {session_data['message']}")
    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")

st.markdown("</div>", unsafe_allow_html=True)
