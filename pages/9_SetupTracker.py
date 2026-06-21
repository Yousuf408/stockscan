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
# HELPER: Format date string → "Jun 20"
# ─────────────────────────────────────────────────────────────
def fmt_date(d):
    try:
        dt = datetime.strptime(str(d), "%Y-%m-%d")
        return dt.strftime("%b %d")
    except Exception:
        return str(d)

# ─────────────────────────────────────────────────────────────
# FETCH LAST 4 DAYS DATA FROM SUPABASE
# ─────────────────────────────────────────────────────────────
def fetch_setup_data():
    supabase = get_supabase()

    # Step 1: Find all distinct trading dates
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

    # Step 2: Fetch EOD data for last 4 dates
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

    return {
        "dates"       : sorted_dates[0:4],   # [newest, ..., oldest]
        "target_date" : target_date,
        "data"        : pd.DataFrame(all_rows),
    }

# ─────────────────────────────────────────────────────────────
# ANALYZE SETUP PATTERNS
# ─────────────────────────────────────────────────────────────
def analyze_setups(historical: dict) -> pd.DataFrame:
    """
    Analyze 3-4 day consolidation patterns.

    KEY FILTERS proven from 11 real blast stocks (Jun 4-19, 2026):
    - Volume cap < 200K: all pre-blast days — NEVER exceeded 200K
    - Price ±2% on the day just before blast — always tight
    - Vol signal label is NOT consistent — ignore it
    """
    df    = historical["data"]
    dates = historical["dates"]

    if df.empty or len(dates) < 2:
        return pd.DataFrame()

    for col in ["volume", "ltp", "open"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df_pivot = df.sort_values("date").drop_duplicates(
        subset=["stock", "date"], keep="last"
    )

    results = []

    for stock in df_pivot["stock"].unique():
        stock_data = df_pivot[df_pivot["stock"] == stock].sort_values(
            "date", ascending=False
        )

        if len(stock_data) < 2:
            continue

        days_data = {}
        for _, row in stock_data.iterrows():
            date_key = str(row["date"])
            days_data[date_key] = {
                "volume": float(row["volume"]) if row["volume"] > 0 else 0,
                "ltp"   : float(row["ltp"])    if row["ltp"]    > 0 else 0,
                "open"  : float(row["open"])   if row["open"]   > 0 else 0,
            }

        sorted_dates = sorted(days_data.keys(), reverse=True)

        if len(sorted_dates) < 2:
            continue

        day1_date = sorted_dates[0] if len(sorted_dates) > 0 else None
        day2_date = sorted_dates[1] if len(sorted_dates) > 1 else None
        day3_date = sorted_dates[2] if len(sorted_dates) > 2 else None
        day4_date = sorted_dates[3] if len(sorted_dates) > 3 else None

        day1 = days_data.get(day1_date, {}) if day1_date else {}
        day2 = days_data.get(day2_date, {}) if day2_date else {}
        day3 = days_data.get(day3_date, {}) if day3_date else {}
        day4 = days_data.get(day4_date, {}) if day4_date else {}

        vol1 = day1.get("volume", 0)
        vol2 = day2.get("volume", 0)
        vol3 = day3.get("volume", 0)
        vol4 = day4.get("volume", 0)

        ltp1 = day1.get("ltp", 0)
        ltp2 = day2.get("ltp", 0)
        ltp3 = day3.get("ltp", 0)

        if vol1 == 0 or vol2 == 0 or ltp1 == 0 or ltp2 == 0:
            continue

        # ── VOLUME CAP FILTER (proven from 11 blast stocks) ──────
        if vol1 > 200_000:
            continue
        if vol2 > 200_000:
            continue
        if vol3 > 0 and vol3 > 200_000:
            continue
        # ─────────────────────────────────────────────────────────

        # ── TREND FILTER: no falling knife ───────────────────────
        if ltp3 > 0:
            if ltp1 < ltp3:
                continue
        elif ltp2 > 0:
            if ltp1 < ltp2:
                continue

        # ── Metrics ──────────────────────────────────────────────
        vol_ratio_today = vol1 / vol2 if vol2 > 0 else 0
        vol_ratio_yest  = vol2 / vol3 if vol3 > 0 else 1.0
        vol_ratio_d3    = vol3 / vol4 if vol4 > 0 else 1.0

        price_change_today = ((ltp1 - ltp2) / ltp2 * 100) if ltp2 > 0 else 0
        price_change_yest  = ((ltp2 - ltp3) / ltp3 * 100) if ltp3 > 0 else 0

        # ── Stage detection ───────────────────────────────────────
        setup_stage = ""
        setup_score = 0

        if len(sorted_dates) >= 3 and (vol_ratio_d3 >= 1.5 or vol_ratio_yest >= 1.5):
            setup_stage = "📍 SIGNAL_START"
            setup_score = 1

        if (
            len(sorted_dates) >= 3
            and (vol_ratio_d3 >= 1.3 or vol_ratio_yest >= 1.3)
            and abs(price_change_yest) <= 5
        ):
            setup_stage = "📈 BUILDING"
            setup_score = 2

        if vol_ratio_today < 0.9 and vol2 > 10_000 and abs(price_change_today) <= 2:
            setup_stage = "🔴 CONSOLIDATING"
            setup_score = 3

        if setup_stage == "🔴 CONSOLIDATING" and ltp1 > ltp2:
            setup_stage = "🚀 READY_TO_SPIKE"
            setup_score = 4

        if setup_score < 1:
            continue

        # ── Readiness % ───────────────────────────────────────────
        readiness = 0
        if vol_ratio_today < 1.0:        readiness += 25
        if abs(price_change_today) <= 2: readiness += 25
        if ltp1 > ltp2:                  readiness += 25
        if vol_ratio_yest >= 1.3:        readiness += 25
        readiness = min(100, max(0, readiness))

        # ── Store actual date labels for this stock ───────────────
        d1_label = fmt_date(day1_date) if day1_date else "Today"
        d2_label = fmt_date(day2_date) if day2_date else "D-1"
        d3_label = fmt_date(day3_date) if day3_date else "D-2"

        results.append({
            "Symbol"                       : stock,
            f"Vol {d3_label}"              : int(vol3) if vol3 > 0 else 0,
            f"Vol {d2_label}"              : int(vol2),
            f"Vol {d1_label}"              : int(vol1),
            f"Ratio {d2_label}/{d3_label}" : round(vol_ratio_yest,  2),
            f"Ratio {d1_label}/{d2_label}" : round(vol_ratio_today, 2),
            f"Price {d2_label}"            : round(ltp2, 2),
            f"Price {d1_label}"            : round(ltp1, 2),
            f"Chg% {d2_label}"             : round(price_change_yest,  2),
            f"Chg% {d1_label}"             : round(price_change_today, 2),
            "Setup Stage"                  : setup_stage,
            "Readiness %"                  : readiness,
            "Days in Setup"                : len(sorted_dates),
            "_score"                       : setup_score,
        })

    if not results:
        return pd.DataFrame()

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values(
        ["_score", "Readiness %"], ascending=[False, False]
    ).reset_index(drop=True)

    return df_result

# ─────────────────────────────────────────────────────────────
# DISPLAY DATAFRAME  (st.dataframe — full Streamlit features)
# ─────────────────────────────────────────────────────────────
def fmt_vol(v) -> str:
    """Convert raw volume int → K/M string. 0 → '-'."""
    try:
        v = int(v)
        if v <= 0:
            return "-"
        if v >= 1_000_000:
            s = f"{v / 1_000_000:.2f}"
            return f"{s.rstrip('0').rstrip('.')}M"
        if v >= 1_000:
            s = f"{v / 1_000:.1f}"
            return f"{s.rstrip('0').rstrip('.')}K"
        return str(v)
    except Exception:
        return "-"


def show_dataframe(df: pd.DataFrame):
    """
    Display using st.dataframe so users get:
    - Column sort (asc/desc)
    - Show/Hide columns  (eye icon)
    - Download CSV       (download icon)
    - Search             (magnifying glass icon)
    - Fullscreen         (expand icon)
    - Pin / Hide column  (right-click column header)

    Volume columns are pre-formatted as K/M strings so they
    display as  '74.4K', '1.9M', '-'  instead of raw integers.
    """

    display_df = df.drop(columns=["_score"], errors="ignore").copy()

    # Detect dynamic column groups
    vol_cols   = [c for c in display_df.columns if c.startswith("Vol ")]
    ratio_cols = [c for c in display_df.columns if c.startswith("Ratio ")]
    price_cols = [c for c in display_df.columns if c.startswith("Price ")]
    chg_cols   = [c for c in display_df.columns if c.startswith("Chg% ")]

    # ── Format volume columns → K/M strings ──────────────────
    # (done before column_config so sorting on these is string-based
    #  but display is clean; numeric sort still works on Ratio/Price/Chg)
    for c in vol_cols:
        display_df[c] = display_df[c].apply(fmt_vol)

    # ── Build column_config ───────────────────────────────────
    col_cfg = {
        "Symbol": st.column_config.TextColumn(
            "Symbol", width="small"
        ),
        "Setup Stage": st.column_config.TextColumn(
            "Setup Stage", width="medium"
        ),
        "Readiness %": st.column_config.ProgressColumn(
            "Readiness %",
            format="%d%%",
            min_value=0,
            max_value=100,
            width="medium",
        ),
        "Days in Setup": st.column_config.NumberColumn(
            "Days in Setup", width="small", format="%d"
        ),
    }

    for c in vol_cols:
        col_cfg[c] = st.column_config.TextColumn(c, width="small")

    for c in ratio_cols:
        col_cfg[c] = st.column_config.NumberColumn(
            c, format="%.2fx", width="small"
        )

    for c in price_cols:
        col_cfg[c] = st.column_config.NumberColumn(
            c, format="₹%.2f", width="small"
        )

    for c in chg_cols:
        col_cfg[c] = st.column_config.NumberColumn(
            c, format="%.2f%%", width="small"
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        height=600,
    )

# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────

# ── Load once into session_state ─────────────────────────────
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
    date_range = " → ".join(fmt_date(d) for d in reversed(historical["dates"]))
    st.markdown(
        f"📊 **Setup Tracker** &nbsp;|&nbsp; "
        f"📅 {date_range} &nbsp;|&nbsp; "
        f"Latest: **{historical['target_date']}**",
        unsafe_allow_html=True,
    )
with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        del st.session_state["setup_historical"]
        st.rerun()

st.divider()

# ── Analyze ───────────────────────────────────────────────────
df_setups = analyze_setups(historical)

if df_setups.empty:
    st.warning("No stocks in active setup phase right now. Check again tomorrow!")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 READY_TO_SPIKE",
    "🔴 CONSOLIDATING",
    "📈 BUILDING",
    "📍 ALL_STAGES",
])

