# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Main entry point + Global styles
#  AngelOne WebSocket Live Dashboard
# ══════════════════════════════════════════

import streamlit as st
import pyotp
import time
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pandas as pd

# ── Page Config ──
st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# ══════════════════════════════════════════
#  GLOBAL CSS — Applied to ALL pages
# ══════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600&display=swap');

/* ── App background ── */
.stApp { background: #0a0a0f !important; }
.block-container { padding: 1rem 1rem 0 1rem !important; }

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background: #111118 !important;
    border-right: 1px solid #ffffff15 !important;
    min-width: 220px !important;
}

/* Sidebar nav page links */
[data-testid="stSidebar"] a {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    color: #c8c8d8 !important;
    letter-spacing: 0.06em !important;
    padding: 6px 12px !important;
    border-radius: 5px !important;
    transition: all 0.2s !important;
}
[data-testid="stSidebar"] a:hover {
    color: #00e676 !important;
    background: #00e67610 !important;
}

/* Active page highlight */
[data-testid="stSidebar"] [aria-current="page"] {
    color: #00e676 !important;
    background: #00e67618 !important;
    border-left: 2px solid #00e676 !important;
}

/* Sidebar logo/header area */
[data-testid="stSidebarHeader"] {
    background: #0a0a0f !important;
    border-bottom: 1px solid #ffffff12 !important;
    padding: 12px !important;
}

/* ── SIDEBAR TOGGLE BUTTON (collapse/expand) ── */
/* When sidebar is OPEN — show the « button */
[data-testid="stSidebarCollapseButton"] button {
    background: #1a1a24 !important;
    border: 1px solid #00e676 !important;
    border-radius: 6px !important;
    color: #00e676 !important;
    width: 28px !important;
    height: 28px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    visibility: visible !important;
    opacity: 1 !important;
}
[data-testid="stSidebarCollapseButton"] button:hover {
    background: #00e67620 !important;
}

/* When sidebar is CLOSED — show the » button to reopen */
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    position: fixed !important;
    top: 14px !important;
    left: 14px !important;
    z-index: 999999 !important;
    background: #111118 !important;
    border: 1px solid #00e676 !important;
    border-radius: 6px !important;
    width: 32px !important;
    height: 32px !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    box-shadow: 0 0 10px #00e67640 !important;
}
[data-testid="collapsedControl"]:hover {
    background: #00e67620 !important;
    box-shadow: 0 0 16px #00e67660 !important;
}
[data-testid="collapsedControl"] svg {
    color: #00e676 !important;
    fill: #00e676 !important;
}

/* ── Hide default Streamlit chrome ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #ffffff20; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #00e676; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
#  SIDEBAR BRANDING
# ══════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="padding:8px 4px 16px 4px;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:15px;
      font-weight:700;color:#e8e8f0;letter-spacing:0.08em;">
        TRADE<span style="color:#00e676;">SENTRY</span>
      </div>
      <div style="font-size:9px;color:#888899;font-family:'JetBrains Mono',monospace;
      letter-spacing:0.1em;margin-top:3px;">NSE LIVE DASHBOARD</div>
    </div>
    <hr style="border:none;border-top:1px solid #ffffff12;margin:0 0 10px 0;">
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════
#  MAIN PAGE — AngelOne Live Dashboard
# ══════════════════════════════════════════
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

# ── WEBSOCKET CALLBACKS ──
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

# ── MAIN EXECUTION ──
if start_btn:
    st.info("🔄 Connecting to Angel One & Generating Session...")
    try:
        api_key    = st.secrets["API_KEY"]
        username   = st.secrets["CLIENT_CODE"]
        password   = st.secrets["PASSWORD"]
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
