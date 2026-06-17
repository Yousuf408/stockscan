# pages/5_LiveFeed.py
import streamlit as st
import pandas as pd
import time
from angel_auth import angel_login
from angel_ws import start_websocket, stop_websocket, get_latest_ticks

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

WATCHLIST = [
    ("NIFTY 50",   "26000", 1),
    ("BANK NIFTY", "26009", 1),
    ("RELIANCE",   "2885",  1),
    ("INFOSYS",    "1594",  1),
    ("TCS",        "11536", 1),
    ("HDFC BANK",  "1333",  1),
]

TOKEN_LIST = [{"exchangeType": 1, "tokens": [t for _, t, _ in WATCHLIST]}]

if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "latest_ticks" not in st.session_state:
    st.session_state.latest_ticks = {}

col1, col2 = st.columns([1, 1])

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Logging in..."):
                creds = angel_login()
                if creds:
                    st.session_state.angel_creds = creds
                    st.session_state.angel_connected = True
                    start_websocket(
                        jwt_token  = creds['jwt_token'],
                        api_key    = creds['api_key'],
                        client_id  = creds['client_id'],
                        feed_token = creds['feed_token'],
                        token_list = TOKEN_LIST
                    )
                    st.success("Connected!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Login failed!")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.session_state.latest_ticks = {}
            st.rerun()

st.divider()

if st.session_state.angel_connected:

    placeholder = st.empty()

    while True:
        ticks = get_latest_ticks()

        rows = []
        for name, token, _ in WATCHLIST:
            tick = ticks.get(token, {})
            ltp        = tick.get('ltp', 0)
            change     = tick.get('change', 0)
            change_pct = tick.get('change_pct', 0)
            rows.append({
                "Stock"    : name,
                "LTP (₹)"  : f"₹{ltp:.2f}" if ltp else "⏳ Waiting...",
                "Open"     : f"₹{tick.get('open', 0):.2f}" if tick else "-",
                "High"     : f"₹{tick.get('high', 0):.2f}" if tick else "-",
                "Low"      : f"₹{tick.get('low', 0):.2f}" if tick else "-",
                "Change"   : f"{change:+.2f}" if tick else "-",
                "Change %" : f"{change_pct:+.2f}%" if tick else "-",
                "Volume"   : f"{tick.get('volume', 0):,}" if tick else "-",
            })

        df = pd.DataFrame(rows)

        with placeholder.container():
            st.dataframe(df, hide_index=True, use_container_width=True, height=300)
            st.caption(f"🕐 Last updated: {pd.Timestamp.now().strftime('%H:%M:%S')}")

        time.sleep(2)

else:
    st.info("👆 Connect Angel One button dabao.")
