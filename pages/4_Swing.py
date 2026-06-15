# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — pages/4_Swing.py  v4.4
#  v4.4: Intraday Watch column filters via components.html (proper iframe).
#        Last 2 history cols + LIVE col have ▼ dropdown with checkbox filters.
#        Multi-column AND filtering. Live header shows date inline (e.g. 11JUN · LIVE).
#
#  PAGE LOAD  → auto reads DB, shows results instantly, no button needed
#  SYNC 5D    → fetches only missing trading days from yfinance, saves hist
#  REFRESH    → fetches today's live price, updates swing_live_data
#  POPULATE   → one-time: calculates + saves last 10 days status snapshots
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import os, sys, time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from swing_core import (
    load_swing_stocks, add_swing_stock, update_swing_stock,
    delete_swing_stock, bulk_add_swing_stocks,
    load_from_db, sync_5d_history, refresh_live,
    populate_status_history,
    get_intraday_watch,
    fmt_vol, is_market_open,  # ← Keep this!
)
market_open = is_market_open()

try:
    from core import add_to_watchlist, get_user_watchlist_names
    WATCHLIST_PUSH = True
except Exception:
    WATCHLIST_PUSH = False

st.set_page_config(page_title="Swing · TradeSentry", layout="wide",
                   page_icon="📈", initial_sidebar_state="collapsed")
apply_styles()
sidebar_brand()

if not st.session_state.get("user_id"):
    st.warning("Please login.")
    if st.button("Go to Login →", type="primary"):
        st.switch_page("pages/0_Login.py")
    st.stop()

page_header("Swing Scanner", "Positional trade setups — 5d + current")

