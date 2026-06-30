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
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION START — imports            ║
    # ╚═══════════════════════════════════════════════════════════╝
    fetch_initial_candles_yahoo,
    build_ws_candle,
    append_candle_and_save,
    save_initial_candles_to_db,
    calculate_ema9_with_live,
    detect_phase_and_trend,
    update_phase_in_supabase,
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION END                        ║
    # ╚═══════════════════════════════════════════════════════════╝
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


# ╔═══════════════════════════════════════════════════════════════╗
# ║  UNIFIED CANDLE SYSTEM — SESSION STATE                        ║
# ║  candle_cache: { stock: [candle1...candle9] } in RAM          ║
# ║  DB (candles jsonb) = persistent across page refresh           ║
# ║  Flow:                                                         ║
# ║  1. Signal detected → Yahoo 8 candles → background thread     ║
# ║  2. Every 5 min → WS candle built → append DB + RAM           ║
# ║  3. Every 5 sec → live LTP + candles → EMA9 + Phase           ║
# ║  4. Page refresh → DB candles → instant restore                ║
# ╚═══════════════════════════════════════════════════════════════╝

import threading

def get_candle_cache() -> dict:
    """Get or init candle cache from session state."""
    if "candle_cache" not in st.session_state:
        st.session_state["candle_cache"] = {}
    return st.session_state["candle_cache"]


def _yahoo_fetch_worker(stocks: list, supabase, today_str: str, candle_cache: dict):
    """
    Background thread — fetch Yahoo candles without blocking fragment.
    Writes directly into candle_cache (shared dict reference).
    """
    try:
        yahoo_data = fetch_initial_candles_yahoo(stocks)
        for stock, candles in yahoo_data.items():
            if candles:
                candle_cache[stock] = candles
                save_initial_candles_to_db(supabase, stock, today_str, candles)
    except Exception:
        pass


