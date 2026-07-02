# ──────────────────────────────────────────────────────────────────────────────
# pages/12_SwingStrategy.py
# Swing Breakout Scanner — Zone Detection + 1H Breakout
# ──────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from datetime import datetime, timezone, timedelta

from swing_strategy.backend  import run_swing_scan, fetch_saved_signals, update_signal_status
from swing_strategy.renderer import render_swing_cards

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "Swing Strategy",
    page_icon  = "📊",
    layout     = "wide"
)

st.markdown("<style>header{visibility:hidden;}</style>", unsafe_allow_html=True)
st.markdown("<style>.block-container{padding-top:1rem !important;}</style>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

try:
    from styles import apply_styles, sidebar_brand
    apply_styles()
    sidebar_brand("SwingStrategy")
except:
    pass

IST = timezone(timedelta(hours=5, minutes=30))

# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns([4, 1, 1])

with col1:
    st.markdown("📊 **Swing Strategy** &nbsp;|&nbsp; Zone Breakout Scanner", unsafe_allow_html=True)

with col2:
    min_score = st.selectbox(
        "Min Zone Score",
        options  = [3, 4, 5, 6, 7, 8, 9],
        index    = 2,   # default = 5
        label_visibility = "collapsed"
    )

with col3:
    run_scan = st.button("🔍 Run Scanner", use_container_width=True)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📡 Live Scan", "📋 Saved Signals"])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — LIVE SCAN
# ──────────────────────────────────────────────────────────────────────────────

with tab1:
    if run_scan:
        with st.spinner("🔍 Scanning all stocks for consolidation zones..."):
            results = run_swing_scan(min_score=min_score)
            st.session_state["swing_results"]   = results
            st.session_state["swing_scan_time"] = datetime.now(IST).strftime("%H:%M:%S")
            st.session_state["swing_min_score"] = min_score

    if "swing_results" in st.session_state:
        results   = st.session_state["swing_results"]
        scan_time = st.session_state.get("swing_scan_time", "—")
        used_score = st.session_state.get("swing_min_score", min_score)

        triggered = [r for r in results if r["status"] == "TRIGGERED"]
        watching  = [r for r in results if r["status"] == "WATCHING"]

        st.caption(
            f"Last scan: {scan_time} | Min Score used: {used_score} | "
            f"Total: {len(results)} | 🟢 Triggered: {len(triggered)} | 🔵 Watching: {len(watching)}"
        )

        if triggered:
            st.markdown("### 🚀 Breakout Triggered")
            st.components.v1.html(
                render_swing_cards(triggered),
                height    = min(800, 200 + len(triggered) * 200),
                scrolling = True
            )

        if watching:
            st.markdown("### 👀 Watching — Zone Ready, Awaiting Breakout")
            st.components.v1.html(
                render_swing_cards(watching),
                height    = min(1200, 200 + len(watching) * 200),
                scrolling = True
            )

        if not results:
            st.info(f"No stocks matched criteria with Min Zone Score = {used_score}. Try lowering the score.")

    else:
        st.info("👆 'Run Scanner' button dabao — sab stocks scan hoga consolidation zones ke liye.")
        st.markdown("""
        **How it works:**
        - ✅ Last 5 trading days ka consolidation detect karta hai
        - ✅ Zone score 0-10 calculate karta hai
        - ✅ Entry, Stoploss, Target auto-calculate
        - ✅ Signals Supabase mein save hote hain
        - 🔜 1H breakout detection — coming soon
        """)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — SAVED SIGNALS
# ──────────────────────────────────────────────────────────────────────────────

with tab2:
    col_a, col_b = st.columns([3, 1])

    with col_a:
        days_back = st.selectbox(
            "Show signals from last:",
            options     = [1, 3, 7, 14],
            index       = 2,
            format_func = lambda x: f"{x} days"
        )

    with col_b:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    saved = fetch_saved_signals(days_back=days_back)

    if saved:
        status_filter = st.radio(
            "Filter by status:",
            options    = ["All", "TRIGGERED", "WATCHING", "EXITED"],
            horizontal = True
        )

        if status_filter != "All":
            saved = [s for s in saved if s.get("status") == status_filter]

        st.caption(f"Showing {len(saved)} signals")

        st.components.v1.html(
            render_swing_cards(saved),
            height    = min(1200, 200 + len(saved) * 200),
            scrolling = True
        )
    else:
        st.info("No saved signals found. Run the scanner first.")
