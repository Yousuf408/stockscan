"""
9_SetupTracker.py
Setup Pattern Tracker — Historical 3-4 day volume consolidation analysis
Identifies stocks in pre-spike consolidation phase

KEY INSIGHT (from real data analysis of 11 blast stocks):
- All blast stocks had volume < 200K across ALL pre-blast days
- Day before blast: price always within ±2%
- Vol signal is NOT consistent — volume cap IS the real filter
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
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
    .block-container {padding-top: 0.5rem !important;}
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

IST = timezone(timedelta(hours=5, minutes=30))

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
        return dt.strftime("%b %d")
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

    # ── Step 1: Find last 4 distinct trading dates ──────────────
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
    target_date  = sorted_dates[0]
    last_4_dates = sorted_dates[0:4]

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

    KEY FILTER (from real data analysis of 11 blast stocks Jun 4–19):
    - Volume cap < 200K: ALL blast stocks had vol < 200K across every
      pre-blast day. Stocks with higher vol (TITAGARH 922K) are
      exhaustion/institutional — not fresh setups.
    - Price ±2% on the day just before blast: always tight.
    - Vol signal is NOT consistent — Weak/Build/Explosive all appeared.
      Volume cap is the real filter, not the signal label.
    """
    df = historical["data"]
    dates = historical["dates"]

    if df.empty or len(dates) < 2:
        return pd.DataFrame()

    # Convert columns to numeric
    for col in ["volume", "ltp", "open"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Get latest price per stock per date (remove duplicates)
    df_pivot = df.sort_values("date").drop_duplicates(
        subset=["stock", "date"], keep="last"
    )

    results = []

    for stock in df_pivot["stock"].unique():
        stock_data = df_pivot[df_pivot["stock"] == stock].sort_values(
            "date", ascending=False
        )

        # Must have at least 2 days
        if len(stock_data) < 2:
            continue

        # ── Build days_data dict safely ──────────────────────────
        days_data = {}
        for _, row in stock_data.iterrows():
            date_key = str(row["date"])
            days_data[date_key] = {
                "volume": float(row["volume"]) if row["volume"] > 0 else 0,
                "ltp"   : float(row["ltp"])    if row["ltp"]    > 0 else 0,
                "open"  : float(row["open"])   if row["open"]   > 0 else 0,
            }

        # Sorted dates most recent first, max 4
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

        # Extract values ─────────────────────────────────────────
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

        # ── VOLUME CAP FILTER ────────────────────────────────────
        # Proven from 11 blast stocks: ALL pre-blast days had vol < 200K
        # Higher vol stocks are already institutional / exhausted
        if vol1 > 200_000:
            continue
        if vol2 > 200_000:
            continue
        if vol3 > 0 and vol3 > 200_000:
            continue
        # ─────────────────────────────────────────────────────────

        # ── TREND FILTER: Eliminate Downtrends ──────────────────
        # Today's price must be >= price 2 days ago (no falling knife)
        if ltp3 > 0:
            if ltp1 < ltp3:
                continue
        elif ltp2 > 0:
            if ltp1 < ltp2:
                continue

        # ── Calculate metrics ────────────────────────────────────
        vol_ratio_today = vol1 / vol2 if vol2 > 0 else 0
        vol_ratio_yest  = vol2 / vol3 if vol3 > 0 else 1.0
        vol_ratio_d3    = vol3 / vol4 if vol4 > 0 else 1.0

        price_change_today = ((ltp1 - ltp2) / ltp2 * 100) if ltp2 > 0 else 0
        price_change_yest  = ((ltp2 - ltp3) / ltp3 * 100) if ltp3 > 0 else 0

        # ── SETUP STAGE DETECTION ────────────────────────────────
        setup_stage = ""
        setup_score = 0

        # Stage 1: Signal Start — early volume spike seen
        if len(sorted_dates) >= 3 and (vol_ratio_d3 >= 1.5 or vol_ratio_yest >= 1.5):
            setup_stage = "📍 SIGNAL_START"
            setup_score = 1

        # Stage 2: Building — sustained elevated volume
        if (
            len(sorted_dates) >= 3
            and (vol_ratio_d3 >= 1.3 or vol_ratio_yest >= 1.3)
            and abs(price_change_yest) <= 5
        ):
            setup_stage = "📈 BUILDING"
            setup_score = 2

        # Stage 3: Consolidating — volume drops + price stable (PRE-SPIKE!)
        # Price ±2% confirmed from all 11 blast stocks on their final pre-blast day
        if vol_ratio_today < 0.9 and vol2 > 10_000 and abs(price_change_today) <= 2:
            setup_stage = "🔴 CONSOLIDATING"
            setup_score = 3

        # Stage 4: Ready to Spike — consolidation + bullish close
        if setup_stage == "🔴 CONSOLIDATING" and ltp1 > ltp2:
            setup_stage = "🚀 READY_TO_SPIKE"
            setup_score = 4

        if setup_score < 1:
            continue

        # ── Readiness score ──────────────────────────────────────
        readiness = 0
        if vol_ratio_today < 1.0:   readiness += 25   # Volume dropped
        if abs(price_change_today) <= 2: readiness += 25   # Price stable
        if ltp1 > ltp2:             readiness += 25   # Bullish close
        if vol_ratio_yest >= 1.3:   readiness += 25   # Previous buildup

        readiness = min(100, max(0, readiness))

        results.append({
            "Symbol"       : stock,
            "Day_1_Vol"    : int(vol1),
            "Day_2_Vol"    : int(vol2),
            "Day_3_Vol"    : int(vol3),
            "Day_4_Vol"    : int(vol4),
            "Vol_D1_D2"    : f"{vol_ratio_today:.2f}x",
            "Vol_D2_D3"    : f"{vol_ratio_yest:.2f}x",
            "Price_D1"     : f"₹{ltp1:.2f}",
            "Price_D2"     : f"₹{ltp2:.2f}",
            "Chg_D1_%"     : f"{price_change_today:+.2f}%",
            "Chg_D2_%"     : f"{price_change_yest:+.2f}%",
            "Setup_Stage"  : setup_stage,
            "Readiness_%"  : readiness,
            "Days_in_Setup": len(sorted_dates),
            "setup_score"  : setup_score,
        })

    if not results:
        return pd.DataFrame()

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values("Readiness_%", ascending=False)
    df_result = df_result.reset_index(drop=True)

    return df_result

# ─────────────────────────────────────────────────────────────
# HTML TABLE WITH CLICK-TO-COPY + ACTUAL DATES
# ─────────────────────────────────────────────────────────────
def render_setup_table(df: pd.DataFrame, dates: list) -> str:
    """Render HTML table with actual dates as column headers."""

    # dates[0] = newest, dates[3] = oldest
    d1 = fmt_date(dates[0]) if len(dates) > 0 else "Today"
    d2 = fmt_date(dates[1]) if len(dates) > 1 else "D-1"
    d3 = fmt_date(dates[2]) if len(dates) > 2 else "D-2"

    def stage_color(stage):
        if "READY_TO_SPIKE"  in stage: return "#d4edda"
        if "CONSOLIDATING"   in stage: return "#fff3cd"
        if "BUILDING"        in stage: return "#cce5ff"
        if "SIGNAL_START"    in stage: return "#f8d7da"
        return "#ffffff"

    html = f"""
    <style>
    .setup-table {{width:100%; border-collapse:collapse; font-size:12px; font-family:sans-serif;}}
    .setup-table th {{
        background:#1e293b; color:#ffffff; font-weight:600;
        padding:10px 8px; text-align:left;
        border-bottom:2px solid #e2e8f0; white-space:nowrap;
    }}
    .setup-table td {{
        padding:8px 8px; border-bottom:1px solid #e2e8f0; white-space:nowrap;
    }}
    .copy-btn {{
        cursor:pointer; font-weight:700; color:#0f172a;
        background:#e2e8f0; border:none; padding:4px 10px;
        border-radius:4px; font-size:11px; transition:background 0.2s;
    }}
    .copy-btn:hover  {{background:#10b981; color:white;}}
    .copy-btn.copied {{background:#10b981; color:white;}}
    .readiness-wrap {{display:flex; align-items:center; gap:6px;}}
    .readiness-bar {{
        width:70px; height:14px; background:#e2e8f0;
        border-radius:3px; overflow:hidden;
    }}
    .readiness-fill {{
        height:100%;
        background:linear-gradient(90deg,#ef4444,#f97316,#eab308,#10b981);
    }}
    .readiness-label {{font-size:11px; font-weight:600; color:#0f172a;}}
    .toast {{
        position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
        background:#0f172a; color:white; padding:8px 20px;
        border-radius:8px; font-size:12px; z-index:9999;
        opacity:0; transition:opacity 0.3s; pointer-events:none;
    }}
    .toast.show {{opacity:1;}}
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
        <th>Chg {d2}%</th>
        <th>Chg {d1}%</th>
        <th>Setup Stage</th>
        <th>Readiness</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        bg     = stage_color(row["Setup_Stage"])
        symbol = str(row["Symbol"])
        pct    = int(row["Readiness_%"])

        vol_d3 = fmt_volume_val(row["Day_3_Vol"])
        vol_d2 = fmt_volume_val(row["Day_2_Vol"])
        vol_d1 = fmt_volume_val(row["Day_1_Vol"])

        html += f"""
        <tr style="background:{bg}">
            <td><button class="copy-btn" onclick="copySymbol(this,'{symbol}')">{symbol}</button></td>
            <td>{vol_d3}</td>
            <td>{vol_d2}</td>
            <td><strong>{vol_d1}</strong></td>
            <td>{row['Vol_D2_D3']}</td>
            <td><strong>{row['Vol_D1_D2']}</strong></td>
            <td>{row['Price_D2']}</td>
            <td>{row['Price_D1']}</td>
            <td>{row['Chg_D2_%']}</td>
            <td>{row['Chg_D1_%']}</td>
            <td><strong>{row['Setup_Stage']}</strong></td>
            <td>
                <div class="readiness-wrap">
                    <div class="readiness-bar">
                        <div class="readiness-fill" style="width:{pct}%;"></div>
                    </div>
                    <span class="readiness-label">{pct}%</span>
                </div>
            </td>
        </tr>"""

    html += "</tbody></table>"
    return html

# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────

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

# ── Top bar ──────────────────────────────────────────────────
col1, col2 = st.columns([5, 1])
with col1:
    st.markdown(
        f"📊 **Setup Tracker** &nbsp;|&nbsp; "
        f"📅 Last 4 Trading Days &nbsp;|&nbsp; "
        f"Latest: **{historical['target_date']}** &nbsp;|&nbsp; "
        f"Dates: {' → '.join(fmt_date(d) for d in reversed(historical['dates']))}",
        unsafe_allow_html=True
    )
with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        del st.session_state["setup_historical"]
        st.rerun()

st.divider()

# ── Main analysis ─────────────────────────────────────────────
df_setups = analyze_setups(historical)

if df_setups.empty:
    st.warning("No stocks in active setup phase right now. Check again tomorrow!")
else:
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 READY_TO_SPIKE",
        "🔴 CONSOLIDATING",
        "📈 BUILDING",
        "📍 ALL_STAGES",
    ])

    with tab1:
        df_ready = df_setups[df_setups["Setup_Stage"].str.contains("READY_TO_SPIKE")]
        if df_ready.empty:
            st.info("No stocks in READY_TO_SPIKE phase yet.")
        else:
            st.success(f"**{len(df_ready)} stocks** ready to spike! (Consolidation + Bullish close)")
            st.components.v1.html(
                render_setup_table(df_ready, historical["dates"]),
                height=min(700, 65 + len(df_ready) * 42),
                scrolling=True
            )

    with tab2:
        df_cons = df_setups[df_setups["Setup_Stage"].str.contains("CONSOLIDATING")]
        if df_cons.empty:
            st.info("No stocks consolidating right now.")
        else:
            st.warning(f"**{len(df_cons)} stocks** consolidating — spike possible tomorrow!")
            st.components.v1.html(
                render_setup_table(df_cons, historical["dates"]),
                height=min(700, 65 + len(df_cons) * 42),
                scrolling=True
            )

    with tab3:
        df_build = df_setups[df_setups["Setup_Stage"].str.contains("BUILDING")]
        if df_build.empty:
            st.info("No stocks in building phase.")
        else:
            st.info(f"**{len(df_build)} stocks** building momentum (2-3 days away)")
            st.components.v1.html(
                render_setup_table(df_build, historical["dates"]),
                height=min(700, 65 + len(df_build) * 42),
                scrolling=True
            )

    with tab4:
        st.caption(
            f"All {len(df_setups)} stocks in setup phase "
            f"| Vol cap: <200K | Price filter: ±2% on latest day"
        )
        st.components.v1.html(
            render_setup_table(df_setups, historical["dates"]),
            height=min(900, 65 + len(df_setups) * 42),
            scrolling=True
        )

st.divider()

# ── Info section ─────────────────────────────────────────────
with st.expander("📖 How to use Setup Tracker"):
    st.markdown("""
    ### Setup Stages

    | Stage | What it means | Action |
    |-------|--------------|--------|
    | 📍 **SIGNAL_START** | Volume spike seen 3-4 days ago | Mark for watch |
    | 📈 **BUILDING** | Sustained elevated volume, 2-3 days away | Monitor daily |
    | 🔴 **CONSOLIDATING** | Volume dropped + price ±2% stable → **PRE-SPIKE!** | Watch for tomorrow spike |
    | 🚀 **READY_TO_SPIKE** | Consolidation + bullish close today | **Highest probability entry** |

    ### Why Volume Cap < 200K?
    Analyzed 11 real blast stocks (Jun 4–19, 2026). Every single one had
    volume under 200K across all pre-blast days — even AIIL (182K) and
    RPTECH (160K). Stocks like TITAGARH (922K pre-blast) were already
    exhausted — not fresh setups. This single filter cuts noise by ~60%.

    ### Best Strategy
    1. Morning 9:15 — open **MomentumScanner** for live signals
    2. Cross-check **CONSOLIDATING** stocks from yesterday → spike likely today
    3. **READY_TO_SPIKE** at 75%+ readiness = highest confidence entry

    ### Readiness %
    | Score | Meaning |
    |-------|---------|
    | 75–100% | Spike likely within 24–48 hrs |
    | 50–75% | Monitor closely |
    | < 50% | Too early |
    """)
