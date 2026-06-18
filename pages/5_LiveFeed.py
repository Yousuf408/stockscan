# pages/5_LiveFeed.py - SIMPLE VERSION
# Just insert live data every 15 seconds

import streamlit as st
import pandas as pd
import time
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST
from simple_batch_insert import insert_live_data_to_db

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "last_insert_time" not in st.session_state:
    st.session_state.last_insert_time = 0

col1, col2 = st.columns(2)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Connecting..."):
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
                    st.session_state.last_insert_time = time.time()
                    st.success("✅ Connected!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Login failed!")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True):
            angel_ws.stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.rerun()

st.divider()

if st.session_state.angel_connected:
    
    with st.expander("🔍 Debug", expanded=False):
        ticks = angel_ws.latest_ticks
        st.write(f"Ticks received: {len(ticks)}")
        sample = dict(list(ticks.items())[:5])
        st.json(sample)
    
    st.subheader(f"📊 Live Prices ({len(STOCKS_WATCHLIST)} stocks)")
    placeholder = st.empty()
    insert_placeholder = st.empty()
    
    insert_counter = 0
    
    while True:
        ticks = angel_ws.latest_ticks
        
        rows = []
        for name, token, kind in STOCKS_WATCHLIST:
            tick = ticks.get(token, {})
            ltp = tick.get('ltp', 0)
            open_p = tick.get('open', 0)
            high_p = tick.get('high', 0)
            low_p = tick.get('low', 0)
            change_pct = tick.get('change_pct', 0)
            volume = tick.get('volume', 0)
            
            if tick:
                ltp_str = f"₹{ltp:.2f}"
                open_str = f"₹{open_p:.2f}"
                high_str = f"₹{high_p:.2f}"
                low_str = f"₹{low_p:.2f}"
                pct_str = f"{change_pct:+.2f}%"
                vol_str = f"{volume:,}"
            else:
                ltp_str = open_str = high_str = low_str = pct_str = vol_str = "⏳"
            
            rows.append({
                "Stock": name,
                "Type": "📈" if kind == "index" else "🏢",
                "LTP": ltp_str,
                "Open": open_str,
                "High": high_str,
                "Low": low_str,
                "Change %": pct_str,
                "Volume": vol_str,
            })
        
        df = pd.DataFrame(rows)
        
        with placeholder.container():
            st.dataframe(df, hide_index=True, use_container_width=True)
        
        # Every 15 seconds: Insert to DB
        current_time = time.time()
        if current_time - st.session_state.last_insert_time >= 15:
            try:
                from supabase import create_client
                supabase_url = st.secrets["supabase"]["url"]
                supabase_key = st.secrets["supabase"]["key"]
                supabase = create_client(supabase_url, supabase_key)
                
                user = supabase.auth.get_user()
                user_id = user.id if user else None
                
                if user_id and ticks:
                    success = insert_live_data_to_db(ticks, supabase, user_id)
                    insert_counter += 1
                    st.session_state.last_insert_time = current_time
                    
            except Exception as e:
                pass
        
        with insert_placeholder.container():
            st.caption(
                f"🕐 {pd.Timestamp.now().strftime('%H:%M:%S')} | "
                f"Ticks: {len(ticks)}/{len(STOCKS_WATCHLIST)} | "
                f"💾 Inserts: {insert_counter}"
            )
        
        time.sleep(2)

else:
    st.info("👆 Click 'Connect Angel One' to start")
