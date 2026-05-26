# ══════════════════════════════════════════
#  TRADESENTRY — pages/3_Watchlist.py
#  Multi-watchlist: Today / Yesterday / New
#  Price: Angel One (primary) → yfinance (fallback)
#  Storage: watchlist.json (auto-created)
#  Styling: all classes live in styles.py
# ══════════════════════════════════════════

import streamlit as st
import json, os, pyotp, yfinance as yf
from datetime import datetime
from SmartApi import SmartConnect

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from stocks import SECTOR_YAHOO, get_stock_token, get_stock_sector
from styles import apply_styles, sidebar_brand, page_header

# ── PAGE CONFIG ──
st.set_page_config(
    page_title="Watchlist · TradeSentry",
    layout="wide",
    page_icon="👁",
    initial_sidebar_state="expanded"
)
apply_styles()        # ← single call — loads ALL styles including watchlist classes
sidebar_brand()
page_header("Watchlist", "Track your trades")


# ══════════════════════════════════════════
#  STORAGE
# ══════════════════════════════════════════

WATCHLIST_FILE  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

def load_all() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}
    try:
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        for n in WATCHLIST_NAMES:
            data.setdefault(f"watchlist_{n}", [])
        return data
    except Exception:
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}

def save_all(data: dict):
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Save error: {e}")

def get_list(tab: str) -> list:
    return load_all().get(f"watchlist_{tab}", [])

def set_list(tab: str, lst: list):
    data = load_all()
    data[f"watchlist_{tab}"] = lst
    save_all(data)


# ══════════════════════════════════════════
#  ANGEL ONE SESSION
# ══════════════════════════════════════════

@st.cache_resource(ttl=3600)
def get_angel_session():
    try:
        obj  = SmartConnect(api_key=st.secrets["API_KEY"])
        totp = pyotp.TOTP(st.secrets["TOTP_SECRET"]).now()
        sess = obj.generateSession(st.secrets["CLIENT_CODE"], st.secrets["PASSWORD"], totp)
        return obj if sess.get("status") else None
    except Exception:
        return None


# ══════════════════════════════════════════
#  PRICE FETCHING
# ══════════════════════════════════════════

def fetch_ltp_angel(symbol: str, exchange: str) -> float | None:
    try:
        obj   = get_angel_session()
        if not obj: return None
        token = get_stock_token(symbol)
        if not token: return None
        exch  = "NSE" if exchange == "NS" else "BSE"
        resp  = obj.ltpData(exch, symbol, token)
        if resp and resp.get("status"):
            return float(resp["data"]["ltp"])
    except Exception:
        pass
    return None

def fetch_ltp_yfinance(symbol: str, exchange: str) -> float | None:
    try:
        suffix = ".NS" if exchange == "NS" else ".BO"
        t = yf.Ticker(f"{symbol}{suffix}")
        p = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        return float(p) if p else None
    except Exception:
        return None

def fetch_ltp(symbol: str, exchange: str) -> tuple[float | None, str]:
    p = fetch_ltp_angel(symbol, exchange)
    if p: return p, "angel"
    p = fetch_ltp_yfinance(symbol, exchange)
    if p: return p, "yfinance"
    return None, "none"

@st.cache_data(ttl=60)
def fetch_sector_pct(yahoo_sym: str) -> float | None:
    try:
        t     = yf.Ticker(yahoo_sym)
        prev  = t.fast_info.get("previousClose") or t.fast_info.get("regularMarketPreviousClose")
        price = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        if prev and price and prev != 0:
            return round((price - prev) / prev * 100, 2)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════
#  STATUS LOGIC
# ══════════════════════════════════════════

