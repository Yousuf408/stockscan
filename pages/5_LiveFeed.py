# pages/5_LiveFeed.py
import streamlit as st
import pandas as pd
import time
from angel_auth import angel_login
from angel_ws import start_websocket, stop_websocket, get_latest_ticks

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ─── JO STOCKS TRACK KARNE HAIN ──────────────────────────────
# Format: (Name, NSE Token, exchangeType)
# exchangeType: 1=NSE, 2=NFO, 3=BSE
WATCHLIST = [
    ("NIFTY 50",   "26000", 1),
    ("BANK NIFTY", "26009", 1),
    ("RELIANCE",   "2885",  1),
    ("INFOSYS",    "1594",  1),
    ("TCS",        "11536", 1),
    ("HDFC BANK",  "1333",  1),
]
# ─────────────────────────────────────────────────────────────

# Token list angel_ws ke liye
TOKEN_LIST = [
    {
        "exchangeType": 1,
        "tokens": [t for _, t, ex in WATCHLIST if ex == 1]
    }
]

# ─── SESSION STATE SETUP ──────────────────────────────────────
if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None

# ─── CONNECT / DISCONNECT BUTTONS ────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Logging in to Angel One..."):
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
                    st.success("Connected! Live data aa raha hai...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Login failed! Credentials check karo.")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.rerun()

st.divider()

# ─── LIVE DATA TABLE ─────────────────────────────────────────
if st.session_state.angel_connected:

    # Auto refresh every 2 seconds
    refresh = st.empty()
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
                "Stock"      : name,
                "LTP (₹)"    : f"{ltp:.2f}" if ltp else "⏳ Waiting...",
                "Open"       : f"{tick.get('open', 0):.2f}",
                "High"       : f"{tick.get('high', 0):.2f}",
                "Low"        : f"{tick.get('low', 0):.2f}",
                "Change"     : f"{change:+.2f}",
                "Change %"   : f"{change_pct:+.2f}%",
                "Volume"     : tick.get('volume', '-'),
            })

        df = pd.DataFrame(rows)

        with placeholder.container():
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=300
            )
            st.caption(f"🕐 Last updated: {pd.Timestamp.now().strftime('%H:%M:%S')}")

        time.sleep(2)
        placeholder.empty()

else:
    st.info("👆 Upar 'Connect Angel One' button dabao live data dekhne ke liye.")
    
