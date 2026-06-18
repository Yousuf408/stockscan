# pages/5_LiveFeed.py - SIMPLIFIED (No Supabase client creation)
# Place this file inside your pages/ folder

import streamlit as st
import pandas as pd
import time
import sys
import os

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ── Session State Init ────────────────────────────────────────
if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ── Connect / Disconnect Buttons ─────────────────────────────
col1, col2 = st.columns(2)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Logging in to Angel One..."):
                
                # Get user_id from session state (should be set by Login page)
                user_id = st.session_state.get("user_id")
                
                if not user_id:
                    st.error("❌ User ID not found. Please login from Login page first.")
                else:
                    creds = angel_login()
                    if creds:
                        st.session_state.angel_creds = creds
                        st.session_state.angel_connected = True
                        
                        angel_ws.start_websocket(
                            jwt_token=creds['jwt_token'],
                            api_key=creds['api_key'],
                            client_id=creds['client_id'],
                            feed_token=creds['feed_token'],
                        )
                        
                        # Start batch insert
                        try:
                            from supabase import create_client
                            supabase_url = st.secrets["supabase"]["url"]
                            supabase_key = st.secrets["supabase"]["key"]
                            supabase = create_client(supabase_url, supabase_key)
                            
                            angel_ws.start_batch_insert(
                                supabase_client=supabase,
                                user_id=user_id,
                                interval_seconds=15
                            )
                            st.success("✅ Connected! Ticks and batch insert running.")
                        except Exception as e:
                            st.warning(f"⚠️ Batch insert error: {e}")
                            st.info("WebSocket is running. Batch insert will retry.")
                        
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ Angel One login failed!")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            angel_ws.stop_websocket()
            angel_ws.stop_batch_insert()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.rerun()

st.divider()

# ── Main Display ──────────────────────────────────────────────
if st.session_state.angel_connected:

    # ── Debug Panel ───────────────────────────────────────────
    with st.expander("🔍 Debug Panel", expanded=False):
        raw = angel_ws._raw_messages
        ticks_debug = angel_ws.latest_ticks

        st.write(f"**Total tokens received:** {len(ticks_debug)}")

        if raw:
            st.write("**Last raw message:**")
            st.json(raw[-1])
        else:
            st.warning("No raw messages yet...")

        st.write("**Ticks sample (first 10):**")
        sample = dict(list(ticks_debug.items())[:10])
        st.json(sample)
        
        st.divider()
        st.write("**Batch Insert:**")
        st.write(f"Active: {angel_ws._batch_insert_active}")
        st.write(f"User ID: {st.session_state.user_id}")
        st.write(f"Ticks ready: {len(ticks_debug)}")

    # ── Live Table ────────────────────────────────────────────
    st.subheader(f"📊 Live Prices ({len(STOCKS_WATCHLIST)} stocks)")
    placeholder = st.empty()

    while True:
        ticks = angel_ws.latest_ticks

        rows = []
        for name, token, kind in STOCKS_WATCHLIST:
            tick = ticks.get(token, {})
            ltp = tick.get('ltp', 0)
            open_p = tick.get('open', 0)
            high_p = tick.get('high', 0)
            low_p = tick.get('low', 0)
            change = tick.get('change', 0)
            change_pct = tick.get('change_pct', 0)
            volume = tick.get('volume', 0)
            timestamp = tick.get('timestamp', '-')

            if tick:
                ltp_str = f"₹{ltp:.2f}"
                open_str = f"₹{open_p:.2f}"
                high_str = f"₹{high_p:.2f}"
                low_str = f"₹{low_p:.2f}"
                chng_str = f"{change:+.2f}"
                pct_str = f"{change_pct:+.2f}%"
                vol_str = f"{volume:,}"
                time_str = timestamp
            else:
                ltp_str = open_str = high_str = low_str = chng_str = pct_str = vol_str = "⏳"
                time_str = "-"

            rows.append({
                "Stock": name,
                "Type": "📈 Index" if kind == "index" else "🏢 Stock",
                "LTP (₹)": ltp_str,
                "Open": open_str,
                "High": high_str,
                "Low": low_str,
                "Change": chng_str,
                "Change %": pct_str,
                "Volume": vol_str,
                "Time": time_str,
            })

        df = pd.DataFrame(rows)

        with placeholder.container():
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.caption(
                f"Updated: {pd.Timestamp.now().strftime('%H:%M:%S')} | "
                f"Ticks: {len(ticks)}/{len(STOCKS_WATCHLIST)} | "
                f"DB: Every 15s"
            )

        time.sleep(2)

else:
    st.info("👆 Click 'Connect Angel One' to start live feed")
