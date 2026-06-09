# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — pages/4_Swing.py  v4.0
#  v4.0: Date-driven, auto-load on open, no Run Scan button
#        DB-first for hist, live fetch for today only
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import os, sys, time
from datetime import datetime, date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from swing_core import (
    load_swing_stocks, add_swing_stock, update_swing_stock,
    delete_swing_stock, bulk_add_swing_stocks, run_swing_scan,
    fmt_vol, refresh_live_data, is_market_open,
)

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
.sw-vsig { font-size:12px; font-weight:600; }
.sw-vsub { font-size:10px; color:#9ca3af; font-family:'JetBrains Mono',monospace; margin-top:3px; }
.sw-med  { font-size:9px; color:#f59e0b; margin-top:3px; }
.sw-badge-B { background:#ede9fe; color:#3C3489; border:1px solid #7c3aed40; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-badge-R { background:#f0faf5; color:#0F6E56; border:1px solid #1D9E7540; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-badge-W { background:#fffbeb; color:#854F0B; border:1px solid #f59e0b40; font-size:11px; font-weight:700; padding:4px 10px; border-radius:10px; display:inline-block; white-space:nowrap; }
.sw-link { font-size:12px; color:#2563eb; text-decoration:none; font-weight:500; }
.sw-link:hover { text-decoration:underline; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──
for k, v in [("sw_results",[]),("sw_errors",[]),("sw_scan_time",None),
              ("sw_show_manage",False),("sw_stocks_cache",None),
              ("sw_last_refresh",None),("sw_auto_refresh",True),
              ("sw_selected_date", date.today()),("sw_loading",False)]:
    if k not in st.session_state:
        st.session_state[k] = v

def load_cached():
    if st.session_state.sw_stocks_cache is None:
        st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def refresh_cache():
    st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

# ─────────────────────────────────────────────────────────────────────────────
# SVG HELPERS — unchanged from v2.x
# ─────────────────────────────────────────────────────────────────────────────

def price_svg(opens, highs, lows, closes, dates,
              cur_open=None, cur_high=None, cur_low=None, cur_close=None,
              cur_date=None, w=200, h=62):
    if not closes:
        return f'<svg width="{w}" height="{h}"><text x="6" y="30" font-size="10" fill="#9ca3af">No data</text></svg>'
    has_cur = all(v is not None for v in [cur_open, cur_high, cur_low, cur_close])
    n, pad, bw, gap = len(closes), 4, 16, 5
    all_p = [v for v in highs + lows if v and v > 0]
    if has_cur:
        all_p += [cur_high, cur_low]
    if not all_p:
        return f'<svg width="{w}" height="{h}"></svg>'
    mn, mx = min(all_p), max(all_p)
    rng = mx - mn or 1
    def sy(v): return round(pad + (h - pad*2 - 10) * (1 - (v - mn) / rng), 1)
    parts = []
    for i in range(n):
        x, cx = pad + i*(bw+gap), pad + i*(bw+gap) + bw//2
        o, h2, l2, c = opens[i], highs[i], lows[i], closes[i]
        col = "#00a854" if c >= o else "#e53935"
        by, bh = sy(max(o,c)), max(2, abs(sy(o)-sy(c)))
        lbl = dates[i].split(" ")[0] if i < len(dates) else str(i+1)
        parts.append(f'<line x1="{cx}" x2="{cx}" y1="{sy(h2)}" y2="{sy(l2)}" stroke="{col}" stroke-width="1.2"/>'
                     f'<rect x="{x}" y="{by}" width="{bw}" height="{bh}" fill="{col}" rx="2"/>'
                     f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="#9ca3af">{lbl}</text>')
    if has_cur:
        sep_x = pad + n*(bw+gap) + 2
        cx, tx = sep_x + 5 + bw//2, sep_x + 5
        col = "#7c3aed"
        by, bh = sy(max(cur_open, cur_close)), max(2, abs(sy(cur_open)-sy(cur_close)))
        lbl = cur_date.split(" ")[0] if cur_date else "today"
        parts.append(f'<line x1="{sep_x}" x2="{sep_x}" y1="{pad}" y2="{h-12}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>'
                     f'<line x1="{cx}" x2="{cx}" y1="{sy(cur_high)}" y2="{sy(cur_low)}" stroke="{col}" stroke-width="1.2"/>'
                     f'<rect x="{tx}" y="{by}" width="{bw}" height="{bh}" fill="{col}30" stroke="{col}" stroke-width="1.5" rx="2"/>'
                     f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="8" fill="{col}" font-weight="500">{lbl}</text>')
        total_w = sep_x + 5 + bw + pad
    else:
        total_w = pad + n*(bw+gap)
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def volume_svg(hist_vols, cur_vol, median_vol, w=195, h=62):
    n, pad, bw, gap = len(hist_vols), 4, 18, 5
    bar_area = h - pad - 14
    all_v = [v for v in hist_vols if v and v > 0] + ([cur_vol] if cur_vol else [])
    mx = max(all_v) if all_v else 1
    def bh(v): return max(3, int((v/mx)*bar_area))
    parts = []
    for i, v in enumerate(hist_vols):
        x, h2, y = pad + i*(bw+gap), bh(v), h - 14 - bh(v)
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{h2}" fill="#e8eaed" stroke="#c4c9d4" stroke-width="0.5" rx="2"/>'
                     f'<text x="{x+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="#9ca3af">{i+1}</text>')
    sep = pad + n*(bw+gap) + 2
    parts.append(f'<line x1="{sep}" x2="{sep}" y1="{pad}" y2="{h-14}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')
    cx, ch2 = sep + 4, bh(cur_vol) if cur_vol else 3
    ratio = round(cur_vol/median_vol, 2) if median_vol and median_vol > 0 else 0
    cc = "#7c3aed" if ratio > 2.0 else "#2563eb"
    parts.append(f'<rect x="{cx}" y="{h-14-ch2}" width="{bw}" height="{ch2}" fill="{cc}25" stroke="{cc}" stroke-width="1.5" rx="2"/>'
                 f'<text x="{cx+bw//2}" y="{h-3}" text-anchor="middle" font-size="8" fill="{cc}">cur</text>')
    if median_vol and median_vol > 0:
        med_y, med_x2 = round(h - 14 - bh(median_vol), 1), pad + n*(bw+gap) - gap
        parts.append(f'<line x1="{pad}" x2="{med_x2}" y1="{med_y}" y2="{med_y}" stroke="#f59e0b" stroke-width="1.2" stroke-dasharray="3,2"/>')
    total_w = cx + bw + pad
    return f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}">{"".join(parts)}</svg>'


def status_badge(status):
    cls = {"BLASTING":"sw-badge-B","READY":"sw-badge-R","WATCH":"sw-badge-W"}.get(status,"")
    ico = {"BLASTING":"🔥","READY":"✅","WATCH":"👁"}.get(status,"")
    return f'<span class="{cls}">{ico} {status}</span>' if cls else "—"

def border_color(status):
    return {"BLASTING":"#7c3aed","READY":"#00a854","WATCH":"#f59e0b"}.get(status,"#e0e3e8")

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
stocks       = load_cached()
total_stocks = len(stocks)

# ── Auto-fetch on load or date change ──
def _trigger_scan(selected_date):
    with st.spinner(f"Loading {total_stocks} stocks for {selected_date.strftime('%d %b %Y')}..."):
        results, errors = run_swing_scan(stocks, selected_date=selected_date)
        st.session_state.sw_results      = results
        st.session_state.sw_errors       = errors
        st.session_state.sw_scan_time    = time.time()
        st.session_state.sw_last_refresh = time.time()

# Auto-load on first open
if not st.session_state.sw_results and total_stocks > 0:
    _trigger_scan(st.session_state.sw_selected_date)
    st.rerun()

# ── Auto-refresh every 5 mins during market hours ──
_now  = time.time()
_last = st.session_state.sw_last_refresh
if (st.session_state.sw_auto_refresh
        and st.session_state.sw_results
        and is_market_open()
        and _last is not None
        and (_now - _last) >= 300):
    st.session_state.sw_last_refresh = _now
    updated = refresh_live_data(st.session_state.sw_results)
    st.session_state.sw_results = updated

# ─────────────────────────────────────────────────────────────────────────────
# CONTROL BAR
# ─────────────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns([1.1, 1.3, 0.9, 0.9, 3.5])

with c1:
    lbl = "✕ Manage" if st.session_state.sw_show_manage else "⚙ Manage Stocks"
    if st.button(lbl, use_container_width=True):
        st.session_state.sw_show_manage = not st.session_state.sw_show_manage
        st.rerun()

with c2:
    # Date picker — calendar widget
    selected = st.date_input(
        "Date", value=st.session_state.sw_selected_date,
        max_value=date.today(),
        label_visibility="collapsed",
    )
    if selected != st.session_state.sw_selected_date:
        st.session_state.sw_selected_date = selected
        st.session_state.sw_results       = []
        st.session_state.sw_errors        = []
        st.session_state.sw_scan_time     = None
        st.rerun()

with c3:
    if st.button("🔄 Refresh", use_container_width=True,
                 disabled=not st.session_state.sw_results,
                 help="Refresh today's live price & volume"):
        with st.spinner("Refreshing..."):
            updated = refresh_live_data(st.session_state.sw_results)
            st.session_state.sw_results      = updated
            st.session_state.sw_last_refresh = time.time()
        st.toast("🔄 Live data refreshed", icon="✅")
        st.rerun()

with c4:
    if st.button("🗑 Clear", use_container_width=True,
                 disabled=not st.session_state.sw_results):
        st.session_state.sw_results      = []
        st.session_state.sw_errors       = []
        st.session_state.sw_scan_time    = None
        st.session_state.sw_last_refresh = None
        st.rerun()

with c5:
    if st.session_state.sw_scan_time:
        t        = datetime.fromtimestamp(st.session_state.sw_scan_time).strftime("%I:%M %p")
        blasting = sum(1 for r in st.session_state.sw_results if r.get("status") == "BLASTING")
        ready    = sum(1 for r in st.session_state.sw_results if r.get("status") == "READY")
        watch    = sum(1 for r in st.session_state.sw_results if r.get("status") == "WATCH")
        last_ref = ""
        if st.session_state.sw_last_refresh:
            rt = datetime.fromtimestamp(st.session_state.sw_last_refresh).strftime("%I:%M %p")
            last_ref = f"&nbsp;&nbsp;🔄 {rt}"
        mkt = "🟢 Live" if is_market_open() else "🔴 Closed"
        st.markdown(
            f"<div style='display:flex;gap:16px;align-items:center;padding-top:8px;flex-wrap:wrap;'>"
            f"<span style='font-size:12px;color:#7c3aed;font-weight:700;'>🔥 {blasting}</span>"
            f"<span style='font-size:12px;color:#00a854;font-weight:700;'>✅ {ready}</span>"
            f"<span style='font-size:12px;color:#d97706;font-weight:700;'>👁 {watch}</span>"
            f"<span style='font-size:11px;color:#9ca3af;'>Loaded: {t}{last_ref}</span>"
            f"<span style='font-size:11px;color:#9ca3af;'>{mkt}</span>"
            f"</div>", unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='padding-top:8px;font-size:12px;color:#7a8394;'>"
            f"📋 <b style='color:#0f1117'>{total_stocks}</b> stocks</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MANAGE PANEL
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.sw_show_manage:
    st.markdown("### ⚙ Manage Swing Stocks")
    t1, t2, t3 = st.tabs(["➕ Add Single", "📋 Bulk Add", "📝 Stock List"])
    with t1:
        with st.form("add_form", clear_on_submit=True):
            a1, a2 = st.columns([1,2])
            with a1: sym  = st.text_input("NSE Symbol *", placeholder="HEROMOTOCO")
            with a2: url  = st.text_input("Screener URL (optional)")
            a3, a4 = st.columns([1,2])
            with a3: bd   = st.date_input("Breakout Date (optional)", value=None)
            with a4: note = st.text_input("Notes (optional)")
            if st.form_submit_button("➕ Add", type="primary"):
                if not sym.strip():
                    st.error("Symbol required.")
                else:
                    try:
                        add_swing_stock(sym.strip(), url.strip(), bd, note.strip())
                        refresh_cache(); st.success(f"✅ {sym.upper()} added."); st.rerun()
                    except ValueError as e: st.warning(str(e))
                    except Exception as e:  st.error(str(e))
    with t2:
        txt = st.text_area("Symbols — one per line or comma separated", height=150,
                           placeholder="HEROMOTOCO\nTITAN\nHDFCBANK")
        if st.button("📋 Add All", type="primary"):
            raw  = txt.replace(",","\n").splitlines()
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
                r1, r2, r3, r4, r5 = st.columns([2,2,3,2,1])
                with r1: st.markdown(f"**`{s['symbol']}`**")
                with r2: st.markdown(f"<span style='font-size:11px;color:#9ca3af;'>{s.get('breakout_date') or '—'}</span>", unsafe_allow_html=True)
                with r3: st.markdown(f"<span style='font-size:11px;color:#9ca3af;'>{(s.get('notes') or '')[:40]}</span>", unsafe_allow_html=True)
                with r4:
                    new_bd = st.date_input("", value=None, key=f"ebd_{s['id']}", label_visibility="collapsed")
                    if new_bd:
                        try: update_swing_stock(s["id"], {"breakout_date": str(new_bd)}); refresh_cache(); st.rerun()
                        except Exception as e: st.error(str(e))
                with r5:
                    if st.button("✕", key=f"del_{s['id']}"):
                        try: delete_swing_stock(s["id"]); refresh_cache(); st.rerun()
                        except Exception as e: st.error(str(e))
    st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# FILTER PILLS
# ─────────────────────────────────────────────────────────────────────────────
all_results = st.session_state.sw_results

if all_results:
    b_n  = sum(1 for r in all_results if r.get("status") == "BLASTING")
    r_n  = sum(1 for r in all_results if r.get("status") == "READY")
    w_n  = sum(1 for r in all_results if r.get("status") == "WATCH")
    a_n  = len(all_results)
    ex_n = sum(1 for r in all_results if "Explosive" in r.get("vol_signal",""))
    st_n = sum(1 for r in all_results if "Strong"    in r.get("vol_signal",""))
    bu_n = sum(1 for r in all_results if "Build"     in r.get("vol_signal",""))
    wk_n = sum(1 for r in all_results if "Weak"      in r.get("vol_signal",""))

    status_opts = [f"ALL ({a_n})", f"🔥 BLASTING ({b_n})", f"✅ READY ({r_n})", f"👁 WATCH ({w_n})"]
    sel_status  = st.pills("Status", status_opts, default=status_opts[0], label_visibility="collapsed")
    vol_opts    = ["All signals", f"🔥 Explosive ({ex_n})", f"🟢 Strong ({st_n})", f"🟡 Build ({bu_n})", f"🔴 Weak ({wk_n})"]
    sel_vol     = st.pills("Vol signal", vol_opts, default=vol_opts[0], label_visibility="collapsed")

    if   sel_status and "BLASTING" in sel_status: view = [r for r in all_results if r.get("status") == "BLASTING"]
    elif sel_status and "READY"    in sel_status: view = [r for r in all_results if r.get("status") == "READY"]
    elif sel_status and "WATCH"    in sel_status: view = [r for r in all_results if r.get("status") == "WATCH"]
    else:                                          view = all_results

    if   sel_vol and "Explosive" in sel_vol: view = [r for r in view if "Explosive" in r.get("vol_signal","")]
    elif sel_vol and "Strong"    in sel_vol: view = [r for r in view if "Strong"    in r.get("vol_signal","")]
    elif sel_vol and "Build"     in sel_vol: view = [r for r in view if "Build"     in r.get("vol_signal","")]
    elif sel_vol and "Weak"      in sel_vol: view = [r for r in view if "Weak"      in r.get("vol_signal","")]

    st.markdown(f"<div style='font-size:11px;color:#9ca3af;padding:4px 0 8px;'>Showing {len(view)} stocks</div>",
                unsafe_allow_html=True)
else:
    view = []

# ─────────────────────────────────────────────────────────────────────────────
# EMPTY STATE
# ─────────────────────────────────────────────────────────────────────────────
if not all_results:
    if total_stocks == 0:
        st.info("👆 Add stocks via Manage Stocks.")
    else:
        st.markdown(f"""
        <div style='text-align:center;padding:52px 0;color:#9ca3af;'>
            <div style='font-size:38px;margin-bottom:12px;'>📈</div>
            <div style='font-size:15px;font-weight:600;color:#0f1117;'>Loading {total_stocks} stocks...</div>
        </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS TABLE — identical layout to v2.x
# ─────────────────────────────────────────────────────────────────────────────
COL = [1.4, 2.0, 2.1, 1.2, 1.3, 1.8, 1.0, 0.9]

header = st.columns(COL)
labels = ["Stock", "Price candles — 5d | today", "Volume — 5d hist | current",
          "LTP", "Today H / L", "Vol signal", "Status", "Screener"]
for col, lbl in zip(header, labels):
    col.markdown(
        f"<div style='font-size:10px;font-weight:600;color:#7a8394;"
        f"text-transform:uppercase;letter-spacing:0.07em;"
        f"padding:8px 4px;border-bottom:2px solid #e0e3e8;'>{lbl}</div>",
        unsafe_allow_html=True,
    )

for r in view:
    sym, status = r["symbol"], r.get("status","")
    bc = border_color(status)

    p_svg = price_svg(
        r.get("hist_opens",[]), r.get("hist_highs",[]),
        r.get("hist_lows",[]),  r.get("hist_closes",[]),
        r.get("hist_dates",[]),
        cur_open=r.get("current_open"), cur_high=r.get("current_high"),
        cur_low=r.get("current_low"),   cur_close=r.get("current_price"),
        cur_date=r.get("current_date"),
    )
    v_svg = volume_svg(r.get("hist_volumes",[]), r.get("current_vol",0), r.get("median_vol",1))

    ltp     = r.get("current_price", 0)
    pct     = r.get("pct_vs_high", 0)
    pct_col = "#00a854" if pct >= 0 else "#e53935"

    st.markdown(f"<div style='border-left:3px solid {bc};border-bottom:1px solid #f0f2f5;'></div>",
                unsafe_allow_html=True)
    row = st.columns(COL)

    row[0].markdown(f"<div style='padding:8px 4px;'><div class='sw-sym'>{sym}</div><div class='sw-bd'>{r.get('breakout_date') or '—'}</div></div>", unsafe_allow_html=True)
    row[1].markdown(f"<div style='padding:4px 0;'>{p_svg}</div>", unsafe_allow_html=True)
    row[2].markdown(f"<div style='padding:4px 0;'>{v_svg}<div class='sw-med'>— median {fmt_vol(r.get('median_vol'))}</div></div>", unsafe_allow_html=True)
    row[3].markdown(f"<div style='padding:8px 4px;'><div class='sw-ltp'>₹{ltp:,.2f}</div><div class='sw-pct' style='color:{pct_col};'>{pct:+.1f}% vs 5d high</div></div>", unsafe_allow_html=True)
    row[4].markdown(f"<div style='padding:8px 4px;'><div class='sw-hl' style='color:#00a854;'>H: ₹{r.get('current_high',0):,.2f}</div><div class='sw-hl' style='color:#e53935;'>L: ₹{r.get('current_low',0):,.2f}</div></div>", unsafe_allow_html=True)
    row[5].markdown(f"<div style='padding:8px 4px;'><div class='sw-vsig'>{r.get('vol_signal','—')}</div><div class='sw-vsub'>{fmt_vol(r.get('current_vol'))} / med {fmt_vol(r.get('median_vol'))}</div></div>", unsafe_allow_html=True)
    row[6].markdown(f"<div style='padding:8px 4px;'>{status_badge(status)}</div>", unsafe_allow_html=True)
    row[7].markdown(f"<div style='padding:8px 4px;'><a href='{r.get('screener_url','#')}' target='_blank' class='sw-link'>Screener ↗</a></div>", unsafe_allow_html=True)

# ── Push to watchlist ──
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
        p1, p2, p3 = st.columns([2,2,1])
        with p1: st.markdown(f"`{sym}` {status_badge(r.get('status',''))}", unsafe_allow_html=True)
        with p2: chosen = st.selectbox("WL", wl_names, key=f"wl_{sym}", label_visibility="collapsed")
        with p3:
            if st.button("➕", key=f"wladd_{sym}", use_container_width=True):
                try:
                    add_to_watchlist(chosen, {
                        "symbol": sym, "status": "BUY",
                        "lastPrice": r.get("current_price",0),
                        "entry":   r.get("current_price",0),
                        "sl":      round(r.get("current_low",0)*0.99, 2),
                        "target1": round(r.get("current_price",0)*1.05, 2),
                        "target2": round(r.get("current_price",0)*1.10, 2),
                        "note":    f"Swing {r.get('status','')} — {r.get('vol_ratio',0)}x vol",
                    })
                    st.success(f"✅ {sym} → {chosen}")
                except Exception as e: st.error(str(e))

# ── Errors ──
if st.session_state.sw_errors:
    with st.expander(f"⚠ {len(st.session_state.sw_errors)} fetch errors"):
        for e in st.session_state.sw_errors:
            st.markdown(f"`{e['symbol']}` — {e['error']}")