def compute_status(stock: dict, ltp: float) -> str:
    entry = stock.get("entry")
    sl    = stock.get("sl")
    t1    = stock.get("target1")
    t2    = stock.get("target2")
    d     = stock.get("direction", "BUY")
    if not entry: return "WATCHING"
    if d == "BUY":
        if sl and ltp <= sl:                   return "SL_HIT"
        if t2 and ltp >= t2:                   return "TARGET2"
        if t1 and ltp >= t1:                   return "TARGET1"
        if ltp >= entry:                        return "TRIGGERED"
        if abs(ltp - entry) / entry <= 0.01:   return "NEAR"
    else:
        if sl and ltp >= sl:                   return "SL_HIT"
        if t2 and ltp <= t2:                   return "TARGET2"
        if t1 and ltp <= t1:                   return "TARGET1"
        if ltp <= entry:                        return "TRIGGERED"
        if abs(ltp - entry) / entry <= 0.01:   return "NEAR"
    return "WATCHING"

# All badge classes come from styles.py
STATUS_LABEL = {
    "WATCHING":  "👁 Watching",
    "NEAR":      "⚠ Near Entry",
    "TRIGGERED": "✓ Triggered",
    "SL_HIT":    "✕ SL Hit",
    "TARGET1":   "🎯 T1 Hit",
    "TARGET2":   "🏆 T2 Hit",
}
STATUS_BADGE = {
    "WATCHING":  "ts-badge-amber",
    "NEAR":      "ts-badge-amber",
    "TRIGGERED": "ts-badge-green",
    "SL_HIT":    "ts-badge-red",
    "TARGET1":   "ts-badge-blue",
    "TARGET2":   "ts-badge-purple",
}
STATUS_CARD = {
    "WATCHING":  "wl-watching",
    "NEAR":      "wl-near",
    "TRIGGERED": "wl-triggered",
    "SL_HIT":    "wl-sl_hit",
    "TARGET1":   "wl-target1",
    "TARGET2":   "wl-target2",
}

def fmt(v) -> str:
    if v is None: return "---"
    try: return f"₹{float(v):,.2f}"
    except: return "---"

def pct_html(ltp, entry) -> str:
    if not ltp or not entry: return ""
    p   = (ltp - entry) / entry * 100
    cls = "wl-pct-pos" if p >= 0 else "wl-pct-neg"
    s   = "+" if p >= 0 else ""
    return f'<span class="{cls}">{s}{p:.2f}% from entry</span>'


# ══════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════

for k, v in [("current_tab","Today"), ("direction","BUY"), ("exchange","NS"),
             ("edit_index",None), ("edit_tab","Today"), ("price_source",{})]:
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════
#  SIDEBAR — Add Stock Form
# ══════════════════════════════════════════

