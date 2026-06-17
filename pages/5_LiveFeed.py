# pages/5_LiveFeed.py
# Place this file inside your pages/ folder

import streamlit as st
import pandas as pd
import time
import sys
import os

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws   # import MODULE directly — not just functions
from angel_auth import angel_login

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ── Watchlist ─────────────────────────────────────────────────
# (Name, Token, ExchangeType)
# Indices → Mode 1 only
# Stocks  → Mode 2 (OHLC + Volume)
WATCHLIST = [
    ("NIFTY 50",   "26000", "index"),
    ("BANK NIFTY", "26009", "index"),
    ("RELIANCE",   "2885",  "stock"),
    ("INFOSYS",    "1594",  "stock"),
    ("TCS",        "11536", "stock"),
    ("HDFC BANK",  "1333",  "stock"),
]

# ── Session State Init ────────────────────────────────────────
if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None

# ── Connect / Disconnect Buttons ─────────────────────────────
col1, col2 = st.columns(2)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Logging in to Angel One..."):
                creds = angel_login()
                if creds:
                    st.session_state.angel_creds   = creds
                    st.session_state.angel_connected = True
                    angel_ws.start_websocket(
                        jwt_token  = creds['jwt_token'],
                        api_key    = creds['api_key'],
                        client_id  = creds['client_id'],
                        feed_token = creds['feed_token'],
                    )
                    st.success("Connected! Waiting for ticks...")
                    time.sleep(3)   # give WS time to connect + subscribe
                    st.rerun()
                else:
                    st.error("Login failed! Check credentials in angel_auth.py")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            angel_ws.stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds     = None
            st.rerun()

st.divider()

# ── Main Display ──────────────────────────────────────────────
if st.session_state.angel_connected:

    # ── Debug Panel (can be removed later) ───────────────────
    with st.expander("🔍 Debug Panel", expanded=False):
        # Read directly from angel_ws MODULE global
        raw = angel_ws._raw_messages
        ticks_debug = angel_ws.latest_ticks

        st.write(f"**Total tokens received:** {len(ticks_debug)}")
        st.write(f"**Tokens:** {list(ticks_debug.keys())}")

        if raw:
            st.write("**Last raw message from Angel One:**")
            st.json(raw[-1])
        else:
            st.warning("No raw messages yet — WebSocket may still be connecting...")

        st.write("**Full ticks dict:**")
        st.json(ticks_debug)

    # ── Live Table ────────────────────────────────────────────
    st.subheader("📊 Live Prices")
    placeholder = st.empty()

    while True:
        # ── Read directly from angel_ws module global ─────────
        ticks = angel_ws.latest_ticks

        rows = []
        for name, token, kind in WATCHLIST:
            tick = ticks.get(token, {})
            ltp        = tick.get('ltp', 0)
            open_p     = tick.get('open', 0)
            high_p     = tick.get('high', 0)
            low_p      = tick.get('low', 0)
            change     = tick.get('change', 0)
            change_pct = tick.get('change_pct', 0)
            volume     = tick.get('volume', 0)

            # Color logic for change
            chng_str = f"{change:+.2f}" if tick else "-"
            pct_str  = f"{change_pct:+.2f}%" if tick else "-"

            rows.append({
                "Stock"    : name,
                "Type"     : "📈 Index" if kind == "index" else "🏢 Stock",
                "LTP (₹)"  : f"₹{ltp:.2f}" if ltp else "⏳",
                "Open"     : f"₹{open_p:.2f}" if open_p else "-",
                "High"     : f"₹{high_p:.2f}" if high_p else "-",
                "Low"      : f"₹{low_p:.2f}" if low_p else "-",
                "Change"   : chng_str,
                "Change %" : pct_str,
                "Volume"   : f"{volume:,}" if volume else "-",
                "Time"     : tick.get('timestamp', '-'),
            })

        df = pd.DataFrame(rows)

        with placeholder.container():
            st.dataframe(
                df,
                hide_index=True,
                use_container_width=True,
                height=310,
            )
            st.caption(
                f"🕐 Page refreshed: {pd.Timestamp.now().strftime('%H:%M:%S')} | "
                f"Ticks received: {len(ticks)} tokens"
            )

        time.sleep(2)

else:
    st.info("👆 Upar 'Connect Angel One' button dabao live data dekhne ke liye.")
    st.markdown("""
    ### Setup Checklist
    - ✅ `angel_auth.py` mein credentials fill kiye?
    - ✅ `smartapi-python` installed hai?
    - ✅ Internet connection hai?
    """)
