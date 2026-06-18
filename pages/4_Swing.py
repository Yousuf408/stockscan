# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — pages/4_Swing.py  v5.1 (AUTO-REFRESH REMOVED)
#  v5.1: Intraday Watch now uses price_svg() with real OHLC (open,high,low,close)
#        instead of _price_svg_iw() which only used close — fixes wrong candle colors
#  v5.0: Accumulation Breakout added as sub-tab inside Intraday Watch HTML
#        Same table style: STOCK▼ | PRICE CANDLES | VOLUME RATIO | dates... | BREAKOUT TYPE▼
#
#  MODIFIED: Removed auto-refresh fragments (_auto_refresh_every_5min, _refresh_status_bar)
#            Manual buttons still work: Sync 5D, Refresh Live, Populate History
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import os, sys, time
from datetime import datetime, date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from swing_core import (
    load_swing_stocks, add_swing_stock, update_swing_stock,
    delete_swing_stock, bulk_add_swing_stocks,
    load_from_db, sync_5d_history, refresh_live,
    populate_status_history,
    get_intraday_watch,
    fmt_vol, is_market_open,
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
.sw-sym { font-family:'JetBrains Mono',monospace; font-size:13px; font-weight:700; color:#0f1117; }
.sw-bd  { font-size:10px; color:#9ca3af; margin-top:3px; }
.sw-ltp { font-family:'JetBrains Mono',monospace; font-size:14px; font-weight:700; color:#0f1117; }
.sw-pct { font-size:10px; font-family:monospace; margin-top:3px; }
.sw-hl  { font-family:'JetBrains Mono',monospace; font-size:11px; line-height:1.9; }
.sw-vsig{ font-size:12px; font-weight:600; }
.sw-vsub{ font-size:10px; color:#9ca3af; font-family:'JetBrains Mono',monospace; margin-top:3px; }
.sw-med { font-size:9px; color:#f59e0b; margin-top:3px; }
.sw-badge-B { background:#ede9fe; color:#3C3489; border:1px solid #7c3aed40; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-badge-R { background:#f0faf5; color:#0F6E56; border:1px solid #1D9E7540; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-badge-W { background:#fffbeb; color:#854F0B; border:1px solid #f59e0b40; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-link { font-size:12px; color:#2563eb; text-decoration:none; font-weight:500; }
.sw-link:hover { text-decoration:underline; }
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
    ("sw_sel_status",        None),
    ("sw_sel_vol",           None),
    ("sw_sel_iw",            None),
    ("sw_db_updated",        False),
    ("sw_fetch_start_time",  None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

def load_cached():
    print("[DEBUG] load_cached() called")
    if st.session_state.sw_stocks_cache is None:
        st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def refresh_cache():
    st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

if not st.session_state.sw_loaded:
    with st.spinner("Loading..."):
        results, errors = load_from_db()
    print("[DEBUG] load_from_db() returned")
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        st.session_state.sw_loaded  = True

# ══════════════════════════════════════════════════════════════════════════════
# SVG HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def price_svg(opens, highs, lows, closes, dates,
              cur_open=None, cur_high=None, cur_low=None, cur_close=None,
              cur_date=None, w=200, h=62):
    if not closes:
        return f'<svg width="{w}" height="{h}"><text x="6" y="30" font-size="10" fill="#9ca3af">No data</text></svg>'
    has_cur = all(v is not None for v in [cur_open, cur_high, cur_low, cur_close])
    n = len(closes); pad = 4; bw = 16; gap = 5
    all_p = [v for v in highs + lows if v and v > 0]
    if has_cur: all_p += [cur_high, cur_low]
    if not all_p: return f'<svg width="{w}" height="{h}"></svg>'
    mn, mx = min(all_p), max(all_p); rng = mx - mn or 1
    def sy(v): return round(pad + (h - pad*2 - 10) * (1 - (v - mn) / rng), 1)
    parts = []
    for i in range(n):
        x = pad + i*(bw+gap); cx = x + bw//2
        o, h2, l2, c = opens[i], highs[i], lows[i], closes[i]
        col = "#00a854" if c >= o else "#e53935"
        body_y = sy(max(o, c)); body_h = max(2, abs(sy(o) - sy(c)))
        parts.append(f'<line x1="{cx}" x2="{cx}" y1="{sy(h2)}" y2="{sy(l2)}" stroke="{col}" stroke-width="1.2"/>'
                     f'<rect x="{x}" y="{body_y}" width="{bw}" height="{body_h}" fill="{col}" rx="2"/>')
        lbl = dates[i].split(" ")[0] if i < len(dates) else str(i+1)
        parts.append(f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="#9ca3af">{lbl}</text>')
    if has_cur:
        sep_x = pad + n*(bw+gap) + 2
        parts.append(f'<line x1="{sep_x}" x2="{sep_x}" y1="{pad}" y2="{h-12}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')
        cx = sep_x + 5 + bw//2; tx = sep_x + 5; col = "#7c3aed"
        body_y = sy(max(cur_open, cur_close)); body_h = max(2, abs(sy(cur_open) - sy(cur_close)))
        lbl = str(cur_date).split(" ")[0] if cur_date else "today"
        parts.append(f'<line x1="{cx}" x2="{cx}" y1="{sy(cur_high)}" y2="{sy(cur_low)}" stroke="{col}" stroke-width="1.2"/>'
                     f'<rect x="{tx}" y="{body_y}" width="{bw}" height="{body_h}" fill="{col}30" stroke="{col}" stroke-width="1.5" rx="2"/>'
                     f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="{col}" font-weight="500">{lbl}</text>')
    total_w = (sep_x + 5 + bw + pad) if has_cur else (pad + n*(bw+gap))
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def volume_svg(hist_vols, cur_vol, median_vol, dates=None, cur_date=None, w=195, h=62):
    if dates is None: dates = []
    n = len(hist_vols); pad = 4; bw = 18; gap = 5; bar_area = h - pad - 14
    hist_clean = [v for v in hist_vols if v and v > 0]
    mx_hist = max(hist_clean) if hist_clean else 1
    def bh_hist(v): return max(3, int((v / mx_hist) * bar_area))
    def bh_cur(v):
        if not v or not mx_hist: return 3
        return min(int((v / mx_hist) * bar_area), bar_area)
    parts = []
    for i, v in enumerate(hist_vols):
        x = pad + i*(bw+gap); h2 = bh_hist(v); y = h - 14 - h2
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{h2}" fill="#e8eaed" stroke="#c4c9d4" stroke-width="0.5" rx="2"/>'
                     f'<text x="{x+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="#9ca3af">{dates[i].split(" ")[0] if i < len(dates) else i+1}</text>')
    sep = pad + n*(bw+gap) + 2
    parts.append(f'<line x1="{sep}" x2="{sep}" y1="{pad}" y2="{h-14}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')
    cx = sep + 4; ch2 = bh_cur(cur_vol) if cur_vol else 3; cy = h - 14 - ch2
    ratio = round(cur_vol / median_vol, 2) if median_vol and median_vol > 0 else 0
    cc = "#7c3aed" if ratio > 2.0 else "#2563eb"
    parts.append(f'<rect x="{cx}" y="{cy}" width="{bw}" height="{ch2}" fill="{cc}25" stroke="{cc}" stroke-width="1.5" rx="2"/>'
                 f'<text x="{cx+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="{cc}">{cur_date.split(" ")[0] if cur_date else "cur"}</text>')
    if median_vol and median_vol > 0:
        med_y = round(h - 14 - bh_hist(median_vol), 1)
        med_x2 = pad + n*(bw+gap) - gap
        parts.append(f'<line x1="{pad}" x2="{med_x2}" y1="{med_y}" y2="{med_y}" stroke="#f59e0b" stroke-width="1.2" stroke-dasharray="3,2"/>')
    total_w = cx + bw + pad
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def status_badge(status):
    cls = {"BLASTING":"sw-badge-B","READY":"sw-badge-R","WATCH":"sw-badge-W"}.get(status,"")
    ico = {"BLASTING":"🔥","READY":"✅","WATCH":"👁"}.get(status,"")
    if not cls: return "—"
    return f'<span class="{cls}">{ico} {status}</span>'

def border_color(status):
    return {"BLASTING":"#7c3aed","READY":"#00a854","WATCH":"#f59e0b"}.get(status,"#e0e3e8")

# ══════════════════════════════════════════════════════════════════════════════
# CONTROL BAR
# ══════════════════════════════════════════════════════════════════════════════

stocks       = load_cached()
total_stocks = len(stocks)

c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 0.8, 0.9, 3.5])

with c1:
    lbl = "✕ Manage" if st.session_state.sw_show_manage else "⚙ Manage Stocks"
    if st.button(lbl, use_container_width=True):
        st.session_state.sw_show_manage = not st.session_state.sw_show_manage
        st.rerun()

with c2:
    if st.button("🔄 Sync 5D", use_container_width=True, disabled=total_stocks==0, type="primary",
                 help="Fetch last 5 trading days from yfinance"):
        with st.spinner(f"Syncing {total_stocks} stocks..."):
            res = sync_5d_history()
            st.session_state.sw_last_sync = time.time()
        results, errors = load_from_db()
    print("[DEBUG] load_from_db() returned")
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        if res["synced"] > 0:
            st.success(f"✅ Synced {res['synced']} rows — {res['skipped']} already up to date")
        else:
            st.info(f"✅ All {res['skipped']} symbols already up to date")
        if res["errors"]: st.warning(f"⚠ {len(res['errors'])} errors")
        st.rerun()

with c3:
    from swing_core import can_refresh, refresh_label
    if st.button(refresh_label(), use_container_width=True, disabled=False,
                 help="Weekday: fetch today's price. Weekend: fetch last trading day"):
        with st.spinner("Refreshing live prices..."):
            res = refresh_live()
    print(f"[DEBUG] refresh_live() returned: {res}")
            st.session_state.sw_last_refresh = time.time()
        results, errors = load_from_db()
    print("[DEBUG] load_from_db() returned")
        st.session_state.sw_results = results
        st.session_state.sw_errors  = errors
        st.rerun()

with c4:
    if st.button("🗑 Clear", use_container_width=True, disabled=len(st.session_state.sw_results)==0):
        st.session_state.sw_results = []
        st.session_state.sw_errors  = []
        st.session_state.sw_loaded  = False
        st.rerun()

with c5:
    if st.button("📊 Populate History", use_container_width=True,
                 help="Fetch & save last 10 days status snapshot (now includes open,high,low)"):
        with st.spinner(f"Populating history for {total_stocks} stocks..."):
            res = populate_status_history()
            st.session_state.sw_last_populate = time.time()
        if res["saved"] > 0: st.success(f"✅ Saved {res['saved']} rows")
        if res["errors"]:    st.warning(f"⚠ {len(res['errors'])} errors")
        st.rerun()

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MANAGE PANEL
# ══════════════════════════════════════════════════════════════════════════════

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
                if not sym.strip(): st.error("Symbol required.")
                else:
                    try:
                        add_swing_stock(sym.strip(), url.strip(), bd, note.strip())
                        refresh_cache(); st.success(f"✅ {sym.upper()} added."); st.rerun()
                    except ValueError as e: st.warning(str(e))
                    except Exception as e:  st.error(str(e))
    print(f"[DEBUG] Exception: {str(e)}")
    with t2:
        txt = st.text_area("Symbols — one per line or comma separated", height=150,
                           placeholder="HEROMOTOCO\nTITAN\nHDFCBANK")
        if st.button("📋 Add All", type="primary"):
            raw  = txt.replace(",", "\n").splitlines()
            syms = [s.strip().upper() for s in raw if s.strip()]
            if syms:
                with st.spinner(f"Adding {len(syms)} stocks..."): res = bulk_add_swing_stocks(syms)
                refresh_cache()
                if res["added"]:   st.success(f"✅ Added: {', '.join(res['added'])}")
                if res["skipped"]: st.info(f"⏭ Already exists: {', '.join(res['skipped'])}")
                if res["errors"]:  st.error(f"❌ Failed: {', '.join(res['errors'])}")
                st.rerun()
    with t3:
        curr = refresh_cache()
        if not curr: st.info("No stocks yet.")
        else:
            st.markdown(f"**{len(curr)} stocks in swing list**")
            for s in curr:
                r1, r2, r3, r4, r5 = st.columns([2, 2, 3, 2, 1])
                with r1: st.markdown(f"**`{s['symbol']}`**")
                with r2: st.markdown(f"<span style='font-size:11px;color:#9ca3af;'>{s.get('breakout_date') or '—'}</span>", unsafe_allow_html=True)
                with r3: st.markdown(f"<span style='font-size:11px;color:#9ca3af;'>{(s.get('notes') or '')[:40]}</span>", unsafe_allow_html=True)
                with r4:
                    new_bd = st.date_input("", value=None, key=f"ebd_{s['id']}", label_visibility="collapsed")
                    if new_bd:
                        try: update_swing_stock(s["id"], {"breakout_date": str(new_bd)}); refresh_cache(); st.rerun()
                        except Exception as e: st.error(str(e))
    print(f"[DEBUG] Exception: {str(e)}")
                with r5:
                    if st.button("✕", key=f"del_{s['id']}"):
                        try: delete_swing_stock(s["id"]); refresh_cache(); st.rerun()
                        except Exception as e: st.error(str(e))
    print(f"[DEBUG] Exception: {str(e)}")
    st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STATUS + VOL FILTER BUTTONS
# ══════════════════════════════════════════════════════════════════════════════

all_results = st.session_state.sw_results

if all_results:
    b_n  = sum(1 for r in all_results if r.get("status") == "BLASTING")
    r_n  = sum(1 for r in all_results if r.get("status") == "READY")
    w_n  = sum(1 for r in all_results if r.get("status") == "WATCH")
    a_n  = len(all_results)
    ex_n = sum(1 for r in all_results if "Explosive" in r.get("vol_signal", ""))
    st_n = sum(1 for r in all_results if "Strong"    in r.get("vol_signal", ""))
    bu_n = sum(1 for r in all_results if "Build"     in r.get("vol_signal", ""))
    wk_n = sum(1 for r in all_results if "Weak"      in r.get("vol_signal", ""))

    status_opts = [
        f"ALL ({a_n})",
        f"🔥 BLASTING ({b_n})",
        f"✅ READY ({r_n})",
        f"👁 WATCH ({w_n})",
        "📊 Intraday Watch",
    ]
    if st.session_state.sw_sel_status is None:
        st.session_state.sw_sel_status = status_opts[0]

    st.markdown("**Status**")
    status_cols = st.columns(len(status_opts))
    for i, opt in enumerate(status_opts):
        with status_cols[i]:
            is_active = st.session_state.sw_sel_status == opt
            if st.button(opt, key=f"status_{i}", type="primary" if is_active else "secondary",
                         use_container_width=True):
                st.session_state.sw_sel_status = opt

    vol_opts = ["All signals", f"🔥 Explosive ({ex_n})", f"🟢 Strong ({st_n})",
                f"🟡 Build ({bu_n})", f"🔴 Weak ({wk_n})"]
    if st.session_state.sw_sel_vol is None:
        st.session_state.sw_sel_vol = vol_opts[0]

    st.markdown("**Vol Signal**")
    vol_cols = st.columns(len(vol_opts))
    for i, opt in enumerate(vol_opts):
        with vol_cols[i]:
            is_active = st.session_state.sw_sel_vol == opt
            if st.button(opt, key=f"vol_{i}", type="primary" if is_active else "secondary",
                         use_container_width=True):
                st.session_state.sw_sel_vol = opt

    sel_status = st.session_state.sw_sel_status
    sel_vol    = st.session_state.sw_sel_vol

    if sel_status and "BLASTING"   in sel_status: view = [r for r in all_results if r.get("status") == "BLASTING"]
    elif sel_status and "READY"    in sel_status: view = [r for r in all_results if r.get("status") == "READY"]
    elif sel_status and "WATCH"    in sel_status: view = [r for r in all_results if r.get("status") == "WATCH"]
    elif sel_status and "Intraday" in sel_status: view = []
    else:                                          view = all_results

    if sel_vol and "Explosive" in sel_vol: view = [r for r in view if "Explosive" in r.get("vol_signal","")]
    elif sel_vol and "Strong"  in sel_vol: view = [r for r in view if "Strong"    in r.get("vol_signal","")]
    elif sel_vol and "Build"   in sel_vol: view = [r for r in view if "Build"     in r.get("vol_signal","")]
    elif sel_vol and "Weak"    in sel_vol: view = [r for r in view if "Weak"      in r.get("vol_signal","")]

    st.markdown(
        f"<div style='font-size:11px;color:#9ca3af;padding:4px 0 8px;'>Showing {len(view)} stocks</div>",
        unsafe_allow_html=True)
else:
    view = []
    sel_status = ""
    sel_vol    = ""

# EMPTY STATE
if not all_results:
    if total_stocks == 0:
        st.info("👆 Add stocks via Manage Stocks, then click Sync 5D.")
    else:
        st.markdown(f"""<div style='text-align:center;padding:52px 0;color:#9ca3af;'>
            <div style='font-size:38px;margin-bottom:12px;'>📈</div>
            <div style='font-size:15px;font-weight:600;color:#0f1117;'>{total_stocks} stocks in watchlist</div>
            <div style='font-size:12px;margin-top:6px;'>Click 🔄 Sync 5D to populate price data</div>
        </div>""", unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# INTRADAY WATCH — with sub-tabs: Intraday Watch | Accumulation Breakout
# ══════════════════════════════════════════════════════════════════════════════

if sel_status and "Intraday Watch" in sel_status:
    import streamlit.components.v1 as components

    if "sw_intraday" not in st.session_state:
        with st.spinner("Loading intraday watch data..."):
            st.session_state.sw_intraday = get_intraday_watch()
    print("[DEBUG] get_intraday_watch() called")

    iw_data = st.session_state.sw_intraday or []

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
    if st.session_state.sw_sel_iw is None:
        st.session_state.sw_sel_iw = iw_filter_opts[0]

    st.markdown("**Intraday Filter**")
    iw_cols = st.columns(len(iw_filter_opts))
    for i, opt in enumerate(iw_filter_opts):
        with iw_cols[i]:
            is_active = st.session_state.sw_sel_iw == opt
            if st.button(opt, key=f"iw_{i}", type="primary" if is_active else "secondary",
                         use_container_width=True):
                st.session_state.sw_sel_iw = opt

    sel_iw = st.session_state.sw_sel_iw
    if sel_iw and "4+ Weak"    in sel_iw: iw_view = [r for r in iw_data if r["consec_weak"] >= 4]
    elif sel_iw and "Near High" in sel_iw: iw_view = [r for r in iw_data if r["pct_vs_high"] >= -3.0]
    elif sel_iw and "Vol > 50K" in sel_iw: iw_view = [r for r in iw_data if r["min_vol"] >= 50000]
    else: iw_view = iw_data

    # ── Load Accumulation Breakout data — uses same structure as old working file ──
    @st.cache_data(ttl=300)
    def load_ab_data(user_id: str):
        try:
            from supabase import create_client
            sb = create_client(
                os.environ.get("SUPABASE_URL",""),
                os.environ.get("SUPABASE_KEY","")
            )
            today = date.today()
            trading_days = []
            d = today - timedelta(days=1)
            while len(trading_days) < 7:
                if d.weekday() < 5: trading_days.append(d)
                d -= timedelta(days=1)
            trading_days = sorted(trading_days)
            date_from      = str(trading_days[0])
            date_to        = str(trading_days[-1])
            baseline_date  = str(trading_days[0])
            selection_date = str(trading_days[-1])

            hist = sb.table("swing_status_history")\
                     .select("symbol,trade_date,open,high,low,close,vol_ratio,vol_signal,status")\
                     .eq("user_id", user_id)\
                     .gte("trade_date", date_from)\
                     .lte("trade_date", date_to)\
                     .order("symbol").order("trade_date")\
                     .execute()

            live = sb.table("swing_live_data")\
                     .select("symbol,close,open,high,low,vol_ratio,vol_signal,status,trade_date")\
                     .eq("user_id", user_id)\
                     .execute()

            live_map = {r["symbol"]: r for r in (live.data or [])}

            from collections import defaultdict
            sym_hist = defaultdict(list)
            for r in (hist.data or []):
                sym_hist[r["symbol"]].append(r)

            results = []
            for sym, rows in sym_hist.items():
                rows_sorted = sorted(rows, key=lambda x: x["trade_date"])
                baseline  = next((r for r in rows_sorted if r["trade_date"] == baseline_date), None)
                selection = next((r for r in rows_sorted if r["trade_date"] == selection_date), None)
                if not baseline or not selection: continue

                c8  = float(baseline.get("close") or 0)
                c_s = float(selection.get("close") or 0)
                v8  = float(baseline.get("vol_ratio") or 0)
                v_s = float(selection.get("vol_ratio") or 0)
                if c8 <= 0 or c_s <= 0: continue

                price_gain  = (c_s - c8) / c8 * 100
                vol_improve = v_s - v8
                avg_5d      = sum(float(r.get("close") or 0) for r in rows_sorted) / len(rows_sorted)

                if not (4.0 <= price_gain <= 10.0): continue
                if vol_improve < 1.5: continue
                if not (2.0 <= v_s <= 4.5): continue

                live_r      = live_map.get(sym, {})
                live_close  = float(live_r.get("close") or c_s)
                live_vr     = float(live_r.get("vol_ratio") or 0)
                live_date   = str(live_r.get("trade_date") or today)
                live_status = live_r.get("status", "WATCH")
                live_vsig   = live_r.get("vol_signal", "")

                pct_today = (live_close - c_s) / c_s * 100 if c_s > 0 else 0
                if pct_today > 1.5:    direction="up";   dir_arrow="↑"; dir_color="#16a34a"
                elif pct_today < -1.5: direction="down"; dir_arrow="↓"; dir_color="#dc2626"
                else:                  direction="side"; dir_arrow="→"; dir_color="#6b7280"

                if vol_improve >= 2.5: btype = "Accumulation"
                elif v8 > 0.8:         btype = "Washout"
                else:                  btype = "Shakeout"

                # ── hist_rows kept for build_ab_rows() compatibility ──
                results.append({
                    "symbol":        sym,
                    "hist_rows":     rows_sorted,     # ← needed by build_ab_rows
                    "trading_days":  trading_days,
                    "price_gain":    round(price_gain, 2),
                    "vol_improve":   round(vol_improve, 2),
                    "vol_ratio_base": round(v8, 2),
                    "vol_ratio_sel":  round(v_s, 2),
                    "avg_5d":        round(avg_5d, 2),
                    "close_base":    round(c8, 2),
                    "close_sel":     round(c_s, 2),
                    "live_close":    round(live_close, 2),
                    "live_vr":       round(live_vr, 2),
                    "live_date":     live_date,
                    "live_status":   live_status,
                    "live_vsig":     live_vsig,
                    "direction":     direction,
                    "dir_arrow":     dir_arrow,
                    "dir_color":     dir_color,
                    "breakout_type": btype,           # ← needed by build_ab_rows
                    "screener_url":  f"https://www.screener.in/company/{sym}/",
                })
            results.sort(key=lambda x: x["price_gain"], reverse=True)
            return results
        except Exception as e:
    print(f"[DEBUG] Exception: {str(e)}")
            return []

    ab_data = load_ab_data(st.session_state.user_id)
    print("[DEBUG] load_ab_data() called")

    # ── Helper functions for HTML ──
    def _vol_emoji(vs):
        if "Explosive" in vs: return "🔥"
        if "Strong"    in vs: return "🟢"
        if "Build"     in vs: return "🟡"
        return "🔴"

    def _sig_key(vs):
        if "Explosive" in vs: return "Explosive"
        if "Strong"    in vs: return "Strong"
        if "Build"     in vs: return "Build"
        if "Weak"      in vs: return "Weak"
        return "None"

    def _cat_label(s):
        return {"BLASTING":"BLASTING","READY":"READY","WATCH":"WATCH"}.get(s,"—")

    # ══════════════════════════════════════════════════════════════════════════
    # v5.1: price_svg_for_iw — real OHLC candles for Intraday Watch
    # ══════════════════════════════════════════════════════════════════════════
    def price_svg_for_iw(days, live_open, live_high, live_low, live_close, live_date, h=70):
        if not days:
            return f'<svg width="160" height="{h}"><text x="6" y="30" font-size="10" fill="#9ca3af">No data</text></svg>'

        hist_opens  = [d["open"]       for d in days]
        hist_highs  = [d["high"]       for d in days]
        hist_lows   = [d["low"]        for d in days]
        hist_closes = [d["close"]      for d in days]
        hist_dates  = [d["date_label"] for d in days]

        hist_opens  = [o if o > 0 else c for o, c in zip(hist_opens,  hist_closes)]
        hist_highs  = [hh if hh > 0 else c for hh, c in zip(hist_highs, hist_closes)]
        hist_lows   = [l if l > 0 else c for l, c in zip(hist_lows,  hist_closes)]

        cur_open  = live_open  if live_open  and live_open  > 0 else live_close
        cur_high  = live_high  if live_high  and live_high  > 0 else live_close
        cur_low   = live_low   if live_low   and live_low   > 0 else live_close
        cur_close = live_close
        try:
            cur_date = str(live_date)[8:10] if live_date else "—"
        except Exception:
            cur_date = "—"

        return price_svg(
            opens=hist_opens, highs=hist_highs, lows=hist_lows, closes=hist_closes,
            dates=hist_dates,
            cur_open=cur_open, cur_high=cur_high, cur_low=cur_low, cur_close=cur_close,
            cur_date=cur_date, h=h,
        )

    def _volume_svg_iw(days_data, h=70):
        ratios    = [d["vol_ratio"]       for d in days_data]
        dates_lbl = [d["date_label"][-2:] for d in days_data]
        if not ratios: return f'<svg width="140" height="{h}"></svg>'
        n, pad, bw, gap = len(ratios), 4, 14, 5
        bar_area = h - pad - 14
        mx = max(ratios) if ratios else 1
        def bh(v): return max(3, int((v/mx)*bar_area)) if mx > 0 else 3
        parts = []
        for i, rv in enumerate(ratios):
            x = pad+i*(bw+gap); h2 = bh(rv); y = h-14-h2
            parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{h2}" fill="#f59e0b" rx="1"/>'
                        f'<text x="{x+bw//2}" y="{h-3}" text-anchor="middle" font-size="7" fill="#9ca3af">{dates_lbl[i]}</text>'
                        f'<text x="{x+bw//2}" y="{max(y-2,8)}" text-anchor="middle" font-size="7" fill="#b45309">{rv:.1f}x</text>')
        med_y = round(h-14-bh(1.0), 1)
        parts.append(f'<line x1="{pad}" x2="{pad+n*(bw+gap)-gap}" y1="{med_y}" y2="{med_y}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,2"/>')
        tw = pad+n*(bw+gap)
        return f'<svg width="{tw}" height="{h}" viewBox="0 0 {tw} {h}">{"".join(parts)}</svg>'

    # ── _iw_dropdown must be defined BEFORE build_iw_rows uses it ──
    def _iw_dropdown(col_id):
        return f'''<div id="{col_id}-dd" class="dd-menu">
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
</div>'''

    # ── Build Intraday Watch rows ──
    def build_iw_rows(iw_view, date_labels, n_days, live_date_hdr):
        header = '''<th class="stock-col">
  <div class="date-trigger" onclick="toggleDD('iw-dir-dd')">
    <span class="date-text">STOCK</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="iw-dir-dot"></div>
  <div id="iw-dir-dd" class="dd-menu">
    <div class="dd-section">Price Direction</div>
    <label class="dd-opt"><input type="checkbox" data-iwf="dir" value="up"> ↑ Upside</label>
    <label class="dd-opt"><input type="checkbox" data-iwf="dir" value="down"> ↓ Downside</label>
    <label class="dd-opt"><input type="checkbox" data-iwf="dir" value="side"> → Sideways</label>
    <div class="dd-divider"></div>
    <div class="dd-clear"><button type="button" onclick="iwClearDir()">Clear</button></div>
  </div>
</th>
<th class="chart-col">PRICE CANDLES</th>
<th class="chart-col">VOLUME RATIO</th>'''
        for i, lbl in enumerate(date_labels):
            header += f'''
<th class="date-col filterable" data-colid="col-{i}">
  <div class="date-trigger" onclick="toggleDD('col-{i}-dd')">
    <span class="date-text">{lbl}</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="col-{i}-dot"></div>
  {_iw_dropdown(f"col-{i}")}
</th>'''
        header += f'''
<th class="date-col filterable" data-colid="col-live">
  <div class="date-trigger" onclick="toggleDD('col-live-dd')">
    <span class="date-text">{live_date_hdr}</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="col-live-dot"></div>
  {_iw_dropdown("col-live")}
</th>
<th class="date-col ab-break-col">
  <div class="date-trigger" onclick="toggleDD('iw-break-dd')">
    <span class="date-text">BREAKOUT TYPE</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="iw-break-dot"></div>
  <div id="iw-break-dd" class="dd-menu">
    <div class="dd-section">Breakout Type</div>
    <label class="dd-opt"><input type="checkbox" data-iwf="break" value="accumulation"> Accumulation</label>
    <div class="dd-divider"></div>
    <div class="dd-clear"><button type="button" onclick="iwClearBreak()">Clear</button></div>
  </div>
</th>'''

        rows = ""
        for r in iw_view:
            sym          = r["symbol"]
            prc          = r["live_price"]
            pct_avg_iw   = r.get("pct_vs_avg_iw", 0)
            dir_arrow_iw = r.get("direction_arrow_iw", "→")
            dir_color_iw = r.get("direction_color_iw", "#6b7280")
            days         = r["days"][-6:]

            live_open  = r.get("live_open",  0)
            live_high  = r.get("live_high",  0)
            live_low   = r.get("live_low",   0)
            live_date  = r.get("live_date",  "")

            # Direction for JS filtering
            if pct_avg_iw > 1:   iw_dir = "up"
            elif pct_avg_iw < -1: iw_dir = "down"
            else:                 iw_dir = "side"

            # Accumulation Breakout detection
            breakout_type = "—"
            has_breakout  = False
            if len(days) >= 5:
                hist_4d_ago = days[-4] if len(days) >= 4 else days[0]
                price_base  = hist_4d_ago["close"]
                vol_base    = hist_4d_ago["vol_ratio"]
                vol_today   = r.get("live_vol_ratio", 0)
                if price_base > 0:
                    price_gain  = (prc - price_base) / price_base * 100
                    vol_improve = vol_today - vol_base
                    if (4.0 <= price_gain <= 10.0 and 2.0 <= vol_today <= 4.5 and vol_improve >= 1.5):
                        breakout_type = "Accumulation"
                        has_breakout  = True

            btype_lower = "accumulation" if has_breakout else "none"

            # ── FIX: use data-iw-dir / data-iw-break (matches JS) ──
            # ── FIX: always write data-iw-break (even when "none") ──
            # ── FIX: write per-column sig/sta attributes for col filters ──
            d_attrs = f' data-iw-dir="{iw_dir}" data-iw-break="{btype_lower}"'
            for col_idx in range(n_days):
                col_id_attr = f"col-{col_idx}"
                if col_idx < len(days):
                    sig = _sig_key(days[col_idx]["vol_signal"])
                    sta = days[col_idx]["status"]
                else:
                    sig = "None"; sta = "NONE"
                d_attrs += f' data-{col_id_attr}-sig="{sig}" data-{col_id_attr}-sta="{sta}"'
            live_sig = _sig_key(r.get("live_signal", ""))
            live_sta = r.get("live_status", "WATCH")
            d_attrs += f' data-col-live-sig="{live_sig}" data-col-live-sta="{live_sta}"'

            p_svg = price_svg_for_iw(
                days=days, live_open=live_open, live_high=live_high,
                live_low=live_low, live_close=prc, live_date=live_date,
            )

            rows += (f'<tr class="iw-row"{d_attrs}>'
                     f'<td class="stock-cell">'
                     f'<div class="sym">{sym}</div>'
                     f'<div class="prc">₹{prc:,.0f} <span style="color:{dir_color_iw};font-size:14px;">{dir_arrow_iw}</span> <span style="color:{dir_color_iw};">{pct_avg_iw:+.1f}%</span></div>'
                     f'<div style="font-size:10px;color:#6b7280;margin-top:2px;">5D Avg: ₹{r.get("avg_5d_price_iw",0):,.0f}</div>'
                     f'</td>'
                     f'<td class="chart-cell">{p_svg}</td>'
                     f'<td class="chart-cell">{_volume_svg_iw(days)}</td>')
            for i in range(n_days):
                if i < len(days):
                    d = days[i]
                    rows += (f'<td class="data-cell"><div class="cell-stack">'
                             f'<span class="cell-emoji">{_vol_emoji(d["vol_signal"])}</span>'
                             f'<span class="cell-cat">{_cat_label(d["status"])}</span>'
                             f'<span class="cell-ratio">{d["vol_ratio"]:.1f}x</span>'
                             f'</div></td>')
                else:
                    rows += '<td class="data-cell empty">—</td>'
            live_emoji = _vol_emoji(r["live_signal"])
            live_cat   = _cat_label(r.get("live_status","WATCH"))
            live_ratio = f"{r.get('live_vol_ratio',0):.1f}x"
            rows += (f'<td class="data-cell live-cell"><div class="cell-stack">'
                     f'<span class="cell-emoji">{live_emoji}</span>'
                     f'<span class="cell-cat">{live_cat}</span>'
                     f'<span class="cell-ratio">{live_ratio}</span>'
                     f'</div></td>')
            if has_breakout:
                rows += (f'<td class="data-cell break-cell">'
                         f'<span style="display:inline-block;font-size:11px;font-weight:500;padding:4px 10px;border-radius:20px;background:#f3f0ff;color:#5b21b6;border:0.5px solid #c4b5fd;">'
                         f'Accumulation</span></td></tr>')
            else:
                rows += f'<td class="data-cell break-cell">—</td></tr>'
        return header, rows

    # ── Build Accumulation Breakout rows — restored from old working file ──
    def build_ab_rows(ab_data):
        if not ab_data:
            return "", ""

        # Build date labels from hist_rows of first result
        sample = ab_data[0]["hist_rows"]
        date_labels = []
        for r in sample:
            d = str(r["trade_date"])
            try:
                lbl = datetime.strptime(d, "%Y-%m-%d").strftime("%-d%b").upper()
            except:
                lbl = d[-5:]
            date_labels.append(lbl)

        try:
            live_lbl = datetime.strptime(ab_data[0]["live_date"], "%Y-%m-%d").strftime("%-d%b").upper() + " · LIVE"
        except:
            live_lbl = "LIVE"

        def breakout_dd():
            return '''<div id="ab-break-dd" class="dd-menu">
  <div class="dd-section">Breakout Type</div>
  <label class="dd-opt"><input type="checkbox" data-abf="break" value="accumulation"> Accumulation</label>
  <label class="dd-opt"><input type="checkbox" data-abf="break" value="washout"> Washout</label>
  <label class="dd-opt"><input type="checkbox" data-abf="break" value="shakeout"> Shakeout</label>
  <div class="dd-divider"></div>
  <div class="dd-clear"><button type="button" onclick="abClearDD(\'ab-break-dd\',\'break\')">Clear</button></div>
</div>'''

        header = '''<th class="stock-col ab-stock-col">
  <div class="date-trigger" onclick="toggleDD(\'ab-dir-dd\')">
    <span class="date-text">STOCK</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="ab-dir-dot"></div>
  <div id="ab-dir-dd" class="dd-menu">
    <div class="dd-section">Price Direction</div>
    <label class="dd-opt"><input type="checkbox" data-abf="dir" value="up"> ↑ Upside</label>
    <label class="dd-opt"><input type="checkbox" data-abf="dir" value="down"> ↓ Downside</label>
    <label class="dd-opt"><input type="checkbox" data-abf="dir" value="side"> → Sideways</label>
    <div class="dd-divider"></div>
    <div class="dd-clear"><button type="button" onclick="abClearDD(\'ab-dir-dd\',\'dir\')">Clear</button></div>
  </div>
</th>
<th class="chart-col">PRICE CANDLES</th>
<th class="chart-col">VOLUME RATIO</th>'''

        for lbl in date_labels:
            header += f'<th class="date-col">{lbl}</th>'
        header += f'<th class="date-col">{live_lbl}</th>'
        header += '''<th class="date-col ab-break-col">
  <div class="date-trigger" onclick="toggleDD(\'ab-break-dd\')">
    <span class="date-text">BREAKOUT TYPE</span><span class="dd-arrow">▼</span>
  </div>
  <div class="dd-dot" id="ab-break-dot"></div>''' + breakout_dd() + '</th>'

        def price_candle_svg(hist_rows, live_close, live_date):
            closes = [float(r.get("close") or 0) for r in hist_rows]
            dates2 = []
            for r in hist_rows:
                try:
                    dates2.append(datetime.strptime(str(r["trade_date"]), "%Y-%m-%d").strftime("%-d"))
                except:
                    dates2.append(str(r["trade_date"])[-2:])
            all_p = closes + [live_close]
            mn = min(p for p in all_p if p > 0); mx = max(all_p)
            rng = mx - mn or 1
            h, pad, bw, gap = 70, 4, 12, 5
            def sy(v): return round(pad + (h-pad*2-12)*(1-(v-mn)/rng), 1)
            parts = []
            for i, c in enumerate(closes):
                x = pad + i*(bw+gap); cx = x + bw//2
                prev = closes[i-1] if i > 0 else c
                col = "#00a854" if c >= prev else "#e53935"
                by = sy(max(c,prev)); bh2 = max(3, abs(sy(c)-sy(prev)))
                parts.append(f'<line x1="{cx}" x2="{cx}" y1="{sy(c)-2}" y2="{by+bh2+2}" stroke="{col}" stroke-width="1"/>'
                             f'<rect x="{x}" y="{by}" width="{bw}" height="{bh2}" fill="{col}" rx="1"/>'
                             f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="#9ca3af">{dates2[i]}</text>')
            n2 = len(closes)
            sep = pad + n2*(bw+gap)+2
            parts.append(f'<line x1="{sep}" x2="{sep}" y1="{pad}" y2="{h-12}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')
            cx = sep+4+bw//2; tx = sep+4; col="#7c3aed"
            last = closes[-1] if closes else live_close
            by = sy(max(live_close,last)); bh2 = max(3, abs(sy(live_close)-sy(last)))
            try:
                llbl = datetime.strptime(live_date,"%Y-%m-%d").strftime("%-d")
            except: llbl = "T"
            parts.append(f'<line x1="{cx}" x2="{cx}" y1="{sy(live_close)-2}" y2="{by+bh2+2}" stroke="{col}" stroke-width="1"/>'
                        f'<rect x="{tx}" y="{by}" width="{bw}" height="{bh2}" fill="{col}30" stroke="{col}" stroke-width="1.5" rx="1"/>'
                        f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="{col}">{llbl}</text>')
            tw = sep+4+bw+pad
            gain_pct = (live_close-closes[0])/closes[0]*100 if closes and closes[0]>0 else 0
            gcol = "#16a34a" if gain_pct >= 0 else "#dc2626"
            arrow = "↑" if gain_pct >= 0 else "↓"
            lbl2 = f'<text x="{tw//2}" y="{h+10}" text-anchor="middle" font-size="9" fill="{gcol}">{arrow} {gain_pct:+.1f}%</text>'
            return f'<svg width="{tw}" height="{h+14}" viewBox="0 0 {tw} {h+14}">{"".join(parts)}{lbl2}</svg>'

        def vol_ratio_svg(hist_rows, live_vr, live_date):
            ratios = [float(r.get("vol_ratio") or 0) for r in hist_rows]
            dates2 = []
            for r in hist_rows:
                try:
                    dates2.append(datetime.strptime(str(r["trade_date"]),"%Y-%m-%d").strftime("%-d"))
                except: dates2.append(str(r["trade_date"])[-2:])
            all_r = ratios + [live_vr]
            mx = max(all_r) if all_r else 1
            h, pad, bw, gap = 70, 4, 12, 5
            bar_area = h - pad - 14
            def bh(v): return max(3, int((v/mx)*bar_area)) if mx > 0 else 3
            parts = []
            for i, rv in enumerate(ratios):
                x = pad+i*(bw+gap); h2 = bh(rv); y = h-14-h2
                parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{h2}" fill="#f59e0b" rx="1"/>'
                            f'<text x="{x+bw//2}" y="{h-3}" text-anchor="middle" font-size="7" fill="#9ca3af">{dates2[i]}</text>'
                            f'<text x="{x+bw//2}" y="{max(y-2,8)}" text-anchor="middle" font-size="7" fill="#b45309">{rv:.1f}x</text>')
            n2 = len(ratios)
            med_y = round(h-14-bh(1.0),1)
            parts.append(f'<line x1="{pad}" x2="{pad+n2*(bw+gap)-gap}" y1="{med_y}" y2="{med_y}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,2"/>')
            sep = pad+n2*(bw+gap)+2
            parts.append(f'<line x1="{sep}" x2="{sep}" y1="{pad}" y2="{h-14}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')
            cx = sep+4; h2 = bh(live_vr); y = h-14-h2
            cc = "#7c3aed" if live_vr > 2.0 else "#378add"
            try:
                llbl = datetime.strptime(live_date,"%Y-%m-%d").strftime("%-d")
            except: llbl="T"
            parts.append(f'<rect x="{cx}" y="{y}" width="{bw}" height="{h2}" fill="{cc}30" stroke="{cc}" stroke-width="1.5" rx="1"/>'
                        f'<text x="{cx+bw//2}" y="{h-3}" text-anchor="middle" font-size="7" fill="{cc}">{llbl}</text>'
                        f'<text x="{cx+bw//2}" y="{max(y-2,8)}" text-anchor="middle" font-size="7" fill="{cc}">{live_vr:.1f}x</text>')
            tw = cx+bw+pad
            vb = ratios[0] if ratios else 0
            sub = f'<text x="{tw//2}" y="{h+10}" text-anchor="middle" font-size="9" fill="#6b7280">{vb:.1f}x→{live_vr:.1f}x</text>'
            return f'<svg width="{tw}" height="{h+14}" viewBox="0 0 {tw} {h+14}">{"".join(parts)}{sub}</svg>'

        def badge(btype):
            s = {"Accumulation":"background:#f3f0ff;color:#5b21b6;border:0.5px solid #c4b5fd",
                 "Washout":     "background:#fff7ed;color:#9a3412;border:0.5px solid #fed7aa",
                 "Shakeout":    "background:#f0fdf4;color:#166534;border:0.5px solid #86efac"}.get(btype,"background:#f3f4f6;color:#374151")
            return f'<span style="display:inline-block;font-size:11px;font-weight:500;padding:4px 10px;border-radius:20px;{s};">{btype}</span>'

        rows = ""
        for r in ab_data:
            sym   = r["symbol"]
            lc    = r["live_close"]
            arrow = r["dir_arrow"]
            acol  = r["dir_color"]
            gain  = r["price_gain"]
            btype = r["breakout_type"]
            hist  = r["hist_rows"]
            lvr   = r["live_vr"]
            ld    = r["live_date"]
            ls    = r["live_status"]
            lsig  = r["live_vsig"]

            p_svg = price_candle_svg(hist, lc, ld)
            v_svg = vol_ratio_svg(hist, lvr, ld)

            date_cells = ""
            for hr in hist:
                sig   = _sig_key(hr.get("vol_signal",""))
                sta   = hr.get("status","WATCH")
                emoji = _vol_emoji(hr.get("vol_signal",""))
                cat   = _cat_label(sta)
                rv    = float(hr.get("vol_ratio") or 0)
                date_cells += (f'<td class="data-cell"><div class="cell-stack">'
                               f'<span class="cell-emoji">{emoji}</span>'
                               f'<span class="cell-cat">{cat}</span>'
                               f'<span class="cell-ratio">{rv:.1f}x</span>'
                               f'</div></td>')

            live_emoji = _vol_emoji(lsig)
            live_cat   = _cat_label(ls)
            date_cells += (f'<td class="data-cell live-cell"><div class="cell-stack">'
                          f'<span class="cell-emoji">{live_emoji}</span>'
                          f'<span class="cell-cat">{live_cat}</span>'
                          f'<span class="cell-ratio">{lvr:.1f}x</span>'
                          f'</div></td>')

            rows += (f'<tr class="ab-row" data-dir="{r["direction"]}" data-break="{btype.lower()}">'
                     f'<td class="stock-cell">'
                     f'<div class="sym">{sym}</div>'
                     f'<div class="prc">₹{lc:,.2f} <span style="color:{acol};font-size:13px;">{arrow} <span style="font-size:11px;">{gain:+.1f}%</span></span></div>'
                     f'<div style="font-size:10px;color:#6b7280;margin-top:2px;">5D Avg: ₹{r["avg_5d"]:,.2f}</div>'
                     f'</td>'
                     f'<td class="chart-cell">{p_svg}</td>'
                     f'<td class="chart-cell">{v_svg}</td>'
                     f'{date_cells}'
                     f'<td class="data-cell break-cell">{badge(btype)}</td>'
                     f'</tr>')
        return header, rows

    # ── Build both tables ──
    iw_header_html       = ""
    iw_rows_html         = ""
    live_date_for_header = "LIVE"
    n_days = 0
    if iw_view:
        sample_days = iw_view[0]["days"]
        date_labels = [d["date_label"] for d in sample_days[-6:]]
        n_days = len(date_labels)
        try:
            live_date_for_header = datetime.strptime(iw_view[0].get("live_date",""), "%Y-%m-%d").strftime("%-d%b").upper() + " · LIVE"
        except: pass
        iw_header_html, iw_rows_html = build_iw_rows(iw_view, date_labels, n_days, live_date_for_header)

    ab_header_html = ""
    ab_rows_html   = ""
    if ab_data:
        ab_header_html, ab_rows_html = build_ab_rows(ab_data)

    total_iw = len(iw_view)
    total_ab = len(ab_data)

    # ══ SINGLE HTML with two sub-tabs ══
    full_html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:transparent;color:#111;}}

.subtab-bar{{display:flex;gap:0;border-bottom:1px solid #e5e7eb;margin-bottom:12px;}}
.subtab{{padding:8px 20px;font-size:13px;font-weight:500;color:#6b7280;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;}}
.subtab:hover{{color:#111;}}
.subtab.active{{color:#7c3aed;border-bottom:2px solid #7c3aed;font-weight:600;}}
.subtab-panel{{display:none;}}
.subtab-panel.active{{display:block;}}

.count-bar{{font-size:11px;color:#6b7280;padding:4px 0 8px;}}
.table-wrap{{background:white;border:0.5px solid #e5e7eb;border-radius:8px;overflow-x:auto;}}
table{{width:100%;border-collapse:collapse;}}
thead tr{{background:#f9fafb;border-bottom:1px solid #e5e7eb;}}
th{{font-size:11px;font-weight:600;color:#6b7280;padding:10px 8px;text-align:center;text-transform:uppercase;letter-spacing:0.04em;white-space:nowrap;position:relative;}}
th.stock-col{{text-align:left;padding:10px 16px;min-width:150px;}}
th.ab-stock-col{{text-align:left;padding:10px 16px;min-width:160px;}}
th.chart-col{{min-width:160px;}}
th.date-col{{min-width:90px;}}
th.ab-break-col{{color:#7c3aed;border-left:2px solid #e9d5ff;min-width:150px;}}

.date-trigger{{display:inline-flex;align-items:center;gap:5px;cursor:pointer;padding:2px 5px;border-radius:4px;user-select:none;}}
.date-trigger:hover{{background:#f3f4f6;}}
.date-text{{font-weight:600;}}
.dd-arrow{{font-size:10px;color:#9ca3af;}}
.dd-dot{{display:none;width:7px;height:7px;background:#7c3aed;border-radius:50%;position:absolute;top:5px;right:5px;}}
.dd-dot.active{{display:block;}}

.dd-menu{{display:none;position:absolute;top:105%;left:50%;transform:translateX(-50%);background:white;border:1px solid #e5e7eb;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.12);z-index:9999;min-width:185px;padding:8px 0;text-align:left;margin-top:4px;}}
.dd-menu.open{{display:block;}}
.dd-section{{padding:5px 14px;font-size:10px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.05em;}}
.dd-opt{{display:flex;align-items:center;gap:10px;padding:7px 14px;cursor:pointer;font-size:13px;color:#111;}}
.dd-opt:hover{{background:#f9fafb;}}
.dd-opt input{{accent-color:#7c3aed;width:14px;height:14px;cursor:pointer;margin:0;}}
.dd-divider{{height:1px;background:#f3f4f6;margin:5px 0;}}
.dd-clear{{display:flex;justify-content:center;padding:4px 0;}}
.dd-clear button{{font-size:11px;color:#6b7280;background:none;border:none;cursor:pointer;text-decoration:underline;}}

tbody tr{{border-bottom:0.5px solid #f3f4f6;background:white;}}
tbody tr:last-child{{border-bottom:none;}}
td.stock-cell{{padding:12px 16px;text-align:left;vertical-align:middle;}}
td.chart-cell{{padding:8px 6px;text-align:center;vertical-align:middle;}}
td.data-cell{{padding:10px 4px;text-align:center;vertical-align:middle;}}
td.break-cell{{border-left:2px solid #e9d5ff;}}
td.data-cell.empty{{color:#9ca3af;}}
td.live-cell{{background:#fafaf8;}}
.sym{{font-size:14px;font-weight:600;color:#0f1117;}}
.prc{{font-size:12px;color:#374151;margin-top:3px;}}
.cell-stack{{display:inline-flex;flex-direction:column;align-items:center;gap:3px;}}
.cell-emoji{{font-size:20px;line-height:1;}}
.cell-cat{{font-size:11px;font-weight:600;color:#000;}}
.cell-ratio{{font-size:11px;color:#374151;}}
</style>
</head>
<body>

<div class="subtab-bar">
  <div class="subtab active" onclick="switchTab('iw')" id="tab-iw">📊 Intraday Watch ({total_iw})</div>
  <div class="subtab" onclick="switchTab('ab')" id="tab-ab">🚀 Accumulation Breakout ({total_ab})</div>
</div>

<div class="subtab-panel active" id="panel-iw">
  <div class="count-bar" id="iw-count">Showing {total_iw} stocks</div>
  <div class="table-wrap">
  <table>
  <thead><tr>{iw_header_html}</tr></thead>
  <tbody id="iw-body">{iw_rows_html}</tbody>
  </table>
  </div>
</div>

<div class="subtab-panel" id="panel-ab">
  <div class="count-bar" id="ab-count">Showing {total_ab} stocks</div>
  <div class="table-wrap">
  <table>
  <thead><tr>{ab_header_html}</tr></thead>
  <tbody id="ab-body">{ab_rows_html}</tbody>
  </table>
  </div>
</div>

<script>
var IW_TOTAL = {total_iw};
var AB_TOTAL = {total_ab};

function switchTab(tab) {{
  document.querySelectorAll('.subtab').forEach(function(t){{t.classList.remove('active');}});
  document.querySelectorAll('.subtab-panel').forEach(function(p){{p.classList.remove('active');}});
  document.getElementById('tab-'+tab).classList.add('active');
  document.getElementById('panel-'+tab).classList.add('active');
}}

function toggleDD(ddId) {{
  document.querySelectorAll('.dd-menu').forEach(function(m) {{
    if (m.id !== ddId) m.classList.remove('open');
  }});
  var el = document.getElementById(ddId);
  if (el) el.classList.toggle('open');
}}

document.addEventListener('click', function(e) {{
  if (!e.target.closest('.dd-menu') && !e.target.closest('.date-trigger')) {{
    document.querySelectorAll('.dd-menu').forEach(function(m){{m.classList.remove('open');}});
  }}
}});

/* ── Intraday Watch filters ── */
function iwClearDir() {{
  document.querySelectorAll('input[data-iwf="dir"]').forEach(function(cb){{cb.checked=false;}});
  document.getElementById('iw-dir-dd').classList.remove('open');
  iwApplyFilter();
}}

function iwClearBreak() {{
  document.querySelectorAll('input[data-iwf="break"]').forEach(function(cb){{cb.checked=false;}});
  document.getElementById('iw-break-dd').classList.remove('open');
  iwApplyFilter();
}}

function iwClearCol(colId) {{
  document.querySelectorAll('input[data-col="'+colId+'"]').forEach(function(cb){{cb.checked=false;}});
  document.getElementById(colId+'-dd').classList.remove('open');
  iwApplyFilter();
}}

function iwApplyFilter() {{
  var dirVals   = Array.from(document.querySelectorAll('input[data-iwf="dir"]:checked')).map(function(c){{return c.value;}});
  var breakVals = Array.from(document.querySelectorAll('input[data-iwf="break"]:checked')).map(function(c){{return c.value;}});
  document.getElementById('iw-dir-dot').className   = 'dd-dot' + (dirVals.length   ? ' active' : '');
  document.getElementById('iw-break-dot').className = 'dd-dot' + (breakVals.length ? ' active' : '');

  /* Build col filters — split sig vs sta */
  var colFilters = {{}};
  document.querySelectorAll('input[data-col]:checked').forEach(function(cb) {{
    var col = cb.getAttribute('data-col');
    if (!colFilters[col]) colFilters[col] = {{sigs:[], stas:[]}};
    var val = cb.value;
    if (['Explosive','Strong','Build','Weak'].indexOf(val) >= 0) colFilters[col].sigs.push(val);
    else colFilters[col].stas.push(val);
  }});

  /* Update dot indicators for col headers */
  document.querySelectorAll('.dd-dot').forEach(function(dot) {{
    var colId = dot.id.replace('-dot','');
    if (colFilters[colId]) dot.classList.add('active');
    else dot.classList.remove('active');
  }});

  var rows = document.querySelectorAll('#iw-body .iw-row');
  var visible = 0;
  rows.forEach(function(row) {{
    var showDir   = !dirVals.length   || dirVals.indexOf(row.getAttribute('data-iw-dir'))   >= 0;
    var showBreak = !breakVals.length || breakVals.indexOf(row.getAttribute('data-iw-break')) >= 0;
    var show = showDir && showBreak;
    /* Apply column filters */
    Object.keys(colFilters).forEach(function(col) {{
      var f   = colFilters[col];
      var rs  = row.getAttribute('data-' + col + '-sig') || '';
      var rst = row.getAttribute('data-' + col + '-sta') || '';
      if (f.sigs.length > 0 && f.sigs.indexOf(rs)  < 0) show = false;
      if (f.stas.length > 0 && f.stas.indexOf(rst) < 0) show = false;
    }});
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  var anyActive = dirVals.length > 0 || breakVals.length > 0 || Object.keys(colFilters).length > 0;
  document.getElementById('iw-count').textContent = anyActive
    ? ('Showing ' + visible + ' of ' + IW_TOTAL + ' stocks')
    : ('Showing ' + IW_TOTAL + ' stocks');
}}

/* ── Accumulation Breakout filters ── */
function abClearDD(ddId, filterType) {{
  document.querySelectorAll('input[data-abf="'+filterType+'"]').forEach(function(cb){{cb.checked=false;}});
  document.getElementById(ddId).classList.remove('open');
  abApplyFilter();
}}

function abApplyFilter() {{
  var dirVals   = Array.from(document.querySelectorAll('input[data-abf="dir"]:checked')).map(function(c){{return c.value;}});
  var breakVals = Array.from(document.querySelectorAll('input[data-abf="break"]:checked')).map(function(c){{return c.value;}});
  document.getElementById('ab-dir-dot').className   = 'dd-dot' + (dirVals.length   ? ' active' : '');
  document.getElementById('ab-break-dot').className = 'dd-dot' + (breakVals.length ? ' active' : '');
  var rows = document.querySelectorAll('#ab-body .ab-row');
  var visible = 0;
  rows.forEach(function(row) {{
    var dir = row.getAttribute('data-dir');
    var brk = row.getAttribute('data-break');
    var showDir   = !dirVals.length   || dirVals.indexOf(dir)   >= 0;
    var showBreak = !breakVals.length || breakVals.indexOf(brk) >= 0;
    row.style.display = (showDir && showBreak) ? '' : 'none';
    if (showDir && showBreak) visible++;
  }});
  var any = dirVals.length > 0 || breakVals.length > 0;
  document.getElementById('ab-count').textContent = any
    ? ('Showing ' + visible + ' of ' + AB_TOTAL + ' stocks')
    : ('Showing ' + AB_TOTAL + ' stocks');
}}

/* ── Attach listeners ── */
document.querySelectorAll('input[data-col]').forEach(function(cb) {{
  cb.addEventListener('change', function() {{ iwApplyFilter(); }});
}});
document.querySelectorAll('input[data-iwf]').forEach(function(cb) {{
  cb.addEventListener('change', function() {{ iwApplyFilter(); }});
}});
document.querySelectorAll('input[data-abf]').forEach(function(cb) {{
  cb.addEventListener('change', function() {{ abApplyFilter(); }});
}});
</script>
</body>
</html>'''

    est_height = 200 + max(len(iw_view), len(ab_data)) * 90
    est_height = min(max(est_height, 400), 6000)
    components.html(full_html, height=est_height, scrolling=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN RESULTS TABLE
# ══════════════════════════════════════════════════════════════════════════════

COL = [1.4, 2.0, 2.1, 1.2, 1.3, 1.8, 1.0, 0.9]
header = st.columns(COL)
labels = ["Stock", "Price Candles — 5D | Today", "Volume — 5D Hist | Current",
          "LTP", "Today H / L", "Vol Signal", "Status", "Screener"]
for col, lbl in zip(header, labels):
    col.markdown(
        f"<div style='font-size:10px;font-weight:600;color:#7a8394;text-transform:uppercase;"
        f"letter-spacing:0.07em;padding:8px 4px;border-bottom:2px solid #e0e3e8;'>{lbl}</div>",
        unsafe_allow_html=True)

for r in view:
    print(f"[DEBUG] Rendering {len(view)} rows")
    sym    = r["symbol"]
    status = r.get("status","")
    bc     = border_color(status)

    p_svg = price_svg(
        r.get("hist_opens",[]), r.get("hist_highs",[]),
        r.get("hist_lows",[]),  r.get("hist_closes",[]),
        r.get("hist_dates",[]),
        cur_open=r.get("current_open"), cur_high=r.get("current_high"),
        cur_low=r.get("current_low"),   cur_close=r.get("current_price"),
        cur_date=r.get("current_date"))
    v_svg = volume_svg(
        r.get("hist_volumes",[]), r.get("current_vol",0),
        r.get("median_vol",1), dates=r.get("hist_dates",[]),
        cur_date=r.get("current_date"))

    ltp       = r.get("current_price",0)
    pct_avg   = r.get("pct_vs_avg",0)
    dir_arrow = r.get("direction_arrow","→")
    dir_color = r.get("direction_color","#7a8394")
    h_val     = r.get("current_high",0)
    l_val     = r.get("current_low",0)
    vsig      = r.get("vol_signal","—")
    cur_v     = fmt_vol(r.get("current_vol"))
    med_v     = fmt_vol(r.get("median_vol"))
    bd        = r.get("breakout_date") or "—"
    s_url     = r.get("screener_url", f"https://www.screener.in/company/{sym}/")

    st.markdown(f"<div style='border-left:3px solid {bc};margin-bottom:0;border-bottom:1px solid #f0f2f5;'></div>",
                unsafe_allow_html=True)
    row = st.columns(COL)
    row[0].markdown(f"<div style='padding:8px 4px;'><div class='sw-sym'>{sym}</div><div class='sw-bd'>{bd}</div></div>", unsafe_allow_html=True)
    row[1].markdown(f"<div style='padding:4px 0;'>{p_svg}</div>", unsafe_allow_html=True)
    row[2].markdown(f"<div style='padding:4px 0;'>{v_svg}<div class='sw-med'>— median {med_v}</div></div>", unsafe_allow_html=True)
    row[3].markdown(f"<div style='padding:8px 4px;'><div class='sw-ltp'>₹{ltp:,.2f} <span style='color:{dir_color};font-size:16px;'>{dir_arrow}</span> <span style='color:{dir_color};'>{pct_avg:+.1f}%</span></div></div>", unsafe_allow_html=True)
    row[4].markdown(f"<div style='padding:8px 4px;'><div class='sw-hl' style='color:#00a854;'>H: ₹{h_val:,.2f}</div><div class='sw-hl' style='color:#e53935;'>L: ₹{l_val:,.2f}</div></div>", unsafe_allow_html=True)
    row[5].markdown(f"<div style='padding:8px 4px;'><div class='sw-vsig'>{vsig}</div><div class='sw-vsub'>{cur_v} / med {med_v}</div></div>", unsafe_allow_html=True)
    row[6].markdown(f"<div style='padding:8px 4px;'>{status_badge(status)}</div>", unsafe_allow_html=True)
    row[7].markdown(f"<div style='padding:8px 4px;'><a href='{s_url}' target='_blank' class='sw-link'>Screener ↗</a></div>", unsafe_allow_html=True)

# Push to watchlist
ready_blast = [r for r in view if r.get("status") in ("BLASTING","READY")]
if ready_blast and WATCHLIST_PUSH:
    try:
        wl_names = get_user_watchlist_names() if st.session_state.get("user_id") else ["Today","Yesterday","New"]
    except Exception:
        wl_names = ["Today","Yesterday","New"]
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("**Push to Watchlist**")
    for r in ready_blast:
        sym = r["symbol"]
        p1, p2, p3 = st.columns([2, 2, 1])
        with p1: st.markdown(f"`{sym}` {status_badge(r.get('status',''))}", unsafe_allow_html=True)
        with p2: chosen = st.selectbox("WL", wl_names, key=f"wl_{sym}", label_visibility="collapsed")
        with p3:
            if st.button("➕", key=f"wladd_{sym}", use_container_width=True):
                try:
                    add_to_watchlist(chosen, {
                        "symbol":    sym, "status": "BUY",
                        "lastPrice": r.get("current_price",0),
                        "entry":     r.get("current_price",0),
                        "sl":        round(r.get("current_low",0)*0.99,2),
                        "target1":   round(r.get("current_price",0)*1.05,2),
                        "target2":   round(r.get("current_price",0)*1.10,2),
                        "note":      f"Swing {r.get('status','')} — {r.get('vol_ratio',0)}x vol",
                    })
                    st.success(f"✅ {sym} → {chosen}")
                except Exception as e: st.error(str(e))
    print(f"[DEBUG] Exception: {str(e)}")

if st.session_state.sw_errors:
    with st.expander(f"⚠ {len(st.session_state.sw_errors)} errors"):
        for e in st.session_state.sw_errors:
            st.markdown(f"`{e['symbol']}` — {e['error']}")
