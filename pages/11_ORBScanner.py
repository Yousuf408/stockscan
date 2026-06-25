"""
11_ORBScanner.py
ORB (Opening Range Breakout) Scanner
- Tracks stocks breaking above yesterday's high in first 15 mins (9:15–9:30 IST)
- Conditions: gap < 1%, yesterday close > EMA20, open/LTP > yesterday high
- After 9:30: stops adding new stocks, keeps showing with live updates
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta
from supabase import create_client

import angel_ws
from config import STOCKS_WATCHLIST

# ── WebSocket — handled by Momentum Scanner tab ─────────────
# ORB Scanner reads from angel_ws.latest_ticks directly
# Keep Momentum Scanner tab open for live ticks

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="ORB Scanner", page_icon="📈", layout="wide")
st.markdown("<style>header {visibility: hidden;}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL       = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY       = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
IST                = timezone(timedelta(hours=5, minutes=30))
EMA_DISTANCE_LIMIT = 8.0
MAX_GAP_PCT        = 1.0   # ignore stocks with gap > 1%

TOKEN_TO_NAME = {token: name for name, token, kind in STOCKS_WATCHLIST}

# ORB window: 9:15 to 9:30 IST
ORB_START_H, ORB_START_M = 9, 15
ORB_END_H,   ORB_END_M   = 9, 30

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────
# FETCH HISTORICAL DATA — YESTERDAY HIGH, CLOSE, MEDIAN VOL
# ─────────────────────────────────────────────────────────────
def fetch_orb_historical_data():
    """
    Fetch from websocket_stock_values:
    1. yesterday_high  → prev day's high per stock
    2. yesterday_close → prev day's close per stock
    3. median_vol_5d   → median volume of last 5 days
    """
    supabase = get_supabase()

    # ── Get distinct trading dates ────────────────────────────
    all_dates = set()
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("date") \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        for r in rows:
            if r.get("date"):
                all_dates.add(r["date"])
        if len(rows) < 1000:
            break
        offset += 1000

    if not all_dates:
        return None

    sorted_dates = sorted(all_dates, reverse=True)
    # sorted_dates[0] = today (LiveFeed already uploaded today's data)
    # sorted_dates[1] = actual yesterday → use for high/close
    prev_date    = sorted_dates[1] if len(sorted_dates) > 1 else sorted_dates[0]
    last_5_dates = sorted_dates[1:6]  # last 5 days excluding today

    # ── Fetch yesterday's high + close ───────────────────────
    prev_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, high, ltp") \
            .eq("date", prev_date) \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        prev_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    df_prev = pd.DataFrame(prev_rows)
    if not df_prev.empty:
        df_prev = df_prev.drop_duplicates(subset="stock", keep="first")
        df_prev["high"] = pd.to_numeric(df_prev["high"], errors="coerce")
        df_prev["ltp"]  = pd.to_numeric(df_prev["ltp"],  errors="coerce")
        df_prev = df_prev.rename(columns={
            "high" : "yesterday_high",
            "ltp"  : "yesterday_close",
        })

    # ── Fetch 5-day median volume ─────────────────────────────
    vol_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, volume") \
            .in_("date", last_5_dates) \
            .gt("volume", 0) \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        vol_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    df_median = pd.DataFrame()
    if vol_rows:
        df_vol = pd.DataFrame(vol_rows)
        df_vol["volume"] = pd.to_numeric(df_vol["volume"], errors="coerce")
        df_median = df_vol.groupby("stock")["volume"].median().reset_index()
        df_median = df_median.rename(columns={"volume": "median_vol"})

    return {
        "prev_date" : prev_date,
        "df_prev"   : df_prev,
        "df_median" : df_median,
    }

# ─────────────────────────────────────────────────────────────
# EMA20 — SAME AS MOMENTUM SCANNER
# ─────────────────────────────────────────────────────────────
def fetch_ema20_for_stocks(stock_names: list) -> dict:
    result = {}
    if not stock_names:
        return result

    tickers = [f"{s}.NS" for s in stock_names]
    try:
        raw = yf.download(
            tickers,
            period="60d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception:
        return result

    if "Close" not in raw.columns and not isinstance(raw.columns, pd.MultiIndex):
        return result

    close_col  = raw["Close"]
    close_data = {}

    if isinstance(close_col, pd.Series):
        close_data[tickers[0]] = close_col
    else:
        for ticker in tickers:
            if ticker in close_col.columns:
                close_data[ticker] = close_col[ticker]

    for stock in stock_names:
        ticker = f"{stock}.NS"
        if ticker not in close_data:
            result[stock] = {"ema20": None, "gap": None, "status": "⚠️ N/A"}
            continue

        series = close_data[ticker].dropna()
        if len(series) < 21:
            result[stock] = {"ema20": None, "gap": None, "status": "⚠️ N/A"}
            continue

        ema_series      = series.ewm(span=20, adjust=False).mean()
        yesterday_close = round(float(series.iloc[-2]), 2)
        ema20_yesterday = round(float(ema_series.iloc[-2]), 2)
        gap             = round(((yesterday_close - ema20_yesterday) / ema20_yesterday) * 100, 2)

        if yesterday_close < ema20_yesterday:
            status = "❌ Below"
        elif gap > EMA_DISTANCE_LIMIT:
            status = f"❌ +{gap:.1f}%"
        else:
            status = f"✅ +{gap:.1f}%"

        result[stock] = {"ema20": ema20_yesterday, "gap": gap, "status": status}

    return result


def get_ema20_cache(stock_names: list) -> dict:
    if "orb_ema20_cache" not in st.session_state:
        st.session_state["orb_ema20_cache"] = {}

    cache      = st.session_state["orb_ema20_cache"]
    new_stocks = [s for s in stock_names if s not in cache]

    if new_stocks:
        fetched = fetch_ema20_for_stocks(new_stocks)
        cache.update(fetched)
        st.session_state["orb_ema20_cache"] = cache

    return cache

# ─────────────────────────────────────────────────────────────
# ORB SUPABASE — SAVE & FETCH
# ─────────────────────────────────────────────────────────────
def fetch_orb_signals_from_supabase(today_str: str) -> dict:
    """
    Fetch today's saved ORB signals.
    Returns dict: {stock: {signal_time, yesterday_high, today_open,
                           gap_pct, signal_price, peak_ltp, ema20_status}}
    """
    try:
        supabase = get_supabase()
        resp = supabase.table("orb")             .select("stock, signal_time, yesterday_high, today_open, gap_pct, signal_price, peak_ltp, ema20_status")             .eq("signal_date", today_str)             .execute()
        result = {}
        for row in resp.data:
            result[row["stock"]] = {
                "signal_time"   : row.get("signal_time", ""),
                "yesterday_high": row.get("yesterday_high", 0),
                "today_open"    : row.get("today_open", 0),
                "gap_pct"       : row.get("gap_pct", 0),
                "signal_price"  : row.get("signal_price", 0),
                "peak_ltp"      : row.get("peak_ltp", 0),
                "ema20_status"  : row.get("ema20_status", ""),
            }
        return result
    except Exception:
        return {}


def save_orb_signal_to_supabase(stock: str, today_str: str, signal_time: str,
                                  yesterday_high: float, today_open: float,
                                  gap_pct: float, signal_price: float,
                                  ema20_status: str):
    """Save ORB signal — ignored if already exists for today."""
    try:
        supabase = get_supabase()
        supabase.table("orb").upsert({
            "stock"         : stock,
            "signal_date"   : today_str,
            "signal_time"   : signal_time,
            "yesterday_high": round(float(yesterday_high), 2),
            "today_open"    : round(float(today_open), 2),
            "gap_pct"       : round(float(gap_pct), 2),
            "signal_price"  : round(float(signal_price), 2),
            "peak_ltp"      : round(float(signal_price), 2),
            "ema20_status"  : ema20_status,
        }, on_conflict="stock,signal_date", ignore_duplicates=True).execute()
    except Exception:
        pass


def update_orb_peak_ltp(stock: str, today_str: str, new_peak: float):
    """Update peak_ltp when new high is reached."""
    try:
        supabase = get_supabase()
        supabase.table("orb")             .update({"peak_ltp": round(float(new_peak), 2)})             .eq("stock", stock)             .eq("signal_date", today_str)             .execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# VOL MOMENTUM HELPER
# ─────────────────────────────────────────────────────────────
def get_vol_momentum(ratio: float) -> str:
    if ratio >= 3.0: return "🔥 Very Strong"
    if ratio >= 2.0: return "⚡ Strong"
    if ratio >= 1.5: return "👀 Building"
    if ratio >= 1.0: return "😐 Weak"
    return ""


# ─────────────────────────────────────────────────────────────
# HTML TABLE
# ─────────────────────────────────────────────────────────────
def render_orb_table(df: pd.DataFrame) -> str:

    def move_color(val):
        try:
            v = float(str(val).replace("%","").replace("+",""))
            if v >= 5.0:  return "#16a34a"
            if v >= 2.0:  return "#ca8a04"
            if v >= 0:    return "#64748b"
            return "#dc2626"
        except:
            return "#64748b"

    def ema_cell(status):
        if not status:
            return '<span style="color:#94a3b8">⏳</span>'
        if status.startswith("✅"):
            return f'<span style="color:#16a34a;font-weight:700">{status}</span>'
        if "Below" in str(status):
            return f'<span style="color:#dc2626;font-weight:700">{status}</span>'
        if status.startswith("❌"):
            return f'<span style="color:#ea580c;font-weight:700">{status}</span>'
        return f'<span style="color:#94a3b8">{status}</span>'

    html = """
    <style>
    .orb-table {width:100%; border-collapse:collapse; font-size:13px; font-family:sans-serif;}
    .orb-table th {background:#f1f5f9; color:#475569; font-weight:600; padding:8px 10px;
                   text-align:left; border-bottom:2px solid #e2e8f0; white-space:nowrap;}
    .orb-table th.th-ema  {background:#dcfce7; color:#166534;}
    .orb-table th.th-new  {background:#ede9fe; color:#5b21b6;}
    .orb-table th.th-orb  {background:#fef3c7; color:#92400e;}
    .orb-table td {padding:7px 10px; border-bottom:1px solid #e2e8f0; white-space:nowrap;}
    .copy-btn {
        cursor:pointer; font-weight:700; color:#0f172a;
        background:#e2e8f0; border:none; padding:3px 8px;
        border-radius:4px; font-size:12px; transition:background 0.2s;
    }
    .copy-btn:hover  {background:#10b981; color:white;}
    .copy-btn.copied {background:#10b981; color:white;}
    .signal-time-col {font-weight:700; color:#0f172a; background:#fef3c7;}
    .peak-val {color:#7c3aed; font-weight:600;}
    .toast {
        position:fixed; bottom:30px; left:50%; transform:translateX(-50%);
        background:#0f172a; color:white; padding:8px 20px;
        border-radius:8px; font-size:13px; z-index:9999;
        opacity:0; transition:opacity 0.3s; pointer-events:none;
    }
    .toast.show {opacity:1;}
    </style>
    <div id="orb-toast" class="toast">✅ Copied!</div>
    <script>
    // ── Scroll position preservation ──────────────────────────
    var SCROLL_KEY = 'orb_scroll_pos';
    function saveScroll() {
        var el = document.getElementById('orb-scroll-wrap');
        if (el) sessionStorage.setItem(SCROLL_KEY, el.scrollTop);
    }
    function restoreScroll() {
        var el = document.getElementById('orb-scroll-wrap');
        var pos = sessionStorage.getItem(SCROLL_KEY);
        if (el && pos) el.scrollTop = parseInt(pos);
    }
    document.addEventListener('DOMContentLoaded', restoreScroll);
    setTimeout(restoreScroll, 100);

    function copyORB(btn, symbol) {
        navigator.clipboard.writeText(symbol);
        btn.classList.add('copied');
        btn.innerText = '✓ ' + symbol;
        var t = document.getElementById('orb-toast');
        t.classList.add('show');
        setTimeout(function() {
            btn.classList.remove('copied');
            btn.innerText = symbol;
            t.classList.remove('show');
        }, 1500);
    }
    </script>
    <div id="orb-scroll-wrap" style="overflow-y:auto; max-height:520px;" onscroll="saveScroll()">
    <table class="orb-table">
    <thead><tr>
        <th>Symbol</th>
        <th>Signal Time</th>
        <th class="th-ema">EMA20 Status</th>
        <th class="th-orb">Yesterday High</th>
        <th class="th-orb">Today Open</th>
        <th>Gap %</th>
        <th>Vol Ratio</th>
        <th>Vol Momentum</th>
        <th class="th-new">Signal Price</th>
        <th style="background:#fee2e2;color:#991b1b;">SL</th>
        <th style="background:#dcfce7;color:#166534;">Target</th>
        <th class="th-new">Move Since Signal %</th>
        <th>LTP</th>
        <th class="th-new">High Since Signal</th>
        <th class="th-new">Peak Move %</th>
        <th>Volume</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        symbol       = str(row["Symbol"])
        signal_time  = str(row.get("Signal Time", "-"))
        ema_status   = row.get("EMA20 Status", "")
        yest_high    = row.get("Yesterday High", 0)
        today_open   = row.get("Today Open", 0)
        gap_pct      = row.get("Gap %", "-")
        vol_ratio    = row.get("Vol Ratio", "-")
        ltp          = float(row.get("LTP", 0))
        signal_price  = row.get("Signal Price", None)
        peak_ltp      = row.get("High Since Signal", None)
        yest_high_val = row.get("Yesterday High", 0)
        vol_mom       = row.get("Vol Momentum", "")

        # SL = Yesterday High
        sl_str = f"₹{float(yest_high_val):.2f}" if yest_high_val else "-"

        # Target = Signal Price + (Signal Price - SL) × 2
        if signal_price and yest_high_val and float(signal_price) > 0:
            risk   = float(signal_price) - float(yest_high_val)
            target = float(signal_price) + (risk * 2)
            target_str = f"₹{target:.2f}" if risk > 0 else "-"
        else:
            target_str = "-"

        # Move since signal
        if signal_price and float(signal_price) > 0:
            move_since     = ((ltp - float(signal_price)) / float(signal_price)) * 100
            move_since_str = f"{move_since:+.2f}%"
            move_c         = move_color(move_since_str)
        else:
            move_since_str = "-"
            move_c         = "#64748b"

        # Peak move
        if signal_price and peak_ltp and float(signal_price) > 0:
            peak_move     = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{peak_move:+.2f}%"
        else:
            peak_move_str = "-"

        signal_price_str = f"₹{float(signal_price):.2f}" if signal_price else "-"
        peak_ltp_str     = f"₹{float(peak_ltp):.2f}"    if peak_ltp     else "-"
        yest_high_str    = f"₹{float(yest_high):.2f}"   if yest_high    else "-"
        today_open_str   = f"₹{float(today_open):.2f}"  if today_open   else "-"

        html += f"""
        <tr>
            <td><button class="copy-btn" onclick="copyORB(this, '{symbol}')">{symbol}</button></td>
            <td class="signal-time-col">{signal_time}</td>
            <td>{ema_cell(ema_status)}</td>
            <td class="peak-val">{yest_high_str}</td>
            <td>₹{float(today_open):.2f}</td>
            <td>{gap_pct}</td>
            <td>{vol_ratio}</td>
            <td>{vol_mom}</td>
            <td>{signal_price_str}</td>
            <td style="color:#dc2626;font-weight:700">{sl_str}</td>
            <td style="color:#16a34a;font-weight:700">{target_str}</td>
            <td><span style="font-weight:700;color:{move_c}">{move_since_str}</span></td>
            <td>₹{ltp:.2f}</td>
            <td class="peak-val">{peak_ltp_str}</td>
            <td class="peak-val">{peak_move_str}</td>
            <td>{int(float(row.get("Volume", 0))):,}</td>
        </tr>"""

    html += "</tbody></table></div>"
    return html

# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────
st.markdown("""
    <style>.block-container {padding-top: 1rem !important;}</style>
""", unsafe_allow_html=True)

# ── Load historical once ──────────────────────────────────────
if "orb_historical" not in st.session_state:
    with st.spinner("Loading historical data..."):
        hist = fetch_orb_historical_data()
        if hist:
            st.session_state["orb_historical"] = hist
        else:
            st.error("❌ No data found in websocket_stock_values")
            st.stop()

historical = st.session_state["orb_historical"]

# ── Tracked stocks — load from Supabase on page load ─────────
today_str = datetime.now(IST).strftime("%Y-%m-%d")
if (
    "orb_tracked" not in st.session_state or
    st.session_state.get("orb_tracked_date") != today_str
):
    loaded = fetch_orb_signals_from_supabase(today_str)
    st.session_state["orb_tracked"]      = loaded
    st.session_state["orb_tracked_date"] = today_str

# ── Top bar ───────────────────────────────────────────────────
col1, col2 = st.columns([5, 1])
with col1:
    ws_status = "🟢 Live" if angel_ws.is_connected() else "🔴 Disconnected"
    now_ist   = datetime.now(IST)
    orb_end   = now_ist.replace(hour=ORB_END_H, minute=ORB_END_M, second=0, microsecond=0)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)

    if now_ist < orb_start:
        window_status = "⏳ Waiting for market open (9:15)"
    elif now_ist <= orb_end:
        mins_left = int((orb_end - now_ist).total_seconds() / 60)
        window_status = f"🟢 ORB Window Active — {mins_left} min left"
    else:
        window_status = "🔒 ORB Window Closed (9:30 passed)"

    st.markdown(
        f"📈 **ORB Scanner** &nbsp;|&nbsp; 📅 {historical['prev_date']} &nbsp;|&nbsp; "
        f"WS: {ws_status} &nbsp;|&nbsp; {window_status}",
        unsafe_allow_html=True
    )
with col2:
    if st.button("🔄 Reload", use_container_width=True):
        for key in ["orb_historical", "orb_tracked", "orb_tracked_date", "orb_ema20_cache"]:
            st.session_state.pop(key, None)
        st.rerun()

st.divider()

# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def orb_scanner_table():
    now_ist   = datetime.now(IST)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    orb_end   = now_ist.replace(hour=ORB_END_H,   minute=ORB_END_M,   second=0, microsecond=0)
    in_window = orb_start <= now_ist <= orb_end

    now_str       = now_ist.strftime("%H:%M:%S")
    live_ticks    = angel_ws.latest_ticks
    df_prev       = st.session_state["orb_historical"]["df_prev"]
    df_median     = st.session_state["orb_historical"]["df_median"]
    orb_tracked   = st.session_state["orb_tracked"]

    st.caption(
        f"Last updated: {now_str} | Ticks: {len(live_ticks)} | "
        f"Tracked: {len(orb_tracked)} stocks"
    )

    # ── Batch fetch EMA for pending stocks ───────────────────
    pending = st.session_state.get("orb_ema_pending", set())
    if pending:
        get_ema20_cache(list(pending))
        st.session_state["orb_ema_pending"] = set()

    # ── Scan for new stocks (time restriction removed for testing) ──
    if live_ticks:
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if not symbol or symbol in orb_tracked:
                continue

            live_ltp    = float(tick.get("ltp",    0))
            today_open  = float(tick.get("open",   0))
            live_volume = float(tick.get("volume", 0))

            if live_ltp <= 0 or today_open <= 0:
                continue

            # ── Get yesterday's high + close ──────────────────
            prev_row = df_prev[df_prev["stock"] == symbol]
            if prev_row.empty:
                continue

            yest_high  = float(prev_row["yesterday_high"].values[0])
            yest_close = float(prev_row["yesterday_close"].values[0])

            if yest_high <= 0 or yest_close <= 0:
                continue

            # ── Condition 3: Gap up OR gap down > 1% → ignore ───
            gap_pct = ((today_open - yest_close) / yest_close) * 100
            if abs(gap_pct) >= MAX_GAP_PCT:
                continue

            # ── Condition 2: open > yest_high OR ltp > yest_high
            if not (today_open > yest_high or live_ltp > yest_high):
                continue

            # ── Get median vol + vol ratio check ─────────────────
            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
            if median_vol <= 0:
                continue
            vol_ratio_val = live_volume / median_vol
            if vol_ratio_val < 1.0:
                continue  # vol ratio < 1x → skip

            # ── Condition 1: Yesterday close > EMA20 ─────────
            # Check cache first — avoid yfinance call inside tick loop
            ema_cache_check = st.session_state.get("orb_ema20_cache", {})
            if symbol in ema_cache_check:
                ema_status = ema_cache_check[symbol].get("status", "")
                if not ema_status.startswith("✅"):
                    continue
            else:
                # Not in cache yet — add to pending, will check next cycle
                if "orb_ema_pending" not in st.session_state:
                    st.session_state["orb_ema_pending"] = set()
                st.session_state["orb_ema_pending"].add(symbol)
                continue

            # ── All conditions pass → save to Supabase + track ──
            today_date = datetime.now(IST).strftime("%Y-%m-%d")
            save_orb_signal_to_supabase(
                stock          = symbol,
                today_str      = today_date,
                signal_time    = now_str,
                yesterday_high = yest_high,
                today_open     = today_open,
                gap_pct        = gap_pct,
                signal_price   = live_ltp,
                ema20_status   = ema_status,
            )
            orb_tracked[symbol] = {
                "signal_time"   : now_str,
                "signal_price"  : live_ltp,
                "peak_ltp"      : live_ltp,
                "yesterday_high": yest_high,
                "yesterday_close": yest_close,
                "today_open"    : today_open,
                "gap_pct"       : round(gap_pct, 2),
                "median_vol"    : median_vol,
            }

        st.session_state["orb_tracked"] = orb_tracked

    if not orb_tracked:
        if in_window:
            st.info("⏳ Scanning... No breakout stocks found yet.")
        else:
            st.info("No stocks were tracked during the ORB window today.")
        return

    # ── Update peak_ltp for tracked stocks ───────────────────
    if live_ticks:
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if symbol not in orb_tracked:
                continue
            ltp = float(tick.get("ltp", 0))
            if ltp > orb_tracked[symbol].get("peak_ltp", 0):
                update_orb_peak_ltp(symbol, datetime.now(IST).strftime("%Y-%m-%d"), ltp)
                orb_tracked[symbol]["peak_ltp"] = ltp
        st.session_state["orb_tracked"] = orb_tracked

    # ── Build display DataFrame ───────────────────────────────
    rows = []
    for symbol, data in orb_tracked.items():
        token      = None
        for t, n in TOKEN_TO_NAME.items():
            if n == symbol:
                token = t
                break

        live_ltp    = float(live_ticks.get(token, {}).get("ltp",    data["signal_price"])) if token else data["signal_price"]
        live_volume = float(live_ticks.get(token, {}).get("volume", 0)) if token else 0
        # median_vol — from session data or df_median fallback
        median_vol  = data.get("median_vol", 0)
        if median_vol == 0:
            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
        vol_ratio   = round(live_volume / median_vol, 2) if median_vol > 0 else 0

        vol_ratio_num = round(live_volume / median_vol, 2) if median_vol > 0 else 0
        rows.append({
            "Symbol"        : symbol,
            "Signal Time"   : data["signal_time"],
            "Yesterday High": data["yesterday_high"],
            "Today Open"    : data["today_open"],
            "Gap %"         : f"{data['gap_pct']:+.2f}%",
            "Vol Ratio"     : f"{vol_ratio_num:.2f}x",
            "Vol Momentum"  : get_vol_momentum(vol_ratio_num),
            "Signal Price"  : data["signal_price"],
            "LTP"           : live_ltp,
            "High Since Signal": data["peak_ltp"],
            "Volume"        : live_volume,
        })

    df_display = pd.DataFrame(rows)

    # ── EMA20 — fetch only for tracked stocks ─────────────────
    ema_cache = get_ema20_cache(list(orb_tracked.keys()))
    df_display["EMA20 Status"] = df_display["Symbol"].apply(
        lambda s: ema_cache.get(s, {}).get("status", "⏳")
    )

    # ── Sort: by Vol Ratio descending ────────────────────────
    df_display["vol_ratio_num"] = df_display["Vol Ratio"].apply(
        lambda x: float(str(x).replace("x","")) if x else 0
    )
    df_display = df_display.sort_values("vol_ratio_num", ascending=False)                            .drop(columns=["vol_ratio_num"])                            .reset_index(drop=True)

    st.success(f"**{len(df_display)} stocks** tracked in ORB window")
    st.components.v1.html(
        render_orb_table(df_display),
        height=min(600, 60 + len(df_display) * 38),
        scrolling=False
    )


orb_scanner_table()
