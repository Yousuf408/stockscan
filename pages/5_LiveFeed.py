# pages/5_LiveFeed.py
# Place this file inside your pages/ folder
# ✅ MODIFIED: Added Supabase integration + Update Button

import streamlit as st
import pandas as pd
import time
import sys
import os

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws   # import MODULE directly — not just functions
from angel_auth import angel_login
from config import STOCKS_WATCHLIST  # ← IMPORT from config.py

# ── ✅ NEW: SUPABASE IMPORTS ─────────────────────────────────
from supabase import create_client, Client
from datetime import datetime

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ── ✅ NEW: SUPABASE CONFIGURATION ───────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── ✅ NEW: SUPABASE FUNCTIONS ───────────────────────────────

def extract_and_upload_to_supabase(ticks):
    """
    Extract data from WebSocket ticks and upload to Supabase
    """
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
        
        # Only include if we have LTP data
        if ltp > 0:
            rows.append({
                "stock": name,
                "type": "Index" if kind == "index" else "Stock",
                "ltp": float(ltp),
                "open": float(open_p),
                "high": float(high_p),
                "low": float(low_p),
                "change": float(change),
                "change_percent": float(change_pct),
                "volume": int(volume) if volume else 0,
                "time": str(timestamp)
            })
    
    if not rows:
        return False, "❌ No stock data to upload!", 0
    
    try:
        response = supabase.table("websocket_stock_values").insert(rows).execute()
        
        if response.data:
            count = len(response.data)
            return True, f"✅ Successfully uploaded {count} stocks to Supabase!", count
        else:
            return False, "⚠️ Data inserted but no response received", len(rows)
    
    except Exception as error:
        error_msg = str(error)
        if "duplicate key" in error_msg.lower():
            return False, "⚠️ Stocks already exist for today. Trying tomorrow?", 0
        elif "connection" in error_msg.lower():
            return False, "❌ Connection error! Check internet or Supabase.", 0
        else:
            return False, f"❌ Error: {error_msg}", 0

# ── Session State Init ────────────────────────────────────────
if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "upload_message" not in st.session_state:
    st.session_state.upload_message = None

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

    # ── ✅ NEW: UPLOAD BUTTON SECTION ────────────────────────
    st.subheader("💾 Database Storage")
    col_upload, col_info = st.columns([2, 1])
    
    with col_upload:
        if st.button("📤 Update to Supabase", use_container_width=True, key="upload_btn"):
            ticks = angel_ws.latest_ticks
            if not ticks:
                st.warning("⚠️ No data received yet! Wait for WebSocket connection.")
            else:
                with st.spinner("📤 Uploading to Supabase..."):
                    success, message, count = extract_and_upload_to_supabase(ticks)
                    if success:
                        st.success(message)
                        st.session_state.upload_message = message
                    else:
                        st.error(message)
                        st.session_state.upload_message = message
    
    with col_info:
        if st.session_state.upload_message:
            st.info(st.session_state.upload_message)

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

        st.write("**Full ticks dict (sample):**")
        # Show only first 10 for readability
        sample = dict(list(ticks_debug.items())[:10])
        st.json(sample)

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
                f"Ticks received: {len(ticks)}/{len(STOCKS_WATCHLIST)} tokens"
            )

        time.sleep(2)

else:
    st.info("👆 Upar 'Connect Angel One' button dabao live data dekhne ke liye.")
    st.markdown(f"""
    ### Live Feed Setup
    - ✅ **Total Watchlist:** {len(STOCKS_WATCHLIST)} stocks (2 indices + 849 stocks)
    - ✅ Data source: `config.py`
    - ✅ Real-time updates from Angel One WebSocket
    - ✅ **NEW:** Save data to Supabase with Update button
    
    ### Checklist
    - ✅ `angel_auth.py` mein credentials fill kiye?
    - ✅ `config.py` root folder mein hai?
    - ✅ `smartapi-python` installed hai?
    - ✅ Internet connection hai?
    - ✅ `supabase` package installed hai?
    """)
