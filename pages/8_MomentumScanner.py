"""
pages/8_MomentumScanner.py
Momentum Scanner — Frontend only.
All logic lives in momentum/backend.py and momentum/renderer.py.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from datetime import datetime, time as dt_time
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
# ── For Notification ─────────────────────────────────────────────

from momentum.notification_helper import init_notif_state, process_notifications, request_permission_js
from momentum.delivery import get_latest_available_delivery_pct

# ── Display cutoff — stocks whose FIRST signal was after this time ──
# ── are excluded from the table (still saved to Supabase though)   ──
SIGNAL_CUTOFF_TIME = "11:00:00"   # HH:MM:SS IST

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
# ── STYLES & SIDEBAR ──────────────────────────────────────────
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("MomentumScanner")

# ── STYLES & SIDEBAR end here ──────────────────────────────────

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

# ── DELIVERY % — fetched once per session, cached for the whole day ──
if "delivery_pct_map" not in st.session_state:
    delivery_map, delivery_date = get_latest_available_delivery_pct()
    st.session_state["delivery_pct_map"]  = delivery_map
    st.session_state["delivery_pct_date"] = delivery_date

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

    # ── Market hours check (9:15–15:30 IST) ────────────────────
    current_t   = datetime.now(IST).time()
    market_open = current_t >= dt_time(9, 15) and current_t <= dt_time(15, 30)

    # ── Outside market hours: only show stocks already saved in DB ──
    # (drops brand-new symbols that only appeared from stale ticks)
    if not market_open and not df.empty:
        df = df[df["Symbol"].isin(signal_data.keys())].reset_index(drop=True)

    # ── Status bar + Reload button — always visible ───────────
    col_info, col_btn = st.columns([5, 1])
    with col_info:
        stock_count = len(df) if not df.empty else 0
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;'
            f'padding:8px 14px;font-size:15px;color:#166534;">'
            f'<b>{stock_count} stocks</b> matching momentum criteria &nbsp;|&nbsp; Last updated: {now_ist}'
            f'</div>',
            unsafe_allow_html=True
        )
    with col_btn:
        if st.button("🔄 Reload", use_container_width=True):
            del st.session_state["momentum_historical"]
            st.session_state.pop("ema20_cache",    None)
            st.rerun()

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    # ── Save / update signals — ONLY during market hours (9:15–15:30 IST) ──
    # Outside market hours, stale WebSocket/Yahoo ticks can falsely look like
    # new signals. Table is already filtered above to drop those.
    for _, row in df.iterrows():
        symbol = row["Symbol"]
        ltp    = float(row["LTP"])

        if symbol not in signal_data:
            if not market_open:
                continue   # skip saving a brand-new signal outside market hours
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
                "phase"        : None,
                "vol_trend"    : None,
                "candles"      : None,
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

    # ── DELIVERY % — from cached NSE EOD data (yesterday's session) ──
    delivery_map = st.session_state.get("delivery_pct_map", {})
    df["Delivery %"] = df["Symbol"].apply(lambda s: delivery_map.get(s.upper(), None))

    # ── TIME CUTOFF — hide stocks whose first signal was AFTER ──
    # ── SIGNAL_CUTOFF_TIME from the table. They stay saved in   ──
    # ── Supabase (saved above) for records / future reference.  ──
    df = df[df["Signal Time"].apply(
        lambda t: True if t in (None, "-", "") else str(t) <= SIGNAL_CUTOFF_TIME
    )].reset_index(drop=True)

    if df.empty:
        st.info(f"No stocks matching momentum criteria before {SIGNAL_CUTOFF_TIME} cutoff.")
        return

   # ── Notification ─────────────────────────────────────
    init_notif_state()
    process_notifications(df)

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
        height   = max(500, 160 + len(df) * 90),
        scrolling = True,
    )


request_permission_js()
scanner_table()
