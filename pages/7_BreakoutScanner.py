"""
7_BreakoutScanner.py
UI only — imports all logic from breakout_4h/ module
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST

from breakout_4h.breakout_4h_logic import run_scan
from breakout_4h.breakout_4h_chart import render_chart

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Breakout Scanner",
    page_icon="⚡",
    layout="wide"
)

# ─────────────────────────────────────────────────────────────
# TOKEN MAPS
# ─────────────────────────────────────────────────────────────
NAME_TO_TOKEN = {
    name: token
    for name, token, kind in STOCKS_WATCHLIST
    if kind == "stock"
}
ALL_STOCKS = [name for name, _, kind in STOCKS_WATCHLIST if kind == "stock"]

# ─────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
footer { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }

div[data-testid="stButton"] > button {
    background: linear-gradient(to right, #10b981, #14b8a6) !important;
    color: white !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 10px 28px !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    width: 100%;
}
div[data-testid="stButton"] > button:hover { opacity: 0.88 !important; }

.metric-row { display: flex; gap: 12px; margin-bottom: 20px; }
.metric-tile {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 10px; padding: 14px 18px;
    flex: 1; text-align: center;
}
.metric-val { font-size: 26px; font-weight: 700; color: #059669; }
.metric-lbl { font-size: 12px; color: #64748b; margin-top: 2px; }

.chart-wrap {
    background: #ffffff; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 16px; margin-top: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.dot-live {
    display: inline-block; width: 8px; height: 8px;
    background: #10b981; border-radius: 50%;
    margin-right: 6px; animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #f8fafc; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# WEBSOCKET AUTO-CONNECT
# ─────────────────────────────────────────────────────────────
def ensure_websocket():
    if not angel_ws.is_connected():
        with st.spinner("Connecting to Angel One WebSocket..."):
            creds = angel_login()
            if creds:
                angel_ws.start_websocket(
                    creds["jwt_token"],
                    creds["api_key"],
                    creds["client_id"],
                    creds["feed_token"]
                )
                time.sleep(3)
            else:
                st.error("❌ Angel One login failed. Live prices unavailable.")


# ─────────────────────────────────────────────────────────────
# TABLE RENDER
# ─────────────────────────────────────────────────────────────
def render_table(results: list, ticks: dict):
    if not results:
        st.info("📭 No breakouts found — try scanning again.")
        return

    rows = []
    for r in results:
        symbol        = r["symbol"]
        token         = NAME_TO_TOKEN.get(symbol)
        live_data     = ticks.get(token, {}) if token else {}
        live_price    = live_data.get("ltp", r["price"])
        live_chg      = live_data.get("change_pct", 0)
        chg_str       = f"+{live_chg:.2f}%" if live_chg >= 0 else f"{live_chg:.2f}%"
        brk_pct       = r["breakout_pct"]
        body_pct      = r["body_pct"]
        rel_vol       = r["rel_vol"]
        pct_from_high = r["pct_from_high"]
        con_low       = r["con_low"]
        con_high      = r["con_high"]

        rows.append({
            "Ticker"      : symbol,
            "Live Price"  : f"₹{live_price:,.2f}  {chg_str}",
            "Breakout %"  : f"+{brk_pct:.2f}%",
            "Body %"      : f"{body_pct:.2f}%",
            "Rel. Volume" : f"{rel_vol:.1f}x",
            "% from High" : f"{pct_from_high:.2f}%",
            "Zone"        : f"₹{con_low:,.0f} – ₹{con_high:,.0f}",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=min(len(rows) * 45 + 38, 600),
    )


# ─────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────
def main():
    # ── WS Status ──
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks()
    ticks_count  = len(ticks)
    last_scanned = st.session_state.get("last_scanned", "")

    if ws_connected:
        ws_html = f'<span class="dot-live"></span><span style="color:#059669;font-size:12px;font-weight:500">Live · {ticks_count} ticks</span>'
    else:
        ws_html = '<span style="color:#dc2626;font-size:12px;">⚠️ WS disconnected</span>'

    ls_html = f'<span style="color:#94a3b8;font-size:12px;">Last scanned: {last_scanned}</span>' if last_scanned else ""

    # ── Header — single clean row ──
    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0 8px 0;border-bottom:1px solid #e2e8f0;margin-bottom:12px;">
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:700;color:#0f172a;">⚡ Breakout Scanner</span>
            <span style="font-size:12px;color:#94a3b8;">4H consolidation · India NSE</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">
            {ws_html}
            {ls_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Scan button ──
    col_btn, _ = st.columns([1, 5])
    with col_btn:
        scan_clicked = st.button("🔍 Scan Now", use_container_width=True)

    # ── Filters ──
    apply_clicked = False
    with st.expander("🔧 Scanner Filters", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)

        CONSOL_OPTS   = [5, 8, 10, 12, 15, 20]
        BREAKOUT_OPTS = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        BODY_OPTS     = [1, 2, 3, 4, 5, 7, 10]
        RELVOL_OPTS   = [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
        DVOL_OPTS     = [100_000, 200_000, 300_000, 500_000, 1_000_000, 2_000_000, 5_000_000]
        MKTCAP_OPTS   = [1_000_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000, 500_000_000, 1_000_000_000]
        NEARHIGH_OPTS = [5, 8, 10, 15, 20, 25]
        TREND_OPTS    = ["both", "sma20", "sma50", "disable"]

        with fc1:
            f_consol = st.selectbox(
                "Consolidation Range", CONSOL_OPTS,
                index=CONSOL_OPTS.index(st.session_state.get("f_consol", 12)),
                format_func=lambda x: f"≤ {x}%", key="f_consol"
            )
            f_breakout = st.selectbox(
                "Breakout Above Zone", BREAKOUT_OPTS,
                index=BREAKOUT_OPTS.index(st.session_state.get("f_breakout", 2.0)),
                format_func=lambda x: f"{x}%" if x > 0 else "0% (just above)",
                key="f_breakout"
            )
        with fc2:
            f_body = st.selectbox(
                "Min Body Size", BODY_OPTS,
                index=BODY_OPTS.index(st.session_state.get("f_body", 5)),
                format_func=lambda x: f"{x}%", key="f_body"
            )
            f_relvol = st.selectbox(
                "Relative Volume", RELVOL_OPTS,
                index=RELVOL_OPTS.index(st.session_state.get("f_relvol", 1.5)),
                format_func=lambda x: f"{x}x", key="f_relvol"
            )
        with fc3:
            f_dailyvol = st.selectbox(
                "Min Daily Volume", DVOL_OPTS,
                index=DVOL_OPTS.index(st.session_state.get("f_dailyvol", 500_000)),
                format_func=lambda x: f"{int(x/1000)}k" if x < 1_000_000 else f"{int(x/1_000_000)}M",
                key="f_dailyvol"
            )
            f_mktcap = st.selectbox(
                "Market Cap", MKTCAP_OPTS,
                index=MKTCAP_OPTS.index(st.session_state.get("f_mktcap", 50_000_000)),
                format_func=lambda x: f"${int(x/1_000_000)}M" if x < 1_000_000_000 else f"${int(x/1_000_000_000)}B",
                key="f_mktcap"
            )
        with fc4:
            f_nearhigh = st.selectbox(
                "Price Near High", NEARHIGH_OPTS,
                index=NEARHIGH_OPTS.index(st.session_state.get("f_nearhigh", 10)),
                format_func=lambda x: f"Within {x}%", key="f_nearhigh"
            )
            f_trend = st.selectbox(
                "Trend (SMA)", TREND_OPTS,
                index=TREND_OPTS.index(st.session_state.get("f_trend", "both")),
                format_func=lambda x: {
                    "both": "SMA20 & SMA50", "sma20": "Only SMA20",
                    "sma50": "Only SMA50", "disable": "Disabled"
                }[x],
                key="f_trend"
            )

        btn_col1, btn_col2 = st.columns([1, 1])
        with btn_col1:
            if st.button("↺ Reset to Defaults", key="reset_filters", use_container_width=True):
                for k in ["f_consol","f_breakout","f_body","f_relvol",
                          "f_dailyvol","f_mktcap","f_nearhigh","f_trend"]:
                    st.session_state.pop(k, None)
                st.rerun()
        with btn_col2:
            apply_clicked = st.button("✅ Apply & Scan", key="apply_filters", use_container_width=True)

    st.markdown("---")

    # ── Build scan_filters ──
    scan_filters = {
        "consol_pct"    : f_consol,
        "breakout_mult" : 1 + (float(f_breakout) / 100),
        "body_pct"      : float(f_body),
        "rel_vol"       : float(f_relvol),
        "daily_vol"     : int(f_dailyvol),
        "mktcap"        : int(f_mktcap),
        "near_high"     : int(f_nearhigh),
        "trend"         : f_trend,
    }

    # ── Scan trigger ──
    if scan_clicked or apply_clicked:
        ensure_websocket()
        progress_bar = st.progress(0, text="Starting scan...")
        status_text  = st.empty()

        def on_progress(done, total):
            progress_bar.progress(int(done / total * 100), text=f"Scanning... {done}/{total}")

        def on_status(symbol, done, total):
            status_text.caption(f"⚡ Checking {symbol} ({done}/{total})")

        results = run_scan(
            all_stocks  = ALL_STOCKS,
            progress_cb = on_progress,
            status_cb   = on_status,
            filters     = scan_filters,
        )
        progress_bar.empty()
        status_text.empty()

        st.session_state["scan_results"] = results
        st.session_state["last_scanned"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        st.rerun()

    # ── Results ──
    results = st.session_state.get("scan_results", None)
    ticks   = angel_ws.get_latest_ticks()

    if results is None:
        st.markdown(f"""
        <div style="text-align:center;padding:60px 20px;color:#94a3b8;">
            <div style="font-size:40px;margin-bottom:12px;">🔍</div>
            <div style="font-size:15px;color:#475569;">
                Click <b style="color:#10b981">Scan Now</b> to find 4H breakout stocks.<br>
                <span style="font-size:12px;color:#94a3b8;">Scans all {len(ALL_STOCKS)} stocks from your watchlist.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Metric tiles ──
    passed   = len(results)
    total    = len(ALL_STOCKS)
    avg_rvol = round(np.mean([r["rel_vol"] for r in results]), 1) if results else 0
    top_rvol = round(max([r["rel_vol"] for r in results]), 1) if results else 0

    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-tile">
            <div class="metric-val">{passed}</div>
            <div class="metric-lbl">Breakouts Found</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{total}</div>
            <div class="metric-lbl">Stocks Scanned</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{avg_rvol}x</div>
            <div class="metric-lbl">Avg Rel. Volume</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{top_rvol}x</div>
            <div class="metric-lbl">Top Rel. Volume</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Table ──
    st.markdown(
        '<h3 style="color:#0f172a;font-size:16px;font-weight:600;margin-bottom:10px">📋 Breakout Stocks</h3>',
        unsafe_allow_html=True
    )
    render_table(results, ticks)

    # ── Chart ──
    if results:
        st.markdown("---")
        st.markdown(
            '<h3 style="color:#0f172a;font-size:16px;font-weight:600;margin-bottom:10px">📊 4H Candle Chart</h3>',
            unsafe_allow_html=True
        )

        symbols      = [r["symbol"] for r in results]
        selected_sym = st.selectbox(
            "Select stock", options=symbols, label_visibility="collapsed"
        )
        selected = next((r for r in results if r["symbol"] == selected_sym), None)

        if selected:
            c1, c2, c3, c4 = st.columns(4)
            price    = selected["price"]
            brk_pct  = selected["breakout_pct"]
            rel_vol  = selected["rel_vol"]
            rng_pct  = selected["range_pct"]
            c1.metric("Price",        f"₹{price:,.2f}")
            c2.metric("Breakout %",   f"+{brk_pct:.2f}%")
            c3.metric("Rel. Volume",  f"{rel_vol:.1f}x")
            c4.metric("Zone Range %", f"{rng_pct:.2f}%")

            st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
            render_chart(selected)
            st.markdown("""
            <div style="display:flex;gap:20px;margin-top:10px;font-size:12px;color:#64748b;">
                <span>🟩 Breakout candle</span>
                <span>🔴 Consolidation zone</span>
                <span>⬜ Prior 4H candles</span>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Footer ──
    st.markdown("---")
    st.markdown(
        '<p style="text-align:center;color:#94a3b8;font-size:12px;">'
        '⚠️ For educational and research purposes only. Not financial advice.'
        '</p>',
        unsafe_allow_html=True
    )


main()
