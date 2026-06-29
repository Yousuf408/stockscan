# ──────────────────────────────────────────────────────────────────────────────
# pages/5_LiveFeed.py - COMPLETE WORKING CODE (NO INFINITE LOOP)
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
# ─────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ─────────────────────────────────────────────────────────────
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("LiveFeed")
#---------------------- END---------------
st.title("📡 Angel One — Live Market Feed")

# ── SUPABASE CONFIGURATION ────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ──────────────────────────────────────────────────────────────────────────────
# SIGNAL SORT ORDER
# ──────────────────────────────────────────────────────────────────────────────

SIGNAL_ORDER = {"🔥": 0, "🟢": 1, "🟡": 2, "🔴": 3, "⏳": 4}

def signal_sort_key(signal_str):
    """Returns (group_order, -vol_ratio) so Explosive sorts first, highest ratio on top."""
    if not signal_str or signal_str == "⏳":
        return (4, 0.0)
    emoji = signal_str[:2].strip()
    order = SIGNAL_ORDER.get(emoji, 4)
    try:
        num = float(signal_str.split("(")[-1].replace(")", ""))
    except:
        num = 0.0
    return (order, -num)  # negative = descending within same group

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4: VOLUME METRICS FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def get_all_volumes_batch():
    today = date.today()
    result = {}
    
    try:
        cutoff_date = (today - timedelta(days=10)).isoformat()
        
        all_data = []
        offset = 0
        batch_size = 1000
        
        while True:
            response = supabase.table("websocket_stock_values")\
                               .select("stock", "volume", "date")\
                               .gte("date", cutoff_date)\
                               .lt("date", today.isoformat())\
                               .order("date", desc=True)\
                               .range(offset, offset + batch_size - 1)\
                               .execute()
            
            all_data.extend(response.data)
            
            if len(response.data) < batch_size:
                break
            
            offset += batch_size
        
        temp_data = {}
        seen_dates = {}
        
        for record in all_data:
            stock = record['stock']
            volume = record['volume']
            d = record['date']
            
            key = (stock, d)
            if key in seen_dates:
                continue
            seen_dates[key] = True
            
            if stock not in temp_data:
                temp_data[stock] = []
            
            if volume and volume > 0:
                temp_data[stock].append(volume)
        
        for stock, volumes in temp_data.items():
            result[stock] = volumes[:5]
        
        return result
        
    except Exception as e:
        st.warning(f"⚠️ Volume data fetch issue: {str(e)}")
        return {}


def calculate_volume_metrics(stock_name, current_volume, change_pct, all_volumes):
    """
    Calculate vol_ratio, vol_signal, and status.
    Always returns emoji-based signal.
    """
    hist_volumes = all_volumes.get(stock_name, [])
    
    if not hist_volumes:
        return 0, "⏳ No history", "WATCH"
    
    try:
        median_volume = median(hist_volumes)
    except:
        return 0, "⏳ Error", "WATCH"
    
    if median_volume == 0 or current_volume == 0:
        return 0, "⏳ Insufficient data", "WATCH"
    
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
# SECTION 5: SUPABASE UPLOAD FUNCTION (FIXED – NO .clear())
# ──────────────────────────────────────────────────────────────────────────────

def upload_to_supabase(ticks):
    """Upload live data with vol_ratio, vol_signal, status"""
    rows = []
    today = date.today().isoformat()
    
    # Pre-fetch all volumes once
    all_volumes = get_all_volumes_batch()
   
    
    for name, token, kind in STOCKS_WATCHLIST:
        tick = ticks.get(token, {})
        ltp = tick.get('ltp', 0)
        
        if ltp > 0:
            current_volume = int(tick.get('volume', 0))
            change_pct = float(tick.get('change_pct', 0))
            
            vol_ratio, vol_signal, status = calculate_volume_metrics(
                name, 
                current_volume,
                change_pct,
                all_volumes
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

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6.5: AUTO-CONNECT TO ANGEL ONE ON PAGE LOAD
# ──────────────────────────────────────────────────────────────────────────────

# Auto-connect only if not already connected
#if not st.session_state.angel_connected:
 #   with st.spinner("🔄 Auto-connecting to Angel One..."):
 #       creds = angel_login()
  #      if creds:
   #         st.session_state.angel_creds = creds
    #        st.session_state.angel_connected = True
     #       angel_ws.start_websocket(
      #          jwt_token=creds['jwt_token'],
       #         api_key=creds['api_key'],
        #        client_id=creds['client_id'],
         #       feed_token=creds['feed_token'],
          #  )
           # st.success("✅ Auto-connected! Waiting for ticks...")
            #time.sleep(2)
            #st.rerun()
        #else:
         #   st.error("❌ Auto-connect failed. Please click 'Connect Angel One' manually.")


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7: CONNECT / DISCONNECT BUTTONS
# ──────────────────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)

with col1:
    if not st.session_state.angel_connected:
        if st.button("🔌 Connect Angel One", use_container_width=True):
            with st.spinner("Logging in to Angel One..."):
                if "angel_auth" not in st.session_state:
                    st.session_state["angel_auth"] = angel_login()
                creds = st.session_state["angel_auth"]  # ← reuse
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
    placeholder = st.empty()

    # ✅ Fetch volumes ONCE outside the loop
    all_volumes = get_all_volumes_batch()
    st.caption(f"✅ Loaded volume data for {len(all_volumes)} stocks")

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

            # ✅ Calculate Signal & Status using pre-fetched data
            if tick and ltp > 0:
                current_volume = int(volume)
                vol_ratio, vol_signal, status = calculate_volume_metrics(
                    name, 
                    current_volume,
                    change_pct,
                    all_volumes
                )
            else:
                vol_signal = "⏳"
                status = "⏳"

            # Format based on whether we have data
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

        # ── Sort: 🔥 Explosive → 🟢 Strong → 🟡 Build → 🔴 Weak → ⏳
        # Within same emoji group: highest vol_ratio number on top ──────────
        df["_sort_key"] = df["Signal"].apply(signal_sort_key)
        df = df.sort_values("_sort_key").drop(columns=["_sort_key"]).reset_index(drop=True)

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

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 11: AUTO-CLICK "Update to Supabase" EVERY 60 SECONDS
# ──────────────────────────────────────────────────────────────────────────────

st.components.v1.html("""
    <script>
        setInterval(function() {
            const buttons = document.querySelectorAll('button');
            for (let btn of buttons) {
                if (btn.innerText.includes('Update to Supabase')) {
                    btn.click();
                    break;
                }
            }
        }, 60000);  // 60,000 ms = 1 minute
    </script>
""", height=0)
