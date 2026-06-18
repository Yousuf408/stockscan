# ╔════════════════════════════════════════════════════════════╗
# ║         ANGEL ONE - LIVE FEED WITH SUPABASE UPLOAD          ║
# ║    Real-time stock data streaming + Database storage        ║
# ╚════════════════════════════════════════════════════════════╝

# ── SECTION 1: IMPORTS ────────────────────────────────────────
import streamlit as st
import pandas as pd
import time
import sys
import os

# Custom imports from root folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST
from supabase_handler import (
    extract_stock_data_from_websocket,
    upload_stocks_to_supabase,
    get_latest_stocks_from_supabase
)


# ── SECTION 2: PAGE CONFIGURATION ────────────────────────────
st.set_page_config(
    page_title="Live Feed", 
    page_icon="📡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📡 Angel One — Live Market Feed")
st.markdown("Real-time stock prices + Save to Database")


# ── SECTION 3: SESSION STATE INITIALIZATION ──────────────────
if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "upload_status" not in st.session_state:
    st.session_state.upload_status = None


# ── SECTION 4: CONNECTION BUTTONS ────────────────────────────
st.subheader("🔌 Angel One Connection")
col1, col2, col3 = st.columns(3)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🟢 Connect Angel One", use_container_width=True, key="connect_btn"):
            with st.spinner("Logging in to Angel One..."):
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
                    st.success("✅ Connected! Waiting for ticks...")
                    time.sleep(3)
                    st.rerun()
                else:
                    st.error("❌ Login failed! Check credentials in angel_auth.py")
    else:
        st.success("🟢 Angel One Connected")

with col2:
    if st.session_state.angel_connected:
        if st.button("⛔ Disconnect", use_container_width=True, key="disconnect_btn"):
            angel_ws.stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.rerun()

with col3:
    if st.session_state.angel_connected:
        st.write("")  # Spacing

st.divider()


# ── SECTION 5: MAIN DISPLAY - LIVE DATA ──────────────────────
if st.session_state.angel_connected:

    # ── TAB 1: LIVE PRICES ───────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📊 Live Prices", "🔍 Debug Info", "💾 Database Verification"])

    with tab1:
        st.subheader(f"📈 Live Stock Prices ({len(STOCKS_WATCHLIST)} stocks)")
        
        # ── SUPABASE UPLOAD SECTION ──────────────────────────
        st.info("💡 Data updates every 2 seconds. Click 'Upload to Supabase' when ready to save.")
        
        col_upload, col_refresh = st.columns(2)
        
        with col_upload:
            upload_button = st.button(
                "📤 Upload Current Data to Supabase", 
                use_container_width=True,
                key="upload_supabase_btn"
            )
        
        with col_refresh:
            refresh_button = st.button(
                "🔄 Refresh Data", 
                use_container_width=True,
                key="refresh_data_btn"
            )
        
        # ── HANDLE UPLOAD BUTTON CLICK ───────────────────────
        if upload_button:
            ticks = angel_ws.latest_ticks
            
            if not ticks:
                st.warning("⚠️ No data received yet! Wait for WebSocket connection.")
            else:
                with st.spinner("📤 Uploading to Supabase..."):
                    # Extract data from WebSocket
                    stock_data = extract_stock_data_from_websocket(ticks, STOCKS_WATCHLIST)
                    
                    # Upload to Supabase
                    success, message, count = upload_stocks_to_supabase(stock_data)
                    
                    # Show result
                    if success:
                        st.success(message)
                        st.session_state.upload_status = (True, message, count)
                    else:
                        st.error(message)
                        st.session_state.upload_status = (False, message, 0)
        
        # ── DISPLAY LIVE TABLE ───────────────────────────────
        placeholder = st.empty()
        
        while st.session_state.angel_connected:
            # Read data from WebSocket
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
                
                # Format values
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
                st.dataframe(
                    df,
                    hide_index=True,
                    use_container_width=True,
                    height=600
                )
                
                # Status footer
                status_col1, status_col2 = st.columns(2)
                with status_col1:
                    st.caption(f"🕐 Last updated: {pd.Timestamp.now().strftime('%H:%M:%S')}")
                with status_col2:
                    st.caption(f"✅ Ticks received: {len(ticks)}/{len(STOCKS_WATCHLIST)}")
            
            time.sleep(2)  # Refresh every 2 seconds


    # ── TAB 2: DEBUG INFORMATION ─────────────────────────────
    with tab2:
        st.subheader("🔍 Debug Information")
        
        ticks_debug = angel_ws.latest_ticks
        raw_messages = angel_ws._raw_messages
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.metric("Total Tokens Received", len(ticks_debug))
            st.metric("Raw Messages Count", len(raw_messages))
        
        with col_info2:
            st.metric("Watchlist Size", len(STOCKS_WATCHLIST))
            st.metric("Connection Status", "🟢 Connected" if st.session_state.angel_connected else "🔴 Disconnected")
        
        st.write("**Tokens with data:**")
        st.write(sorted(list(ticks_debug.keys())))
        
        if raw_messages:
            st.write("**Last raw message from Angel One:**")
            st.json(raw_messages[-1])
        else:
            st.warning("No raw messages yet — WebSocket may still be connecting...")
        
        st.write("**Ticks data (sample - first 5):**")
        sample = dict(list(ticks_debug.items())[:5])
        st.json(sample)


    # ── TAB 3: DATABASE VERIFICATION ─────────────────────────
    with tab3:
        st.subheader("💾 Supabase Database Verification")
        
        st.info("View the latest records saved in your Supabase database")
        
        if st.button("🔄 Fetch Latest Records from Database", use_container_width=True):
            with st.spinner("Fetching from Supabase..."):
                records = get_latest_stocks_from_supabase(limit=20)
                
                if records:
                    df_db = pd.DataFrame(records)
                    st.success(f"✅ Found {len(records)} records in database")
                    
                    # Display in table format
                    st.dataframe(
                        df_db[[
                            "stock", "type", "ltp", "open", "high", "low", 
                            "change", "change_percent", "volume", "time", "created_at"
                        ]],
                        use_container_width=True,
                        height=400
                    )
                    
                    # Download option
                    csv = df_db.to_csv(index=False)
                    st.download_button(
                        "📥 Download as CSV",
                        csv,
                        "stocks_database.csv",
                        "text/csv"
                    )
                else:
                    st.warning("⚠️ No records found in database yet. Try uploading first!")
        
        st.divider()
        st.subheader("📊 Upload Status")
        if st.session_state.upload_status:
            success, message, count = st.session_state.upload_status
            if success:
                st.success(message)
            else:
                st.error(message)
        else:
            st.info("ℹ️ No uploads yet in this session")


