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
# HELPER: Format date string for display
# ─────────────────────────────────────────────────────────────
def fmt_date(d):
    """Convert '2026-06-20' → 'Jun 20' for column headers."""
    try:
        dt = datetime.strptime(str(d), "%Y-%m-%d")
        return dt.strftime("%b %d")  # e.g., "Jun 20"
    except Exception:
        return str(d)

# ─────────────────────────────────────────────────────────────
# HELPER: Format volume to clean shorthand (K / M)
# ─────────────────────────────────────────────────────────────
def fmt_volume_val(val):
    """Convert raw volume number to shorthand string (e.g., 3.07M, 74.4K)."""
    try:
        val = float(val)
        if val >= 1_000_000:
            formatted = f"{val / 1_000_000:.2f}"
            if formatted.endswith(".00"):
                return f"{int(val / 1_000_000)}M"
            elif formatted.endswith("0"):
                return f"{val / 1_000_000:.1f}M"
            return f"{formatted}M"
        elif val >= 1_000:
            formatted = f"{val / 1_000:.1f}"
            if formatted.endswith(".0"):
                return f"{int(val / 1_000)}K"
            return f"{formatted}K"
        return str(int(val))
    except Exception:
        return str(val)

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

    # Get latest price per stock per date (remove duplicates)
    df_pivot = df.sort_values("date").drop_duplicates(subset=["stock", "date"], keep="last")

    results = []

    for stock in df_pivot["stock"].unique():
        stock_data = df_pivot[df_pivot["stock"] == stock].sort_values("date", ascending=False)
        
        # Must have at least 2 days
        if len(stock_data) < 2:
            continue

        # ── Build days_data dict safely ──────────────────────────
        days_data = {}
        for idx, row in stock_data.iterrows():
            date_key = str(row["date"])
            days_data[date_key] = {
                "volume": float(row["volume"]) if row["volume"] > 0 else 0,
                "ltp": float(row["ltp"]) if row["ltp"] > 0 else 0,
                "open": float(row["open"]) if row["open"] > 0 else 0,
            }

        # Get sorted dates (most recent first), take max 4
        sorted_dates = sorted(days_data.keys(), reverse=True)
        
        if len(sorted_dates) < 2:
            continue

        # Safely extract day data ─────────────────────────────────
        day1_date = sorted_dates[0] if len(sorted_dates) > 0 else None
        day2_date = sorted_dates[1] if len(sorted_dates) > 1 else None
        day3_date = sorted_dates[2] if len(sorted_dates) > 2 else None
        day4_date = sorted_dates[3] if len(sorted_dates) > 3 else None

        day1 = days_data.get(day1_date, {}) if day1_date else {}
        day2 = days_data.get(day2_date, {}) if day2_date else {}
        day3 = days_data.get(day3_date, {}) if day3_date else {}
        day4 = days_data.get(day4_date, {}) if day4_date else {}

        # Extract values with safety ─────────────────────────────
        vol1 = day1.get("volume", 0)
        vol2 = day2.get("volume", 0)
        vol3 = day3.get("volume", 0)
        vol4 = day4.get("volume", 0)

        ltp1 = day1.get("ltp", 0)
        ltp2 = day2.get("ltp", 0)
        ltp3 = day3.get("ltp", 0)

        # Skip if critical data missing
        if vol1 == 0 or vol2 == 0 or ltp1 == 0 or ltp2 == 0:
            continue

        # ── Calculate consolidation metrics ──────────────────────
        vol_ratio_today = vol1 / vol2 if vol2 > 0 else 0
        vol_ratio_yest = vol2 / vol3 if vol3 > 0 else 1.0
        vol_ratio_d3 = vol3 / vol4 if vol4 > 0 else 1.0

        price_change_today = ((ltp1 - ltp2) / ltp2 * 100) if ltp2 > 0 else 0
        price_change_yest = ((ltp2 - ltp3) / ltp3 * 100) if ltp3 > 0 else 0

        # ── SETUP STAGE DETECTION ────────────────────────────────
        setup_stage = ""
        setup_score = 0

        # Stage 1: Signal appearing (vol spike in early days)
        if len(sorted_dates) >= 3 and (vol_ratio_d3 >= 1.5 or vol_ratio_yest >= 1.5):
            setup_stage = "📍 SIGNAL_START"
            setup_score = 1

        # Stage 2: Building (multiple days with elevated volume)
        if len(sorted_dates) >= 3 and (vol_ratio_d3 >= 1.3 or vol_ratio_yest >= 1.3) and abs(price_change_yest) <= 5:
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
            "Day_1_Vol": int(vol1),
            "Day_2_Vol": int(vol2),
            "Day_3_Vol": int(vol3),
            "Day_4_Vol": int(vol4),
            "Vol_D1_D2": f"{vol_ratio_today:.2f}x",
            "Vol_D2_D3": f"{vol_ratio_yest:.2f}x",
            "Price_D1": f"₹{ltp1:.2f}",
            "Price_D2": f"₹{ltp2:.2f}",
            "Chg_D1_%": f"{price_change_today:+.2f}%",
            "Chg_D2_%": f"{price_change_yest:+.2f}%",
            "Setup_Stage": setup_stage,
            "Readiness_%": readiness,
            "Days_in_Setup": len(sorted_dates),
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
def render_setup_table(df: pd.DataFrame, dates: list) -> str:
    """Render HTML table with actual dates chronologically and shorthand volumes."""

    # ── Format dates for column headers (Oldest to Newest) ──────────
    d1 = fmt_date(dates[0]) if len(dates) > 0 else "Day 1" # Newest
    d2 = fmt_date(dates[1]) if len(dates) > 1 else "Day 2"
    d3 = fmt_date(dates[2]) if len(dates) > 2 else "Day 3" # Oldest

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

    html = f"""
    <style>
    .setup-table {{width:100%; border-collapse:collapse; font-size:12px; font-family:sans-serif;}}
    .setup-table th {{background:#1e293b; color:#ffffff; font-weight:600; padding:10px 8px; text-align:left; border-bottom:2px solid #e2e8f0; white-space:nowrap;}}
    .setup-table td {{padding:8px 8px; border-bottom:1px solid #e2e8f0; white-space:nowrap;}}
    .copy-btn {{
        cursor:pointer; font-weight:700; color:#0f172a;
        background:#e2e8f0; border:none; padding:4px 10px;
        border-radius:4px; font-size:11px; transition:background 0.2s;
    }}
    .copy-btn:hover {{background:#10b981; color:white;}}
    .copy-btn.copied {{background:#10b981; color:white;}}
    .readiness-bar {{
        width:100%; height:20px; background:#e2e8f0; border-radius:3px;
        overflow:hidden; font-size:10px; color:white; text-align:center;
        font-weight:bold; line-height:20px;
    }}
    .readiness-fill {{height:100%; background:linear-gradient(90deg, #ef4444, #f97316, #eab308, #10b981);}}
    .toast {{
        position:fixed; bottom:30px; left:50%; transform:translateX(-50%);
        background:#0f172a; color:white; padding:8px 20px;
        border-radius:8px; font-size:12px; z-index:9999;
        opacity:0; transition:opacity 0.3s; pointer-events:none;
    }}
    .toast.show {{opacity:1;}}
    .vol-badge {{
        background: #f1f5f9;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: bold;
        color: #334155;
    }}
    .ratio-badge {{
        background: #f1f5f9;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: bold;
        color: #0f172a;
    }}
    </style>
    <div id="toast" class="toast">✅ Copied!</div>
    <script>
    function copySymbol(btn, symbol) {{
        navigator.clipboard.writeText(symbol);
        btn.classList.add('copied');
        btn.innerText = '✓ ' + symbol;
        var toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(function() {{
            btn.classList.remove('copied');
            btn.innerText = symbol;
            toast.classList.remove('show');
        }}, 1500);
    }}
    </script>
    <table class="setup-table">
    <thead><tr>
        <th>Symbol</th>
        <th>{d3} Vol</th>
        <th>{d2} Vol</th>
        <th>{d1} Vol</th>
        <th>Vol {d2}:{d3}</th>
        <th>Vol {d1}:{d2}</th>
        <th>Price {d2}</th>
        <th>Price {d1}</th>
        <th>Chg {d2} %</th>
        <th>Chg {d1} %</th>
        <th>Setup Stage</th>
        <th>Readiness</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        bg = stage_color(row["Setup_Stage"])
        symbol = str(row["Symbol"])
        readiness = int(row["Readiness_%"])
        
        # Format the volumes to shorthand
        vol_d3_formatted = fmt_volume_val(row['Day_3_Vol'])
        vol_d2_formatted = fmt_volume_val(row['Day_2_Vol'])
        vol_d1_formatted = fmt_volume_val(row['Day_1_Vol'])

        html += f"""
        <tr style="background:{bg}">
            <td><button class="copy-btn" onclick="copySymbol(this, '{symbol}')">{symbol}</button></td>
            <td><span class="vol-badge">{vol_d3_formatted}</span></td>
            <td><span class="vol-badge">{vol_d2_formatted}</span></td>
            <td><span class="vol-badge">{vol_d1_formatted}</span></td>
            <td><span class="ratio-badge">{row['Vol_D2_D3']}</span></td>
            <td><span class="ratio-badge">{row['Vol_D1_D2']}</span></td>
            <td>{row['Price_D2']}</td>
            <td>{row['Price_D1']}</td>
            <td>{row['Chg_D2_%']}</td>
            <td>{row['Chg_D1_%']}</td>
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
            st.components.v1.html(render_setup_table(df_ready, historical["dates"]), height=min(600, 60 + len(df_ready) * 40), scrolling=True)

    with tab2:
        df_cons = df_setups[df_setups["Setup_Stage"].str.contains("CONSOLIDATING")]
        if df_cons.empty:
            st.info("No stocks consolidating. Watch for next signal.")
        else:
            st.warning(f"**{len(df_cons)} stocks** in consolidation phase (watch for spike tomorrow!)")
            st.components.v1.html(render_setup_table(df_cons, historical["dates"]), height=min(600, 60 + len(df_cons) * 40), scrolling=True)

    with tab3:
        df_build = df_setups[df_setups["Setup_Stage"].str.contains("BUILDING")]
        if df_build.empty:
            st.info("No stocks building momentum.")
        else:
            st.info(f"**{len(df_build)} stocks** still building momentum (2-3 days away)")
            st.components.v1.html(render_setup_table(df_build, historical["dates"]), height=min(600, 60 + len(df_build) * 40), scrolling=True)

    with tab4:
        st.caption(f"All {len(df_setups)} stocks in setup phase")
        st.components.v1.html(render_setup_table(df_setups, historical["dates"]), height=min(800, 60 + len(df_setups) * 40), scrolling=True)

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
