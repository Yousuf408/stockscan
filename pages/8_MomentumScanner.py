"""
pages/8_MomentumScanner.py
Momentum Scanner — Frontend only.
All logic lives in momentum/backend.py and momentum/renderer.py.
"""

import sys
import os

# ── Proxy — must be set via env vars for SmartAPI to route correctly ──
_PROXY = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"]  = _PROXY
os.environ["HTTPS_PROXY"] = _PROXY

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

    # ── Time cutoff (temporarily disabled) ──────────────────────
    # df = df[df["Signal Time"].apply(
    #     lambda t: True if t in (None, "-", "") else str(t) <= SIGNAL_CUTOFF_TIME
    # )].reset_index(drop=True)
    # if df.empty:
    #     st.info(f"No stocks matching momentum criteria before {SIGNAL_CUTOFF_TIME} cutoff.")
    #     return

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
        df          = df,
        data_source = data_source,
        target_date = historical["target_date"],
        prev_date   = historical["prev_date"],
        tick_count  = tick_count,
    )

    st.components.v1.html(
        html,
        height    = max(500, 160 + len(df) * 90),
        scrolling = True,
    )

    # ─────────────────────────────────────────────────────────
    # OPTION B — Slim BUY strip (Streamlit native, guaranteed)
    # ─────────────────────────────────────────────────────────
    import math
    import pyotp
    from SmartApi import SmartConnect

    # ── Get smart_api — from session or create fresh ──────────
    # Credentials hardcoded here — no import dependency
    _API_KEY    = "QFectj5C"
    _CLIENT_ID  = "IIRA29771"
    _PASSWORD   = "1993"
    _TOTP_SEC   = "JFTG3DYADWLYSW6FC6RVV4THWM"
    _PROXY      = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"

    def get_smart_api():
        auth = st.session_state.get("angel_auth")
        # Try session first
        if auth and auth.get("smart_api"):
            return auth["smart_api"]
        # Fresh login with proxy
        try:
            obj = SmartConnect(api_key=_API_KEY)
            obj.proxy = {"http": _PROXY, "https": _PROXY}
            totp = pyotp.TOTP(_TOTP_SEC).now()
            data = obj.generateSession(_CLIENT_ID, _PASSWORD, totp)
            if data and data.get("status"):
                if auth:
                    auth["smart_api"] = obj
                    st.session_state["angel_auth"] = auth
                return obj
            else:
                st.error(f"Login failed: {data.get('message') if data else 'No response'}")
        except Exception as e:
            st.error(f"Angel One login error: {e}")
        return None

    capital_per_trade = total_capital / 4

    st.markdown(
        '<div style="background:#f8faff;border:1px solid #e2e8f0;border-radius:8px;'
        'padding:6px 14px 2px 14px;margin-top:4px;">'
        '<span style="font-size:11px;font-weight:700;color:#64748b;'
        'text-transform:uppercase;letter-spacing:0.5px;">Quick Buy</span></div>',
        unsafe_allow_html=True,
    )

    for _, row in df.iterrows():
        symbol  = str(row["Symbol"])
        ltp     = float(row["LTP"])
        qty     = max(math.floor(capital_per_trade / ltp), 1) if ltp > 0 else 1
        est     = round(qty * ltp, 0)
        already = symbol in st.session_state["already_bought"]

        c1, c2, c3 = st.columns([1, 2, 1])

        c1.markdown(
            f'<div style="padding:6px 0;">'
            f'<span style="font-size:13px;font-weight:800;color:#0f172a;">{symbol}</span><br>'
            f'<span style="font-size:11px;color:#94a3b8;">x{qty} &nbsp;≈ ₹{int(est):,}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c2.markdown(
            f'<div style="padding:6px 0;font-size:12px;color:#64748b;">'
            f'LTP: <b style="color:#0f172a;">₹{ltp:,.2f}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )

        with c3:
            if already:
                st.markdown(
                    '<span style="color:#16a34a;font-weight:700;font-size:13px;">✅ Bought</span>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(
                    f"BUY x{qty}",
                    key  = f"strip_buy_{symbol}",
                    type = "primary",
                    use_container_width=True,
                ):
                    token = SYMBOL_TO_TOKEN.get(symbol)
                    if not token:
                        st.error(f"Token not found: {symbol}")
                    else:
                        with st.spinner(f"Connecting & placing {symbol}..."):
                            smart_api = get_smart_api()
                            if not smart_api:
                                st.error("Angel One login failed. Credentials check karo.")
                            else:
                                from momentum.auto_trader import place_buy_order
                                result = place_buy_order(smart_api, symbol, token, qty)
                                if result["success"]:
                                    st.session_state["already_bought"].add(symbol)
                                    st.session_state["trade_log"].append({
                                        "time"        : datetime.now(IST).strftime("%H:%M:%S"),
                                        "type"        : "MANUAL",
                                        "symbol"      : symbol,
                                        "qty"         : qty,
                                        "ltp"         : ltp,
                                        "capital_used": int(est),
                                        "success"     : True,
                                        "order_id"    : result["order_id"],
                                        "error"       : None,
                                    })
                                    st.toast(f"✅ {symbol} x{qty} @ ₹{ltp}", icon="🚀")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Order failed: {result['error']}")

        st.divider()

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
