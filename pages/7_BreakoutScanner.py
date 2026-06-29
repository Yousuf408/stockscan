"""
7_BreakoutScanner.py
Two tabs:
  Tab 1: Consolidation Watch  — stocks consolidating, monitor live
  Tab 2: Breakout Scanner     — stocks that already broke out
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
from breakout_4h.breakout_4h_chart  import render_chart
from breakout_4h.breakout_4h_watch  import scan_consolidating, check_live_alerts

st.set_page_config(page_title="Breakout Scanner", page_icon="⚡", layout="wide")
# ─────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ─────────────────────────────────────────────────────────────
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("BreakoutScanner")
#------------ END ---------------

NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST if kind == "stock"}
ALL_STOCKS    = [name for name, _, kind in STOCKS_WATCHLIST if kind == "stock"]

st.markdown("""
<style>
footer { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }

div[data-testid="stButton"] > button {
    background: linear-gradient(to right, #10b981, #14b8a6) !important;
    color: white !important; border: none !important;
    border-radius: 9999px !important; font-weight: 600 !important;
    font-size: 14px !important; width: 100%;
}
div[data-testid="stButton"] > button:hover { opacity: 0.88 !important; }

.metric-row { display: flex; gap: 12px; margin-bottom: 20px; }
.metric-tile {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 10px; padding: 14px 18px; flex: 1; text-align: center;
}
.metric-val       { font-size: 26px; font-weight: 700; color: #059669; }
.metric-val-pink  { font-size: 26px; font-weight: 700; color: #db2777; }
.metric-val-amber { font-size: 26px; font-weight: 700; color: #d97706; }
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
.alert-box {
    display: flex; align-items: center; gap: 12px;
    background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
    font-size: 13px;
}
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #f8fafc; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


def ensure_websocket():
    if not angel_ws.is_connected():
        with st.spinner("Connecting to Angel One WebSocket..."):
            creds = angel_login()
            if creds:
                angel_ws.start_websocket(
                    creds["jwt_token"], creds["api_key"],
                    creds["client_id"], creds["feed_token"]
                )
                time.sleep(3)
            else:
                st.error("❌ Angel One login failed.")


def render_breakout_table(results, ticks):
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
        rows.append({
            "Ticker"      : symbol,
            "Live Price"  : f"₹{live_price:,.2f}  {chg_str}",
            "Breakout %"  : f"+{r['breakout_pct']:.2f}%",
            "Body %"      : f"{r['body_pct']:.2f}%",
            "Rel. Volume" : f"{r['rel_vol']:.1f}x",
            "% from High" : f"{r['pct_from_high']:.2f}%",
            "Zone"        : f"₹{r['con_low']:,.0f} – ₹{r['con_high']:,.0f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 height=min(len(rows) * 45 + 38, 500))


def render_watch_table(enriched):
    if not enriched:
        st.info("📭 No consolidating stocks found.")
        return

    TH = "padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;border-bottom:2px solid #e2e8f0;background:#f8fafc;white-space:nowrap;"
    TD = "padding:9px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;"

    rows_html = ""
    for s in enriched:
        sym      = s["symbol"]
        ltp      = s["ltp"]
        con_high = s["con_high"]
        con_low  = s["con_low"]
        rng      = s["range_pct"]
        ptb      = s["pct_to_breakout"]
        prox     = s["proximity_pct"]
        status   = s["status"]

        if status == "broke_out":
            row_bg  = "background:#f0fdf4;"
            ltp_col = f'<span style="color:#059669;font-weight:700;">₹{ltp:,.2f}</span>'
            ptb_col = f'<span style="color:#059669;font-weight:600;">+{ptb:.1f}% above</span>'
            badge   = '<span style="background:#d1fae5;color:#059669;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Broke out!</span>'
            bar_clr = "#059669"
        elif status == "near_zone":
            row_bg  = "background:#fff7ed;"
            ltp_col = f'<span style="color:#d97706;font-weight:700;">₹{ltp:,.2f}</span>'
            ptb_col = f'<span style="color:#d97706;font-weight:600;">{ptb:.1f}% to go</span>'
            badge   = '<span style="background:#fce7f3;color:#db2777;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Near zone!</span>'
            bar_clr = "#f59e0b"
        else:
            row_bg  = "background:#ffffff;"
            ltp_col = f'₹{ltp:,.2f}'
            ptb_col = f'{ptb:.1f}% to go'
            badge   = ('<span style="background:#e0f2fe;color:#0284c7;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Tight range</span>'
                       if rng <= 6 else
                       '<span style="background:#fef3c7;color:#d97706;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Watching</span>')
            bar_clr = "#10b981"

        bar_w = int(min(100, max(5, prox)))
        rows_html += f"""
        <tr style="{row_bg}">
            <td style="{TD}font-weight:600;">{sym}</td>
            <td style="{TD}">{ltp_col}</td>
            <td style="{TD}">₹{con_high:,.0f}</td>
            <td style="{TD}">₹{con_low:,.0f}</td>
            <td style="{TD}">{rng:.1f}%</td>
            <td style="{TD}">{ptb_col}</td>
            <td style="{TD}">
                <div style="width:80px;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;display:inline-block;">
                    <div style="width:{bar_w}%;height:100%;background:{bar_clr};border-radius:3px;"></div>
                </div>
            </td>
            <td style="{TD}">{badge}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head>
    <style>body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
    table{{width:100%;border-collapse:collapse;font-size:13px;}}</style></head><body>
    <div style="overflow-x:auto;border-radius:10px;border:1px solid #e2e8f0;">
    <table>
        <thead><tr>
            <th style="{TH}">Ticker</th><th style="{TH}">LTP</th>
            <th style="{TH}">Zone High</th><th style="{TH}">Zone Low</th>
            <th style="{TH}">Range %</th><th style="{TH}">% to Breakout</th>
            <th style="{TH}">Proximity</th><th style="{TH}">Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table></div></body></html>"""
    st.components.v1.html(html, height=min(len(enriched) * 48 + 55, 600), scrolling=True)


def main():
    # ── WS Status ──
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks()
    ticks_count  = len(ticks)
    last_scanned = st.session_state.get("last_scanned", "")

    ws_html = (f'<span class="dot-live"></span><span style="color:#059669;font-size:12px;font-weight:500">Live · {ticks_count} ticks</span>'
               if ws_connected else
               '<span style="color:#dc2626;font-size:12px;">⚠️ WS disconnected</span>')
    ls_html = f'<span style="color:#94a3b8;font-size:12px;">Last scan: {last_scanned}</span>' if last_scanned else ""

    # ── Header ──
    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:4px 0 10px 0;border-bottom:1px solid #e2e8f0;margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:700;color:#0f172a;">⚡ Breakout Scanner</span>
            <span style="font-size:12px;color:#94a3b8;">4H consolidation · India NSE</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">{ws_html} &nbsp; {ls_html}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tabs ──
    watch_count = len(st.session_state.get("watch_results", []))
    tab_label_1 = f"👁️ Consolidation Watch · {watch_count} stocks" if watch_count else "👁️ Consolidation Watch"
    tab_label_2 = "🔍 Breakout Scanner"

    tab1, tab2 = st.tabs([tab_label_1, tab_label_2])

    # ══════════════════════════════════════════════════════════
    # TAB 1 — CONSOLIDATION WATCH
    # ══════════════════════════════════════════════════════════
    with tab1:
        b1, b2, b3_info = st.columns([1, 1, 4])
        with b1:
            build_clicked = st.button("📡 Build Watchlist", use_container_width=True, key="build_btn")
        with b2:
            refresh_clicked = st.button("🔄 Refresh Live", use_container_width=True, key="refresh_btn")
        with b3_info:
            st.markdown('<p style="color:#94a3b8;font-size:12px;margin-top:10px;">Auto-refresh every 30s · LTP from Angel WS</p>', unsafe_allow_html=True)

        if build_clicked:
            ensure_websocket()
            pb     = st.progress(0, text="Building watchlist...")
            st_txt = st.empty()
            def on_prog_w(d, t): pb.progress(int(d/t*100), text=f"Scanning... {d}/{t}")
            def on_stat_w(sym, d, t): st_txt.caption(f"⚡ Checking {sym} ({d}/{t})")
            watch_raw = scan_consolidating(ALL_STOCKS, on_prog_w, on_stat_w)
            pb.empty(); st_txt.empty()
            st.session_state["watch_results"]    = watch_raw
            st.session_state["watch_built_time"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
            st.rerun()

        watch_raw  = st.session_state.get("watch_results", None)
        built_time = st.session_state.get("watch_built_time", "")

        if watch_raw is None:
            st.markdown("""
            <div style="text-align:center;padding:60px 20px;color:#94a3b8;">
                <div style="font-size:40px;margin-bottom:12px;">👁️</div>
                <div style="font-size:15px;color:#475569;">
                    Click <b style="color:#10b981">Build Watchlist</b> to monitor consolidating stocks.<br>
                    <span style="font-size:12px;">Live LTP vs 4H zone tracked via Angel WebSocket.</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            ticks    = angel_ws.get_latest_ticks()
            enriched = check_live_alerts(watch_raw, ticks, NAME_TO_TOKEN)

            broke_out = [s for s in enriched if s["status"] == "broke_out"]
            near_zone = [s for s in enriched if s["status"] == "near_zone"]
            avg_range = round(np.mean([s["range_pct"] for s in enriched]), 1) if enriched else 0

            # Alert banners
            for s in broke_out:
                st.markdown(f"""
                <div class="alert-box">
                    <span style="font-size:20px;">🔔</span>
                    <div>
                        <strong>{s["symbol"]}</strong> ne zone toda!
                        LTP ₹{s["ltp"]:,.2f} &gt; Zone High ₹{s["con_high"]:,.0f}
                        &nbsp;<span style="color:#059669;font-weight:600;">+{s["pct_to_breakout"]:.1f}% above zone</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            if built_time:
                st.markdown(f'<p style="font-size:11px;color:#94a3b8;margin-bottom:10px;">Watchlist built: {built_time} · auto-refresh every 30s</p>', unsafe_allow_html=True)

            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-tile"><div class="metric-val">{len(enriched)}</div><div class="metric-lbl">Consolidating</div></div>
                <div class="metric-tile"><div class="metric-val-pink">{len(near_zone)}</div><div class="metric-lbl">Near Breakout</div></div>
                <div class="metric-tile"><div class="metric-val">{len(broke_out)}</div><div class="metric-lbl">Just Broke Out</div></div>
                <div class="metric-tile"><div class="metric-val-amber">{avg_range}%</div><div class="metric-lbl">Avg Zone Range</div></div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<p style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:8px;">📋 Watchlist — sorted by proximity to Zone High</p>', unsafe_allow_html=True)
            render_watch_table(enriched)

    # ══════════════════════════════════════════════════════════
    # TAB 2 — BREAKOUT SCANNER
    # ══════════════════════════════════════════════════════════
    with tab2:
        col_btn, _ = st.columns([1, 5])
        with col_btn:
            scan_clicked = st.button("🔍 Scan Now", use_container_width=True, key="scan_btn")

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
                f_consol   = st.selectbox("Consolidation Range", CONSOL_OPTS,
                    index=CONSOL_OPTS.index(st.session_state.get("f_consol", 12)),
                    format_func=lambda x: f"≤ {x}%", key="f_consol")
                f_breakout = st.selectbox("Breakout Above Zone", BREAKOUT_OPTS,
                    index=BREAKOUT_OPTS.index(st.session_state.get("f_breakout", 2.0)),
                    format_func=lambda x: f"{x}%" if x > 0 else "0% (just above)", key="f_breakout")
            with fc2:
                f_body   = st.selectbox("Min Body Size", BODY_OPTS,
                    index=BODY_OPTS.index(st.session_state.get("f_body", 5)),
                    format_func=lambda x: f"{x}%", key="f_body")
                f_relvol = st.selectbox("Relative Volume", RELVOL_OPTS,
                    index=RELVOL_OPTS.index(st.session_state.get("f_relvol", 1.5)),
                    format_func=lambda x: f"{x}x", key="f_relvol")
            with fc3:
                f_dailyvol = st.selectbox("Min Daily Volume", DVOL_OPTS,
                    index=DVOL_OPTS.index(st.session_state.get("f_dailyvol", 500_000)),
                    format_func=lambda x: f"{int(x/1000)}k" if x < 1_000_000 else f"{int(x/1_000_000)}M",
                    key="f_dailyvol")
                f_mktcap = st.selectbox("Market Cap", MKTCAP_OPTS,
                    index=MKTCAP_OPTS.index(st.session_state.get("f_mktcap", 50_000_000)),
                    format_func=lambda x: f"${int(x/1_000_000)}M" if x < 1_000_000_000 else f"${int(x/1_000_000_000)}B",
                    key="f_mktcap")
            with fc4:
                f_nearhigh = st.selectbox("Price Near High", NEARHIGH_OPTS,
                    index=NEARHIGH_OPTS.index(st.session_state.get("f_nearhigh", 10)),
                    format_func=lambda x: f"Within {x}%", key="f_nearhigh")
                f_trend = st.selectbox("Trend (SMA)", TREND_OPTS,
                    index=TREND_OPTS.index(st.session_state.get("f_trend", "both")),
                    format_func=lambda x: {"both":"SMA20 & SMA50","sma20":"Only SMA20","sma50":"Only SMA50","disable":"Disabled"}[x],
                    key="f_trend")

            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("↺ Reset to Defaults", key="reset_filters", use_container_width=True):
                    for k in ["f_consol","f_breakout","f_body","f_relvol","f_dailyvol","f_mktcap","f_nearhigh","f_trend"]:
                        st.session_state.pop(k, None)
                    st.rerun()
            with rc2:
                apply_clicked = st.button("✅ Apply & Scan", key="apply_filters", use_container_width=True)

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

        if scan_clicked or apply_clicked:
            ensure_websocket()
            pb     = st.progress(0, text="Starting scan...")
            st_txt = st.empty()
            def on_prog(d, t): pb.progress(int(d/t*100), text=f"Scanning... {d}/{t}")
            def on_stat(sym, d, t): st_txt.caption(f"⚡ Checking {sym} ({d}/{t})")
            results = run_scan(ALL_STOCKS, on_prog, on_stat, scan_filters)
            pb.empty(); st_txt.empty()
            st.session_state["scan_results"] = results
            st.session_state["last_scanned"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
            st.rerun()

        results = st.session_state.get("scan_results", None)
        ticks   = angel_ws.get_latest_ticks()

        if results is None:
            st.markdown(f"""
            <div style="text-align:center;padding:60px 20px;color:#94a3b8;">
                <div style="font-size:40px;margin-bottom:12px;">🔍</div>
                <div style="font-size:15px;color:#475569;">
                    Click <b style="color:#10b981">Scan Now</b> to find 4H breakout stocks.<br>
                    <span style="font-size:12px;">Scans all {len(ALL_STOCKS)} stocks.</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            passed   = len(results)
            avg_rvol = round(np.mean([r["rel_vol"] for r in results]), 1) if results else 0
            top_rvol = round(max([r["rel_vol"] for r in results]), 1) if results else 0

            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-tile"><div class="metric-val">{passed}</div><div class="metric-lbl">Breakouts Found</div></div>
                <div class="metric-tile"><div class="metric-val">{len(ALL_STOCKS)}</div><div class="metric-lbl">Stocks Scanned</div></div>
                <div class="metric-tile"><div class="metric-val">{avg_rvol}x</div><div class="metric-lbl">Avg Rel. Volume</div></div>
                <div class="metric-tile"><div class="metric-val">{top_rvol}x</div><div class="metric-lbl">Top Rel. Volume</div></div>
            </div>
            """, unsafe_allow_html=True)

            render_breakout_table(results, ticks)

            if results:
                st.markdown('<p style="font-size:15px;font-weight:600;color:#0f172a;margin:16px 0 8px 0;">📊 4H Candle Chart</p>', unsafe_allow_html=True)
                selected_sym = st.selectbox("Select stock", [r["symbol"] for r in results],
                                            label_visibility="collapsed", key="chart_select")
                selected = next((r for r in results if r["symbol"] == selected_sym), None)
                if selected:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Price",        f"₹{selected['price']:,.2f}")
                    c2.metric("Breakout %",   f"+{selected['breakout_pct']:.2f}%")
                    c3.metric("Rel. Volume",  f"{selected['rel_vol']:.1f}x")
                    c4.metric("Zone Range %", f"{selected['range_pct']:.2f}%")
                    st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
                    render_chart(selected)
                    st.markdown('<div style="display:flex;gap:20px;margin-top:10px;font-size:12px;color:#64748b;"><span>🟩 Breakout candle</span><span>🔴 Consolidation zone</span><span>⬜ Prior 4H candles</span></div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

    # ── Footer ──
    st.markdown("---")
    st.markdown('<p style="text-align:center;color:#94a3b8;font-size:12px;">⚠️ For educational and research purposes only. Not financial advice.</p>', unsafe_allow_html=True)


main()
