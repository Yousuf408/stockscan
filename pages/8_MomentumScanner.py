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
from momentum.notification_helper import init_notif_state, process_notifications, request_permission_js
from momentum.delivery import get_latest_available_delivery_pct
from momentum.first_candle import fetch_body_ratio_for_stocks
from momentum.auto_trader import build_symbol_to_token, run_auto_trade

# ── Display cutoff — stocks whose FIRST signal was after this time ──
SIGNAL_CUTOFF_TIME = "11:00:00"   # HH:MM:SS IST

# ── Token lookups ─────────────────────────────────────────────
TOKEN_TO_NAME    = {token: name for name, token, kind in STOCKS_WATCHLIST}
SYMBOL_TO_TOKEN  = build_symbol_to_token(STOCKS_WATCHLIST)

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

from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("MomentumScanner")

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
# BODY RATIO SESSION-STATE CACHE
# ─────────────────────────────────────────────────────────────
def get_body_ratio_cache(df) -> dict:
    if "body_ratio_cache" not in st.session_state:
        st.session_state["body_ratio_cache"] = {}
    cache         = st.session_state["body_ratio_cache"]
    result_stocks = df["Symbol"].tolist()
    new_stocks    = [s for s in result_stocks if s not in cache]
    if new_stocks:
        fetched = fetch_body_ratio_for_stocks(new_stocks)
        cache.update(fetched)
        st.session_state["body_ratio_cache"] = cache
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

# ── DELIVERY % ────────────────────────────────────────────────
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
# AUTO-TRADE SESSION STATE INIT
# ─────────────────────────────────────────────────────────────
if "auto_trade_enabled" not in st.session_state:
    st.session_state["auto_trade_enabled"] = False
if "already_bought" not in st.session_state:
    st.session_state["already_bought"] = set()
if "trade_log" not in st.session_state:
    st.session_state["trade_log"] = []

# ─────────────────────────────────────────────────────────────
# SIDEBAR — AUTO TRADER CONTROLS
# ─────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Auto Trader")

total_capital = st.sidebar.number_input(
    "Capital (₹)",
    min_value  = 10000,
    max_value  = 1000000,
    value      = 100000,
    step       = 5000,
    help       = "Per trade = Capital ÷ 4  |  Max 3 positions",
)
per_trade = total_capital / 4
st.sidebar.caption(f"Per trade: ₹{per_trade:,.0f}  |  Max 3 positions")

st.session_state["auto_trade_enabled"] = st.sidebar.toggle(
    "🤖 Auto Buy",
    value = st.session_state["auto_trade_enabled"],
    key   = "auto_trade_toggle",
)

# Positions counter
bought_count = len(st.session_state["already_bought"])
st.sidebar.caption(f"Positions open: {bought_count} / 3")

# Show bought stocks
if st.session_state["already_bought"]:
    for sym in st.session_state["already_bought"]:
        st.sidebar.markdown(f"✅ {sym}")

