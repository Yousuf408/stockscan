# ──────────────────────────────────────────────────────────────────────────────
# pages/5_LiveFeed.py - PRODUCTION READY (OPTION A — raw ticks, no Signal in table)
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

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Live Feed", page_icon="📡", layout="wide")
st.title("📡 Angel One — Live Market Feed")

# ──────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT (cached — no reconnect on every rerun)
# ──────────────────────────────────────────────────────────────────────────────

SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()


# ──────────────────────────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ──────────────────────────────────────────────────────────────────────────────

if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False
if "angel_creds" not in st.session_state:
    st.session_state.angel_creds = None
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True


# ──────────────────────────────────────────────────────────────────────────────
# VOLUME METRICS — used ONLY in upload_to_supabase(), NOT in table display
# ──────────────────────────────────────────────────────────────────────────────

def get_stock_volume_history(stock_name: str) -> list:
    """Get last 5 days historical volumes for a stock from Supabase."""
    today = date.today()
    volumes = []
    for i in range(1, 6):
        past_date = (today - timedelta(days=i)).isoformat()
        try:
            resp = supabase.table("websocket_stock_values") \
                           .select("volume") \
                           .eq("stock", stock_name) \
                           .eq("date", past_date) \
                           .execute()
            if resp.data and resp.data[0]["volume"] > 0:
                volumes.append(resp.data[0]["volume"])
        except Exception:
            continue
    return volumes


def calculate_volume_metrics(stock_name: str, current_volume: int, change_pct: float):
    """Returns: (vol_ratio, vol_signal, status)"""
    hist = get_stock_volume_history(stock_name)

    if len(hist) < 5:
        return 0.0, f"⏳ Building ({len(hist)}/5 days)", "WATCH"

    try:
        med = median(hist)
    except Exception:
        return 0.0, "🔴 Weak (0)", "WATCH"

    if med == 0 or current_volume == 0:
        return 0.0, "🔴 Weak (0)", "WATCH"

    vol_ratio = current_volume / med

    if vol_ratio > 2:
        vol_signal = f"🔥 Explosive ({vol_ratio:.2f})"
    elif vol_ratio > 1.5:
        vol_signal = f"🟢 Strong ({vol_ratio:.2f})"
    elif vol_ratio > 1:
        vol_signal = f"🟡 Build ({vol_ratio:.2f})"
    else:
        vol_signal = f"🔴 Weak ({vol_ratio:.2f})"

    status = "READY" if (vol_ratio > 1.5 and change_pct > 0) else "WATCH"
    return round(vol_ratio, 2), vol_signal, status


# ──────────────────────────────────────────────────────────────────────────────
# SUPABASE UPLOAD — computes Signal/Status here, not in table
# ──────────────────────────────────────────────────────────────────────────────

def upload_to_supabase(ticks: dict):
    """Upload live ticks with volume signals to Supabase."""
    today = date.today().isoformat()
    rows = []

    for name, token, kind in STOCKS_WATCHLIST:
        tick = ticks.get(token, {})
        ltp  = tick.get("ltp", 0)
        if ltp <= 0:
            continue

        current_volume = int(tick.get("volume", 0))
        change_pct     = float(tick.get("change_pct", 0))

        vol_ratio, vol_signal, status = calculate_volume_metrics(
            name, current_volume, change_pct
        )

        rows.append({
            "stock":          name,
            "type":           "Index" if kind == "index" else "Stock",
            "ltp":            float(ltp),
            "open":           float(tick.get("open", 0)),
            "high":           float(tick.get("high", 0)),
            "low":            float(tick.get("low", 0)),
            "change":         float(tick.get("change", 0)),
            "change_percent": change_pct,
            "volume":         current_volume,
            "time":           str(tick.get("timestamp", "-")),
            "date":           today,
            "vol_ratio":      vol_ratio,
            "vol_signal":     vol_signal,
            "status":         status,
        })

    if not rows:
        return False, "No LTP data to upload"

    try:
        supabase.table("websocket_stock_values") \
                .delete() \
                .eq("date", today) \
                .execute()
        supabase.table("websocket_stock_values").insert(rows).execute()
        return True, f"✅ Updated {len(rows)} stocks with volume signals"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# BUILD DISPLAY DATAFRAME — raw ticks only, ZERO Supabase calls
# Signal/Status columns removed from here (computed only on upload)
# ──────────────────────────────────────────────────────────────────────────────

