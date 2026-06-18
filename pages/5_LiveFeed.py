# pages/5_LiveFeed.py - COMPLETE WITH BATCH INSERT
# Place this file inside your pages/ folder

import streamlit as st
import pandas as pd
import time
import sys
import os

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws   # import MODULE directly — not just functions
from angel_ws import start_batch_insert, stop_batch_insert  # ← NEW: Import batch functions
from angel_auth import angel_login
from config import STOCKS_WATCHLIST  # ← IMPORT from config.py

# Import Supabase
from supabase import create_client
import streamlit_authenticator as stauth

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ── Initialize Supabase ──────────────────────────────────────
@st.cache_resource
def init_supabase():
    """Initialize Supabase client."""
    # Get credentials from secrets
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"❌ Supabase connection failed: {e}")
    st.stop()

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
                # ── NEW: Get user_id from Supabase auth ──────────────
                try:
                    user = supabase.auth.get_user()
                    user_id = user.id if user else None
                    
                    if not user_id:
                        st.error("❌ Not logged in! Please login from Login page first.")
                    else:
                        creds = angel_login()
                        if creds:
                            st.session_state.angel_creds   = creds
                            st.session_state.user_id       = user_id  # ← Store user_id
                            st.session_state.angel_connected = True
                            
                            angel_ws.start_websocket(
                                jwt_token  = creds['jwt_token'],
                                api_key    = creds['api_key'],
                                client_id  = creds['client_id'],
                                feed_token = creds['feed_token'],
                            )
                            
                            # ── NEW: Start batch insert in background ────
                            start_batch_insert(
                                supabase_client=supabase,
                                user_id=user_id,
                                interval_seconds=15
                            )
                            # ─────────────────────────────────────────────
                            
                            st.success("✅ Connected! Waiting for ticks...")
                            time.sleep(3)
                            st.rerun()
                        else:
                            st.error("❌ Login failed! Check credentials in angel_auth.py")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            angel_ws.stop_websocket()
            stop_batch_insert()  # ← NEW: Stop batch insert
            st.session_state.angel_connected = False
            st.session_state.angel_creds     = None
            st.session_state.user_id         = None
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
        st.write(f"**Tokens with data:** {sorted(list(ticks_debug.keys()))}")

        if raw:
            st.write("**Last raw message from Angel One:**")
            st.json(raw[-1])
        else:
            st.warning("No raw messages yet — WebSocket may still be connecting...")

        st.write("**Full ticks dict (sample - first 10):**")
        # Show only first 10 for readability
        sample = dict(list(ticks_debug.items())[:10])
        st.json(sample)
        
        # ── NEW: Batch insert status ─────────────────────────
        st.divider()
        st.write("**Batch Insert Status:**")
        st.write(f"🔄 Active: {angel_ws._batch_insert_active}")
        st.write(f"👤 User ID: {st.session_state.user_id}")
        st.write(f"📦 Ticks ready for insert: {len(ticks_debug)}")
        # ─────────────────────────────────────────────────────

    # ── Live Table ────────────────────────────────────────────
    st.subheader(f"📊 Live Prices ({len(STOCKS_WATCHLIST)} stocks)")
    placeholder = st.empty()

    while True:
        # ── Read directly from angel_ws module global ─────────
        ticks = angel_ws.latest_ticks

        rows = []
        for name, token, kind in STOCKS_WATCHLIST:
            tick = ticks.get(token, {})
            ltp        = tick.get('ltp', 0)
            open_p     = tick.get('open', 0)
            high_p     = tick.get('high', 0)
            low_p      = tick.get('low', 0)
            change     = tick.get('change', 0)
            change_pct = tick.get('change_pct', 0)
            volume     = tick.get('volume', 0)
            timestamp  = tick.get('timestamp', '-')

            # Format based on whether we have data
            if tick:
                ltp_str    = f"₹{ltp:.2f}"
                open_str   = f"₹{open_p:.2f}"
                high_str   = f"₹{high_p:.2f}"
                low_str    = f"₹{low_p:.2f}"
                chng_str   = f"{change:+.2f}"
                pct_str    = f"{change_pct:+.2f}%"
                vol_str    = f"{volume:,}"
                time_str   = timestamp
            else:
                ltp_str = open_str = high_str = low_str = chng_str = pct_str = vol_str = "⏳"
                time_str = "-"

            rows.append({
                "Stock"    : name,
                "Type"     : "📈 Index" if kind == "index" else "🏢 Stock",
                "LTP (₹)"  : ltp_str,
                "Open"     : open_str,
                "High"     : high_str,
                "Low"      : low_str,
                "Change"   : chng_str,
                "Change %" : pct_str,
                "Volume"   : vol_str,
                "Time"     : time_str,
            })

        df = pd.DataFrame(rows)

        with placeholder.container():
            st.dataframe(
                df,
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                f"🕐 Page refreshed: {pd.Timestamp.now().strftime('%H:%M:%S')} | "
                f"Ticks received: {len(ticks)}/{len(STOCKS_WATCHLIST)} tokens | "
                f"💾 DB updating every 15 seconds"
            )

        time.sleep(2)

else:
    st.info("👆 Upar 'Connect Angel One' button dabao live data dekhne ke liye.")
    st.markdown(f"""
    ### Live Feed Setup
    - ✅ **Total Watchlist:** {len(STOCKS_WATCHLIST)} stocks (2 indices + 849 stocks)
    - ✅ Data source: `config.py`
    - ✅ Real-time updates from Angel One WebSocket
    - ✅ Automatic batch insert to swing_live_data table every 15 seconds
    
    ### Checklist
    - ✅ `angel_auth.py` mein credentials fill kiye?
    - ✅ `config.py` root folder mein hai?
    - ✅ `smartapi-python` installed hai?
    - ✅ Internet connection hai?
    - ✅ Login page se pehle login kiya hai?
    """)
