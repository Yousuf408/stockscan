"""
9_SetupTracker.py
Setup Pattern Tracker — Historical 3-4 day volume consolidation analysis
Identifies stocks in pre-spike consolidation phase
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from supabase import create_client

from config import STOCKS_WATCHLIST

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Setup Tracker",
    page_icon="📊",
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
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jekt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

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
# FETCH LAST 4 DAYS DATA FROM SUPABASE
# ─────────────────────────────────────────────────────────────
def fetch_setup_data():
    """
    Fetch last 4 trading days data to analyze consolidation patterns.
    Returns dict with dates and volume/price data per stock per day.
    """
    supabase = get_supabase()

    # ── Step 1: Find last 5 distinct trading dates ──────────────
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
    target_date = sorted_dates[0]        # Today (last trading day)
    last_4_dates = sorted_dates[0:4]     # Today + 3 previous days

    st.caption(f"Analyzing: {sorted_dates[0:4]} | Total dates in DB: {len(sorted_dates)}")

    # ── Step 2: Fetch EOD data for last 4 days ──────────────────
    all_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, date, ltp, open, volume") \
            .in_("date", last_4_dates) \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    
    return {
        "dates"       : sorted_dates[0:4],
        "target_date" : target_date,
        "data"        : df,
    }

# ─────────────────────────────────────────────────────────────
# ANALYZE SETUP PATTERNS (3-4 DAY CONSOLIDATION)
# ─────────────────────────────────────────────────────────────
def analyze_setups(historical: dict) -> pd.DataFrame:
    """
    Analyze 3-4 day consolidation patterns.
    Returns stocks in setup phase with stage and readiness score.
    """
    df = historical["data"]
    dates = historical["dates"]
    
    if df.empty or len(dates) < 2:
        return pd.DataFrame()

    # Convert columns to numeric
    for col in ["volume", "ltp", "open"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Get latest price per stock per date
    df_pivot = df.drop_duplicates(subset=["stock", "date"], keep="last")

    results = []

    for stock in df_pivot["stock"].unique():
        stock_data = df_pivot[df_pivot["stock"] == stock].sort_values("date", ascending=False)
        
        if len(stock_data) < 2:
            continue

        # ── Extract volumes and prices for each day ──────────────
        days_data = {}
        for idx, row in stock_data.iterrows():
            days_data[row["date"]] = {
                "volume": row["volume"],
                "ltp": row["ltp"],
                "open": row["open"],
            }

        # Get 4 days (or less if not available)
        day_list = sorted(days_data.keys(), reverse=True)[:4]
        
        if len(day_list) < 2:
            continue

        # Day 1 (today), Day 2 (yesterday), Day 3 (2 days ago), Day 4 (3 days ago)
        day1 = days_data.get(day_list[0], {})  # Today
        day2 = days_data.get(day_list[1], {})  # Yesterday
        day3 = days_data.get(day_list[2], {})  # 2 days ago
        day4 = days_data.get(day_list[3], {})  # 3 days ago

        vol1 = day1.get("volume", 0)
        vol2 = day2.get("volume", 0)
        vol3 = day3.get("volume", 0)
        vol4 = day4.get("volume", 0)

        ltp1 = day1.get("ltp", 0)
        ltp2 = day2.get("ltp", 0)
        ltp3 = day3.get("ltp", 0)

        if vol1 == 0 or vol2 == 0 or ltp2 == 0:
            continue

        # ── Calculate consolidation metrics ──────────────────────
        vol_ratio_today = vol1 / max(vol2, 1)  # Today vs Yesterday
        vol_ratio_yest = vol2 / max(vol3, 1)   # Yesterday vs 2 days ago
        vol_ratio_d3 = vol3 / max(vol4, 1)     # 2 days ago vs 3 days ago

        price_change_today = ((ltp1 - ltp2) / ltp2 * 100) if ltp2 > 0 else 0
        price_change_yest = ((ltp2 - ltp3) / ltp3 * 100) if ltp3 > 0 else 0

        # ── SETUP STAGE DETECTION ────────────────────────────────
        setup_stage = ""
        setup_score = 0

        # Stage 1: Signal appearing (vol spike in early days)
        if vol_ratio_d3 >= 1.5 or vol_ratio_yest >= 1.5:
            setup_stage = "📍 SIGNAL_START"
            setup_score = 1

        # Stage 2: Building (multiple days with elevated volume)
        if (vol_ratio_d3 >= 1.3 or vol_ratio_yest >= 1.3) and abs(price_change_yest) <= 5:
            setup_stage = "📈 BUILDING"
            setup_score = 2

        # Stage 3: CONSOLIDATION (key signal!)
        # Volume drops significantly but price stable
        if vol_ratio_today < 0.9 and vol2 > 10000 and abs(price_change_today) <= 2:
            setup_stage = "🔴 CONSOLIDATING"
            setup_score = 3  # HIGHEST!

        # Stage 4: Ready to spike (consolidation + bullish signal)
        if setup_stage == "🔴 CONSOLIDATING" and ltp1 > ltp2:
            setup_stage = "🚀 READY_TO_SPIKE"
            setup_score = 4  # PRIME!

        if setup_score < 1:
            continue

        # ── Calculate readiness percentage ───────────────────────
        readiness = 0
        if vol_ratio_today < 1.0:
            readiness += 25  # Volume dropped
        if abs(price_change_today) <= 2:
            readiness += 25  # Price stable
        if ltp1 > ltp2:
            readiness += 25  # Bullish close
        if vol_ratio_yest >= 1.3:
            readiness += 25  # Previous buildup

        readiness = min(100, max(0, readiness))

        results.append({
            "Symbol": stock,
            "Day_1_Vol": vol1,
            "Day_2_Vol": vol2,
            "Day_3_Vol": vol3,
            "Day_4_Vol": vol4,
            "Vol_D1_D2": f"{vol_ratio_today:.2f}x",
            "Vol_D2_D3": f"{vol_ratio_yest:.2f}x",
            "Price_D1": f"₹{ltp1:.2f}",
            "Price_D2": f"₹{ltp2:.2f}",
            "Chg_D1_%": f"{price_change_today:+.2f}%",
            "Chg_D2_%": f"{price_change_yest:+.2f}%",
            "Setup_Stage": setup_stage,
            "Readiness_%": readiness,
            "Days_in_Setup": len(day_list),
            "setup_score": setup_score,
        })

    if not results:
        return pd.DataFrame()

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values("Readiness_%", ascending=False)
    df_result = df_result.reset_index(drop=True)

    return df_result

# ─────────────────────────────────────────────────────────────
# HTML TABLE WITH CLICK-TO-COPY
# ─────────────────────────────────────────────────────────────
def render_setup_table(df: pd.DataFrame) -> str:
    def stage_color(stage):
        if "READY_TO_SPIKE" in stage:
            return "#d4edda"  # Green
        if "CONSOLIDATING" in stage:
            return "#fff3cd"  # Yellow
        if "BUILDING" in stage:
            return "#cce5ff"  # Blue
        if "SIGNAL_START" in stage:
            return "#f8d7da"  # Light red
        return "#ffffff"

    html = """
    <style>
    .setup-table {width:100%; border-collapse:collapse; font-size:12px; font-family:sans-serif;}
    .setup-table th {background:#1e293b; color:#ffffff; font-weight:600; padding:10px 8px; text-align:left; border-bottom:2px solid #e2e8f0; white-space:nowrap;}
    .setup-table td {padding:8px 8px; border-bottom:1px solid #e2e8f0; white-space:nowrap;}
    .copy-btn {
        cursor:pointer; font-weight:700; color:#0f172a;
        background:#e2e8f0; border:none; padding:4px 10px;
        border-radius:4px; font-size:11px; transition:background 0.2s;
    }
    .copy-btn:hover {background:#10b981; color:white;}
    .copy-btn.copied {background:#10b981; color:white;}
    .readiness-bar {
        width:100%; height:20px; background:#e2e8f0; border-radius:3px;
        overflow:hidden; font-size:10px; color:white; text-align:center;
        font-weight:bold; line-height:20px;
    }
    .readiness-fill {height:100%; background:linear-gradient(90deg, #ef4444, #f97316, #eab308, #10b981);}
    .toast {
        position:fixed; bottom:30px; left:50%; transform:translateX(-50%);
        background:#0f172a; color:white; padding:8px 20px;
        border-radius:8px; font-size:12px; z-index:9999;
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
    <table class="setup-table">
    <thead><tr>
        <th>Symbol</th><th>Day 1 Vol</th><th>Day 2 Vol</th><th>Day 3 Vol</th>
        <th>Vol D1:D2</th><th>Vol D2:D3</th><th>Price D1</th><th>Price D2</th>
        <th>Chg D1 %</th><th>Chg D2 %</th><th>Setup Stage</th><th>Readiness</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        bg = stage_color(row["Setup_Stage"])
        symbol = str(row["Symbol"])
        readiness = int(row["Readiness_%"])
        
        html += f"""
        <tr style="background:{bg}">
            <td><button class="copy-btn" onclick="copySymbol(this, '{symbol}')">{symbol}</button></td>
            <td>{int(row['Day_1_Vol']):,}</td>
            <td>{int(row['Day_2_Vol']):,}</td>
            <td>{int(row['Day_3_Vol']):,}</td>
            <td><strong>{row['Vol_D1_D2']}</strong></td>
            <td>{row['Vol_D2_D3']}</td>
            <td>{row['Price_D1']}</td>
            <td>{row['Price_D2']}</td>
            <td>{row['Chg_D1_%']}</td>
            <td>{row['Chg_D2_%']}</td>
            <td><strong>{row['Setup_Stage']}</strong></td>
            <td>
                <div class="readiness-bar">
                    <div class="readiness-fill" style="width:{readiness}%;"></div>
                </div>
                {readiness}%
            </td>
        </tr>"""

    html += "</tbody></table>"
    return html

# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────
st.markdown("""
    <style>
    .block-container {padding-top: 0.5rem !important;}
    </style>
""", unsafe_allow_html=True)

# ── Load historical once into session_state ──────────────────
if "setup_historical" not in st.session_state:
    with st.spinner("Loading 4-day historical data..."):
        hist = fetch_setup_data()
        if hist:
            st.session_state["setup_historical"] = hist
        else:
            st.error("❌ Insufficient data in websocket_stock_values")
            st.stop()

historical = st.session_state["setup_historical"]

# ── Compact top bar ──────────────────────────────────────────
col1, col2 = st.columns([5, 1])
with col1:
    st.markdown(f"📊 **Setup Tracker** &nbsp;|&nbsp; 📅 Analyzing Last 4 Trading Days &nbsp;|&nbsp; Latest: {historical['target_date']}", unsafe_allow_html=True)
with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        del st.session_state["setup_historical"]
        st.rerun()

st.divider()

# ── Main analysis ────────────────────────────────────────────
df_setups = analyze_setups(historical)

if df_setups.empty:
    st.warning("No stocks in active setup phase right now. Check again tomorrow!")
else:
    # ── Filter tabs ──────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 READY_TO_SPIKE",
        "🔴 CONSOLIDATING",
        "📈 BUILDING",
        "📍 ALL_STAGES"
    ])

    with tab1:
        df_ready = df_setups[df_setups["Setup_Stage"].str.contains("READY_TO_SPIKE")]
        if df_ready.empty:
            st.info("No stocks in READY_TO_SPIKE phase yet.")
        else:
            st.success(f"**{len(df_ready)} stocks** ready to spike!")
            st.components.v1.html(render_setup_table(df_ready), height=min(600, 60 + len(df_ready) * 40), scrolling=True)

    with tab2:
        df_cons = df_setups[df_setups["Setup_Stage"].str.contains("CONSOLIDATING")]
        if df_cons.empty:
            st.info("No stocks consolidating. Watch for next signal.")
        else:
            st.warning(f"**{len(df_cons)} stocks** in consolidation phase (watch for spike tomorrow!)")
            st.components.v1.html(render_setup_table(df_cons), height=min(600, 60 + len(df_cons) * 40), scrolling=True)

    with tab3:
        df_build = df_setups[df_setups["Setup_Stage"].str.contains("BUILDING")]
        if df_build.empty:
            st.info("No stocks building momentum.")
        else:
            st.info(f"**{len(df_build)} stocks** still building momentum (2-3 days away)")
            st.components.v1.html(render_setup_table(df_build), height=min(600, 60 + len(df_build) * 40), scrolling=True)

    with tab4:
        st.caption(f"All {len(df_setups)} stocks in setup phase")
        st.components.v1.html(render_setup_table(df_setups), height=min(800, 60 + len(df_setups) * 40), scrolling=True)

st.divider()

# ── Info section ────────────────────────────────────────────
with st.expander("📖 How to use Setup Tracker"):
    st.markdown("""
    ### **Setup Stages Explained:**
    
    1. **📍 SIGNAL_START** — Volume spike detected 3-4 days ago. Mark for watch.
    2. **📈 BUILDING** — Multiple days of elevated volume. Building momentum.
    3. **🔴 CONSOLIDATING** — Volume drops significantly, price stable. **PRE-SPIKE PHASE!**
    4. **🚀 READY_TO_SPIKE** — Consolidation + Bullish confirmation. **HIGHEST CHANCE!**
    
    ### **Best Strategy:**
    - Watch **CONSOLIDATING** stocks → spike likely NEXT DAY
    - Focus on **READY_TO_SPIKE** → highest probability entries
    - Use alongside MomentumScanner for real-time confirmation
    
    ### **Readiness %:**
    - 75%+ = High chance of spike within 24-48 hours
    - 50-75% = Monitor closely, check daily
    - <50% = Early stage, needs more time
    """)
