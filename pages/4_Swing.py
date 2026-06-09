# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — pages/4_Swing.py  v2.0
#  Swing Scanner — SVG inline candles + volume bars, exact sheet layout
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import os, sys, time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from styles import apply_styles, sidebar_brand, page_header
from swing_core import (
    load_swing_stocks, add_swing_stock, delete_swing_stock,
    bulk_add_swing_stocks, run_swing_scan, fmt_vol,
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

# ── CSS ──
st.markdown("""
<style>
.sw-table { width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; }
.sw-th {
    font-size:10px; font-weight:600; color:#7a8394;
    text-transform:uppercase; letter-spacing:0.07em;
    padding:8px 10px; background:#f8f9fb;
    border-bottom:1px solid #e0e3e8; white-space:nowrap;
}
.sw-td { padding:10px 10px; border-bottom:1px solid #f0f2f5; vertical-align:middle; }
.sw-row:hover td { background:#fafbfc; }
.sw-sym { font-family:'JetBrains Mono',monospace; font-size:14px; font-weight:700; color:#0f1117; }
.sw-bd  { font-size:10px; color:#9ca3af; margin-top:2px; }
.sw-ltp { font-family:'JetBrains Mono',monospace; font-size:14px; font-weight:700; color:#0f1117; }
.sw-hl  { font-family:'JetBrains Mono',monospace; font-size:11px; }
.sw-badge-B { background:#ede9fe; color:#3C3489; border:1px solid #7c3aed40; font-size:10px; font-weight:700; padding:2px 8px; border-radius:10px; white-space:nowrap; }
.sw-badge-R { background:#f0faf5; color:#0F6E56; border:1px solid #1D9E7540; font-size:10px; font-weight:700; padding:2px 8px; border-radius:10px; white-space:nowrap; }
.sw-badge-W { background:#fffbeb; color:#854F0B; border:1px solid #f59e0b40; font-size:10px; font-weight:700; padding:2px 8px; border-radius:10px; white-space:nowrap; }
.sw-vsig { font-size:12px; font-weight:600; }
.sw-vsub { font-size:10px; color:#9ca3af; font-family:'JetBrains Mono',monospace; }
.sw-link { font-size:11px; color:#2563eb; text-decoration:none; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──
for k, v in [("sw_results",[]),("sw_errors",[]),("sw_scan_time",None),
              ("sw_show_manage",False),("sw_stocks_cache",None),("sw_filter","ALL")]:
    if k not in st.session_state: st.session_state[k] = v

def load_cached():
    if st.session_state.sw_stocks_cache is None:
        st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

def refresh_cache():
    st.session_state.sw_stocks_cache = load_swing_stocks()
    return st.session_state.sw_stocks_cache

# ── SVG helpers ──
def price_candles_svg(opens, highs, lows, closes, dates, w=130, h=52):
    if not closes:
        return "<svg width='130' height='52'><text x='10' y='30' font-size='10' fill='#9ca3af'>No data</text></svg>"
    n    = len(closes)
    pad  = 4
    bw   = 14
    gap  = (w - pad*2 - bw*n) // max(n-1,1)
    allp = highs + lows
    mn, mx = min(allp), max(allp)
    rng  = mx - mn or 1

    def sy(v):
        return pad + (h - pad*2 - 10) * (1 - (v - mn) / rng)

    parts = []
    for i in range(n):
        x  = pad + i * (bw + gap)
        cx = x + bw // 2
        o, h2, l2, c = opens[i], highs[i], lows[i], closes[i]
        green  = c >= o
        color  = "#00a854" if green else "#e53935"
        body_y = round(sy(max(o,c)), 1)
        body_h = max(2, round(abs(sy(o) - sy(c)), 1))
        wick_t = round(sy(h2), 1)
        wick_b = round(sy(l2), 1)
        parts.append(
            f'<line x1="{cx}" x2="{cx}" y1="{wick_t}" y2="{wick_b}" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{x}" y="{body_y}" width="{bw}" height="{body_h}" fill="{color}" rx="1"/>'
        )
        lbl = dates[i].split(" ")[0] if dates else str(i+1)
        parts.append(f'<text x="{cx}" y="{h-1}" text-anchor="middle" font-size="7" fill="#9ca3af">{lbl}</text>')

    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{"".join(parts)}</svg>'


def volume_bars_svg(hist_vols, current_vol, median_vol, w=150, h=52):
    n    = len(hist_vols)
    pad  = 4
    bw   = 12
    gap  = 4
    bar_h_max = h - pad - 12

    all_vols = [v for v in hist_vols if v > 0] + [current_vol]
    mx_vol   = max(all_vols) if all_vols else 1

    def bar_h(v):
        return max(3, int((v / mx_vol) * bar_h_max))

    parts = []
    total_w = pad + n*(bw+gap) + 6 + bw + pad

    # Hist bars (grey)
    for i, v in enumerate(hist_vols):
        x = pad + i*(bw+gap)
        bh = bar_h(v)
        y  = h - 12 - bh
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="#e0e3e8" stroke="#9ca3af" stroke-width="0.5" rx="1"/>')
        parts.append(f'<text x="{x+bw//2}" y="{h-2}" text-anchor="middle" font-size="7" fill="#9ca3af">{i+1}</text>')

    # Separator dashed line
    sep_x = pad + n*(bw+gap) + 2
    parts.append(f'<line x1="{sep_x}" x2="{sep_x}" y1="{pad}" y2="{h-12}" stroke="#e0e3e8" stroke-width="1" stroke-dasharray="2,2"/>')

    # Current bar (blue/purple based on height)
    cx = sep_x + 4
    cbh = bar_h(current_vol)
    cy  = h - 12 - cbh
    cur_color = "#7c3aed" if vol_ratio_from(current_vol, median_vol) > 2 else "#2563eb"
    parts.append(f'<rect x="{cx}" y="{cy}" width="{bw}" height="{cbh}" fill="{cur_color}30" stroke="{cur_color}" stroke-width="1" rx="1"/>')
    parts.append(f'<text x="{cx+bw//2}" y="{h-2}" text-anchor="middle" font-size="7" fill="{cur_color}">cur</text>')

    # Median line across hist bars
    if median_vol > 0:
        med_y = round(h - 12 - bar_h(median_vol), 1)
        med_x2 = pad + n*(bw+gap) - gap
        parts.append(f'<line x1="{pad}" x2="{med_x2}" y1="{med_y}" y2="{med_y}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,2"/>')

    actual_w = cx + bw + pad
    return f'<svg width="{actual_w}" height="{h}" viewBox="0 0 {actual_w} {h}">{"".join(parts)}</svg>'


def vol_ratio_from(current_vol, median_vol):
    return round(current_vol / median_vol, 2) if median_vol > 0 else 0


def status_badge(status):
    cls = {"BLASTING":"sw-badge-B","READY":"sw-badge-R","WATCH":"sw-badge-W"}.get(status,"")
    ico = {"BLASTING":"🔥","READY":"✅","WATCH":"👁"}.get(status,"")
    if not cls: return "—"
    return f'<span class="{cls}">{ico} {status}</span>'


def border_color(status):
    return {"BLASTING":"#7c3aed","READY":"#00a854","WATCH":"#f59e0b"}.get(status,"#e0e3e8")

# ══════════════════════════════════════════
#  CONTROL BAR
# ══════════════════════════════════════════
stocks       = load_cached()
total_stocks = len(stocks)

c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 0.8, 0.9, 3])

with c1:
    lbl = "✕ Manage" if st.session_state.sw_show_manage else "⚙ Manage Stocks"
    if st.button(lbl, use_container_width=True):
        st.session_state.sw_show_manage = not st.session_state.sw_show_manage
        st.rerun()

with c2:
    if st.button("▷ Run Scan", use_container_width=True,
                 disabled=total_stocks==0, type="primary"):
        with st.spinner(f"Scanning {total_stocks} stocks..."):
            results, errors = run_swing_scan(stocks)
            st.session_state.sw_results   = results
            st.session_state.sw_errors    = errors
            st.session_state.sw_scan_time = time.time()
        st.rerun()

with c3:
    if st.button("🗑 Clear", use_container_width=True,
                 disabled=len(st.session_state.sw_results)==0):
        st.session_state.sw_results   = []
        st.session_state.sw_errors    = []
        st.session_state.sw_scan_time = None
        st.rerun()

with c4:
    st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#7a8394;'>📋 <b style='color:#0f1117'>{total_stocks}</b> stocks</div>",
                unsafe_allow_html=True)

with c5:
    if st.session_state.sw_scan_time:
        t        = datetime.fromtimestamp(st.session_state.sw_scan_time).strftime("%I:%M %p")
        blasting = sum(1 for r in st.session_state.sw_results if r.get("status")=="BLASTING")
        ready    = sum(1 for r in st.session_state.sw_results if r.get("status")=="READY")
        watch    = sum(1 for r in st.session_state.sw_results if r.get("status")=="WATCH")
        st.markdown(
            f"<div style='display:flex;gap:16px;align-items:center;padding-top:8px;'>"
            f"<span style='font-size:12px;color:#7c3aed;font-weight:700;'>🔥 {blasting}</span>"
            f"<span style='font-size:12px;color:#00a854;font-weight:700;'>✅ {ready}</span>"
            f"<span style='font-size:12px;color:#d97706;font-weight:700;'>👁 {watch}</span>"
            f"<span style='font-size:11px;color:#9ca3af;'>Last scan: {t}</span></div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════
#  MANAGE PANEL
# ══════════════════════════════════════════
if st.session_state.sw_show_manage:
    with st.container():
        st.markdown("### ⚙ Manage Swing Stocks")
        t1, t2, t3 = st.tabs(["➕ Add Single", "📋 Bulk Add", "📝 Stock List"])

        with t1:
            with st.form("add_form", clear_on_submit=True):
                col1, col2 = st.columns([1,2])
                with col1:
                    sym  = st.text_input("NSE Symbol *", placeholder="HEROMOTOCO")
                with col2:
                    url  = st.text_input("Screener URL (optional)")
                col3, col4 = st.columns([1,2])
                with col3:
                    bd   = st.date_input("Breakout Date (optional)", value=None)
                with col4:
                    note = st.text_input("Notes (optional)")
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
                    with st.spinner("Adding..."):
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
                st.markdown(f"**{len(curr)} stocks**")
                for s in curr:
                    c1, c2, c3 = st.columns([2,3,1])
                    with c1: st.markdown(f"**`{s['symbol']}`**")
                    with c2:
                        bd = s.get("breakout_date") or "—"
                        st.markdown(f"<span style='font-size:11px;color:#9ca3af;'>Breakout: {bd}</span>",
                                    unsafe_allow_html=True)
                    with c3:
                        if st.button("✕", key=f"del_{s['id']}"):
                            delete_swing_stock(s["id"]); refresh_cache(); st.rerun()
    st.markdown("---")

# ══════════════════════════════════════════
#  FILTER PILLS
# ══════════════════════════════════════════
all_results = st.session_state.sw_results

if all_results:
    blasting_n = sum(1 for r in all_results if r.get("status")=="BLASTING")
    ready_n    = sum(1 for r in all_results if r.get("status")=="READY")
    watch_n    = sum(1 for r in all_results if r.get("status")=="WATCH")
    all_n      = len(all_results)

    opts = [f"ALL ({all_n})", f"🔥 BLASTING ({blasting_n})",
            f"✅ READY ({ready_n})", f"👁 WATCH ({watch_n})"]
    sel  = st.pills("Filter", opts, default=opts[0], label_visibility="collapsed")

    if sel and "BLASTING" in sel:
        view = [r for r in all_results if r.get("status")=="BLASTING"]
    elif sel and "READY" in sel:
        view = [r for r in all_results if r.get("status")=="READY"]
    elif sel and "WATCH" in sel:
        view = [r for r in all_results if r.get("status")=="WATCH"]
    else:
        view = all_results

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

else:
    view = []

# ══════════════════════════════════════════
#  RESULTS TABLE
# ══════════════════════════════════════════
if not all_results:
    if total_stocks == 0:
        st.info("👆 Add stocks via Manage Stocks, then run a scan.")
    else:
        st.markdown(f"""
        <div style='text-align:center;padding:48px 0;color:#9ca3af;'>
            <div style='font-size:36px;margin-bottom:10px;'>📈</div>
            <div style='font-size:15px;font-weight:600;color:#0f1117;'>{total_stocks} stocks ready</div>
            <div style='font-size:12px;margin-top:4px;'>Click ▷ Run Scan to find setups</div>
        </div>""", unsafe_allow_html=True)
else:
    if WATCHLIST_PUSH:
        try:
            wl_names = get_user_watchlist_names() if st.session_state.get("user_id") else ["Today","Yesterday","New"]
        except Exception:
            wl_names = ["Today","Yesterday","New"]
    else:
        wl_names = []

    # Table header
    st.markdown("""
    <table class="sw-table">
    <thead><tr>
        <th class="sw-th" style="width:140px">Stock</th>
        <th class="sw-th" style="width:150px">Price candles — 5d</th>
        <th class="sw-th" style="width:170px">Volume — 5d hist | current</th>
        <th class="sw-th" style="width:100px">LTP</th>
        <th class="sw-th" style="width:110px">Today H / L</th>
        <th class="sw-th" style="width:150px">Vol signal</th>
        <th class="sw-th" style="width:90px">Status</th>
        <th class="sw-th" style="width:70px">Link</th>
    </tr></thead>
    <tbody>
    """, unsafe_allow_html=True)

    for r in view:
        sym    = r["symbol"]
        status = r.get("status","")
        bc     = border_color(status)

        price_svg = price_candles_svg(
            r.get("hist_opens",[]), r.get("hist_highs",[]),
            r.get("hist_lows",[]),  r.get("hist_closes",[]),
            r.get("hist_dates",[])
        )
        vol_svg = volume_bars_svg(
            r.get("hist_volumes",[]),
            r.get("current_vol", 0),
            r.get("median_vol", 1),
        )

        ltp     = r.get("current_price", 0)
        pct     = r.get("pct_vs_high", 0)
        pct_col = "#00a854" if pct >= 0 else "#e53935"
        pct_str = f"{pct:+.1f}% vs 5d high"
        h_val   = r.get("current_high", 0)
        l_val   = r.get("current_low", 0)
        vsig    = r.get("vol_signal","—")
        cur_vol = fmt_vol(r.get("current_vol"))
        med_vol = fmt_vol(r.get("median_vol"))
        ratio   = r.get("vol_ratio", 0)
        bd      = r.get("breakout_date") or "—"
        s_url   = r.get("screener_url","#")
        badge   = status_badge(status)

        st.markdown(f"""
        <tr class="sw-row" style="border-left:3px solid {bc};">
            <td class="sw-td">
                <div class="sw-sym">{sym}</div>
                <div class="sw-bd">{bd}</div>
            </td>
            <td class="sw-td">{price_svg}</td>
            <td class="sw-td">
                {vol_svg}
                <div class="sw-vsub" style="margin-top:2px;">med: {med_vol}</div>
            </td>
            <td class="sw-td">
                <div class="sw-ltp">₹{ltp:,.2f}</div>
                <div style="font-size:10px;color:{pct_col};font-family:monospace;">{pct_str}</div>
            </td>
            <td class="sw-td">
                <div class="sw-hl" style="color:#00a854;">H: ₹{h_val:,.2f}</div>
                <div class="sw-hl" style="color:#e53935;">L: ₹{l_val:,.2f}</div>
            </td>
            <td class="sw-td">
                <div class="sw-vsig">{vsig}</div>
                <div class="sw-vsub">{cur_vol} / med {med_vol}</div>
            </td>
            <td class="sw-td">{badge}</td>
            <td class="sw-td"><a href="{s_url}" target="_blank" class="sw-link">Screener ↗</a></td>
        </tr>
        """, unsafe_allow_html=True)

    st.markdown("</tbody></table>", unsafe_allow_html=True)

    # Push to watchlist — shown below table for READY/BLASTING only
    ready_blast = [r for r in view if r.get("status") in ("BLASTING","READY")]
    if ready_blast and WATCHLIST_PUSH and wl_names:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown("**Push to Watchlist**")
        for r in ready_blast:
            sym = r["symbol"]
            c1, c2, c3 = st.columns([2,2,1])
            with c1:
                st.markdown(f"`{sym}` — {status_badge(r.get('status',''))}",
                            unsafe_allow_html=True)
            with c2:
                chosen = st.selectbox("Watchlist", wl_names, key=f"wl_{sym}",
                                      label_visibility="collapsed")
            with c3:
                if st.button("➕ Add", key=f"wladd_{sym}"):
                    try:
                        add_to_watchlist(chosen, {
                            "symbol":  sym, "status": "BUY",
                            "lastPrice": r.get("current_price",0),
                            "entry":   r.get("current_price",0),
                            "sl":      round(r.get("current_low",0)*0.99, 2),
                            "target1": round(r.get("current_price",0)*1.05, 2),
                            "target2": round(r.get("current_price",0)*1.10, 2),
                            "note":    f"Swing {r.get('status','')} — vol {r.get('vol_ratio',0)}x",
                        })
                        st.success(f"{sym} → {chosen}")
                    except Exception as e:
                        st.error(str(e))

    # Errors expander
    if st.session_state.sw_errors:
        with st.expander(f"⚠ {len(st.session_state.sw_errors)} fetch errors"):
            for e in st.session_state.sw_errors:
                st.markdown(f"`{e['symbol']}` — {e['error']}")