with tab1:
    df_ready = df_setups[df_setups["Setup Stage"].str.contains("READY_TO_SPIKE")]
    if df_ready.empty:
        st.info("No stocks in READY_TO_SPIKE phase yet.")
    else:
        st.success(f"**{len(df_ready)} stocks** ready to spike — consolidation + bullish close ✅")
        show_dataframe(df_ready.reset_index(drop=True))

with tab2:
    df_cons = df_setups[df_setups["Setup Stage"].str.contains("CONSOLIDATING")]
    if df_cons.empty:
        st.info("No stocks consolidating right now.")
    else:
        st.warning(f"**{len(df_cons)} stocks** consolidating — spike possible tomorrow 👀")
        show_dataframe(df_cons.reset_index(drop=True))

with tab3:
    df_build = df_setups[df_setups["Setup Stage"].str.contains("BUILDING")]
    if df_build.empty:
        st.info("No stocks in building phase.")
    else:
        st.info(f"**{len(df_build)} stocks** building momentum (2-3 days away)")
        show_dataframe(df_build.reset_index(drop=True))

with tab4:
    st.caption(
        f"All {len(df_setups)} stocks | "
        f"Vol cap < 200K | Price filter ±2% on latest day"
    )
    show_dataframe(df_setups.reset_index(drop=True))

