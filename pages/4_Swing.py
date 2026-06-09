# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — pages/4_Swing.py  v1.0
#  Swing Scanner — positional trade setup detector
#  Logic: price near 5d high + volume building → WATCH / READY / BLASTING
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import os, sys, time
from datetime import datetime, date

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from swing_core import (
    load_swing_stocks,
    add_swing_stock,
    update_swing_stock,
    delete_swing_stock,
    bulk_add_swing_stocks,
    run_swing_scan,
)

# ── Try watchlist push ──
try:
    from core import add_to_watchlist, get_user_watchlist_names
    WATCHLIST_PUSH = True
except Exception:
    WATCHLIST_PUSH = False

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Swing Scanner · TradeSentry",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="collapsed",
)

apply_styles()
sidebar_brand()

# ── Auth guard ──
if not st.session_state.get("user_id"):
    st.warning("Please login to access this page.")
    if st.button("Go to Login →", type="primary"):
        st.switch_page("pages/0_Login.py")
    st.stop()

page_header("Swing Scanner", "Positional trade setups")

# ─────────────────────────────────────────────────────────────────────────────
# EXTRA CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.sw-card {
    background: #ffffff;
    border: 1px solid #e0e3e8;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: box-shadow 0.15s;
}
.sw-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.09); }

.sw-blasting { border-left: 4px solid #7c3aed; }
.sw-ready    { border-left: 4px solid #00a854; }
.sw-watch    { border-left: 4px solid #f59e0b; }
.sw-none     { border-left: 4px solid #e0e3e8; }

.sw-badge-blasting {
    background: #ede9fe; color: #7c3aed;
    border: 1px solid #c4b5fd;
    font-size: 11px; font-weight: 700;
    padding: 2px 10px; border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
}
.sw-badge-ready {
    background: #f0faf5; color: #00a854;
    border: 1px solid #00a85430;
    font-size: 11px; font-weight: 700;
    padding: 2px 10px; border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
}
.sw-badge-watch {
    background: #fffbeb; color: #d97706;
    border: 1px solid #f59e0b40;
    font-size: 11px; font-weight: 700;
    padding: 2px 10px; border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
}
.sw-symbol {
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px; font-weight: 700; color: #0f1117;
    letter-spacing: 0.04em;
}
.sw-price {
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px; font-weight: 700; color: #0f1117;
}
.sw-label {
    font-size: 10px; font-weight: 600; color: #7a8394;
    text-transform: uppercase; letter-spacing: 0.08em;
    font-family: 'Inter', sans-serif;
}
.sw-val {
    font-size: 13px; font-weight: 600; color: #0f1117;
    font-family: 'JetBrains Mono', monospace;
}
.sw-trend {
    display: flex; gap: 4px; align-items: flex-end;
}
.sw-bar {
    width: 10px; border-radius: 2px 2px 0 0;
    display: inline-block;
}
.sw-manage-row {
    background: #f8f9fb;
    border: 1px solid #e0e3e8;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "sw_results"      not in st.session_state: st.session_state.sw_results      = []
if "sw_errors"       not in st.session_state: st.session_state.sw_errors       = []
if "sw_scan_time"    not in st.session_state: st.session_state.sw_scan_time    = None
if "sw_show_manage"  not in st.session_state: st.session_state.sw_show_manage  = False
if "sw_stocks_cache" not in st.session_state: st.session_state.sw_stocks_cache = None
if "sw_filter"       not in st.session_state: st.session_state.sw_filter       = "ALL"
if "sw_edit_id"      not in st.session_state: st.session_state.sw_edit_id      = None

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load_stocks_cached():
    if st.session_state.sw_stocks_cache is None:
        st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def refresh_stocks():
    st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def trend_html(closes: list) -> str:
    if not closes:
        return "—"
    mn, mx = min(closes), max(closes)
    rng    = mx - mn or 1
    bars   = ""
    for i, c in enumerate(closes):
        h     = max(8, int(((c - mn) / rng) * 32) + 8)
        color = "#00a854" if i == len(closes)-1 else "#cbd5e1"
        bars += f'<div class="sw-bar" style="height:{h}px;background:{color};"></div>'
    return f'<div class="sw-trend">{bars}</div>'

def status_badge(status: str) -> str:
    cls = {"BLASTING": "sw-badge-blasting", "READY": "sw-badge-ready", "WATCH": "sw-badge-watch"}
    icon = {"BLASTING": "🚀", "READY": "✅", "WATCH": "👁"}
    c = cls.get(status, "")
    i = icon.get(status, "")
    if not c:
        return ""
    return f'<span class="{c}">{i} {status}</span>'

def card_class(status: str) -> str:
    return {"BLASTING": "sw-card sw-blasting", "READY": "sw-card sw-ready",
            "WATCH": "sw-card sw-watch"}.get(status, "sw-card sw-none")

# ─────────────────────────────────────────────────────────────────────────────
# CONTROL BAR
# ─────────────────────────────────────────────────────────────────────────────
stocks = load_stocks_cached()
total_stocks = len(stocks)

c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1, 1, 2.5])

with c1:
    manage_label = "✕ Manage" if st.session_state.sw_show_manage else "⚙ Manage Stocks"
    if st.button(manage_label, use_container_width=True):
        st.session_state.sw_show_manage = not st.session_state.sw_show_manage
        st.rerun()

with c2:
    scan_disabled = total_stocks == 0
    if st.button("▷ Run Scan", use_container_width=True, disabled=scan_disabled,
                 type="primary"):
        with st.spinner(f"Scanning {total_stocks} stocks..."):
            t0 = time.time()
            results, errors = run_swing_scan(stocks)
            st.session_state.sw_results   = results
            st.session_state.sw_errors    = errors
            st.session_state.sw_scan_time = time.time()
        st.rerun()

with c3:
    if st.button("🗑 Clear", use_container_width=True,
                 disabled=len(st.session_state.sw_results) == 0):
        st.session_state.sw_results   = []
        st.session_state.sw_errors    = []
        st.session_state.sw_scan_time = None
        st.session_state.sw_filter    = "ALL"
        st.rerun()

with c4:
    st.markdown(f"""
    <div style="text-align:center;padding-top:6px;">
        <span style="font-size:12px;color:#7a8394;">
            📋 <b style="color:#0f1117;">{total_stocks}</b> stocks
        </span>
    </div>
    """, unsafe_allow_html=True)

with c5:
    if st.session_state.sw_scan_time:
        t = datetime.fromtimestamp(st.session_state.sw_scan_time).strftime("%I:%M %p")
        blasting = sum(1 for r in st.session_state.sw_results if r.get("status") == "BLASTING")
        ready    = sum(1 for r in st.session_state.sw_results if r.get("status") == "READY")
        watch    = sum(1 for r in st.session_state.sw_results if r.get("status") == "WATCH")
        st.markdown(f"""
        <div style="display:flex;gap:16px;align-items:center;justify-content:flex-end;padding-top:6px;">
            <span style="font-size:12px;color:#7c3aed;font-weight:700;">🚀 {blasting}</span>
            <span style="font-size:12px;color:#00a854;font-weight:700;">✅ {ready}</span>
            <span style="font-size:12px;color:#d97706;font-weight:700;">👁 {watch}</span>
            <span style="font-size:11px;color:#7a8394;">Last scan: {t}</span>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MANAGE STOCKS PANEL
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.sw_show_manage:
    with st.container():
        st.markdown("### ⚙ Manage Swing Stocks")
        tab_add, tab_bulk, tab_list = st.tabs(["➕ Add Single", "📋 Bulk Add", "📝 Stock List"])

        # ── ADD SINGLE ──
        with tab_add:
            with st.form("add_single_form", clear_on_submit=True):
                col1, col2 = st.columns([1, 2])
                with col1:
                    sym = st.text_input("NSE Symbol *", placeholder="e.g. HEROMOTOCO")
                with col2:
                    url = st.text_input("Screener URL (optional)",
                                        placeholder="https://www.screener.in/company/HEROMOTOCO/")
                col3, col4 = st.columns([1, 2])
                with col3:
                    bd = st.date_input("Breakout Date (optional)", value=None)
                with col4:
                    notes = st.text_input("Notes (optional)", placeholder="Near ATH, consolidating...")
                submitted = st.form_submit_button("➕ Add Stock", type="primary")
                if submitted:
                    if not sym.strip():
                        st.error("Symbol is required.")
                    else:
                        try:
                            add_swing_stock(sym.strip(), url.strip(), bd, notes.strip())
                            refresh_stocks()
                            st.success(f"✅ {sym.upper()} added.")
                            st.rerun()
                        except ValueError as e:
                            st.warning(str(e))
                        except Exception as e:
                            st.error(f"Error: {e}")

        # ── BULK ADD ──
        with tab_bulk:
            st.markdown("Paste symbols one per line or comma-separated:")
            bulk_text = st.text_area("Symbols", height=150,
                                     placeholder="HEROMOTOCO\nTITAN\nHDFCBANK\n...")
            if st.button("📋 Add All", type="primary"):
                if not bulk_text.strip():
                    st.warning("Enter at least one symbol.")
                else:
                    # Parse — handle newlines and commas
                    raw = bulk_text.replace(",", "\n").splitlines()
                    syms = [s.strip().upper() for s in raw if s.strip()]
                    if syms:
                        with st.spinner(f"Adding {len(syms)} stocks..."):
                            result = bulk_add_swing_stocks(syms)
                        refresh_stocks()
                        if result["added"]:
                            st.success(f"✅ Added: {', '.join(result['added'])}")
                        if result["skipped"]:
                            st.info(f"⏭ Already exists: {', '.join(result['skipped'])}")
                        if result["errors"]:
                            st.error(f"❌ Failed: {', '.join(result['errors'])}")
                        st.rerun()

        # ── STOCK LIST ──
        with tab_list:
            current_stocks = refresh_stocks()
            if not current_stocks:
                st.info("No stocks yet. Add stocks using the tabs above.")
            else:
                st.markdown(f"**{len(current_stocks)} stocks in swing list**")
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                for s in current_stocks:
                    col1, col2, col3, col4 = st.columns([2, 3, 2, 1])
                    with col1:
                        st.markdown(f"**`{s['symbol']}`**")
                    with col2:
                        bd = s.get("breakout_date") or "—"
                        st.markdown(f"<span style='font-size:12px;color:#7a8394;'>Breakout: {bd}</span>",
                                    unsafe_allow_html=True)
                    with col3:
                        notes = s.get("notes") or ""
                        if notes:
                            st.markdown(f"<span style='font-size:12px;color:#7a8394;'>{notes[:40]}</span>",
                                        unsafe_allow_html=True)
                    with col4:
                        if st.button("✕", key=f"del_{s['id']}", help=f"Remove {s['symbol']}"):
                            try:
                                delete_swing_stock(s["id"])
                                refresh_stocks()
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

    st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# FILTER BAR
# ─────────────────────────────────────────────────────────────────────────────
results = st.session_state.sw_results

if results:
    all_count      = len(results)
    blasting_count = sum(1 for r in results if r.get("status") == "BLASTING")
    ready_count    = sum(1 for r in results if r.get("status") == "READY")
    watch_count    = sum(1 for r in results if r.get("status") == "WATCH")

    filter_options = [
        f"ALL ({all_count})",
        f"🚀 BLASTING ({blasting_count})",
        f"✅ READY ({ready_count})",
        f"👁 WATCH ({watch_count})",
    ]

    selected = st.pills("Filter", filter_options, default=filter_options[0],
                        label_visibility="collapsed")

    if selected:
        if "BLASTING" in selected:
            results = [r for r in results if r.get("status") == "BLASTING"]
        elif "READY" in selected:
            results = [r for r in results if r.get("status") == "READY"]
        elif "WATCH" in selected:
            results = [r for r in results if r.get("status") == "WATCH"]

    st.markdown(f"<div style='height:8px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.sw_results:
    if total_stocks == 0:
        st.info("👆 Add stocks via **Manage Stocks**, then run a scan.")
    else:
        st.info(f"▷ Click **Run Scan** to scan {total_stocks} stocks.")
else:
    # Watchlist names for push button
    if WATCHLIST_PUSH:
        try:
            wl_names = get_user_watchlist_names() if st.session_state.get("user_id") else ["Today", "Yesterday", "New"]
        except Exception:
            wl_names = ["Today", "Yesterday", "New"]
    else:
        wl_names = []

    for r in results:
        sym    = r["symbol"]
        status = r.get("status", "")
        closes = r.get("closes", [])
        ltp    = r.get("current_price", 0)
        vol_sig= r.get("vol_signal", "—")
        ratio  = r.get("vol_ratio", 0)
        bd     = r.get("breakout_date") or "—"
        s_url  = r.get("screener_url", f"https://www.screener.in/company/{sym}/")
        high   = r.get("today_high", 0)
        low    = r.get("today_low", 0)
        cur_vol= r.get("current_vol", 0)
        avg_vol= r.get("avg_vol_3d", 0)
        max_cl = r.get("max_close", 0)
        notes  = r.get("notes", "")

        css_class = card_class(status)

        st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)

        row1, row2, row3 = st.columns([3, 5, 3])

        with row1:
            st.markdown(
                f'<span class="sw-symbol">{sym}</span>&nbsp;&nbsp;'
                f'{status_badge(status)}',
                unsafe_allow_html=True,
            )
            if notes:
                st.markdown(
                    f'<span style="font-size:11px;color:#7a8394;">{notes}</span>',
                    unsafe_allow_html=True,
                )

        with row2:
            # Trend sparkline + key numbers
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown('<div class="sw-label">5D Trend</div>', unsafe_allow_html=True)
                st.markdown(trend_html(closes), unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="sw-label">LTP</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="sw-price">₹{ltp:,.2f}</div>', unsafe_allow_html=True)
                pct_from_high = round(((ltp - max_cl) / max_cl) * 100, 1) if max_cl else 0
                color = "#00a854" if pct_from_high >= 0 else "#e53935"
                st.markdown(
                    f'<span style="font-size:11px;color:{color};font-family:monospace;">'
                    f'{pct_from_high:+.1f}% vs 5d high</span>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown('<div class="sw-label">Vol Signal</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:13px;">{vol_sig}</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<span style="font-size:11px;color:#7a8394;">'
                    f'cur:{cur_vol:,} / avg:{avg_vol:,}</span>',
                    unsafe_allow_html=True,
                )
            with c4:
                st.markdown('<div class="sw-label">Today H/L</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="sw-val">H: ₹{high:,.2f}</div>'
                    f'<div class="sw-val">L: ₹{low:,.2f}</div>',
                    unsafe_allow_html=True,
                )

        with row3:
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                st.markdown(
                    f'<div class="sw-label">Breakout Date</div>'
                    f'<div class="sw-val">{bd}</div>',
                    unsafe_allow_html=True,
                )
            with bc2:
                st.link_button("Screener ↗", s_url, use_container_width=True)
            with bc3:
                if WATCHLIST_PUSH and status in ("BLASTING", "READY"):
                    wl_key = f"wl_push_{sym}"
                    if wl_key not in st.session_state:
                        st.session_state[wl_key] = wl_names[0] if wl_names else "Today"
                    chosen_wl = st.selectbox(
                        "→ Watchlist",
                        wl_names,
                        key=f"wl_sel_{sym}",
                        label_visibility="collapsed",
                    )
                    if st.button("➕ Add", key=f"wl_btn_{sym}", use_container_width=True):
                        try:
                            add_to_watchlist(chosen_wl, {
                                "symbol":    sym,
                                "status":    "BUY",
                                "lastPrice": ltp,
                                "entry":     ltp,
                                "sl":        round(low * 0.99, 2),
                                "target1":   round(ltp * 1.05, 2),
                                "target2":   round(ltp * 1.10, 2),
                                "note":      f"Swing {status} — vol ratio {ratio}x",
                            })
                            st.success(f"Added {sym} → {chosen_wl}")
                        except Exception as e:
                            st.error(str(e))

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Errors section ──
    if st.session_state.sw_errors:
        with st.expander(f"⚠ {len(st.session_state.sw_errors)} stocks failed to fetch"):
            for e in st.session_state.sw_errors:
                st.markdown(
                    f'`{e["symbol"]}` — <span style="color:#e53935;">{e["error"]}</span>',
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────────────────────────────────────────────
# EMPTY STATE — no scan run yet but stocks exist
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.sw_results and total_stocks > 0 and not st.session_state.sw_show_manage:
    st.markdown(f"""
    <div style="text-align:center;padding:40px 0;color:#7a8394;">
        <div style="font-size:40px;margin-bottom:12px;">📈</div>
        <div style="font-size:16px;font-weight:600;color:#0f1117;">{total_stocks} stocks ready to scan</div>
        <div style="font-size:13px;margin-top:6px;">Click <b>▷ Run Scan</b> to find BLASTING / READY / WATCH setups</div>
    </div>
    """, unsafe_allow_html=True)
