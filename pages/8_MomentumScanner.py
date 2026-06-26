"""
pages/8_MomentumScanner.py
Momentum Scanner — Frontend only.
All logic lives in momentum/backend.py and momentum/renderer.py.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from datetime import datetime
from supabase import create_client

import angel_ws
from config import STOCKS_WATCHLIST

from momentum.backend import (
    fetch_historical_data,
    run_momentum_scan,
    fetch_ema20_for_stocks,
    fetch_signal_data_from_supabase,
    save_signal_to_supabase,
    update_peak_ltp_in_supabase,
    SUPABASE_URL,
    SUPABASE_KEY,
    IST,
)
from momentum.renderer import render_html_table

# ── Token lookups ─────────────────────────────────────────────
TOKEN_TO_NAME = {token: name for name, token, kind in STOCKS_WATCHLIST}

# ── Auto-connect WebSocket ────────────────────────────────────
if not angel_ws.is_connected():
    if "ws_init" not in st.session_state:
        st.session_state["ws_init"] = True
        if "angel_auth" not in st.session_state:
            from angel_auth import angel_login
            st.session_state["angel_auth"] = angel_login()
        auth = st.session_state["angel_auth"]
        if auth:
            angel_ws.start_websocket(
                jwt_token  = auth["jwt_token"],
                api_key    = auth["api_key"],
                client_id  = auth["client_id"],
                feed_token = auth["feed_token"],
            )

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Momentum Scanner",
    page_icon="🚀",
    layout="wide"
)

st.markdown("""
    <style>
    header { visibility: hidden; }
    .block-container { padding-top: 0.5rem !important; padding-bottom: 0 !important; }
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────
# EMA20 SESSION-STATE CACHE
# ─────────────────────────────────────────────────────────────
def get_ema20_status(df) -> dict:
    if "ema20_cache" not in st.session_state:
        st.session_state["ema20_cache"] = {}
    cache         = st.session_state["ema20_cache"]
    result_stocks = df["Symbol"].tolist()
    new_stocks    = [s for s in result_stocks if s not in cache]
    if new_stocks:
        fetched = fetch_ema20_for_stocks(new_stocks)
        cache.update(fetched)
        st.session_state["ema20_cache"] = cache
    return cache


# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA LOAD
# ─────────────────────────────────────────────────────────────
today_str = datetime.now(IST).strftime("%Y-%m-%d")

if "momentum_historical" not in st.session_state:
    with st.spinner("Loading historical data..."):
        hist = fetch_historical_data(get_supabase())
        if hist:
            st.session_state["momentum_historical"] = hist
        else:
            st.error("❌ No data found in websocket_stock_values")
            st.stop()

historical = st.session_state["momentum_historical"]

# ── Signal data (today only, refresh on new day) ──────────────
if (
    "signal_data"      not in st.session_state or
    st.session_state.get("signal_data_date") != today_str
):
    st.session_state["signal_data"]      = fetch_signal_data_from_supabase(get_supabase(), today_str)
    st.session_state["signal_data_date"] = today_str


# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def scanner_table():
    supabase    = get_supabase()
    historical  = st.session_state["momentum_historical"]
    signal_data = st.session_state["signal_data"]
    today       = datetime.now(IST).strftime("%Y-%m-%d")

    df, data_source = run_momentum_scan(
        historical    = historical,
        live_ticks    = angel_ws.latest_ticks,
        token_to_name = TOKEN_TO_NAME,
    )

    now_ist    = datetime.now(IST).strftime("%H:%M:%S")
    tick_count = len(angel_ws.latest_ticks)

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    # ── Save / update signals ─────────────────────────────────
    for _, row in df.iterrows():
        symbol = row["Symbol"]
        ltp    = float(row["LTP"])

        if symbol not in signal_data:
            signal_time_ist = datetime.now(IST).strftime("%H:%M:%S")
            save_signal_to_supabase(
                supabase     = supabase,
                stock        = symbol,
                today_str    = today,
                signal_time  = signal_time_ist,
                vol_ratio    = row.get("vol_ratio", 0),
                intraday_pct = row.get("intraday_pct", 0),
                vol_momentum = str(row.get("Vol Momentum", "")),
                momentum     = str(row.get("Momentum", "")),
                score        = row.get("Score", 0),
                signal_price = ltp,
            )
            signal_data[symbol] = {
                "signal_time"  : signal_time_ist,
                "signal_price" : ltp,
                "peak_ltp"     : ltp,
            }
        else:
            current_peak = signal_data[symbol].get("peak_ltp") or ltp
            if ltp > current_peak:
                update_peak_ltp_in_supabase(supabase, symbol, today, ltp)
                signal_data[symbol]["peak_ltp"] = ltp

    # ── EMA20 ─────────────────────────────────────────────────
    ema_cache = get_ema20_status(df)

    # ── Assign display columns ────────────────────────────────
    df["Signal Time"]       = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_time",  "-"))
    df["Signal Price"]      = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_price", None))
    df["High Since Signal"] = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("peak_ltp",     None))
    df["EMA20 Status"]      = df["Symbol"].apply(lambda s: ema_cache.get(s, {}).get("status",         "⏳"))

    # ── Status bar + Reload button in one row ─────────────────
    col_info, col_btn = st.columns([5, 1])
    with col_info:
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;'
            f'padding:8px 14px;font-size:14px;color:#166534;">'
            f'<b>{len(df)} stocks</b> matching momentum criteria &nbsp;|&nbsp; Last updated: {now_ist}'
            f'</div>',
            unsafe_allow_html=True
        )
    with col_btn:
        if st.button("🔄 Reload", use_container_width=True):
            del st.session_state["momentum_historical"]
            st.session_state.pop("ema20_cache", None)
            st.rerun()

    # ── Render HTML table ─────────────────────────────────────
    html = render_html_table(
        df          = df,
        data_source = data_source,
        target_date = historical["target_date"],
        prev_date   = historical["prev_date"],
        tick_count  = tick_count,
    )

    st.components.v1.html(
        html,
        height    = min(900, 160 + len(df) * 52),
        scrolling = True,
    )


scanner_table()
