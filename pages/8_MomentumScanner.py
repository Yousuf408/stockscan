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
    # Paginate to get all dates
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
    target_date   = sorted_dates[0]           # Latest trading day
    prev_date     = sorted_dates[1] if len(sorted_dates) > 1 else None
    last_5_dates  = sorted_dates[1:6]         # 5 days BEFORE target_date

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

    # Keep last (most recent) row per stock
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
# CORE SCAN LOGIC (pure Python — mirrors SQL query)
# ─────────────────────────────────────────────────────────────
def run_momentum_scan(historical: dict) -> pd.DataFrame:
    """
    Merge live ticks (or Supabase fallback) with historical cache.
    Apply all SQL filters and labels. Return final DataFrame.
    """
    df_target  = historical["df_target"]
    df_prev    = historical["df_prev"]
    df_median  = historical["df_median"]

    # ── Decide data source: live WS or Supabase fallback ────
    live_ticks = angel_ws.latest_ticks  # {token: {ltp, open, volume, ...}}

    if live_ticks:
        # Build live DataFrame from WebSocket ticks
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
        # Fallback: use Supabase target_date data
        df_live = df_target.copy() if not df_target.empty else pd.DataFrame()
        data_source = "🟡 Supabase (Market Closed)"

    if df_live.empty or df_prev.empty or df_median.empty:
        return pd.DataFrame(), data_source

    # ── Merge all three ──────────────────────────────────────
    df = df_live.merge(df_prev,   on="stock", how="inner")
    df = df.merge(df_median,      on="stock", how="inner")

    # Convert to numeric
    for col in ["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop nulls / zeros
    df = df.dropna(subset=["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"])
    df = df[df["median_vol"] > 0]
    df = df[df["yesterday_close"] > 0]

    # ── Calculate metrics ────────────────────────────────────
    df["vol_ratio"]      = (df["live_volume"] / df["median_vol"]).round(2)
    df["gap_pct"]        = ((df["live_open"] - df["yesterday_close"]) / df["yesterday_close"] * 100).round(2)
    df["intraday_pct"]   = ((df["live_ltp"]  - df["live_open"])       / df["live_open"]        * 100).round(2)
    df["chg_vs_prev"]    = ((df["live_ltp"]  - df["yesterday_close"]) / df["yesterday_close"]  * 100).round(2)

    # ── Priority score ───────────────────────────────────────
    df["priority_score"] = (df["vol_ratio"] * 0.3 + df["intraday_pct"] * 0.7).round(2)

    # ── FILTERS (mirrors SQL WHERE clause) ───────────────────
    df = df[
        (df["vol_ratio"]    >= 1.5) &
        (df["intraday_pct"] >= 1.0) &
        (df["live_ltp"]     >  df["live_open"]) &          # Green candle
        (df["live_ltp"]     >  df["yesterday_close"]) &    # Above prev close
        (df["live_open"]    <= df["yesterday_close"] * 1.01)  # Max 1% gap-up
    ]

    if df.empty:
        return pd.DataFrame(), data_source

    # ── Labels ───────────────────────────────────────────────
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

    def live_action(r):
        if r >= 3.0: return "🚀 STRONG BLAST"
        if r >= 2.0: return "⚡ BLASTING"
        if r >= 1.5: return "👀 PRE-BLAST"
        return ""

    df["vol_momentum"]       = df["vol_ratio"].apply(vol_momentum)
    df["momentum_detection"] = df.apply(lambda x: momentum_detection(x["vol_ratio"], x["intraday_pct"], x["gap_pct"]), axis=1)
    df["live_action"]        = df["vol_ratio"].apply(live_action)

    # ── Final display columns ────────────────────────────────
    df = df.rename(columns={
        "stock"         : "Symbol",
        "yesterday_close": "Prev Close",
        "live_open"     : "Open",
        "live_ltp"      : "LTP",
        "live_volume"   : "Volume",
    })

    df["Gap %"]          = df["gap_pct"].apply(lambda x: f"{x:+.2f}%")
    df["Intraday %"]     = df["intraday_pct"].apply(lambda x: f"{x:+.2f}%")
    df["Chg vs Prev %"]  = df["chg_vs_prev"].apply(lambda x: f"{x:+.2f}%")
    df["Vol Ratio"]      = df["vol_ratio"].apply(lambda x: f"{x:.2f}x")
    df["Score"]          = df["priority_score"]

    display_cols = [
        "Symbol", "Prev Close", "Open", "LTP", "Volume",
        "Gap %", "Intraday %", "Chg vs Prev %",
        "Vol Ratio", "vol_momentum", "momentum_detection", "live_action", "Score"
    ]

    df = df[display_cols].rename(columns={
        "vol_momentum"      : "Vol Momentum",
        "momentum_detection": "Momentum",
        "live_action"       : "Action",
    })

    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return df, data_source


# ─────────────────────────────────────────────────────────────
# HTML TABLE WITH CLICK-TO-COPY SYMBOL
# ─────────────────────────────────────────────────────────────
def render_html_table(df: pd.DataFrame) -> str:
    def row_bg(momentum):
        if "STRONG BUILDING" in momentum: return "#d4edda"
        if "BUILDING"        in momentum: return "#cce5ff"
        if "STABLE"          in momentum: return "#fff3cd"
        if "COOLING"         in momentum: return "#f8d7da"
        return "#ffffff"

    html = """
    <style>
    .mom-table {width:100%; border-collapse:collapse; font-size:13px; font-family:sans-serif;}
    .mom-table th {background:#f1f5f9; color:#475569; font-weight:600; padding:8px 10px; text-align:left; border-bottom:2px solid #e2e8f0; white-space:nowrap;}
    .mom-table td {padding:7px 10px; border-bottom:1px solid #e2e8f0; white-space:nowrap;}
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
        <th>Symbol</th><th>Prev Close</th><th>Open</th><th>LTP</th>
        <th>Volume</th><th>Gap %</th><th>Intraday %</th><th>Chg vs Prev %</th>
        <th>Vol Ratio</th><th>Momentum</th><th>Action</th><th>Score</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        bg     = row_bg(str(row.get("Momentum", "")))
        symbol = str(row["Symbol"])
        html += f"""
        <tr style="background:{bg}">
            <td><button class="copy-btn" onclick="copySymbol(this, '{symbol}')">{symbol}</button></td>
            <td>₹{float(row['Prev Close']):.2f}</td>
            <td>₹{float(row['Open']):.2f}</td>
            <td>₹{float(row['LTP']):.2f}</td>
            <td>{int(float(row['Volume'])):,}</td>
            <td>{row['Gap %']}</td>
            <td>{row['Intraday %']}</td>
            <td>{row['Chg vs Prev %']}</td>
            <td>{row['Vol Ratio']}</td>
            <td>{row['Momentum']}</td>
            <td>{row['Action']}</td>
            <td>{float(row['Score']):.2f}</td>
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

# ── Auto-refresh fragment (tick-to-tick table update) ────────
@st.fragment(run_every=5)
def scanner_table():
    df, data_source = run_momentum_scan(st.session_state["momentum_historical"])

    now_ist = datetime.now(IST).strftime("%H:%M:%S")
    st.caption(f"Source: {data_source} | Last updated: {now_ist} | Ticks: {len(angel_ws.latest_ticks)}")

    if df.empty:
        st.info("No stocks matching momentum criteria right now.")
        return

    st.success(f"**{len(df)} stocks** matching momentum criteria")
    st.components.v1.html(render_html_table(df), height=min(600, 60 + len(df) * 38), scrolling=True)

scanner_table()
