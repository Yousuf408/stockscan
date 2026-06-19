# ──────────────────────────────────────────────────────────────────────────────
# pages/5_LiveFeed.py - PRODUCTION READY (No infinite loop)
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import time
import sys
import os
from statistics import median
from datetime import datetime, date, timedelta

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST

# ── SUPABASE IMPORTS ──────────────────────────────────────────
from supabase import create_client, Client

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ── SUPABASE CONFIGURATION ────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4: VOLUME METRICS FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def get_stock_volume_history(stock_name):
    """Get historical volumes for a specific stock"""
    today = date.today()
    volumes = []
    
    for i in range(1, 6):
        past_date = (today - timedelta(days=i)).isoformat()
        
        try:
            response = supabase.table("websocket_stock_values")\
                               .select("volume")\
                               .eq("stock", stock_name)\
                               .eq("date", past_date)\
                               .execute()
            
            if response.data and response.data[0]['volume'] > 0:
                volumes.append(response.data[0]['volume'])
        except:
            continue
    
    return volumes


def calculate_volume_metrics(stock_name, current_volume, change_pct):
    """
    Calculate vol_ratio, vol_signal, and status
    Returns: (vol_ratio, vol_signal, status)
    """
    
    hist_volumes = get_stock_volume_history(stock_name)
    
    if len(hist_volumes) < 5:
        return 0, f"⏳ Building ({len(hist_volumes)}/5 days)", "WATCH"
    
    try:
        median_volume = median(hist_volumes)
    except:
        return 0, "🔴 Weak (0)", "WATCH"
    
    if median_volume == 0 or current_volume == 0:
        return 0, "🔴 Weak (0)", "WATCH"
    
    vol_ratio = current_volume / median_volume
    
    if vol_ratio > 2:
        vol_signal = f"🔥 Explosive ({vol_ratio:.2f})"
    elif vol_ratio > 1.5:
        vol_signal = f"🟢 Strong ({vol_ratio:.2f})"
    elif vol_ratio > 1:
        vol_signal = f"🟡 Build ({vol_ratio:.2f})"
    else:
        vol_signal = f"🔴 Weak ({vol_ratio:.2f})"
    
    if vol_ratio > 1.5 and change_pct > 0:
        status = "READY"
    else:
        status = "WATCH"
    
    return round(vol_ratio, 2), vol_signal, status


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5: SUPABASE UPLOAD FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def upload_to_supabase(ticks):
    """Upload live data with vol_ratio, vol_signal, status"""
    rows = []
    today = date.today().isoformat()
    
    for name, token, kind in STOCKS_WATCHLIST:
        tick = ticks.get(token, {})
        ltp = tick.get('ltp', 0)
        
        if ltp > 0:
            current_volume = int(tick.get('volume', 0))
            change_pct = float(tick.get('change_pct', 0))
            
            vol_ratio, vol_signal, status = calculate_volume_metrics(
                name, 
                current_volume,
                change_pct
            )
            
            rows.append({
                "stock": name,
                "type": "Index" if kind == "index" else "Stock",
                "ltp": float(tick.get('ltp', 0)),
                "open": float(tick.get('open', 0)),
                "high": float(tick.get('high', 0)),
                "low": float(tick.get('low', 0)),
                "change": float(tick.get('change', 0)),
                "change_percent": change_pct,
                "volume": current_volume,
                "time": str(tick.get('timestamp', '-')),
                "date": today,
                "vol_ratio": vol_ratio,
                "vol_signal": vol_signal,
                "status": status
            })
    
    if not rows:
        return False, "No data to upload"
    
    try:
        supabase.table("websocket_stock_values")\
                 .delete()\
                 .eq("date", today)\
                 .execute()
        
        response = supabase.table("websocket_stock_values").insert(rows).execute()
        return True, f"✅ Updated {len(rows)} stocks with volume signals"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6: SESSION STATE INITIALIZATION
