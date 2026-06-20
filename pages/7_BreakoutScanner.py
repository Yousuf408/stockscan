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
# TOKEN MAPS (from config.py)
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

.metric-row {
    display: flex; gap: 12px; margin-bottom: 20px;
}
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
        symbol     = r["symbol"]
        token      = NAME_TO_TOKEN.get(symbol)
        live_data  = ticks.get(token, {}) if token else {}
        live_price = live_data.get("ltp", r["price"])
        live_chg   = live_data.get("change_pct", 0)
        chg_str    = f"+{live_chg:.2f}%" if live_chg >= 0 else f"{live_chg:.2f}%"

        brk_pct      = r["breakout_pct"]
        body_pct     = r["body_pct"]
        rel_vol      = r["rel_vol"]
        pct_from_high= r["pct_from_high"]
        con_low      = r["con_low"]
        con_high     = r["con_high"]

        rows.append({
            "Ticker"        : symbol,
            "Live Price"    : f"₹{live_price:,.2f}  {chg_str}",
            "Breakout %"    : f"+{brk_pct:.2f}%",
            "Body %"        : f"{body_pct:.2f}%",
            "Rel. Volume"   : f"{rel_vol:.1f}x",
            "% from High"   : f"{pct_from_high:.2f}%",
            "Zone"          : f"₹{con_low:,.0f} – ₹{con_high:,.0f}",
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
    # ── Header ──
    col_title, col_btn, col_time = st.columns([4, 1.5, 2])

    with col_title:
        st.markdown(
            '<h1 style="color:#0f172a;font-size:28px;font-weight:700;margin:0">⚡ Breakout Scanner</h1>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<p style="color:#64748b;font-size:13px;margin:0">4H consolidation breakouts · India NSE</p>',
            unsafe_allow_html=True
        )

    with col_time:
        last_scanned = st.session_state.get("last_scanned", None)
        if last_scanned:
            st.markdown(
                f'<p style="color:#64748b;font-size:12px;text-align:right;margin-top:14px">'
                f'Last scanned: {last_scanned}</p>',
                unsafe_allow_html=True
            )

    with col_btn:
        scan_clicked = st.button("🔍 Scan Now", use_container_width=True)

    st.markdown("---")

    # ── WebSocket status ──
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks()
    ticks_count  = len(ticks)

    if ws_connected:
        st.markdown(
            f'<span class="dot-live"></span>'
            f'<span style="color:#059669;font-size:13px;font-weight:500">'
            f'WebSocket Live · {ticks_count} stocks receiving ticks</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<span style="color:#dc2626;font-size:13px">'
            '⚠️ WebSocket disconnected — live prices unavailable</span>',
            unsafe_allow_html=True
        )

    # ── Scan trigger ──
    if scan_clicked:
        ensure_websocket()
        progress_bar = st.progress(0, text="Starting scan...")
        status_text  = st.empty()

        def on_progress(done, total):
            pct = int(done / total * 100)
            progress_bar.progress(pct, text=f"Scanning... {done}/{total}")

        def on_status(symbol, done, total):
            status_text.caption(f"⚡ Checking {symbol} ({done}/{total})")

        results = run_scan(
            all_stocks  = ALL_STOCKS,
            progress_cb = on_progress,
            status_cb   = on_status,
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
            "Select stock",
            options=symbols,
            label_visibility="collapsed"
        )

        selected = next((r for r in results if r["symbol"] == selected_sym), None)
        if selected:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Price",        f"₹{selected["price"]:,.2f}")
            c2.metric("Breakout %",   f"+{selected["breakout_pct"]:.2f}%")
            c3.metric("Rel. Volume",  f"{selected["rel_vol"]:.1f}x")
            c4.metric("Zone Range %", f"{selected["range_pct"]:.2f}%")

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