with st.sidebar:
    st.markdown('<div class="ts-section-label">Add Stock</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▲ BUY", use_container_width=True,
                     type="primary" if st.session_state.direction == "BUY" else "secondary"):
            st.session_state.direction = "BUY"; st.rerun()
    with c2:
        if st.button("▼ SELL", use_container_width=True,
                     type="primary" if st.session_state.direction == "SELL" else "secondary"):
            st.session_state.direction = "SELL"; st.rerun()

    d = st.session_state.direction
    color = "var(--green)" if d == "BUY" else "var(--red)"
    hint  = "🟢 Long — triggers above entry" if d == "BUY" else "🔴 Short — triggers below entry"
    st.markdown(
        f'<div style="font-size:11px;color:{color};font-family:var(--sans);margin:4px 0 10px 0">{hint}</div>',
        unsafe_allow_html=True
    )

    e1, e2 = st.columns(2)
    with e1:
        if st.button("NSE", use_container_width=True,
                     type="primary" if st.session_state.exchange == "NS" else "secondary"):
            st.session_state.exchange = "NS"; st.rerun()
    with e2:
        if st.button("BSE", use_container_width=True,
                     type="primary" if st.session_state.exchange == "BO" else "secondary"):
            st.session_state.exchange = "BO"; st.rerun()

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    symbol = st.text_input("Symbol", placeholder="e.g. RELIANCE").upper().strip()
    entry  = st.number_input("Entry ₹",     min_value=0.0, format="%.2f")
    sl     = st.number_input("Stop Loss ₹", min_value=0.0, format="%.2f")
    t1     = st.number_input("Target 1 ₹",  min_value=0.0, format="%.2f")
    t2     = st.number_input("Target 2 ₹",  min_value=0.0, format="%.2f")
    note   = st.text_input("Note (optional)")

    add_tab   = st.session_state.current_tab
    btn_label = f"{'+ ADD LONG' if d == 'BUY' else '+ ADD SHORT'} → {add_tab}"

    if st.button(btn_label, use_container_width=True, type="primary"):
        if not symbol:
            st.error("Symbol is required")
        elif entry <= 0:
            st.error("Entry price is required")
        else:
            lst       = get_list(add_tab)
            dir_count = sum(1 for s in lst if s.get("direction") == d)
            if dir_count >= 3:
                st.warning(f"⛔ Max 3 {d} positions in {add_tab}. Remove one first.")
            else:
                clean = symbol.replace(".NS","").replace(".BO","")
                lst.append({
                    "symbol":    clean,
                    "exchange":  st.session_state.exchange,
                    "direction": d,
                    "entry":     entry,
                    "sl":        sl  if sl  > 0 else None,
                    "target1":   t1  if t1  > 0 else None,
                    "target2":   t2  if t2  > 0 else None,
                    "note":      note.strip() or None,
                    "sector":    get_stock_sector(clean),
                    "status":    "WATCHING",
                    "lastPrice": None,
                    "added_at":  datetime.now().isoformat(),
                })
                set_list(add_tab, lst)
                st.success(f"✅ {clean} added to {add_tab}")
                st.rerun()

    st.divider()
    st.markdown('<div class="ts-section-label">Sort</div>', unsafe_allow_html=True)
    sort_by = st.selectbox("", ["Default","Status","Symbol","Distance to Entry"],
                           label_visibility="collapsed")


# ══════════════════════════════════════════
#  MAIN — Tab Bar
# ══════════════════════════════════════════