st.markdown("""
<style>
.sw-sym {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px; font-weight: 700; color: #0f1117;
}
.sw-bd { font-size: 10px; color: #9ca3af; margin-top: 3px; }
.sw-ltp {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px; font-weight: 700; color: #0f1117;
}
.sw-pct { font-size: 10px; font-family: monospace; margin-top: 3px; }
.sw-hl  { font-family: 'JetBrains Mono', monospace; font-size: 11px; line-height: 1.9; }
.sw-vsig { font-size: 12px; font-weight: 600; }
.sw-vsub { font-size: 10px; color: #9ca3af; font-family: 'JetBrains Mono', monospace; margin-top: 3px; }
.sw-med  { font-size: 9px; color: #f59e0b; margin-top: 3px; }
.sw-badge-B {
    background: #ede9fe; color: #3C3489; border: 1px solid #7c3aed40;
    font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 10px;
    display: inline-block; white-space: nowrap;
}
.sw-badge-R {
    background: #f0faf5; color: #0F6E56; border: 1px solid #1D9E7540;
    font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 10px;
    display: inline-block; white-space: nowrap;
}
.sw-badge-W {
    background: #fffbeb; color: #854F0B; border: 1px solid #f59e0b40;
    font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 10px;
    display: inline-block; white-space: nowrap;
}
.sw-link {
    font-size: 12px; color: #2563eb;
    text-decoration: none; font-weight: 500;
}
.sw-link:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──
for k, v in [
    ("sw_results",       []),
    ("sw_errors",        []),
    ("sw_loaded",        False),
    ("sw_show_manage",   False),
    ("sw_stocks_cache",  None),
    ("sw_last_sync",     None),
    ("sw_last_refresh",  None),
    ("sw_last_populate", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

def load_cached():
    if st.session_state.sw_stocks_cache is None:
        st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def refresh_cache():
    st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

# AUTO LOAD
if not st.session_state.sw_loaded:
    with st.spinner("Loading..."):
        results, errors = load_from_db()
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        st.session_state.sw_loaded  = True

# SVG HELPERS
def price_svg(opens, highs, lows, closes, dates,
              cur_open=None, cur_high=None, cur_low=None, cur_close=None,
              cur_date=None, w=200, h=62):
    if not closes:
        return f'<svg width="{w}" height="{h}"><text x="6" y="30" font-size="10" fill="#9ca3af">No data</text></svg>'
    has_cur = all(v is not None for v in [cur_open, cur_high, cur_low, cur_close])
    n   = len(closes)
    pad = 4
    bw  = 16
    gap = 5
    all_p = [v for v in highs + lows if v and v > 0]
    if has_cur:
        all_p += [cur_high, cur_low]
    if not all_p:
        return f'<svg width="{w}" height="{h}"></svg>'
    mn, mx = min(all_p), max(all_p)
    rng = mx - mn or 1
    def sy(v):
        return round(pad + (h - pad*2 - 10) * (1 - (v - mn) / rng), 1)
    parts = []
    for i in range(n):
        x  = pad + i*(bw+gap)
        cx = x + bw//2
        o, h2, l2, c = opens[i], highs[i], lows[i], closes[i]
        green  = c >= o
        col    = "#00a854" if green else "#e53935"
        body_y = sy(max(o, c))
        body_h = max(2, abs(sy(o) - sy(c)))
        parts.append(
            f'<line x1="{cx}" x2="{cx}" y1="{sy(h2)}" y2="{sy(l2)}" stroke="{col}" stroke-width="1.2"/>'
            f'<rect x="{x}" y="{body_y}" width="{bw}" height="{body_h}" fill="{col}" rx="2"/>'
        )
        lbl = dates[i].split(" ")[0] if i < len(dates) else str(i+1)
        parts.append(
            f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="#9ca3af">{lbl}</text>'
        )
    if has_cur:
        sep_x = pad + n*(bw+gap) + 2
        parts.append(
            f'<line x1="{sep_x}" x2="{sep_x}" y1="{pad}" y2="{h-12}" '
            f'stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>'
        )
        cx    = sep_x + 5 + bw//2
        tx    = sep_x + 5
        col   = "#7c3aed"
        body_y = sy(max(cur_open, cur_close))
        body_h = max(2, abs(sy(cur_open) - sy(cur_close)))
        lbl = cur_date.split(" ")[0] if cur_date else "today"
        parts.append(
            f'<line x1="{cx}" x2="{cx}" y1="{sy(cur_high)}" y2="{sy(cur_low)}" stroke="{col}" stroke-width="1.2"/>'
            f'<rect x="{tx}" y="{body_y}" width="{bw}" height="{body_h}" '
            f'fill="{col}30" stroke="{col}" stroke-width="1.5" rx="2"/>'
            f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="{col}" font-weight="500">{lbl}</text>'
        )
    total_w = (sep_x + 5 + bw + pad) if has_cur else (pad + n*(bw+gap))
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def volume_svg(hist_vols, cur_vol, median_vol, dates=None, cur_date=None, w=195, h=62):
    if dates is None:
        dates = []
    n        = len(hist_vols)
    pad      = 4
    bw       = 18
    gap      = 5
    bar_area = h - pad - 14
    hist_clean = [v for v in hist_vols if v and v > 0]
    mx_hist    = max(hist_clean) if hist_clean else 1
    def bh_hist(v):
        return max(3, int((v / mx_hist) * bar_area))
    def bh_cur(v):
        if not v or not mx_hist:
            return 3
        ratio = v / mx_hist
        return min(int(ratio * bar_area), bar_area)
    parts = []
    for i, v in enumerate(hist_vols):
        x  = pad + i*(bw+gap)
        h2 = bh_hist(v)
        y  = h - 14 - h2
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{h2}" '
            f'fill="#e8eaed" stroke="#c4c9d4" stroke-width="0.5" rx="2"/>'
            f'<text x="{x+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="#9ca3af">{dates[i].split(" ")[0] if i < len(dates) else i+1}</text>'
        )
    sep = pad + n*(bw+gap) + 2
    parts.append(
        f'<line x1="{sep}" x2="{sep}" y1="{pad}" y2="{h-14}" '
        f'stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>'
    )
    cx   = sep + 4
    ch2  = bh_cur(cur_vol) if cur_vol else 3
    cy   = h - 14 - ch2
    ratio = round(cur_vol / median_vol, 2) if median_vol and median_vol > 0 else 0
    cc   = "#7c3aed" if ratio > 2.0 else "#2563eb"
    parts.append(
        f'<rect x="{cx}" y="{cy}" width="{bw}" height="{ch2}" '
        f'fill="{cc}25" stroke="{cc}" stroke-width="1.5" rx="2"/>'
        f'<text x="{cx+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="{cc}">{cur_date.split(" ")[0] if cur_date else "cur"}</text>'
    )
    if median_vol and median_vol > 0:
        med_y  = round(h - 14 - bh_hist(median_vol), 1)
        med_x2 = pad + n*(bw+gap) - gap
        parts.append(
            f'<line x1="{pad}" x2="{med_x2}" y1="{med_y}" y2="{med_y}" '
            f'stroke="#f59e0b" stroke-width="1.2" stroke-dasharray="3,2"/>'
        )
    total_w = cx + bw + pad
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def status_badge(status):
    cls = {"BLASTING": "sw-badge-B", "READY": "sw-badge-R", "WATCH": "sw-badge-W"}.get(status, "")
    ico = {"BLASTING": "🔥", "READY": "✅", "WATCH": "👁"}.get(status, "")
    if not cls:
        return "—"
    return f'<span class="{cls}">{ico} {status}</span>'

def border_color(status):
    return {"BLASTING": "#7c3aed", "READY": "#00a854", "WATCH": "#f59e0b"}.get(status, "#e0e3e8")

# CONTROL BAR
stocks       = load_cached()
total_stocks = len(stocks)

c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 0.8, 0.9, 3.5])

with c1:
    lbl = "✕ Manage" if st.session_state.sw_show_manage else "⚙ Manage Stocks"
    if st.button(lbl, use_container_width=True):
        st.session_state.sw_show_manage = not st.session_state.sw_show_manage
        st.rerun()

with c2:
    if st.button("🔄 Sync 5D", use_container_width=True,
                 disabled=total_stocks == 0, type="primary",
                 help="Fetch last 5 trading days from yfinance — only fetches missing days"):
        with st.spinner(f"Syncing {total_stocks} stocks..."):
            res = sync_5d_history()
            st.session_state.sw_last_sync = time.time()
        results, errors = load_from_db()
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        if res["synced"] > 0:
            st.success(f"✅ Synced {res['synced']} rows — {res['skipped']} symbols already up to date")
        else:
            st.info(f"✅ All {res['skipped']} symbols already up to date")
        if res["errors"]:
            st.warning(f"⚠ {len(res['errors'])} errors")
        st.rerun()

with c3:
    from swing_core import can_refresh, refresh_label
    
    if st.button(refresh_label(), use_container_width=True,
                 disabled=False,
                 help="Weekday: fetch today's price. Weekend: fetch last trading day"):
        with st.spinner("Refreshing live prices..."):
            res = refresh_live()
            st.session_state.sw_last_refresh = time.time()
        results, errors = load_from_db()
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        st.rerun()

with c4:
    if st.button("🗑 Clear", use_container_width=True,
                 disabled=len(st.session_state.sw_results) == 0):
        st.session_state.sw_results = []
        st.session_state.sw_errors  = []
        st.session_state.sw_loaded  = False
        st.rerun()

with c5:
    blasting = sum(1 for r in st.session_state.sw_results if r.get("status") == "BLASTING")
    ready    = sum(1 for r in st.session_state.sw_results if r.get("status") == "READY")
    watch    = sum(1 for r in st.session_state.sw_results if r.get("status") == "WATCH")
    sync_t   = ""
    ref_t    = ""
    pop_t    = ""
    if st.session_state.sw_last_sync:
        sync_t = f"&nbsp;&nbsp;🔄 Sync: {datetime.fromtimestamp(st.session_state.sw_last_sync).strftime('%I:%M %p')}"
    if st.session_state.sw_last_refresh:
        ref_t  = f"&nbsp;&nbsp;📡 Live: {datetime.fromtimestamp(st.session_state.sw_last_refresh).strftime('%I:%M %p')}"
    if st.session_state.sw_last_populate:
        pop_t  = f"&nbsp;&nbsp;📊 History: {datetime.fromtimestamp(st.session_state.sw_last_populate).strftime('%I:%M %p')}"
    st.markdown(
        f"<div style='display:flex;gap:16px;align-items:center;padding-top:4px;flex-wrap:wrap;'>"
        f"<span style='font-size:12px;color:#7c3aed;font-weight:700;'>🔥 {blasting}</span>"
        f"<span style='font-size:12px;color:#00a854;font-weight:700;'>✅ {ready}</span>"
        f"<span style='font-size:12px;color:#d97706;font-weight:700;'>👁 {watch}</span>"
        f"<span style='font-size:11px;color:#9ca3af;'>📋 {total_stocks} stocks"
        f"{'&nbsp;&nbsp;🟢 Live' if is_market_open() else '&nbsp;&nbsp;🔴 Closed'}"
        f"{sync_t}{ref_t}{pop_t}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    pop_col, _ = st.columns([1.2, 2.3])
    with pop_col:
        if st.button("📊 Populate History", use_container_width=True,
                     help="One-time: fetch & save last 10 days status snapshot to swing_status_history"):
            with st.spinner(f"Populating history for {total_stocks} stocks — this may take ~2 min..."):
                res = populate_status_history()
                st.session_state.sw_last_populate = time.time()
            if res["saved"] > 0:
                st.success(f"✅ Saved {res['saved']} history rows")
            if res["errors"]:
                st.warning(f"⚠ {len(res['errors'])} errors")
            st.rerun()

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# MANAGE PANEL
if st.session_state.sw_show_manage:
    st.markdown("### ⚙ Manage Swing Stocks")
    t1, t2, t3 = st.tabs(["➕ Add Single", "📋 Bulk Add", "📝 Stock List"])

    with t1:
        with st.form("add_form", clear_on_submit=True):
            a1, a2 = st.columns([1, 2])
            with a1: sym  = st.text_input("NSE Symbol *", placeholder="HEROMOTOCO")
            with a2: url  = st.text_input("Screener URL (optional)")
            a3, a4 = st.columns([1, 2])
            with a3: bd   = st.date_input("Breakout Date (optional)", value=None)
            with a4: note = st.text_input("Notes (optional)")
            if st.form_submit_button("➕ Add", type="primary"):
                if not sym.strip():
                    st.error("Symbol required.")
                else:
                    try:
                        add_swing_stock(sym.strip(), url.strip(), bd, note.strip())
                        refresh_cache()
                        st.success(f"✅ {sym.upper()} added.")
                        st.rerun()
                    except ValueError as e: st.warning(str(e))
                    except Exception as e:  st.error(str(e))

    with t2:
        txt = st.text_area("Symbols — one per line or comma separated", height=150,
                           placeholder="HEROMOTOCO\nTITAN\nHDFCBANK")
        if st.button("📋 Add All", type="primary"):
            raw  = txt.replace(",", "\n").splitlines()
            syms = [s.strip().upper() for s in raw if s.strip()]
            if syms:
                with st.spinner(f"Adding {len(syms)} stocks..."):
                    res = bulk_add_swing_stocks(syms)
                refresh_cache()
                if res["added"]:   st.success(f"✅ Added: {', '.join(res['added'])}")
                if res["skipped"]: st.info(f"⏭ Already exists: {', '.join(res['skipped'])}")
                if res["errors"]:  st.error(f"❌ Failed: {', '.join(res['errors'])}")
                st.rerun()

    with t3:
        curr = refresh_cache()
        if not curr:
            st.info("No stocks yet.")
        else:
            st.markdown(f"**{len(curr)} stocks in swing list**")
            for s in curr:
                r1, r2, r3, r4, r5 = st.columns([2, 2, 3, 2, 1])
                with r1: st.markdown(f"**`{s['symbol']}`**")
                with r2:
                    st.markdown(
                        f"<span style='font-size:11px;color:#9ca3af;'>{s.get('breakout_date') or '—'}</span>",
                        unsafe_allow_html=True)
                with r3:
                    st.markdown(
                        f"<span style='font-size:11px;color:#9ca3af;'>{(s.get('notes') or '')[:40]}</span>",
                        unsafe_allow_html=True)
                with r4:
                    new_bd = st.date_input("", value=None, key=f"ebd_{s['id']}",
                                           label_visibility="collapsed")
                    if new_bd:
                        try:
                            update_swing_stock(s["id"], {"breakout_date": str(new_bd)})
                            refresh_cache()
                            st.rerun()
                        except Exception as e: st.error(str(e))
                with r5:
                    if st.button("✕", key=f"del_{s['id']}"):
                        try:
                            delete_swing_stock(s["id"])
                            refresh_cache()
                            st.rerun()
                        except Exception as e: st.error(str(e))

    st.markdown("---")

# FILTER PILLS
all_results = st.session_state.sw_results

if all_results:
    b_n  = sum(1 for r in all_results if r.get("status") == "BLASTING")
    r_n  = sum(1 for r in all_results if r.get("status") == "READY")
    w_n  = sum(1 for r in all_results if r.get("status") == "WATCH")
    a_n  = len(all_results)

  status_opts = [
        f"ALL ({a_n})",
        f"🔥 BLASTING ({b_n})",
        f"✅ READY ({r_n})",
        f"👁 WATCH ({w_n})",
        "📊 Intraday Watch"
    ]

    ex_n = sum(1 for r in all_results if "Explosive" in r.get("vol_signal", ""))
    st_n = sum(1 for r in all_results if "Strong" in r.get("vol_signal", ""))
    bu_n = sum(1 for r in all_results if "Build" in r.get("vol_signal", ""))
    wk_n = sum(1 for r in all_results if "Weak" in r.get("vol_signal", ""))

    vol_opts = [
        "All signals",
        f"🔥 Explosive ({ex_n})",
        f"🟢 Strong ({st_n})",
        f"🟡 Build ({bu_n})",
        f"🔴 Weak ({wk_n})"
    ]

    # Side-by-side filters
    col_status, col_vol = st.columns(2)

    with col_status:
        sel_status = st.selectbox(
            "Status",
            status_opts,
            index=0,
            label_visibility="collapsed",
            key="status_filter"
        )

    with col_vol:
        sel_vol = st.selectbox(
            "Vol signal",
            vol_opts,
            index=0,
            label_visibility="collapsed",
            key="vol_filter"
        )

else:
    view = []

# EMPTY STATE
if not all_results:
    if total_stocks == 0:
        st.info("👆 Add stocks via Manage Stocks, then click Sync 5D.")
    else:
        st.markdown(f"""
        <div style='text-align:center;padding:52px 0;color:#9ca3af;'>
            <div style='font-size:38px;margin-bottom:12px;'>📈</div>
            <div style='font-size:15px;font-weight:600;color:#0f1117;'>{total_stocks} stocks in watchlist</div>
            <div style='font-size:12px;margin-top:6px;'>Click 🔄 Sync 5D to populate price data</div>
        </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# INTRADAY WATCH SECTION
# ─────────────────────────────────────────────────────────────────────────────
if sel_status and "Intraday Watch" in sel_status:
    import streamlit.components.v1 as components

    # ── Load intraday data ──
    if "sw_intraday" not in st.session_state:
        with st.spinner("Loading intraday watch data..."):
            st.session_state.sw_intraday = get_intraday_watch()

    iw_data = st.session_state.sw_intraday

    if not iw_data:
        st.info("No data in swing_status_history. Click 📊 Populate History first.")
        st.stop()

    # ── Filter pills ──
    iw_all_n   = len(iw_data)
    iw_4w_n    = sum(1 for r in iw_data if r["consec_weak"] >= 4)
    iw_near_n  = sum(1 for r in iw_data if r["pct_vs_high"] >= -3.0)
    iw_vol50_n = sum(1 for r in iw_data if r["min_vol"] >= 50000)

    iw_filter_opts = [
        f"All ({iw_all_n})",
        f"4+ Weak Days ({iw_4w_n})",
        f"Near High <3% ({iw_near_n})",
        f"Vol > 50K ({iw_vol50_n})",
    ]
    sel_iw = st.selectbox("Intraday Filter", iw_filter_opts,
                          index=0, label_visibility="collapsed", key="iw_filter")

    if   sel_iw and "4+ Weak"   in sel_iw:
        iw_view = [r for r in iw_data if r["consec_weak"] >= 4]
    elif sel_iw and "Near High" in sel_iw:
        iw_view = [r for r in iw_data if r["pct_vs_high"] >= -3.0]
    elif sel_iw and "Vol > 50K" in sel_iw:
        iw_view = [r for r in iw_data if r["min_vol"] >= 50000]
    else:
        iw_view = iw_data

    if iw_view:
        sample_days  = iw_view[0]["days"]
        date_labels  = [d["date_label"] for d in sample_days[-6:]]
        n_days       = len(date_labels)

        # All columns are filterable (0-based within date_labels)
        FILTER_COL_INDICES = set(range(n_days))

        def _vol_emoji(vol_signal):
            if "Explosive" in vol_signal: return "🔥"
            if "Strong"    in vol_signal: return "🟢"
            if "Build"     in vol_signal: return "🟡"
            return "🔴"

        def _cat_label(status):
            return {"BLASTING": "BLASTING", "READY": "READY", "WATCH": "WATCH"}.get(status, "—")

        def _sig_key(vol_signal):
            if "Explosive" in vol_signal: return "Explosive"
            if "Strong"    in vol_signal: return "Strong"
            if "Build"     in vol_signal: return "Build"
            if "Weak"      in vol_signal: return "Weak"
            return "None"

        # Build LIVE header date inline (e.g. "11JUN · LIVE")
        live_date_for_header = "LIVE"
        if iw_view:
            ld = iw_view[0].get("live_date", "")
            try:
                from datetime import datetime as _dt
                live_date_for_header = _dt.strptime(ld, "%Y-%m-%d").strftime("%-d%b").upper() + " · LIVE"
            except Exception:
                live_date_for_header = "LIVE"

        live_col_id = "col-live"

        # ── Build dropdown menu HTML (reusable) ──
        def _dropdown_html(col_id):
            return f'''
    <div id="{col_id}-dd" class="dd-menu">
      <div class="dd-section">Vol Signal</div>
      <label class="dd-opt"><input type="checkbox" value="Explosive" data-col="{col_id}"> 🔥 Explosive</label>
      <label class="dd-opt"><input type="checkbox" value="Strong"    data-col="{col_id}"> 🟢 Strong</label>
      <label class="dd-opt"><input type="checkbox" value="Build"     data-col="{col_id}"> 🟡 Build</label>
      <label class="dd-opt"><input type="checkbox" value="Weak"      data-col="{col_id}"> 🔴 Weak</label>
      <div class="dd-divider"></div>
      <div class="dd-section">Status</div>
      <label class="dd-opt"><input type="checkbox" value="BLASTING" data-col="{col_id}"> 🔥 BLASTING</label>
      <label class="dd-opt"><input type="checkbox" value="READY"    data-col="{col_id}"> ✅ READY</label>
      <label class="dd-opt"><input type="checkbox" value="WATCH"    data-col="{col_id}"> 👁 WATCH</label>
      <div class="dd-divider"></div>
      <div class="dd-clear"><button type="button" onclick="iwClearCol('{col_id}')">Clear</button></div>
    </div>
'''

        # ── Header HTML ──
        header_html = '<th class="stock-col">STOCK</th>'
        for i, lbl in enumerate(date_labels):
            is_filterable = i in FILTER_COL_INDICES
            col_id = f"col-{i}"
            if is_filterable:
                header_html += f'''
  <th class="date-col filterable" data-colid="{col_id}">
    <div class="date-trigger" onclick="iwToggleDropdown('{col_id}')">
      <span class="date-text">{lbl}</span>
      <span class="dd-arrow">▼</span>
    </div>
    <div class="dd-dot" id="{col_id}-dot"></div>
    {_dropdown_html(col_id)}
  </th>
'''
            else:
                header_html += f'<th class="date-col">{lbl}</th>'

        # LIVE header — filterable
        header_html += f'''
  <th class="date-col filterable" data-colid="{live_col_id}">
    <div class="date-trigger" onclick="iwToggleDropdown('{live_col_id}')">
      <span class="date-text">{live_date_for_header}</span>
      <span class="dd-arrow">▼</span>
    </div>
    <div class="dd-dot" id="{live_col_id}-dot"></div>
    {_dropdown_html(live_col_id)}
  </th>
'''

        # ── Data rows ──
        rows_html = ""
        for r in iw_view:
            sym     = r["symbol"]
            prc     = r["live_price"]
            pct     = r["pct_vs_high"]
            pct_col = "#16a34a" if pct >= 0 else "#dc2626"
            pct_avg_iw = r.get("pct_vs_avg_iw", 0)
            dir_arrow_iw = r.get("direction_arrow_iw", "→")
            dir_color_iw = r.get("direction_color_iw", "#6b7280")
            days    = r["days"][-6:]

          # Data attributes for filterable columns
            d_attrs = ""
            # Map all columns (0 to n_days-1) to their corresponding days
            for col_idx in range(n_days):
                day_idx = col_idx if col_idx < len(days) else -1
                col_id_attr = f"col-{col_idx}"
                if 0 <= day_idx < len(days):
                    sig = _sig_key(days[day_idx]["vol_signal"])
                    sta = days[day_idx]["status"]
                else:
                    sig = "None"
                    sta = "NONE"
                d_attrs += f' data-{col_id_attr}-sig="{sig}" data-{col_id_attr}-sta="{sta}"'
            
            # Live attrs
            live_sig = _sig_key(r.get("live_signal", ""))
            live_sta = r.get("live_status", "WATCH")
            d_attrs += f' data-{live_col_id}-sig="{live_sig}" data-{live_col_id}-sta="{live_sta}"'

            
            rows_html += (
                f'<tr class="iw-row"{d_attrs}>'
                f'<td class="stock-cell">'
                f'<div class="sym">{sym}</div>'
                f'<div class="prc">₹{prc:,.0f} <span style="color:{dir_color_iw}; font-size:14px;">{dir_arrow_iw}</span> <span style="color:{dir_color_iw};">{pct_avg_iw:+.1f}%</span></div>'
                f'<div style="font-size:10px; color:#6b7280; margin-top:2px;">5D Avg: ₹{r.get("avg_5d_price_iw", 0):,.0f}</div>'
                f'</td>'
            )

            for i in range(n_days):
                if i < len(days):
                    d     = days[i]
                    emoji = _vol_emoji(d["vol_signal"])
                    cat   = _cat_label(d["status"])
                    ratio = f"{d['vol_ratio']:.1f}x"
                    rows_html += (
                        f'<td class="data-cell">'
                        f'<div class="cell-stack">'
                        f'<span class="cell-emoji">{emoji}</span>'
                        f'<span class="cell-cat">{cat}</span>'
                        f'<span class="cell-ratio">{ratio}</span>'
                        f'</div></td>'
                    )
                else:
                    rows_html += '<td class="data-cell empty">—</td>'

            # LIVE cell
            live_emoji = _vol_emoji(r["live_signal"])
            live_cat   = _cat_label(r.get("live_status", "WATCH"))
            live_ratio = f"{r.get('live_vol_ratio', 0):.1f}x"
            rows_html += (
                f'<td class="data-cell live-cell">'
                f'<div class="cell-stack">'
                f'<span class="cell-emoji">{live_emoji}</span>'
                f'<span class="cell-cat">{live_cat}</span>'
                f'<span class="cell-ratio">{live_ratio}</span>'
                f'</div></td>'
                f'</tr>'
            )

        # ── Build full HTML document for iframe ──
        total_count = len(iw_view)
        full_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: transparent;
  color: #111;
}}
.count-bar {{
  font-size: 11px;
  color: #6b7280;
  padding: 4px 0 8px;
}}
.table-wrap {{
  background: white;
  border: 0.5px solid #e5e7eb;
  border-radius: 8px;
  overflow: visible;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}}