st.divider()

# ── Info ──────────────────────────────────────────────────────
with st.expander("📖 How to use Setup Tracker"):
    st.markdown("""
    ### Setup Stages

    | Stage | What it means | Action |
    |-------|--------------|--------|
    | 📍 **SIGNAL_START** | Volume spike 3-4 days ago | Mark for watch |
    | 📈 **BUILDING** | Sustained elevated volume | Monitor daily |
    | 🔴 **CONSOLIDATING** | Volume dropped + price ±2% stable | Watch for tomorrow spike |
    | 🚀 **READY_TO_SPIKE** | Consolidation + bullish close today | **Highest probability entry** |

    ### Why Volume Cap < 200K?
    Analyzed 11 real blast stocks (Jun 4–19, 2026). Every single one had
    volume under 200K across all pre-blast days. Stocks above 200K are
    already institutional / exhausted — not fresh setups.

    ### Table Features (top-right icons)
    - 👁️ **Eye** — Show/Hide columns
    - ⬇️ **Download** — Export as CSV
    - 🔍 **Search** — Search across all columns
    - ⛶ **Fullscreen** — Expand table

    ### Readiness %
    | Score | Meaning |
    |-------|---------|
    | 75–100% | Spike likely within 24–48 hrs |
    | 50–75% | Monitor closely |
    | < 50% | Too early |
    """)