# ── SECTION 6: NOT CONNECTED STATE ──────────────────────────
else:
    st.warning("⚠️ You are not connected to Angel One")
    
    col_main1, col_main2 = st.columns(2)
    
    with col_main1:
        st.markdown("""
        ### 📋 How to Use This App:
        
        1. **Connect** - Click 'Connect Angel One' button above
        2. **Wait** - WebSocket will stream live data
        3. **Upload** - Click 'Upload to Supabase' to save data
        4. **Verify** - Check Database tab to confirm
        
        """)
    
    with col_main2:
        st.markdown(f"""
        ### ✅ Setup Status:
        
        - **Watchlist:** {len(STOCKS_WATCHLIST)} stocks (2 indices + 849 stocks)
        - **Data Source:** Angel One WebSocket
        - **Database:** Supabase (websocket_stock_values table)
        
        ### 🔧 Requirements:
        - ✅ `angel_auth.py` configured with credentials
        - ✅ `config.py` with STOCKS_WATCHLIST
        - ✅ `supabase_handler.py` in root folder
        - ✅ `smartapi-python` installed
        - ✅ Internet connection active
        """)


# ── SECTION 7: SIDEBAR INFORMATION ──────────────────────────
with st.sidebar:
    st.header("ℹ️ App Information")
    
    st.subheader("🔗 Connections")
    st.write(f"**Angel One:** {'🟢 Connected' if st.session_state.angel_connected else '🔴 Disconnected'}")
    
    st.subheader("📊 Statistics")
    if st.session_state.angel_connected:
        st.write(f"**Stocks Watched:** {len(STOCKS_WATCHLIST)}")
        st.write(f"**Ticks Received:** {len(angel_ws.latest_ticks)}")
    else:
        st.write("Connect to see live statistics")
    
    st.divider()
    
    st.subheader("🛠️ Settings")
    debug_mode = st.checkbox("Enable Debug Mode", value=False)
    
    if debug_mode:
        st.write("**Debug Mode Enabled**")
        st.write(f"Session State: {st.session_state}")


# ── END OF LIVEFEED.PY ──────────────────────────────────────
