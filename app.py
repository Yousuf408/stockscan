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
    [data-testid="stToolbar"] {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)
apply_styles()

# ── Custom Sidebar Navigation ──
with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 0; text-align: center;">
        <h2 style="margin: 0; font-size: 24px;">Smart<span style="color: #16a34a;">Money</span></h2>
        <p style="color: #9ca3af; font-size: 12px; margin-top: 4px;">FOLLOW THE SMART MONEY</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("<p style='color: #9ca3af; font-size: 11px; font-weight: 600; text-transform: uppercase; margin-bottom: 12px;'>MARKET</p>", unsafe_allow_html=True)
    if st.button("📡 Live Feed", use_container_width=True, key="nav_livefeed"):
        st.switch_page("pages/1_LiveFeed.py")
    
    st.markdown("<p style='color: #9ca3af; font-size: 11px; font-weight: 600; text-transform: uppercase; margin-top: 20px; margin-bottom: 12px;'>SCANNERS</p>", unsafe_allow_html=True)
    if st.button("🚀 Momentum", use_container_width=True, key="nav_momentum"):
        st.switch_page("pages/8_MomentumScanner.py")
    if st.button("⭕ ORB Scanner", use_container_width=True, key="nav_orb"):
        st.switch_page("pages/11_ORBScanner.py")
    if st.button("📊 Breakout 4H", use_container_width=True, key="nav_breakout"):
        st.switch_page("pages/7_BreakoutScanner.py")
    if st.button("🧠 AI Scanner", use_container_width=True, key="nav_ai"):
        st.switch_page("pages/10_AIScanner.py")
    if st.button("📈 Swing Strategy", use_container_width=True, key="nav_swing"):
        st.switch_page("pages/12_SwingStrategy.py")
    if st.button("📺 TV Screener", use_container_width=True, key="nav_tv"):
        st.switch_page("pages/13_TVScreener.py")
    
    st.markdown("<p style='color: #9ca3af; font-size: 11px; font-weight: 600; text-transform: uppercase; margin-top: 20px; margin-bottom: 12px;'>TOOLS</p>", unsafe_allow_html=True)
    if st.button("📋 Watchlist", use_container_width=True, key="nav_watchlist"):
        st.switch_page("pages/6_Watchlist.py")
    if st.button("👁 Observation", use_container_width=True, key="nav_obs"):
        st.switch_page("pages/5_Observation.py")

page_header("Live Market Dashboard")
# ══════════════════════════════════════════
#  STREAMLIT DASHBOARD UI
# ══════════════════════════════════════════
st.info("📊 Dashboard loading... Connect your data source.")
