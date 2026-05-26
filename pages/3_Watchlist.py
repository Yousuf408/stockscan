# ══════════════════════════════════════════
#  TRADESENTRY — pages/3_Watchlist.py
#  Multi-watchlist: Today / Yesterday / New
#  Price: Angel One (primary) → yfinance (fallback)
#  Storage: watchlist.json (local file)
# ══════════════════════════════════════════

import streamlit as st
import json
import os
import pyotp
import yfinance as yf
from datetime import datetime
from SmartApi import SmartConnect

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from stocks import STOCK_UNIVERSE, SECTOR_YAHOO, get_stock_token, get_stock_sector
from styles import apply_styles, sidebar_brand, page_header

# ── PAGE CONFIG ──
st.set_page_config(
    page_title="Watchlist · TradeSentry",
    layout="wide",
    page_icon="👁",
    initial_sidebar_state="expanded"
)
apply_styles()
sidebar_brand()
page_header("Watchlist")

# ══════════════════════════════════════════
#  STORAGE — JSON file (mirrors chrome.storage keys)
# ══════════════════════════════════════════

WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]


def load_all() -> dict:
    """Load entire watchlist.json. Returns dict with all 3 lists."""
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
    """Save entire watchlist.json atomically."""
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
#  ANGEL ONE SESSION (shared from app.py pattern)
# ══════════════════════════════════════════

@st.cache_resource(ttl=3600)
def get_angel_session():
    """
    Login to Angel One once per hour. Cached so all pages share the session.
    Returns SmartConnect object or None if login fails.
    """
    try:
        api_key     = st.secrets["API_KEY"]
        username    = st.secrets["CLIENT_CODE"]
        password    = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"]
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        session = obj.generateSession(username, password, totp)
        if session.get("status"):
            return obj
        return None
    except Exception:
        return None


# ══════════════════════════════════════════
#  PRICE FETCHING — Angel One → yfinance fallback
# ══════════════════════════════════════════

def fetch_ltp_angel(symbol: str, exchange: str) -> float | None:
    """
    Fetch live LTP from Angel One using token from STOCK_UNIVERSE.
    exchange: 'NS' → exchangeType 1 (NSE), 'BO' → exchangeType 3 (BSE)
    """
    try:
        obj = get_angel_session()
        if obj is None:
            return None
        clean = symbol.replace(".NS", "").replace(".BO", "")
        token = get_stock_token(clean)
        if not token:
            return None
        exch_map = {"NS": "NSE", "BO": "BSE"}
        exch_str = exch_map.get(exchange, "NSE")
        resp = obj.ltpData(exch_str, clean, token)
        if resp and resp.get("status"):
            return float(resp["data"]["ltp"])
        return None
    except Exception:
        return None


def fetch_ltp_yfinance(symbol: str) -> float | None:
    """
    Fallback: fetch last price via yfinance.
    symbol should already have .NS or .BO suffix.
    """
    try:
        ticker = yf.Ticker(symbol)
        price = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
        return float(price) if price else None
    except Exception:
        return None


def fetch_ltp(symbol: str, exchange: str) -> tuple[float | None, str]:
    """
    Priority: Angel One → yfinance.
    Returns (price, source) where source is 'angel' or 'yfinance' or 'none'.
    """
    # Ensure symbol has exchange suffix for yfinance
    clean = symbol.replace(".NS", "").replace(".BO", "")
    yf_symbol = f"{clean}.{exchange}" if exchange in ("NS", "BO") else symbol

    price = fetch_ltp_angel(clean, exchange)
    if price is not None:
        return price, "angel"

    price = fetch_ltp_yfinance(yf_symbol)
    if price is not None:
        return price, "yfinance"

    return None, "none"


@st.cache_data(ttl=60)
def fetch_sector_pct(yahoo_sym: str) -> float | None:
    """Cache sector index % change for 60s."""
    try:
        t = yf.Ticker(yahoo_sym)
        info = t.fast_info
        prev  = info.get("previousClose") or info.get("regularMarketPreviousClose")
        price = info.get("last_price") or info.get("regularMarketPrice")
        if prev and price and prev != 0:
            return round((price - prev) / prev * 100, 2)
        return None
    except Exception:
        return None


