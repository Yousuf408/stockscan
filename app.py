# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  v3: Simplified — yfinance only, no AngelOne/WebSocket/HTTP
# ══════════════════════════════════════════

import sys
import streamlit as st
import os
from auth_session import restore_session

print(f"[BOOT] Python {sys.version}")
print("[BOOT] app.py loading...")

try:
    sys.path.append(os.path.dirname(__file__))
    from styles import apply_styles, sidebar_brand, page_header
    print("[BOOT] styles OK")
except Exception as _e:
    print(f"[BOOT] styles FAILED: {_e}")

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# Session restore
if not st.session_state.get("user_id"):
    restore_session()

# Auth guard
if not st.session_state.get("user_id"):
    st.warning("Please login to access this page.")
    if st.button("Go to Login →", type="primary"):
        st.switch_page("pages/0_Login.py")
    st.stop()

# Hide Streamlit default UI
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

apply_styles()
sidebar_brand()
page_header("Live Market Dashboard")

# ══════════════════════════════════════════
#  STREAMLIT DASHBOARD UI
# ══════════════════════════════════════════

st.info("📊 Dashboard loading... Connect your data source.")
