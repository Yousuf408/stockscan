# ──────────────────────────────────────────────────────────────────────────────
# debug_swing.py  — run this directly to check what's happening
# Place in ROOT folder and run: streamlit run debug_swing.py
# ──────────────────────────────────────────────────────────────────────────────

import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from swing_strategy.backend import fetch_all_stocks_bulk, detect_consolidation, calculate_zone_score, get_supabase
from config import STOCKS_WATCHLIST

st.set_page_config(page_title="Swing Debug", layout="wide")
st.title("🔍 Swing Scanner — Debug Mode")

if st.button("Run Debug"):

    # ── Step 1: Check Supabase data ──────────────────────────
    st.subheader("Step 1 — Supabase Bulk Fetch")
    df_all = fetch_all_stocks_bulk()

    if df_all.empty:
        st.error("❌ No data from Supabase — websocket_stock_values empty?")
        st.stop()

    st.success(f"✅ Fetched {len(df_all)} rows | {df_all['stock'].nunique()} stocks | Dates: {sorted(df_all['date'].dt.strftime('%Y-%m-%d').unique())}")
    st.dataframe(df_all.head(20))

    # ── Step 2: Check per stock ───────────────────────────────
    st.subheader("Step 2 — Per Stock Analysis (first 20 stocks)")

    stock_names = {name for name, token, kind in STOCKS_WATCHLIST if kind != "index"}
    rows = []

    for stock, stock_df in df_all.groupby("stock"):
        if stock not in stock_names:
            continue

        stock_df = stock_df.sort_values("date").reset_index(drop=True)
        num_days = len(stock_df)

        # Day range check
        stock_df["day_range_pct"] = ((stock_df["high"] - stock_df["low"]) / stock_df["low"]) * 100
        qualifying_days = len(stock_df[stock_df["day_range_pct"] <= 3.0])

        consol  = detect_consolidation(stock_df)
        score   = calculate_zone_score(stock_df, consol) if consol else 0

        rows.append({
            "Stock"          : stock,
            "Days in DB"     : num_days,
            "Qualifying Days": qualifying_days,
            "Consolidated"   : "✅" if consol else "❌",
            "Zone Width %"   : consol["zone_width_pct"] if consol else "—",
            "Zone Score"     : score if consol else "—",
            "Resistance"     : consol["resistance"] if consol else "—",
            "Support"        : consol["support"] if consol else "—",
            "Fail Reason"    : (
                "Not enough days in DB" if num_days < 5
                else "Range > 3% on some days" if qualifying_days < 5
                else "Zone width out of range" if (consol is None and qualifying_days >= 5)
                else "Score too low" if (consol and score < 5)
                else "✅ Passes"
            )
        })

    df_debug = pd.DataFrame(rows)

    consolidated = df_debug[df_debug["Consolidated"] == "✅"]
    st.success(f"Consolidated stocks: {len(consolidated)} / {len(df_debug)}")

    st.markdown("**All stocks breakdown:**")
    st.dataframe(df_debug, use_container_width=True, hide_index=True)

    # ── Step 3: Show consolidated ones with score ─────────────
    if not consolidated.empty:
        st.subheader("Step 3 — Consolidated Stocks (any score)")
        st.dataframe(consolidated.sort_values("Zone Score", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("No stocks passed consolidation — check fail reasons above")