thead tr {{
  background: #f0f0f0;
  border-bottom: 1px solid #e5e7eb;
}}
th {{
  font-size: 12px;
  font-weight: 600;
  color: #000;
  padding: 12px 8px;
  text-align: center;
  position: relative;
}}
th.stock-col {{
  text-align: left;
  padding: 12px 16px;
  width: 140px;
}}
th.date-col {{
  text-transform: uppercase;
}}
.date-trigger {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background 0.15s;
}}
.date-trigger:hover {{
  background: #e5e7eb;
}}
th.filterable .date-text {{
  font-weight: 600;
}}
.dd-arrow {{
  font-size: 13px;
  color: #6b7280;
  margin-left: 2px;
}}
.dd-dot {{
  display: none;
  width: 8px;
  height: 8px;
  background: #7c3aed;
  border-radius: 50%;
  position: absolute;
  top: 6px;
  right: 6px;
}}
.dd-dot.active {{ display: block; }}
.dd-menu {{
  display: none;
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  z-index: 9999;
  min-width: 180px;
  padding: 8px 0;
  text-align: left;
  margin-top: 4px;
}}
.dd-menu.open {{ display: block; }}
.dd-section {{
  padding: 6px 14px;
  font-size: 10px;
  font-weight: 700;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.dd-opt {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px;
  cursor: pointer;
  font-size: 13px;
  color: #111;
  font-weight: 400;
}}
.dd-opt:hover {{ background: #f9fafb; }}
.dd-opt input[type="checkbox"] {{
  accent-color: #7c3aed;
  cursor: pointer;
  width: 14px;
  height: 14px;
  margin: 0;
}}
.dd-divider {{
  height: 1px;
  background: #f3f4f6;
  margin: 6px 0;
}}
.dd-clear {{
  display: flex;
  justify-content: center;
  padding: 4px 14px;
}}
.dd-clear button {{
  font-size: 11px;
  color: #6b7280;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 4px 8px;
}}
.dd-clear button:hover {{ color: #111; }}

tbody tr {{
  background: white;
  border-bottom: 0.5px solid #e5e7eb;
}}
td.stock-cell {{
  padding: 14px 16px;
  text-align: left;
}}
.sym {{ font-size: 14px; font-weight: 700; color: #000; }}
.prc {{ font-size: 13px; color: #000; margin-top: 3px; }}
.pct {{ font-size: 12px; margin-top: 2px; }}
td.data-cell {{
  padding: 10px 4px;
  text-align: center;
  vertical-align: middle;
}}
td.data-cell.empty {{ color: #9ca3af; }}
.cell-stack {{
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}}
.cell-emoji {{ font-size: 22px; line-height: 1; }}
.cell-cat   {{ font-size: 11px; font-weight: 600; color: #000; }}
.cell-ratio {{ font-size: 11px; color: #000; }}
</style>
</head>
<body>
<div class="count-bar" id="count-bar">Showing {total_count} stocks</div>
<div class="table-wrap">
<table id="iw-table">
<thead>
<tr>{header_html}</tr>
</thead>
<tbody id="iw-body">
{rows_html}
</tbody>
</table>
</div>

<script>
var TOTAL = {total_count};

function iwToggleDropdown(colId) {{
  var dd = document.getElementById(colId + '-dd');
  if (!dd) return;
  // close others
  document.querySelectorAll('.dd-menu').forEach(function(el) {{
    if (el.id !== colId + '-dd') el.classList.remove('open');
  }});
  dd.classList.toggle('open');
}}

function iwClearCol(colId) {{
  document.querySelectorAll('input[data-col="' + colId + '"]').forEach(function(cb) {{
    cb.checked = false;
  }});
  var dd = document.getElementById(colId + '-dd');
  if (dd) dd.classList.remove('open');
  iwApplyFilter();
}}

function iwApplyFilter() {{
  var colFilters = {{}};
  document.querySelectorAll('input[data-col]:checked').forEach(function(cb) {{
    var col = cb.getAttribute('data-col');
    if (!colFilters[col]) colFilters[col] = {{ sigs: [], stas: [] }};
    var val = cb.value;
    if (['Explosive','Strong','Build','Weak'].indexOf(val) >= 0) {{
      colFilters[col].sigs.push(val);
    }} else {{
      colFilters[col].stas.push(val);
    }}
  }});

  // dot indicators
  document.querySelectorAll('.dd-dot').forEach(function(dot) {{
    var colId = dot.id.replace('-dot','');
    if (colFilters[colId]) dot.classList.add('active');
    else                   dot.classList.remove('active');
  }});

  var rows = document.querySelectorAll('#iw-body .iw-row');
  var visible = 0;
  rows.forEach(function(row) {{
    var show = true;
    Object.keys(colFilters).forEach(function(col) {{
      var f = colFilters[col];
      var rowSig = row.getAttribute('data-' + col + '-sig') || '';
      var rowSta = row.getAttribute('data-' + col + '-sta') || '';
      if (f.sigs.length > 0 && f.sigs.indexOf(rowSig) < 0) show = false;
      if (f.stas.length > 0 && f.stas.indexOf(rowSta) < 0) show = false;
    }});
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});

  var countEl = document.getElementById('count-bar');
  var anyActive = Object.keys(colFilters).length > 0;
  if (countEl) {{
    countEl.textContent = anyActive
      ? ('Showing ' + visible + ' of ' + TOTAL + ' stocks')
      : ('Showing ' + TOTAL + ' stocks');
  }}
}}

// Persist filters to localStorage
function iwSaveFilters() {{
  var state = {{}};
  document.querySelectorAll('input[data-col]:checked').forEach(function(cb) {{
    var col = cb.getAttribute('data-col');
    if (!state[col]) state[col] = [];
    state[col].push(cb.value);
  }});
  try {{
    localStorage.setItem('iw_filters', JSON.stringify(state));
  }} catch(e) {{
    console.warn('localStorage save failed:', e);
  }}
}}

// Restore filters from localStorage on load
function iwRestoreFilters() {{
  try {{
    var saved = localStorage.getItem('iw_filters');
    if (!saved) return;
    var state = JSON.parse(saved);
    Object.keys(state).forEach(function(col) {{
      state[col].forEach(function(val) {{
        var cb = document.querySelector('input[data-col="' + col + '"][value="' + val + '"]');
        if (cb) cb.checked = true;
      }});
    }});
  }} catch(e) {{
    console.warn('localStorage restore failed:', e);
  }}
}}

// Attach change handlers
document.querySelectorAll('input[data-col]').forEach(function(cb) {{
  cb.addEventListener('change', function() {{
    iwApplyFilter();
    iwSaveFilters();
  }});
}});

// Close dropdown on outside click
document.addEventListener('click', function(e) {{
  if (!e.target.closest('.dd-menu') && !e.target.closest('.date-trigger')) {{
    document.querySelectorAll('.dd-menu').forEach(function(el) {{
      el.classList.remove('open');
    }});
  }}
}});

// Restore on load
window.addEventListener('load', function() {{
  iwRestoreFilters();
  iwApplyFilter();
}});
</script>
</body>
</html>
'''

        # ── Render via st.html (proper iframe) ──
        # Height: header (~50) + rows (~85 each) + padding
        est_height = 80 + len(iw_view) * 85
        est_height = min(max(est_height, 300), 5000)
        st.html(full_html)  # Note: st.html doesn't support height param

    st.stop()

# RESULTS TABLE
COL = [1.4, 2.0, 2.1, 1.2, 1.3, 1.8, 1.0, 0.9]

header = st.columns(COL)
labels = ["Stock", "Price Candles — 5D | Today", "Volume — 5D Hist | Current",
          "LTP", "Today H / L", "Vol Signal", "Status", "Screener"]
for col, lbl in zip(header, labels):
    col.markdown(
        f"<div style='font-size:10px;font-weight:600;color:#7a8394;"
        f"text-transform:uppercase;letter-spacing:0.07em;"
        f"padding:8px 4px;border-bottom:2px solid #e0e3e8;'>{lbl}</div>",
        unsafe_allow_html=True,
    )

for r in view:
    sym    = r["symbol"]
    status = r.get("status", "")
    bc     = border_color(status)

    p_svg = price_svg(
        r.get("hist_opens",  []), r.get("hist_highs", []),
        r.get("hist_lows",   []), r.get("hist_closes", []),
        r.get("hist_dates",  []),
        cur_open  = r.get("current_open"),
        cur_high  = r.get("current_high"),
        cur_low   = r.get("current_low"),
        cur_close = r.get("current_price"),
        cur_date  = r.get("current_date"),
    )
    v_svg = volume_svg(
        r.get("hist_volumes", []),
        r.get("current_vol", 0),
        r.get("median_vol", 1),
        dates=r.get("hist_dates", []),
        cur_date=r.get("current_date"),
    )

    ltp     = r.get("current_price", 0)
    pct     = r.get("pct_vs_high", 0)
    pct_col = "#00a854" if pct >= 0 else "#e53935"
    pct_avg = r.get("pct_vs_avg", 0)
    dir_arrow = r.get("direction_arrow", "→")
    dir_color = r.get("direction_color", "#7a8394")
    h_val   = r.get("current_high", 0)
    l_val   = r.get("current_low", 0)
    vsig    = r.get("vol_signal", "—")
    cur_v   = fmt_vol(r.get("current_vol"))
    med_v   = fmt_vol(r.get("median_vol"))
    bd      = r.get("breakout_date") or "—"
    s_url   = r.get("screener_url", f"https://www.screener.in/company/{sym}/")

    st.markdown(
        f"<div style='border-left:3px solid {bc};margin-bottom:0;"
        f"border-bottom:1px solid #f0f2f5;'></div>",
        unsafe_allow_html=True,
    )

    row = st.columns(COL)

    row[0].markdown(
        f"<div style='padding:8px 4px;'>"
        f"<div class='sw-sym'>{sym}</div>"
        f"<div class='sw-bd'>{bd}</div></div>",
        unsafe_allow_html=True,
    )
    row[1].markdown(f"<div style='padding:4px 0;'>{p_svg}</div>", unsafe_allow_html=True)
    row[2].markdown(
        f"<div style='padding:4px 0;'>{v_svg}"
        f"<div class='sw-med'>— median {med_v}</div></div>",
        unsafe_allow_html=True,
    )
    row[3].markdown(
        f"<div style='padding:8px 4px;'>"
        f"<div class='sw-ltp'>₹{ltp:,.2f} <span style='color:{dir_color}; font-size:16px;'>{dir_arrow}</span> <span style='color:{dir_color};'>{pct_avg:+.1f}%</span></div></div>",
        unsafe_allow_html=True,
    )
    row[4].markdown(
        f"<div style='padding:8px 4px;'>"
        f"<div class='sw-hl' style='color:#00a854;'>H: ₹{h_val:,.2f}</div>"
        f"<div class='sw-hl' style='color:#e53935;'>L: ₹{l_val:,.2f}</div></div>",
        unsafe_allow_html=True,
    )
    row[5].markdown(
        f"<div style='padding:8px 4px;'>"
        f"<div class='sw-vsig'>{vsig}</div>"
        f"<div class='sw-vsub'>{cur_v} / med {med_v}</div></div>",
        unsafe_allow_html=True,
    )
    row[6].markdown(
        f"<div style='padding:8px 4px;'>{status_badge(status)}</div>",
        unsafe_allow_html=True,
    )
    row[7].markdown(
        f"<div style='padding:8px 4px;'>"
        f"<a href='{s_url}' target='_blank' class='sw-link'>Screener ↗</a></div>",
        unsafe_allow_html=True,
    )

# Push to watchlist
ready_blast = [r for r in view if r.get("status") in ("BLASTING", "READY")]
if ready_blast and WATCHLIST_PUSH:
    try:
        wl_names = get_user_watchlist_names() if st.session_state.get("user_id") else ["Today", "Yesterday", "New"]
    except Exception:
        wl_names = ["Today", "Yesterday", "New"]

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("**Push to Watchlist**")
    for r in ready_blast:
        sym = r["symbol"]
        p1, p2, p3 = st.columns([2, 2, 1])
        with p1:
            st.markdown(f"`{sym}` {status_badge(r.get('status', ''))}", unsafe_allow_html=True)
        with p2:
            chosen = st.selectbox("WL", wl_names, key=f"wl_{sym}", label_visibility="collapsed")
        with p3:
            if st.button("➕", key=f"wladd_{sym}", use_container_width=True):
                try:
                    add_to_watchlist(chosen, {
                        "symbol":    sym,
                        "status":    "BUY",
                        "lastPrice": r.get("current_price", 0),
                        "entry":     r.get("current_price", 0),
                        "sl":        round(r.get("current_low", 0) * 0.99, 2),
                        "target1":   round(r.get("current_price", 0) * 1.05, 2),
                        "target2":   round(r.get("current_price", 0) * 1.10, 2),
                        "note":      f"Swing {r.get('status', '')} — {r.get('vol_ratio', 0)}x vol",
                    })
                    st.success(f"✅ {sym} → {chosen}")
                except Exception as e:
                    st.error(str(e))

if st.session_state.sw_errors:
    with st.expander(f"⚠ {len(st.session_state.sw_errors)} errors"):
        for e in st.session_state.sw_errors:
            st.markdown(f"`{e['symbol']}` — {e['error']}")
            