# ──────────────────────────────────────────────────────────────────────────────

if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7: CONNECT / DISCONNECT BUTTONS
# ──────────────────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
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
                    st.success("Connected! Waiting for ticks...")
                    time.sleep(3)
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
            st.session_state.angel_creds = None
            st.rerun()

with col3:
    if st.session_state.angel_connected:
        if st.button("📤 Update to Supabase", use_container_width=True):
            ticks = angel_ws.latest_ticks
            if not ticks:
                st.warning("⚠️ No data yet. Wait for WebSocket.")
            else:
                with st.spinner("Uploading..."):
                    success, message = upload_to_supabase(ticks)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 8: DIVIDER
# ──────────────────────────────────────────────────────────────────────────────

st.divider()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 9: MAIN DISPLAY (WHEN CONNECTED)
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.angel_connected:

    # ── SECTION 9A: Debug Panel ────────────────────────────────
    with st.expander("🔍 Debug Panel", expanded=False):
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
        sample = dict(list(ticks_debug.items())[:10])
        st.json(sample)

    # ── SECTION 9B: Live Table ──────────────────────────────────
    st.subheader(f"📊 Live Prices ({len(STOCKS_WATCHLIST)} stocks)")
    
    # ✅ Auto-refresh every 2 seconds using Streamlit's built-in rerun
    if st.button("🔄 Auto-Refresh ON", use_container_width=True):
        st.session_state.auto_refresh = True
    
    # Get latest ticks
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

        # ✅ Calculate Signal & Status
        if tick and ltp > 0:
            current_volume = int(volume)
            vol_ratio, vol_signal, status = calculate_volume_metrics(
                name, 
                current_volume,
                change_pct
            )
        else:
            vol_signal = "⏳"
            status = "⏳"

        # Format based on whether we have data
        if tick:
            ltp_str = f"₹{ltp:.2f}"
            open_str = f"₹{open_p:.2f}" if open_p > 0 else "⏳"
            high_str = f"₹{high_p:.2f}" if high_p > 0 else "⏳"
            low_str = f"₹{low_p:.2f}" if low_p > 0 else "⏳"
            chng_str = f"{change:+.2f}"
            pct_str = f"{change_pct:+.2f}%"
            vol_str = f"{volume:,}" if volume > 0 else "0"
            time_str = timestamp
        else:
            ltp_str = open_str = high_str = low_str = chng_str = pct_str = vol_str = "⏳"
            time_str = "-"
            vol_signal = "⏳"
            status = "⏳"

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
            "Signal": vol_signal,
            "Status": status,
            "Time": time_str,
        })

    df = pd.DataFrame(rows)

    # Display the table
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
    )
    
    # Show refresh info
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.caption(
            f"🕐 Last refreshed: {pd.Timestamp.now().strftime('%H:%M:%S')} | "
            f"Ticks received: {len(ticks)}/{len(STOCKS_WATCHLIST)} tokens"
        )
    with col_info2:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()
    
    # Auto-refresh logic (every 2 seconds)
    if "auto_refresh" in st.session_state and st.session_state.auto_refresh:
        time.sleep(2)
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 10: DISPLAY WHEN NOT CONNECTED
# ──────────────────────────────────────────────────────────────────────────────

else:
    st.info("👆 Upar 'Connect Angel One' button dabao live data dekhne ke liye.")
    st.markdown(f"""
    ### Live Feed Setup
    - ✅ **Total Watchlist:** {len(STOCKS_WATCHLIST)} stocks (2 indices + 849 stocks)
    - ✅ Data source: `config.py`
    - ✅ Real-time updates from Angel One WebSocket
    
    ### Checklist
    - ✅ `angel_auth.py` mein credentials fill kiye?
    - ✅ `config.py` root folder mein hai?
    - ✅ `smartapi-python` installed hai?
    - ✅ Internet connection hai?
    """)