# ══════════════════════════════════════════
#  STATUS LOGIC (mirrors watchlist.js)
# ══════════════════════════════════════════

def compute_status(stock: dict, ltp: float) -> str:
    entry   = stock.get("entry")
    sl      = stock.get("sl")
    target1 = stock.get("target1")
    target2 = stock.get("target2")
    direction = stock.get("direction", "BUY")

    if not entry:
        return "WATCHING"

    if direction == "BUY":
        if sl and ltp <= sl:
            return "SL_HIT"
        if target2 and ltp >= target2:
            return "TARGET2"
        if target1 and ltp >= target1:
            return "TARGET1"
        if ltp >= entry:
            return "TRIGGERED"
        near_pct = abs(ltp - entry) / entry
        if near_pct <= 0.01:
            return "NEAR"
    else:  # SELL
        if sl and ltp >= sl:
            return "SL_HIT"
        if target2 and ltp <= target2:
            return "TARGET2"
        if target1 and ltp <= target1:
            return "TARGET1"
        if ltp <= entry:
            return "TRIGGERED"
        near_pct = abs(ltp - entry) / entry
        if near_pct <= 0.01:
            return "NEAR"

    return "WATCHING"


STATUS_LABELS = {
    "WATCHING":  "👁 Watching",
    "NEAR":      "⚠ Near Entry",
    "TRIGGERED": "✓ Triggered",
    "SL_HIT":    "✕ SL Hit",
    "TARGET1":   "🎯 T1 Hit",
    "TARGET2":   "🏆 T2 Hit",
}

STATUS_COLORS = {
    "WATCHING":  "#888",
    "NEAR":      "#EF9F27",
    "TRIGGERED": "#1D9E75",
    "SL_HIT":    "#E24B4A",
    "TARGET1":   "#378ADD",
    "TARGET2":   "#7F77DD",
}


def fmt_price(v) -> str:
    if v is None or v != v:
        return "---"
    return f"₹{float(v):,.2f}"


def pct_from_entry(ltp: float, entry: float) -> str:
    if not ltp or not entry:
        return ""
    pct = (ltp - entry) / entry * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


# ══════════════════════════════════════════
#  SESSION STATE INIT
# ══════════════════════════════════════════

if "current_tab" not in st.session_state:
    st.session_state.current_tab = "Today"
if "edit_index" not in st.session_state:
    st.session_state.edit_index = None
if "price_source" not in st.session_state:
    st.session_state.price_source = {}


# ══════════════════════════════════════════
#  SIDEBAR — Add Stock Form
# ══════════════════════════════════════════