# Manual reset
if st.sidebar.button("🔄 Reset Positions"):
    st.session_state["already_bought"] = set()
    st.session_state["trade_log"]      = []
    st.sidebar.success("Positions cleared!")


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

    # ── Market hours check (9:15–15:30 IST) ──────────────────
    current_t   = datetime.now(IST).time()
    market_open = current_t >= dt_time(9, 15) and current_t <= dt_time(15, 30)

    # ── Outside market hours: only show stocks already saved ──
    if not market_open and not df.empty:
        df = df[df["Symbol"].isin(signal_data.keys())].reset_index(drop=True)

    # ── Status bar + toggle + reload ─────────────────────────
    col_info, col_toggle, col_btn = st.columns([4, 2, 1])
    with col_info:
        stock_count = len(df) if not df.empty else 0
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;'
            f'padding:8px 14px;font-size:15px;color:#166534;">'
            f'<b>{stock_count} stocks</b> matching momentum criteria &nbsp;|&nbsp; Last updated: {now_ist}'
            f'</div>',
            unsafe_allow_html=True
        )
    with col_toggle:
        hide_low_body = st.toggle("Hide low body (<75%)", key="hide_low_body_toggle")
    with col_btn:
        if st.button("🔄 Reload", use_container_width=True):
            del st.session_state["momentum_historical"]
            st.session_state.pop("ema20_cache",      None)
            st.session_state.pop("body_ratio_cache", None)
            st.rerun()

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    # ── Body ratio filter ─────────────────────────────────────
    if hide_low_body:
        body_cache_pre = get_body_ratio_cache(df)
        df = df[df["Symbol"].apply(
            lambda s: (body_cache_pre.get(s) or 0) >= 75
        )].reset_index(drop=True)

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    # ── Save / update signals ─────────────────────────────────
    for _, row in df.iterrows():
        symbol = row["Symbol"]
        ltp    = float(row["LTP"])

        if symbol not in signal_data:
            if not market_open:
                continue
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

    # ── Body ratio ────────────────────────────────────────────
    body_cache = get_body_ratio_cache(df)
    df["Body Ratio"] = df["Symbol"].apply(lambda s: body_cache.get(s, None))

    # ── Hard EMA20 filter ─────────────────────────────────────
    df = df[~df["EMA20 Status"].astype(str).str.startswith("❌")].reset_index(drop=True)

    # ── Delivery % ────────────────────────────────────────────
    delivery_map = st.session_state.get("delivery_pct_map", {})
    df["Delivery %"] = df["Symbol"].apply(lambda s: delivery_map.get(s.upper(), None))

    # ── Time cutoff ───────────────────────────────────────────
    df = df[df["Signal Time"].apply(
        lambda t: True if t in (None, "-", "") else str(t) <= SIGNAL_CUTOFF_TIME
    )].reset_index(drop=True)

    if df.empty:
        st.info(f"No stocks matching momentum criteria before {SIGNAL_CUTOFF_TIME} cutoff.")
        return

    # ── Notifications ─────────────────────────────────────────
    init_notif_state()
    process_notifications(df)

    # ─────────────────────────────────────────────────────────
    # AUTO-TRADE TRIGGER
    # ─────────────────────────────────────────────────────────
    if st.session_state.get("auto_trade_enabled") and market_open:
        auth      = st.session_state.get("angel_auth")
        smart_api = auth.get("smart_api") if auth else None

        if smart_api:
            trade_results = run_auto_trade(
                df              = df,
                smart_api       = smart_api,
                symbol_to_token = SYMBOL_TO_TOKEN,
                total_capital   = total_capital,
                already_bought  = st.session_state["already_bought"],  # mutated in-place
                max_positions   = 3,
            )
            for r in trade_results:
                st.session_state["trade_log"].append(r)
                if r["success"]:
                    st.toast(
                        f"✅ BUY {r['symbol']} x{r['qty']} @ ₹{r['ltp']} "
                        f"| +{r['move_pct']}% | ₹{r['capital_used']} used",
                        icon="🚀",
                    )
                else:
                    st.toast(
                        f"❌ {r['symbol']} failed: {r['error']}",
                        icon="⚠️",
                    )
        else:
            st.warning(
                "⚠️ Auto Trade ON but `smart_api` not found in session. "
                "Update angel_auth.py to return `smart_api` object.",
                icon="⚠️",
            )

    # ── Render HTML table ─────────────────────────────────────
    html = render_html_table(
        df                = df,
        data_source       = data_source,
        target_date       = historical["target_date"],
        prev_date         = historical["prev_date"],
        tick_count        = tick_count,
        already_bought    = st.session_state.get("already_bought", set()),
        capital_per_trade = total_capital / 4,
    )

    st.components.v1.html(
        html,
        height    = max(500, 160 + len(df) * 90),
        scrolling = True,
    )

    # ── postMessage listener — BUY button from HTML table ───────
    st.components.v1.html(
        """<script>
        window.addEventListener('message', function(e) {
            if (e.data && e.data.type === 'ts_manual_buy') {
                window.parent.postMessage(
                    {isStreamlitMessage: true, type: 'streamlit:setComponentValue',
                     value: {action:'buy', symbol: e.data.symbol, qty: e.data.qty, ltp: e.data.ltp}},
                    '*'
                );
            }
        });
        </script>""",
        height=0,
    )

    # ── Pending buy from query_params ────────────────────────
    pending = st.query_params.get("ts_buy", None)
    if pending:
        import json
        try:
            data      = json.loads(pending)
            symbol    = data.get("symbol")
            qty       = int(data.get("qty", 1))
            ltp       = float(data.get("ltp", 0))
            auth      = st.session_state.get("angel_auth")
            smart_api = auth.get("smart_api") if auth else None
            if smart_api and symbol and symbol not in st.session_state["already_bought"]:
                token = SYMBOL_TO_TOKEN.get(symbol)
                if token:
                    from momentum.auto_trader import place_buy_order
                    result = place_buy_order(smart_api, symbol, token, qty)
                    if result["success"]:
                        st.session_state["already_bought"].add(symbol)
                        st.session_state["trade_log"].append({
                            "time": datetime.now(IST).strftime("%H:%M:%S"),
                            "symbol": symbol, "qty": qty, "ltp": ltp,
                            "capital_used": round(qty * ltp, 0),
                            "success": True, "order_id": result["order_id"],
                            "error": None, "type": "MANUAL",
                        })
                        st.toast(f"✅ {symbol} x{qty} order placed!", icon="🚀")
                    else:
                        st.toast(f"❌ {symbol} failed: {result['error']}", icon="⚠️")
        except Exception:
            pass
        st.query_params.clear()

    # ── Trade log ─────────────────────────────────────────────
    if st.session_state.get("trade_log"):
        import pandas as pd
        st.markdown("#### 📋 Today's Trades")
        log_df    = pd.DataFrame(st.session_state["trade_log"])
        want_cols = ["time", "type", "symbol", "qty", "ltp", "capital_used", "success", "order_id", "error"]
        show_cols = [c for c in want_cols if c in log_df.columns]
        st.dataframe(log_df[show_cols], use_container_width=True, hide_index=True)


request_permission_js()
scanner_table()