def process_candles(supabase, df, signal_data: dict,
                    live_ticks: dict, token_to_name: dict,
                    today_str: str) -> tuple:
    """
    Unified function — handles candles, EMA9, Phase, Vol Trend.
    Yahoo fetch runs in background thread — no blur/block.

    Returns:
      ema9_results  : { stock: { ema9, distance, status, signal } }
      phase_results : { stock: { phase, vol_trend } }
    """
    from datetime import datetime as dt

    now          = dt.now(IST)
    current_slot = (now.minute // 5) * 5
    slot_str     = now.strftime(f"%H:{current_slot:02d}")

    # ── Init slot tracking ────────────────────────────────────
    if "candle_slot"         not in st.session_state:
        st.session_state["candle_slot"]         = -1
    if "tick_buffer"         not in st.session_state:
        st.session_state["tick_buffer"]         = {}
    if "yahoo_fetching"      not in st.session_state:
        st.session_state["yahoo_fetching"]      = set()

    candle_cache  = get_candle_cache()
    name_to_token = {v: k for k, v in token_to_name.items()}
    do_ws_candle  = st.session_state["candle_slot"] != current_slot

    # ── Step 1: On new 5min slot → build WS candle + append ──
    if do_ws_candle:
        prev_buffer = st.session_state["tick_buffer"]
        for stock, ticks in prev_buffer.items():
            if stock not in candle_cache:
                continue
            new_candle = build_ws_candle(slot_str, ticks)
            if new_candle:
                candle_cache[stock] = append_candle_and_save(
                    supabase, stock, today_str,
                    candle_cache[stock], new_candle
                )
        st.session_state["tick_buffer"] = {}
        st.session_state["candle_slot"] = current_slot

    # ── Step 2: Accumulate current ticks ──────────────────────
    for token, tick in live_ticks.items():
        stock  = token_to_name.get(token)
        if not stock:
            continue
        ltp    = float(tick.get("ltp",    0))
        volume = float(tick.get("volume", 0))
        if ltp <= 0:
            continue
        buf = st.session_state["tick_buffer"].get(stock, [])
        buf.append({"ltp": ltp, "volume": volume})
        st.session_state["tick_buffer"][stock] = buf

    # ── Step 3: For each scan stock — ensure candles exist ────
    stocks  = df["Symbol"].tolist()
    missing = [s for s in stocks if s not in candle_cache]

    if missing:
        # Try DB first (page refresh case) — instant, no network call
        for stock in missing:
            sig        = signal_data.get(stock, {})
            db_candles = sig.get("candles", None)
            if db_candles and len(db_candles) >= 2:
                candle_cache[stock] = db_candles

        # Still missing → background thread (no blur!)
        still_missing = [
            s for s in missing
            if s not in candle_cache
            and s not in st.session_state["yahoo_fetching"]
        ]
        if still_missing:
            # Mark as fetching so we don't spawn duplicate threads
            st.session_state["yahoo_fetching"].update(still_missing)
            t = threading.Thread(
                target = _yahoo_fetch_worker,
                args   = (still_missing, supabase, today_str, candle_cache),
                daemon = True,
            )
            t.start()
            # Clean up fetching set after thread completes
            def _cleanup(stocks_to_clean=still_missing):
                t.join()
                for s in stocks_to_clean:
                    st.session_state["yahoo_fetching"].discard(s)
            threading.Thread(target=_cleanup, daemon=True).start()

    # ── Step 4: Calculate EMA9 + Phase for all stocks ─────────
    ema9_results  = {}
    phase_results = {}
    do_phase_update = do_ws_candle

    for symbol in stocks:
        candles  = candle_cache.get(symbol, [])
        token    = name_to_token.get(symbol)
        live_ltp = 0.0
        if token and token in live_ticks:
            live_ltp = float(live_ticks[token].get("ltp", 0))

        # ── EMA9 ──────────────────────────────────────────────
        if candles and live_ltp > 0:
            ema9_data = calculate_ema9_with_live(candles, live_ltp)
            ema9_results[symbol] = ema9_data if ema9_data else {
                "ema9": None, "distance": None, "status": "⚠️ N/A", "signal": ""
            }
        else:
            ema9_results[symbol] = {
                "ema9": None, "distance": None,
                "status": "⏳" if not candles else "⚠️ N/A", "signal": ""
            }

        # ── Phase + Vol Trend ──────────────────────────────────
        if len(candles) >= 2:
            phase, vol_trend = detect_phase_and_trend(candles)
            phase_results[symbol] = {"phase": phase, "vol_trend": vol_trend}
            if do_phase_update and symbol in signal_data:
                try:
                    update_phase_in_supabase(
                        supabase, symbol, today_str, phase, vol_trend
                    )
                except Exception:
                    pass
        else:
            sig = signal_data.get(symbol, {})
            phase_results[symbol] = {
                "phase"    : sig.get("phase",     "⏳ Forming"),
                "vol_trend": sig.get("vol_trend", "→ Stable"),
            }

    return ema9_results, phase_results

# ╔═══════════════════════════════════════════════════════════════╗
# ║  UNIFIED CANDLE SYSTEM SECTION END                            ║
# ╚═══════════════════════════════════════════════════════════════╝


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
            st.session_state.pop("candle_cache",   None)
            st.session_state.pop("candle_slot",    None)
            st.session_state.pop("tick_buffer",    None)
            st.rerun()

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

    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM — EMA9 + Phase + Vol Trend         ║
    # ╚═══════════════════════════════════════════════════════════╝
    ema9_cache, phase_cache = process_candles(
        supabase      = supabase,
        df            = df,
        signal_data   = signal_data,
        live_ticks    = angel_ws.latest_ticks,
        token_to_name = TOKEN_TO_NAME,
        today_str     = today,
    )
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION END                        ║
    # ╚═══════════════════════════════════════════════════════════╝

    # ── Assign display columns ────────────────────────────────
    df["Signal Time"]       = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_time",  "-"))
    df["Signal Price"]      = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_price", None))
    df["High Since Signal"] = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("peak_ltp",     None))
    df["EMA20 Status"]      = df["Symbol"].apply(lambda s: ema_cache.get(s, {}).get("status",         "⏳"))
    df["EMA9 5min"]         = df["Symbol"].apply(lambda s: ema9_cache.get(s, {}).get("status",        "⏳"))
    df["EMA9 Value"]        = df["Symbol"].apply(lambda s: ema9_cache.get(s, {}).get("ema9",          None))
    df["Phase"]             = df["Symbol"].apply(lambda s: phase_cache.get(s, {}).get("phase",        "⏳ Forming"))
    df["Vol Trend"]         = df["Symbol"].apply(lambda s: phase_cache.get(s, {}).get("vol_trend",    "→ Stable"))

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


scanner_table()
