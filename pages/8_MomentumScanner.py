"""
8_MomentumScanner.py
Live Momentum Scanner — uses angel_ws.latest_ticks + Supabase historical cache
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from supabase import create_client

import angel_ws
from config import STOCKS_WATCHLIST

# ── Auto-connect WebSocket ───────────────────────────────────
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
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

IST = timezone(timedelta(hours=5, minutes=30))

# Token → Name lookup from config
TOKEN_TO_NAME = {token: name for name, token, kind in STOCKS_WATCHLIST}
NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST}

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────
# SIGNAL TIME — SUPABASE SAVE & FETCH
# ─────────────────────────────────────────────────────────────
def fetch_signal_data_from_supabase(today_str: str) -> dict:
    """
    Fetch all signal data for today from momentum_signal_times table.
    Returns dict: {stock: {signal_time, signal_price, peak_ltp}}
    """
    try:
        supabase = get_supabase()
        resp = supabase.table("momentum_signal_times") \
            .select("stock, signal_time, signal_price, peak_ltp") \
            .eq("signal_date", today_str) \
            .execute()
        result = {}
        for row in resp.data:
            result[row["stock"]] = {
                "signal_time"  : row.get("signal_time", ""),
                "signal_price" : row.get("signal_price", None),
                "peak_ltp"     : row.get("peak_ltp", None),
            }
        return result
    except Exception as e:
        return {}


def save_signal_to_supabase(stock: str, today_str: str, signal_time: str,
                             vol_ratio: float, intraday_pct: float,
                             vol_momentum: str, momentum: str, score: float,
                             signal_price: float):
    """
    Save signal data to Supabase ONLY if not already saved today.
    Uses UNIQUE(stock, signal_date) — duplicate insert will be ignored.
    """
    try:
        supabase = get_supabase()
        supabase.table("momentum_signal_times").upsert({
            "stock"        : stock,
            "signal_date"  : today_str,
            "signal_time"  : signal_time,
            "vol_ratio"    : round(float(vol_ratio), 2),
            "intraday_pct" : round(float(intraday_pct), 2),
            "vol_momentum" : vol_momentum,
            "momentum"     : momentum,
            "score"        : round(float(score), 2),
            "signal_price" : round(float(signal_price), 2),
            "peak_ltp"     : round(float(signal_price), 2),  # init peak = signal price
        }, on_conflict="stock,signal_date", ignore_duplicates=True).execute()
    except Exception as e:
        pass  # Silent fail — don't break scanner if save fails


def update_peak_ltp_in_supabase(stock: str, today_str: str, new_peak_ltp: float):
    """
    Update peak_ltp in Supabase when a new high is reached.
    """
    try:
        supabase = get_supabase()
        supabase.table("momentum_signal_times") \
            .update({"peak_ltp": round(float(new_peak_ltp), 2)}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception as e:
        pass  # Silent fail


# ─────────────────────────────────────────────────────────────
# FETCH HISTORICAL DATA FROM SUPABASE (runs ONCE, cached)
# ─────────────────────────────────────────────────────────────
def fetch_historical_data():
    """
    Fetch from websocket_stock_values:
    1. target_date      → latest trading day's ltp/open/volume (fallback when WS off)
    2. yesterday_close  → prev trading day's last ltp per stock
    3. median_vol_5d    → median volume of last 5 trading days per stock
    Returns dict with all three DataFrames.
    """
    supabase = get_supabase()

    # ── Step 1: Find all distinct trading dates ──────────────
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
    target_date   = sorted_dates[0]
    prev_date     = sorted_dates[1] if len(sorted_dates) > 1 else None
    last_5_dates  = sorted_dates[1:6]

    # ── Step 2: Fetch target_date data (fallback for closed market) ──
    target_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, ltp, open, volume") \
            .eq("date", target_date) \
            .order("created_at", desc=True) \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        target_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    df_target = pd.DataFrame(target_rows)
    if not df_target.empty:
        df_target = df_target.drop_duplicates(subset="stock", keep="first")
        df_target = df_target.rename(columns={"ltp": "live_ltp", "open": "live_open", "volume": "live_volume"})

    # ── Step 3: Fetch yesterday's close ──────────────────────
    df_prev = pd.DataFrame()
    if prev_date:
        prev_rows = []
        offset = 0
        while True:
            resp = supabase.table("websocket_stock_values") \
                .select("stock, ltp") \
                .eq("date", prev_date) \
                .order("created_at", desc=True) \
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
            df_prev = df_prev.rename(columns={"ltp": "yesterday_close"})

    # ── Step 4: Fetch last 5 days volume for median ──────────
    df_median = pd.DataFrame()
    if last_5_dates:
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

        if vol_rows:
            df_vol = pd.DataFrame(vol_rows)
            df_vol["volume"] = pd.to_numeric(df_vol["volume"], errors="coerce")
            df_median = df_vol.groupby("stock")["volume"].median().reset_index()
            df_median = df_median.rename(columns={"volume": "median_vol"})

    return {
        "target_date"  : target_date,
        "prev_date"    : prev_date,
        "df_target"    : df_target,
        "df_prev"      : df_prev,
        "df_median"    : df_median,
    }

# ─────────────────────────────────────────────────────────────
# CORE SCAN LOGIC — UNCHANGED
# ─────────────────────────────────────────────────────────────
def run_momentum_scan(historical: dict) -> pd.DataFrame:
    df_target  = historical["df_target"]
    df_prev    = historical["df_prev"]
    df_median  = historical["df_median"]

    live_ticks = angel_ws.latest_ticks

    if live_ticks:
        rows = []
        for token, tick in live_ticks.items():
            name = TOKEN_TO_NAME.get(token)
            if not name:
                continue
            rows.append({
                "stock"      : name,
                "live_ltp"   : tick.get("ltp", 0),
                "live_open"  : tick.get("open", 0),
                "live_volume": tick.get("volume", 0),
            })
        df_live = pd.DataFrame(rows)
        data_source = "🟢 Live WebSocket"
    else:
        df_live = df_target.copy() if not df_target.empty else pd.DataFrame()
        data_source = "🟡 Supabase (Market Closed)"

    if df_live.empty or df_prev.empty or df_median.empty:
        return pd.DataFrame(), data_source

    df = df_live.merge(df_prev,   on="stock", how="inner")
    df = df.merge(df_median,      on="stock", how="inner")

    for col in ["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"])
    df = df[df["median_vol"] > 0]
    df = df[df["yesterday_close"] > 0]

    # ─────────────────────────────────────────────────────────
    # CALCULATE METRICS (RAW VALUES - NO ROUNDING YET)
    # ─────────────────────────────────────────────────────────
    df["vol_ratio"]      = df["live_volume"] / df["median_vol"]
    df["gap_pct"]        = ((df["live_open"] - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["intraday_pct"]   = ((df["live_ltp"]  - df["live_open"]) / df["live_open"] * 100)
    df["chg_vs_prev"]    = ((df["live_ltp"]  - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["priority_score"] = (df["vol_ratio"] * 0.3 + df["intraday_pct"] * 0.7)

    # ─────────────────────────────────────────────────────────
    # FILTER USING RAW VALUES (BEFORE ROUNDING)
    # ─────────────────────────────────────────────────────────
    df = df[
        (df["vol_ratio"]    >= 1.5) &
        (df["intraday_pct"] >= 1.0) &
        (df["live_ltp"]     >  df["live_open"]) &
        (df["live_ltp"]     >  df["yesterday_close"]) &
        (df["live_open"]    <= df["yesterday_close"] * 1.01)
    ]

    if df.empty:
        return pd.DataFrame(), data_source

    # ─────────────────────────────────────────────────────────
    # SIGNAL DETECTION (using RAW values for detection)
    # ─────────────────────────────────────────────────────────
    def vol_momentum(r):
        if r >= 3.0: return "🔥 Very Strong"
        if r >= 2.0: return "⚡ Strong"
        if r >= 1.5: return "👀 Building"
        return ""

    def momentum_detection(v, i, g):
        if v >= 2.5 and i >= 1.5 and g <= 0.5: return "🚀 STRONG BUILDING"
        if v >= 2.0 and i >= 0.8:               return "📈 BUILDING"
        if v >= 1.5 and 0 <= i <= 0.7:          return "➡️ STABLE"
        if v >= 1.5 and i < 0:                  return "⚠️ COOLING"
        return "❌ WEAK"

    df["vol_momentum"]       = df["vol_ratio"].apply(vol_momentum)
    df["momentum_detection"] = df.apply(lambda x: momentum_detection(x["vol_ratio"], x["intraday_pct"], x["gap_pct"]), axis=1)

    # ─────────────────────────────────────────────────────────
    # NOW ROUND ALL METRICS FOR DISPLAY
    # ─────────────────────────────────────────────────────────
    df["vol_ratio"]      = df["vol_ratio"].round(2)
    df["gap_pct"]        = df["gap_pct"].round(2)
    df["intraday_pct"]   = df["intraday_pct"].round(2)
    df["chg_vs_prev"]    = df["chg_vs_prev"].round(2)
    df["priority_score"] = df["priority_score"].round(2)

    df = df.rename(columns={
        "stock"          : "Symbol",
        "yesterday_close": "Prev Close",
        "live_open"      : "Open",
        "live_ltp"       : "LTP",
        "live_volume"    : "Volume",
    })

    df["Gap %"]         = df["gap_pct"].apply(lambda x: f"{x:+.2f}%")
    df["Chg vs Prev %"] = df["chg_vs_prev"].apply(lambda x: f"{x:+.2f}%")
    df["Vol Ratio"]     = df["vol_ratio"].apply(lambda x: f"{x:.2f}x")
    df["Score"]         = df["priority_score"]

    display_cols = [
        "Symbol", "Prev Close", "Open", "LTP", "Volume",
        "Gap %", "Chg vs Prev %",
        "Vol Ratio", "vol_momentum", "momentum_detection", "Score",
        "vol_ratio", "intraday_pct", "priority_score"
    ]

    df = df[display_cols].rename(columns={
        "vol_momentum"      : "Vol Momentum",
        "momentum_detection": "Momentum",
    })

    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return df, data_source


# ─────────────────────────────────────────────────────────────
# HTML TABLE
# ─────────────────────────────────────────────────────────────
def render_html_table(df: pd.DataFrame) -> str:
    def row_bg(momentum):
        if "STRONG BUILDING" in momentum: return "#d4edda"
        if "BUILDING"        in momentum: return "#cce5ff"
        if "STABLE"          in momentum: return "#fff3cd"
        if "COOLING"         in momentum: return "#f8d7da"
        return "#ffffff"

    def move_color(pct_str):
        """Return color based on move % value"""
        try:
            val = float(pct_str.replace("%", "").replace("+", ""))
            if val >= 5.0:  return "#16a34a"  # strong green
            if val >= 2.0:  return "#ca8a04"  # amber
            if val >= 0:    return "#64748b"  # grey
            return "#dc2626"                   # red for negative
        except:
            return "#64748b"

    html = """
    <style>
    .mom-table {width:100%; border-collapse:collapse; font-size:13px; font-family:sans-serif;}
    .mom-table th {background:#f1f5f9; color:#475569; font-weight:600; padding:8px 10px; text-align:left; border-bottom:2px solid #e2e8f0; white-space:nowrap;}
    .mom-table th.th-new {background:#ede9fe; color:#5b21b6;}
    .mom-table td {padding:7px 10px; border-bottom:1px solid #e2e8f0; white-space:nowrap;}
    .signal-time-col {font-weight:700; color:#0f172a; background:#fef3c7;}
    .peak-val {color:#7c3aed; font-weight:600;}
    .copy-btn {
        cursor:pointer; font-weight:700; color:#0f172a;
        background:#e2e8f0; border:none; padding:3px 8px;
        border-radius:4px; font-size:12px; transition:background 0.2s;
    }
    .copy-btn:hover {background:#10b981; color:white;}
    .copy-btn.copied {background:#10b981; color:white;}
    .toast {
        position:fixed; bottom:30px; left:50%; transform:translateX(-50%);
        background:#0f172a; color:white; padding:8px 20px;
        border-radius:8px; font-size:13px; z-index:9999;
        opacity:0; transition:opacity 0.3s; pointer-events:none;
    }
    .toast.show {opacity:1;}
    </style>
    <div id="toast" class="toast">✅ Copied!</div>
    <script>
    function copySymbol(btn, symbol) {
        navigator.clipboard.writeText(symbol);
        btn.classList.add('copied');
        btn.innerText = '✓ ' + symbol;
        var toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(function() {
            btn.classList.remove('copied');
            btn.innerText = symbol;
            toast.classList.remove('show');
        }, 1500);
    }
    </script>
    <table class="mom-table">
    <thead><tr>
        <th>Symbol</th>
        <th>Signal Time</th>
        <th>Gap %</th>
        <th>Chg vs Prev %</th>
        <th>Vol Ratio</th>
        <th>Vol Momentum</th>
        <th>Momentum</th>
        <th class="th-new">Signal Price</th>
        <th class="th-new">Move Since Signal %</th>
        <th>LTP</th>
        <th class="th-new">High Since Signal</th>
        <th class="th-new">Peak Move %</th>
        <th>Volume</th>
        <th>Open</th>
        <th>Prev Close</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        bg           = row_bg(str(row.get("Momentum", "")))
        symbol       = str(row["Symbol"])
        signal_time  = str(row.get("Signal Time", "-"))
        signal_price = row.get("Signal Price", None)
        ltp          = float(row["LTP"])
        peak_ltp     = row.get("High Since Signal", None)

        # ── Move Since Signal % ──────────────────────────────
        if signal_price and float(signal_price) > 0:
            move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100
            move_since_str = f"{move_since:+.2f}%"
            move_c = move_color(move_since_str)
        else:
            move_since_str = "-"
            move_c = "#64748b"

        # ── Peak Move % ──────────────────────────────────────
        if signal_price and peak_ltp and float(signal_price) > 0:
            peak_move = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{peak_move:+.2f}%"
        else:
            peak_move_str = "-"

        signal_price_str = f"₹{float(signal_price):.2f}" if signal_price else "-"
        peak_ltp_str     = f"₹{float(peak_ltp):.2f}"    if peak_ltp     else "-"

        html += f"""
        <tr style="background:{bg}">
            <td><button class="copy-btn" onclick="copySymbol(this, '{symbol}')">{symbol}</button></td>
            <td class="signal-time-col">{signal_time}</td>
            <td>{row['Gap %']}</td>
            <td>{row['Chg vs Prev %']}</td>
            <td>{row['Vol Ratio']}</td>
            <td>{row['Vol Momentum']}</td>
            <td>{row['Momentum']}</td>
            <td>{signal_price_str}</td>
            <td><span style="font-weight:700;color:{move_c}">{move_since_str}</span></td>
            <td>₹{ltp:.2f}</td>
            <td class="peak-val">{peak_ltp_str}</td>
            <td class="peak-val">{peak_move_str}</td>
            <td>{int(float(row['Volume'])):,}</td>
            <td>₹{float(row['Open']):.2f}</td>
            <td>₹{float(row['Prev Close']):.2f}</td>
        </tr>"""

    html += "</tbody></table>"
    return html


# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────
st.markdown("""
    <style>
    .block-container {padding-top: 1rem !important;}
    </style>
""", unsafe_allow_html=True)

# ── Load historical once into session_state ──────────────────
if "momentum_historical" not in st.session_state:
    with st.spinner("Loading historical data..."):
        hist = fetch_historical_data()
        if hist:
            st.session_state["momentum_historical"] = hist
        else:
            st.error("❌ No data found in websocket_stock_values")
            st.stop()

historical = st.session_state["momentum_historical"]

# ── Today's date string (IST) ────────────────────────────────
today_str = datetime.now(IST).strftime("%Y-%m-%d")

# ── Load signal data from Supabase ONCE per day ──────────────
if (
    "signal_data" not in st.session_state or
    st.session_state.get("signal_data_date") != today_str
):
    st.session_state["signal_data"] = fetch_signal_data_from_supabase(today_str)
    st.session_state["signal_data_date"] = today_str

# ── Compact top bar ──────────────────────────────────────────
col1, col2 = st.columns([5, 1])
with col1:
    ws_status = "🟢 Live" if angel_ws.is_connected() else "🔴 Disconnected"
    st.markdown(f"🚀 **Momentum Scanner** &nbsp;|&nbsp; 📅 {historical['target_date']} vs {historical['prev_date']} &nbsp;|&nbsp; WS: {ws_status}", unsafe_allow_html=True)
with col2:
    if st.button("🔄 Reload", use_container_width=True):
        del st.session_state["momentum_historical"]
        st.rerun()

st.divider()

# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def scanner_table():
    df, data_source = run_momentum_scan(st.session_state["momentum_historical"])

    now_ist = datetime.now(IST).strftime("%H:%M:%S")
    st.caption(f"Source: {data_source} | Last updated: {now_ist} | Ticks: {len(angel_ws.latest_ticks)}")

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    current_time_ist = datetime.now(IST).strftime("%H:%M:%S")
    today            = datetime.now(IST).strftime("%Y-%m-%d")

    signal_data = st.session_state["signal_data"]

    for _, row in df.iterrows():
        symbol = row["Symbol"]
        ltp    = float(row["LTP"])

        if symbol not in signal_data:
            # ── First time — save signal price + init peak ───
            save_signal_to_supabase(
                stock        = symbol,
                today_str    = today,
                signal_time  = current_time_ist,
                vol_ratio    = row.get("vol_ratio", 0),
                intraday_pct = row.get("intraday_pct", 0),
                vol_momentum = str(row.get("Vol Momentum", "")),
                momentum     = str(row.get("Momentum", "")),
                score        = row.get("Score", 0),
                signal_price = ltp,
            )
            signal_data[symbol] = {
                "signal_time"  : current_time_ist,
                "signal_price" : ltp,
                "peak_ltp"     : ltp,
            }

        else:
            # ── Already seen — check if new peak ─────────────
            current_peak = signal_data[symbol].get("peak_ltp") or ltp
            if ltp > current_peak:
                update_peak_ltp_in_supabase(symbol, today, ltp)
                signal_data[symbol]["peak_ltp"] = ltp

    # ── Assign columns safely ────────────────────────────────
    df["Signal Time"]      = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_time", "-"))
    df["Signal Price"]     = df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("signal_price", None))
    df["High Since Signal"]= df["Symbol"].apply(lambda s: signal_data.get(s, {}).get("peak_ltp", None))

    # ── Display columns ──────────────────────────────────────
    display_cols = [
        "Symbol", "Signal Time", "Gap %", "Chg vs Prev %",
        "Vol Ratio", "Vol Momentum", "Momentum",
        "Signal Price", "LTP", "High Since Signal",
        "Volume", "Open", "Prev Close",
    ]
    df_display = df[display_cols]

    st.success(f"**{len(df_display)} stocks** matching momentum criteria")
    st.components.v1.html(render_html_table(df_display), height=min(600, 60 + len(df_display) * 38), scrolling=True)


scanner_table()