def build_dataframe(ticks: dict) -> pd.DataFrame:
    rows = []
    for name, token, kind in STOCKS_WATCHLIST:
        tick     = ticks.get(token, {})
        ltp      = tick.get("ltp", 0)
        has_data = bool(tick) and ltp > 0

        if has_data:
            open_p     = tick.get("open", 0)
            high_p     = tick.get("high", 0)
            low_p      = tick.get("low", 0)
            change     = tick.get("change", 0)
            change_pct = tick.get("change_pct", 0)
            volume     = int(tick.get("volume", 0))
            timestamp  = tick.get("timestamp", "-")

            rows.append({
                "Stock":   name,
                "Type":    "📈 Index" if kind == "index" else "🏢 Stock",
                "LTP (₹)": f"₹{ltp:.2f}",
                "Open":    f"₹{open_p:.2f}" if open_p > 0 else "-",
                "High":    f"₹{high_p:.2f}" if high_p > 0 else "-",
                "Low":     f"₹{low_p:.2f}"  if low_p  > 0 else "-",
                "Change":  f"{change:+.2f}",
                "Chg %":   f"{change_pct:+.2f}%",
                "Volume":  f"{volume:,}" if volume > 0 else "0",
                "Time":    str(timestamp),
            })
        else:
            rows.append({
                "Stock":   name,
                "Type":    "📈 Index" if kind == "index" else "🏢 Stock",
                "LTP (₹)": "⏳", "Open": "⏳", "High": "⏳",
                "Low":     "⏳", "Change": "⏳", "Chg %": "⏳",
                "Volume":  "⏳", "Time": "⏳",
            })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# CONNECT / DISCONNECT / UPLOAD BUTTONS
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
                        jwt_token=creds["jwt_token"],
                        api_key=creds["api_key"],
                        client_id=creds["client_id"],
                        feed_token=creds["feed_token"],
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
        if st.button("⛔ Disconnect", use_container_width=True):
            angel_ws.stop_websocket()
            st.session_state.angel_connected = False
            st.session_state.angel_creds = None
            st.session_state.auto_refresh = False
            st.rerun()

with col3:
    if st.session_state.angel_connected:
        if st.button("📤 Update to Supabase", use_container_width=True):
            ticks = angel_ws.latest_ticks
            if not ticks:
                st.warning("⚠️ No data yet. Wait for WebSocket.")
            else:
                with st.spinner("Uploading & computing volume signals..."):
                    ok, msg = upload_to_supabase(ticks)
                    st.success(msg) if ok else st.error(msg)

st.divider()


# ──────────────────────────────────────────────────────────────────────────────
# MAIN DISPLAY
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.angel_connected:

    # ── Debug Panel ────────────────────────────────────────────
    with st.expander("🔍 Debug Panel", expanded=False):
        raw       = angel_ws._raw_messages
        ticks_dbg = angel_ws.latest_ticks

        st.write(f"**Total tokens received:** {len(ticks_dbg)}")
        st.write(f"**Token keys (first 20):** {sorted(list(ticks_dbg.keys()))[:20]}")

        if raw:
            st.write("**Last raw message:**")
            st.json(raw[-1])
        else:
            st.warning("No raw messages yet — WebSocket may still be connecting...")

        st.write("**Sample ticks (first 5):**")
        st.json(dict(list(ticks_dbg.items())[:5]))

    # ── Auto-refresh toggle + manual button ───────────────────
    auto_col, manual_col = st.columns([3, 1])
    with auto_col:
        st.session_state.auto_refresh = st.toggle(
            "🔁 Auto Refresh (every 1 min)", value=st.session_state.auto_refresh
        )
    with manual_col:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()

    # ── Pull latest ticks ─────────────────────────────────────
    ticks = angel_ws.latest_ticks

    stocks_with_ltp = sum(
        1 for _, token, _ in STOCKS_WATCHLIST
        if ticks.get(token, {}).get("ltp", 0) > 0
    )

    # ── Status metrics ────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Tokens Received", f"{len(ticks)} / {len(STOCKS_WATCHLIST)}")
    with m2:
        st.metric("Stocks with LTP", stocks_with_ltp)
    with m3:
        st.metric("Last Refresh", datetime.now().strftime("%H:%M:%S"))

    st.subheader(f"📊 Live Prices ({len(STOCKS_WATCHLIST)} stocks)")

    # ── No ticks yet ──────────────────────────────────────────
    if not ticks:
        st.warning(
            "⏳ **No ticks received yet.**  \n"
            "WebSocket is connecting — usually takes 3–10 seconds. "
            "Page auto-refreshes every 1 min."
        )

    # ── Render table instantly — no Supabase calls here ───────
    else:
        if stocks_with_ltp == 0:
            st.warning(
                f"⏳ Received {len(ticks)} token(s) but LTP = 0. "
                "Market may be closed or ticks still propagating."
            )
        else:
            st.success(f"✅ {stocks_with_ltp} / {len(STOCKS_WATCHLIST)} stocks have live LTP")

        df = build_dataframe(ticks)   # ← pure dict lookup, instant

        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            height=600,
        )

        st.caption(
            f"🕐 {datetime.now().strftime('%H:%M:%S')}  |  "
            f"Tokens: {len(ticks)}/{len(STOCKS_WATCHLIST)}  |  "
            f"LTP active: {stocks_with_ltp}  |  "
            f"Signal/Status: click '📤 Update to Supabase'"
        )

    # ── Auto-refresh (1 min, no JavaScript) ───────────────────
    if st.session_state.auto_refresh:
        time.sleep(60)
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# DISCONNECTED STATE
# ──────────────────────────────────────────────────────────────────────────────

else:
    st.info("👆 Upar **'Connect Angel One'** button dabao live data dekhne ke liye.")
    st.markdown(f"""
    ### Live Feed Setup
    - ✅ **Total Watchlist:** `{len(STOCKS_WATCHLIST)}` stocks (2 indices + 849 stocks)
    - ✅ Data source: `config.py`
    - ✅ Real-time updates from Angel One WebSocket

    ### Checklist
    - ✅ `angel_auth.py` mein credentials fill kiye?
    - ✅ `config.py` root folder mein hai?
    - ✅ `smartapi-python` installed hai?
    - ✅ Internet connection hai?
    """)