with st.sidebar:
    st.markdown("### ➕ Add Stock")

    col_dir1, col_dir2 = st.columns(2)
    with col_dir1:
        buy_btn  = st.button("▲ BUY",  use_container_width=True,
                             type="primary" if st.session_state.get("direction","BUY")=="BUY" else "secondary")
    with col_dir2:
        sell_btn = st.button("▼ SELL", use_container_width=True,
                             type="primary" if st.session_state.get("direction","BUY")=="SELL" else "secondary")

    if buy_btn:
        st.session_state.direction = "BUY"
    if sell_btn:
        st.session_state.direction = "SELL"

    direction = st.session_state.get("direction", "BUY")
    st.caption(f"{'🟢 Long — triggers above entry' if direction == 'BUY' else '🔴 Short — triggers below entry'}")

    col_ex1, col_ex2 = st.columns(2)
    with col_ex1:
        nse_btn = st.button("NSE", use_container_width=True)
    with col_ex2:
        bse_btn = st.button("BSE", use_container_width=True)

    if nse_btn:
        st.session_state.exchange = "NS"
    if bse_btn:
        st.session_state.exchange = "BO"
    exchange = st.session_state.get("exchange", "NS")
    st.caption(f"Exchange: {'NSE' if exchange == 'NS' else 'BSE'}")

    symbol = st.text_input("Symbol", placeholder="e.g. RELIANCE").upper().strip()
    entry  = st.number_input("Entry Price ₹", min_value=0.0, format="%.2f")
    sl     = st.number_input("Stop Loss ₹",  min_value=0.0, format="%.2f")
    t1     = st.number_input("Target 1 ₹",   min_value=0.0, format="%.2f")
    t2     = st.number_input("Target 2 ₹",   min_value=0.0, format="%.2f")
    note   = st.text_input("Note (optional)")

    pos_limit_warn = ""
    add_tab = st.session_state.current_tab

    if st.button(f"{'+ ADD LONG' if direction=='BUY' else '+ ADD SHORT'} → {add_tab}",
                 use_container_width=True, type="primary"):
        if not symbol:
            st.error("Symbol is required")
        elif entry <= 0:
            st.error("Entry price is required")
        else:
            lst = get_list(add_tab)
            # Position limit: max 3 per direction
            dir_count = sum(1 for s in lst if s.get("direction") == direction)
            if dir_count >= 3:
                st.warning(f"⛔ Max 3 {direction} positions in {add_tab}. Remove one first.")
            else:
                clean_sym = symbol.replace(".NS", "").replace(".BO", "")
                sector = get_stock_sector(clean_sym)
                stock = {
                    "symbol":    clean_sym,
                    "exchange":  exchange,
                    "direction": direction,
                    "entry":     entry,
                    "sl":        sl if sl > 0 else None,
                    "target1":   t1 if t1 > 0 else None,
                    "target2":   t2 if t2 > 0 else None,
                    "note":      note.strip() or None,
                    "sector":    sector,
                    "status":    "WATCHING",
                    "lastPrice": None,
                    "added_at":  datetime.now().isoformat(),
                }
                lst.append(stock)
                set_list(add_tab, lst)
                st.success(f"✅ {clean_sym} added to {add_tab}")
                st.rerun()

    st.divider()
    st.markdown("### ⚙ Sort")
    sort_by = st.selectbox("Sort by", ["Default", "Status", "Symbol", "Distance to Entry"])


# ══════════════════════════════════════════
#  MAIN — Watchlist Tabs
# ══════════════════════════════════════════