tab_cols = st.columns(len(WATCHLIST_NAMES))
for i, name in enumerate(WATCHLIST_NAMES):
    with tab_cols[i]:
        cnt = len(get_list(name))
        is_active = st.session_state.current_tab == name
        if st.button(
            f"{'● ' if is_active else ''}{name}  ({cnt})",
            key=f"tab_{name}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state.current_tab = name
            st.rerun()

st.markdown('<hr class="ts-divider">', unsafe_allow_html=True)

current_tab = st.session_state.current_tab
watchlist   = get_list(current_tab)

# ── Header ──
h1, h2, h3 = st.columns([5, 1, 1])
with h1:
    st.markdown(
        f'<div class="ts-section-label">{current_tab} · '
        f'{len(watchlist)} stock{"s" if len(watchlist)!=1 else ""}</div>',
        unsafe_allow_html=True
    )
with h2:
    refresh = st.button("↺ Refresh", use_container_width=True)
with h3:
    if st.button("🗑 Clear", use_container_width=True) and watchlist:
        set_list(current_tab, [])
        st.rerun()

# ── Fetch prices on refresh ──
if watchlist and refresh:
    updated  = []
    progress = st.progress(0, text="Fetching prices...")
    for i, stock in enumerate(watchlist):
        ltp, source = fetch_ltp(stock["symbol"], stock.get("exchange","NS"))
        s = stock.copy()
        s["lastPrice"] = ltp
        if ltp:
            s["status"] = compute_status(s, ltp)
            st.session_state.price_source[s["symbol"]] = source
        updated.append(s)
        progress.progress((i+1)/len(watchlist), text=f"Fetching {stock['symbol']}...")
    progress.empty()
    set_list(current_tab, updated)
    watchlist = updated

# ── Sort ──
def sort_watchlist(lst, by):
    order = {"SL_HIT":0,"TRIGGERED":1,"NEAR":2,"TARGET1":3,"TARGET2":4,"WATCHING":5}
    if by == "Status":
        return sorted(lst, key=lambda s: order.get(s.get("status","WATCHING"), 9))
    if by == "Symbol":
        return sorted(lst, key=lambda s: s.get("symbol",""))
    if by == "Distance to Entry":
        def dist(s):
            ltp = s.get("lastPrice"); e = s.get("entry")
            return abs(ltp-e)/e if ltp and e else 999
        return sorted(lst, key=dist)
    return lst

watchlist_sorted = sort_watchlist(watchlist, sort_by)

# ── Empty state ──
if not watchlist:
    st.markdown(
        '<div class="ts-card" style="text-align:center;padding:40px">'
        '<div style="font-size:32px;margin-bottom:8px">📭</div>'
        f'<div style="color:var(--text2);font-family:var(--sans)">No stocks in <b>{current_tab}</b> yet.</div>'
        '<div style="color:var(--text3);font-size:12px;margin-top:4px">Use the sidebar to add your first trade.</div>'
        '</div>',
        unsafe_allow_html=True
    )
    st.stop()


# ══════════════════════════════════════════
#  RENDER CARDS
# ══════════════════════════════════════════

def orig_idx(stock):
    for i, s in enumerate(get_list(current_tab)):
        if (s.get("symbol")==stock.get("symbol") and
            s.get("entry")==stock.get("entry") and
            s.get("direction")==stock.get("direction")):
            return i
    return None

COLS = 3
rows = [watchlist_sorted[i:i+COLS] for i in range(0, len(watchlist_sorted), COLS)]

for row in rows:
    cols = st.columns(COLS)
    for col, stock in zip(cols, row):
        with col:
            sym    = stock.get("symbol","")
            dirn   = stock.get("direction","BUY")
            exch   = stock.get("exchange","NS")
            status = stock.get("status","WATCHING")
            ltp    = stock.get("lastPrice")
            entry  = stock.get("entry")
            sector = stock.get("sector")
            src    = st.session_state.price_source.get(sym,"")

            # Sector %
            sect_html = ""
            if sector and sector in SECTOR_YAHOO:
                sp = fetch_sector_pct(SECTOR_YAHOO[sector])
                if sp is not None:
                    sign = "+" if sp >= 0 else ""
                    cls  = "wl-sector-pos" if sp > 0 else ("wl-sector-neg" if sp < 0 else "wl-sector-flat")
                    sect_html = f'<div style="margin-bottom:4px"><span class="{cls}">{sector} {sign}{sp}%</span></div>'

            # Price source
            src_html = ""
            if src == "angel":
                src_html = '&nbsp;<span class="wl-src-angel">⚡ Angel</span>'
            elif src == "yfinance":
                src_html = '&nbsp;<span class="wl-src-yfinance">yf</span>'

            # Exit signal
            exit_html = ""
            if status == "TRIGGERED" and ltp and entry:
                if dirn == "BUY" and ltp < entry:
                    exit_html = '<div class="wl-exit-signal">⚠ Price below entry — consider exit</div>'

            st.markdown(f"""
<div class="wl-card {STATUS_CARD.get(status,'wl-watching')}">

  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <span class="wl-symbol">{sym}</span>&nbsp;
      <span class="wl-pill-{'buy' if dirn=='BUY' else 'sell'}">{'▲ BUY' if dirn=='BUY' else '▼ SELL'}</span>&nbsp;
      <span class="wl-pill-exch">{'NSE' if exch=='NS' else 'BSE'}</span>
    </div>
    <span class="{STATUS_BADGE.get(status,'ts-badge-amber')}">{STATUS_LABEL.get(status,'')}</span>
  </div>

  <div style="margin-bottom:6px">
    {'<span class="wl-ltp">' + fmt(ltp) + '</span>' if ltp else '<span class="wl-ltp-none">--- no price</span>'}
    {pct_html(ltp, entry)}
    {src_html}
  </div>

  <div class="wl-levels">
    <div class="wl-level wl-level-entry">
      <div class="wl-level-lbl">Entry</div>
      <div class="wl-level-val">{fmt(entry)}</div>
    </div>
    <div class="wl-level wl-level-sl">
      <div class="wl-level-lbl">SL</div>
      <div class="wl-level-val">{fmt(stock.get('sl'))}</div>
    </div>
    <div class="wl-level wl-level-t1">
      <div class="wl-level-lbl">T1</div>
      <div class="wl-level-val">{fmt(stock.get('target1'))}</div>
    </div>
    <div class="wl-level wl-level-t2">
      <div class="wl-level-lbl">T2</div>
      <div class="wl-level-val">{fmt(stock.get('target2'))}</div>
    </div>
  </div>

  {sect_html}
  {f'<div class="wl-note">📝 {stock.get("note")}</div>' if stock.get("note") else ''}
  {exit_html}

</div>
""", unsafe_allow_html=True)

            # Action buttons — below each card
            idx = orig_idx(stock)
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("↺ Reset", key=f"rst_{sym}_{idx}", use_container_width=True):
                    lst = get_list(current_tab)
                    if idx is not None:
                        lst[idx]["status"]    = "WATCHING"
                        lst[idx]["lastPrice"] = None
                        set_list(current_tab, lst)
                        st.rerun()
            with a2:
                if st.button("✏ Edit", key=f"edt_{sym}_{idx}", use_container_width=True):
                    st.session_state.edit_index = idx
                    st.session_state.edit_tab   = current_tab
            with a3:
                if st.button("✕ Del", key=f"del_{sym}_{idx}", use_container_width=True):
                    lst = get_list(current_tab)
                    if idx is not None:
                        lst.pop(idx)
                        set_list(current_tab, lst)
                        st.rerun()


# ══════════════════════════════════════════
#  EDIT PANEL
# ══════════════════════════════════════════

if st.session_state.edit_index is not None:
    idx = st.session_state.edit_index
    tab = st.session_state.edit_tab
    lst = get_list(tab)
    if idx < len(lst):
        s = lst[idx]
        st.markdown('<hr class="ts-divider">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ts-section-label">Edit — {s.get("symbol","")}</div>',
            unsafe_allow_html=True
        )
        with st.container(border=True):
            ec1, ec2 = st.columns(2)
            with ec1:
                ne  = st.number_input("Entry ₹",     value=float(s.get("entry")   or 0), format="%.2f", key="e_en")
                ns  = st.number_input("Stop Loss ₹",  value=float(s.get("sl")      or 0), format="%.2f", key="e_sl")
            with ec2:
                nt1 = st.number_input("Target 1 ₹",  value=float(s.get("target1") or 0), format="%.2f", key="e_t1")
                nt2 = st.number_input("Target 2 ₹",  value=float(s.get("target2") or 0), format="%.2f", key="e_t2")
            nn = st.text_input("Note", value=s.get("note") or "", key="e_note")

            sv1, sv2 = st.columns(2)
            with sv1:
                if st.button("💾 Save", use_container_width=True, type="primary", key="save_edit"):
                    lst[idx].update({
                        "entry":   ne  if ne  > 0 else s.get("entry"),
                        "sl":      ns  if ns  > 0 else None,
                        "target1": nt1 if nt1 > 0 else None,
                        "target2": nt2 if nt2 > 0 else None,
                        "note":    nn.strip() or None,
                    })
                    set_list(tab, lst)
                    st.session_state.edit_index = None
                    st.rerun()
            with sv2:
                if st.button("Cancel", use_container_width=True, key="cancel_edit"):
                    st.session_state.edit_index = None
                    st.rerun()


# ══════════════════════════════════════════
#  FOOTER
# ══════════════════════════════════════════

st.markdown('<hr class="ts-divider">', unsafe_allow_html=True)
angel_ok = get_angel_session() is not None
st.markdown(
    f'<div style="font-size:11px;color:var(--text3);font-family:var(--sans)">'
    f'{"🟢 Angel One connected" if angel_ok else "🟡 Angel One offline — using yfinance"}'
    f'&nbsp;·&nbsp;Stored in watchlist.json'
    f'&nbsp;·&nbsp;Press ↺ Refresh to update prices</div>',
    unsafe_allow_html=True
)