tab_cols = st.columns(len(WATCHLIST_NAMES))
for i, name in enumerate(WATCHLIST_NAMES):
    with tab_cols[i]:
        cnt = len(get_list(name))
        is_active = st.session_state.current_tab == name
        label = f"**{name}** ({cnt})" if is_active else f"{name} ({cnt})"
        if st.button(label, key=f"tab_{name}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.current_tab = name
            st.rerun()

st.divider()

current_tab = st.session_state.current_tab
watchlist   = get_list(current_tab)

# Refresh button
col_head1, col_head2, col_head3 = st.columns([4, 1, 1])
with col_head1:
    st.markdown(f"#### {current_tab} · {len(watchlist)} stock{'s' if len(watchlist) != 1 else ''}")
with col_head2:
    refresh = st.button("↺ Refresh", use_container_width=True)
with col_head3:
    if st.button("🗑 Clear All", use_container_width=True):
        if watchlist:
            set_list(current_tab, [])
            st.rerun()

# ── FETCH PRICES & UPDATE STATUS ──
if watchlist and refresh:
    updated = []
    progress = st.progress(0, text="Fetching prices...")
    for i, stock in enumerate(watchlist):
        ltp, source = fetch_ltp(stock["symbol"], stock.get("exchange", "NS"))
        stock = stock.copy()
        stock["lastPrice"] = ltp
        if ltp:
            stock["status"] = compute_status(stock, ltp)
            st.session_state.price_source[stock["symbol"]] = source
        updated.append(stock)
        progress.progress((i + 1) / len(watchlist),
                          text=f"Fetching {stock['symbol']}... ({source})")
    progress.empty()
    set_list(current_tab, updated)
    watchlist = updated

# ── SORT ──
def sort_watchlist(lst, sort_by):
    order = {"SL_HIT": 0, "TRIGGERED": 1, "NEAR": 2, "TARGET1": 3, "TARGET2": 4, "WATCHING": 5}
    if sort_by == "Status":
        return sorted(lst, key=lambda s: order.get(s.get("status", "WATCHING"), 9))
    if sort_by == "Symbol":
        return sorted(lst, key=lambda s: s.get("symbol", ""))
    if sort_by == "Distance to Entry":
        def dist(s):
            ltp   = s.get("lastPrice")
            entry = s.get("entry")
            if ltp and entry:
                return abs(ltp - entry) / entry
            return 999
        return sorted(lst, key=dist)
    return lst

watchlist_sorted = sort_watchlist(watchlist, sort_by)

# ── EMPTY STATE ──
if not watchlist:
    st.info(f"📭 No stocks in {current_tab} yet. Use the sidebar to add one.")
    st.stop()


# ══════════════════════════════════════════
#  RENDER CARDS
# ══════════════════════════════════════════

# Find original index for edit/delete by matching symbol+entry+direction
def orig_idx(stock):
    raw = get_list(current_tab)
    for i, s in enumerate(raw):
        if (s.get("symbol") == stock.get("symbol") and
                s.get("entry") == stock.get("entry") and
                s.get("direction") == stock.get("direction")):
            return i
    return None


CARDS_PER_ROW = 3
rows = [watchlist_sorted[i:i+CARDS_PER_ROW] for i in range(0, len(watchlist_sorted), CARDS_PER_ROW)]

for row in rows:
    cols = st.columns(CARDS_PER_ROW)
    for col, stock in zip(cols, row):
        with col:
            sym       = stock.get("symbol", "")
            direction = stock.get("direction", "BUY")
            exchange  = stock.get("exchange", "NS")
            status    = stock.get("status", "WATCHING")
            ltp       = stock.get("lastPrice")
            entry     = stock.get("entry")
            sl        = stock.get("sl")
            t1        = stock.get("target1")
            t2        = stock.get("target2")
            note      = stock.get("note")
            sector    = stock.get("sector")
            color     = STATUS_COLORS.get(status, "#888")
            src       = st.session_state.price_source.get(sym, "")

            # Sector %
            sect_pct_str = ""
            if sector and sector in SECTOR_YAHOO:
                pct = fetch_sector_pct(SECTOR_YAHOO[sector])
                if pct is not None:
                    sign = "+" if pct >= 0 else ""
                    sect_pct_str = f"{sector} {sign}{pct}%"

            # % from entry
            pct_str = pct_from_entry(ltp, entry) if ltp else ""
            pct_color = "green" if pct_str.startswith("+") else "red" if pct_str.startswith("-") else "gray"

            # Smart exit signals (after TRIGGERED)
            exit_signals = []
            if status == "TRIGGERED" and ltp and entry:
                if direction == "BUY" and ltp < entry:
                    exit_signals.append("⚠ Price below entry — consider exit")

            with st.container(border=True):
                # Header row
                h1, h2 = st.columns([3, 1])
                with h1:
                    side_icon = "▲" if direction == "BUY" else "▼"
                    side_color = "green" if direction == "BUY" else "red"
                    exch_label = "NSE" if exchange == "NS" else "BSE"
                    st.markdown(
                        f"**{sym}** "
                        f"<span style='color:{side_color};font-size:12px'>{side_icon} {direction}</span> "
                        f"<span style='background:#333;color:#aaa;font-size:10px;padding:1px 5px;border-radius:3px'>{exch_label}</span>",
                        unsafe_allow_html=True
                    )
                with h2:
                    st.markdown(
                        f"<span style='color:{color};font-size:11px;font-weight:600'>{STATUS_LABELS.get(status,'')}</span>",
                        unsafe_allow_html=True
                    )

                # LTP
                if ltp:
                    ltp_src = f" <span style='font-size:9px;color:#888'>via {src}</span>" if src else ""
                    st.markdown(
                        f"<span style='font-size:22px;font-weight:700'>{fmt_price(ltp)}</span>"
                        f" <span style='color:{pct_color};font-size:12px'>{pct_str} from entry</span>"
                        f"{ltp_src}",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown("<span style='color:#888;font-size:18px'>--- no price</span>",
                                unsafe_allow_html=True)

                # Levels
                lv1, lv2, lv3, lv4 = st.columns(4)
                with lv1:
                    st.metric("Entry", fmt_price(entry))
                with lv2:
                    st.metric("SL", fmt_price(sl))
                with lv3:
                    st.metric("T1", fmt_price(t1))
                with lv4:
                    st.metric("T2", fmt_price(t2))

                # Sector tag
                if sect_pct_str:
                    s_color = "green" if "+" in sect_pct_str else "red"
                    st.markdown(
                        f"<span style='font-size:11px;color:{s_color}'>{sect_pct_str}</span>",
                        unsafe_allow_html=True
                    )

                # Note
                if note:
                    st.caption(f"📝 {note}")

                # Exit signals
                for sig in exit_signals:
                    st.warning(sig)

                # Action buttons
                a1, a2, a3 = st.columns(3)
                idx = orig_idx(stock)

                with a1:
                    if st.button("↺ Reset", key=f"reset_{sym}_{idx}_{current_tab}",
                                 use_container_width=True):
                        lst = get_list(current_tab)
                        if idx is not None:
                            lst[idx]["status"] = "WATCHING"
                            lst[idx]["lastPrice"] = None
                            set_list(current_tab, lst)
                            st.rerun()
                with a2:
                    if st.button("✏ Edit", key=f"edit_{sym}_{idx}_{current_tab}",
                                 use_container_width=True):
                        st.session_state.edit_index = idx
                        st.session_state.edit_tab   = current_tab
                with a3:
                    if st.button("✕ Del", key=f"del_{sym}_{idx}_{current_tab}",
                                 use_container_width=True):
                        lst = get_list(current_tab)
                        if idx is not None:
                            lst.pop(idx)
                            set_list(current_tab, lst)
                            st.rerun()


# ══════════════════════════════════════════
#  EDIT MODAL (inline expander)
# ══════════════════════════════════════════

if st.session_state.edit_index is not None:
    idx     = st.session_state.edit_index
    tab     = st.session_state.get("edit_tab", current_tab)
    lst     = get_list(tab)

    if idx < len(lst):
        s = lst[idx]
        st.divider()
        with st.expander(f"✏ Edit — {s.get('symbol', '')}", expanded=True):
            ec1, ec2 = st.columns(2)
            with ec1:
                new_entry = st.number_input("Entry ₹",   value=float(s.get("entry") or 0), format="%.2f", key="e_entry")
                new_sl    = st.number_input("SL ₹",      value=float(s.get("sl") or 0),    format="%.2f", key="e_sl")
            with ec2:
                new_t1    = st.number_input("Target 1 ₹", value=float(s.get("target1") or 0), format="%.2f", key="e_t1")
                new_t2    = st.number_input("Target 2 ₹", value=float(s.get("target2") or 0), format="%.2f", key="e_t2")
            new_note = st.text_input("Note", value=s.get("note") or "", key="e_note")

            sv1, sv2 = st.columns(2)
            with sv1:
                if st.button("💾 Save", use_container_width=True, type="primary"):
                    lst[idx].update({
                        "entry":   new_entry if new_entry > 0 else s.get("entry"),
                        "sl":      new_sl    if new_sl > 0 else None,
                        "target1": new_t1    if new_t1 > 0 else None,
                        "target2": new_t2    if new_t2 > 0 else None,
                        "note":    new_note.strip() or None,
                    })
                    set_list(tab, lst)
                    st.session_state.edit_index = None
                    st.success("Saved!")
                    st.rerun()
            with sv2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.edit_index = None
                    st.rerun()


# ══════════════════════════════════════════
#  FOOTER
# ══════════════════════════════════════════

st.divider()
angel_status = "🟢 Angel One connected" if get_angel_session() else "🟡 Angel One offline — using yfinance"
st.caption(f"{angel_status}  ·  Data refreshes on ↺ Refresh  ·  Stored in watchlist.json")
