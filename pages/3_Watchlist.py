# ══════════════════════════════════════════
#  TRADESENTRY — pages/3_Watchlist.py
#  Single row card design - all data inline
# ══════════════════════════════════════════

import streamlit as st
import json, os, pyotp, yfinance as yf
from datetime import datetime
from SmartApi import SmartConnect

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from stocks import SECTOR_YAHOO, get_stock_token, get_stock_sector
from styles import apply_styles, sidebar_brand, page_header

st.set_page_config(
    page_title="Watchlist · TradeSentry",
    layout="wide",
    page_icon="👁",
    initial_sidebar_state="collapsed"
)
apply_styles()
sidebar_brand()
page_header("Watchlist", "Track your trades")


# ══════════════════════════════════════════
#  SOUND ALERT
# ══════════════════════════════════════════

def play_alert_sound(alert_type="triggered"):
    if alert_type == "triggered":
        freq, dur = 800, 300
    elif alert_type == "sl_hit":
        freq, dur = 400, 500
    else:
        freq, dur = 1200, 200
    
    html_code = f"""<script>
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ac.createOscillator(), gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.frequency.value = {freq}; osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ac.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ac.currentTime + {dur/1000});
    osc.start(ac.currentTime); osc.stop(ac.currentTime + {dur/1000});
    </script>"""
    st.components.v1.html(html_code, height=0)


# ══════════════════════════════════════════
#  STORAGE
# ══════════════════════════════════════════

WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

def load_all() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}
    try:
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}

def save_all(data: dict):
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Save error: {e}")

def get_list(tab: str) -> list:
    d = load_all()
    for n in WATCHLIST_NAMES:
        d.setdefault(f"watchlist_{n}", [])
    return d.get(f"watchlist_{tab}", [])

def set_list(tab: str, lst: list):
    data = load_all()
    data[f"watchlist_{tab}"] = lst
    save_all(data)


# ══════════════════════════════════════════
#  ANGEL ONE
# ══════════════════════════════════════════

@st.cache_resource(ttl=3600)
def get_angel_session():
    try:
        obj = SmartConnect(api_key=st.secrets["API_KEY"])
        totp = pyotp.TOTP(st.secrets["TOTP_SECRET"]).now()
        sess = obj.generateSession(st.secrets["CLIENT_CODE"], st.secrets["PASSWORD"], totp)
        return obj if sess.get("status") else None
    except:
        return None


# ══════════════════════════════════════════
#  PRICE FETCH
# ══════════════════════════════════════════

def fetch_ltp_angel(symbol: str, exchange: str) -> float | None:
    try:
        obj = get_angel_session()
        if not obj: return None
        token = get_stock_token(symbol)
        if not token: return None
        resp = obj.ltpData("NSE" if exchange == "NS" else "BSE", symbol, token)
        if resp and resp.get("status"):
            return float(resp["data"]["ltp"])
    except:
        pass
    return None

def fetch_ltp_yfinance(symbol: str, exchange: str) -> float | None:
    try:
        suffix = ".NS" if exchange == "NS" else ".BO"
        t = yf.Ticker(f"{symbol}{suffix}")
        p = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        return float(p) if p else None
    except:
        return None

def fetch_ltp(symbol: str, exchange: str) -> tuple[float | None, str]:
    p = fetch_ltp_angel(symbol, exchange)
    if p: return p, "angel"
    p = fetch_ltp_yfinance(symbol, exchange)
    if p: return p, "yfinance"
    return None, "none"


# ══════════════════════════════════════════
#  STATUS LOGIC
# ══════════════════════════════════════════

def compute_status(stock: dict, ltp: float) -> str:
    entry, sl, t1, t2 = stock.get("entry"), stock.get("sl"), stock.get("target1"), stock.get("target2")
    d = stock.get("direction", "BUY")
    if not entry: return "WATCHING"
    if d == "BUY":
        if sl and ltp <= sl: return "SL_HIT"
        if t2 and ltp >= t2: return "TARGET2"
        if t1 and ltp >= t1: return "TARGET1"
        if ltp >= entry: return "TRIGGERED"
        if abs(ltp - entry) / entry <= 0.01: return "NEAR"
    else:
        if sl and ltp >= sl: return "SL_HIT"
        if t2 and ltp <= t2: return "TARGET2"
        if t1 and ltp <= t1: return "TARGET1"
        if ltp <= entry: return "TRIGGERED"
        if abs(ltp - entry) / entry <= 0.01: return "NEAR"
    return "WATCHING"

STATUS_LABEL = {
    "WATCHING": "Watching",
    "NEAR": "Near Entry", 
    "TRIGGERED": "Entry Triggered",
    "SL_HIT": "SL Hit",
    "TARGET1": "T1 Hit",
    "TARGET2": "T2 Hit"
}
STATUS_COLOR = {
    "WATCHING": "#f59e0b",
    "NEAR": "#f59e0b",
    "TRIGGERED": "#00a854",
    "SL_HIT": "#e53935",
    "TARGET1": "#2563eb",
    "TARGET2": "#7c3aed"
}

def fmt(v) -> str:
    if v is None: return "---"
    try: return f"₹{float(v):,.0f}"
    except: return "---"


# ══════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════

for k, v in [("current_tab","Today"), ("direction","BUY"), ("exchange","NS"),
             ("f_symbol",""), ("f_entry",0.0), ("f_sl",0.0), ("f_t1",0.0), ("f_t2",0.0),
             ("edit_idx",None), ("edit_tab",None), ("price_source",{}), ("sort_by","default"),
             ("sort_open",False), ("sound_enabled",True)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════
#  ADD TRADE FORM
# ══════════════════════════════════════════

with st.expander("➕ ADD TRADE", expanded=False):
    st.markdown(
        '<div style="font-size:11px;color:var(--text3);font-family:var(--mono);'
        'background:var(--bg3);border-radius:6px;padding:8px 12px;margin-bottom:12px">'
        '⚡ Smart paste: <b>RELIANCE 2800 2750 2900 2950</b></div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="ts-section-label">Trade Direction</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        if st.button("▲ BUY", use_container_width=True, key="add_buy",
                     type="primary" if st.session_state.direction == "BUY" else "secondary"):
            st.session_state.direction = "BUY"; st.rerun()
    with d2:
        if st.button("▼ SELL", use_container_width=True, key="add_sell",
                     type="primary" if st.session_state.direction == "SELL" else "secondary"):
            st.session_state.direction = "SELL"; st.rerun()

    st.markdown('<div class="ts-section-label" style="margin-top:10px">Symbol</div>', unsafe_allow_html=True)
    raw_input = st.text_input("", value=st.session_state.f_symbol,
                              placeholder="RELIANCE 2800 2750 2900 2950",
                              key="raw_symbol_input", label_visibility="collapsed")

    if raw_input:
        parts = raw_input.strip().upper().split()
        if len(parts) >= 1:
            st.session_state.f_symbol = parts[0]
            nums = []
            for p in parts[1:]:
                try: nums.append(float(p))
                except: pass
            if len(nums) >= 1: st.session_state.f_entry = nums[0]
            if len(nums) >= 2: st.session_state.f_sl = nums[1]
            if len(nums) >= 3: st.session_state.f_t1 = nums[2]
            if len(nums) >= 4: st.session_state.f_t2 = nums[3]

    symbol = st.session_state.f_symbol.replace(".NS","").replace(".BO","").upper().strip()

    st.markdown('<div class="ts-section-label" style="margin-top:10px">Exchange</div>', unsafe_allow_html=True)
    ex1, ex2 = st.columns(2)
    with ex1:
        if st.button("NSE", use_container_width=True, key="add_nse",
                     type="primary" if st.session_state.exchange == "NS" else "secondary"):
            st.session_state.exchange = "NS"; st.rerun()
    with ex2:
        if st.button("BSE", use_container_width=True, key="add_bse",
                     type="primary" if st.session_state.exchange == "BO" else "secondary"):
            st.session_state.exchange = "BO"; st.rerun()

    st.markdown('<div class="ts-section-label" style="margin-top:10px">Price Levels</div>', unsafe_allow_html=True)
    st.markdown("**Entry**")
    entry = st.number_input("", value=st.session_state.f_entry, min_value=0.0, format="%.0f",
                            key="add_entry", label_visibility="collapsed")
    sl_col, t1_col = st.columns(2)
    with sl_col:
        st.markdown("**SL**")
        sl = st.number_input("", value=st.session_state.f_sl, min_value=0.0, format="%.0f",
                             key="add_sl", label_visibility="collapsed")
    with t1_col:
        st.markdown("**T1**")
        t1 = st.number_input("", value=st.session_state.f_t1, min_value=0.0, format="%.0f",
                             key="add_t1", label_visibility="collapsed")
    st.markdown("**T2** (optional)")
    t2 = st.number_input("", value=st.session_state.f_t2, min_value=0.0, format="%.0f",
                         key="add_t2", label_visibility="collapsed")
    st.markdown("**Notes** (optional)")
    note = st.text_input("", placeholder="e.g. Breakout", key="add_note", label_visibility="collapsed")

    if st.button(f"{'▲ ADD LONG' if st.session_state.direction=='BUY' else '▼ ADD SHORT'} → {st.session_state.current_tab}",
                 use_container_width=True, type="primary", key="add_submit"):
        if not symbol:
            st.error("Symbol required")
        elif entry <= 0:
            st.error("Entry required")
        else:
            lst = get_list(st.session_state.current_tab)
            dup = [s for s in lst if s.get("symbol")==symbol and s.get("exchange")==st.session_state.exchange 
                                      and s.get("direction")==st.session_state.direction]
            if dup:
                st.error(f"⚠ {symbol} {st.session_state.direction} already exists")
            else:
                lst.append({
                    "symbol": symbol, "exchange": st.session_state.exchange, "direction": st.session_state.direction,
                    "entry": entry, "sl": sl if sl > 0 else None, "target1": t1 if t1 > 0 else None,
                    "target2": t2 if t2 > 0 else None, "note": note.strip() or None,
                    "sector": get_stock_sector(symbol), "status": "WATCHING", "lastPrice": None,
                    "added_at": datetime.now().isoformat(),
                })
                set_list(st.session_state.current_tab, lst)
                for k in ["f_symbol","f_entry","f_sl","f_t1","f_t2"]:
                    st.session_state[k] = "" if k == "f_symbol" else 0.0
                st.success(f"✅ {symbol} added!")
                st.rerun()

st.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════

tc1, tc2, tc3 = st.columns(3)
for i, name in enumerate([tc1, tc2, tc3]):
    with name:
        cnt = len(get_list(WATCHLIST_NAMES[i]))
        is_active = st.session_state.current_tab == WATCHLIST_NAMES[i]
        if st.button(f"{'● ' if is_active else ''}{WATCHLIST_NAMES[i]}  ({cnt})",
                     key=f"tab_{WATCHLIST_NAMES[i]}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.current_tab = WATCHLIST_NAMES[i]
            st.rerun()

st.markdown('<hr class="ts-divider">', unsafe_allow_html=True)

current_tab = st.session_state.current_tab
watchlist = get_list(current_tab)

# Header Controls
h1, h2, h3, h4 = st.columns([2.5, 0.8, 0.8, 0.8])
with h1:
    st.markdown(f'<div class="ts-section-label">{current_tab} · {len(watchlist)} stock{"s" if len(watchlist)!=1 else ""}</div>',
                unsafe_allow_html=True)
with h2:
    if st.button("Sort", use_container_width=True, key="sort_btn"):
        st.session_state.sort_open = not st.session_state.sort_open
        st.rerun()
with h3:
    refresh = st.button("↺", use_container_width=True, help="Refresh", key="refresh_btn")
with h4:
    if st.button("🗑", use_container_width=True, help="Clear all", key="clear_btn"):
        if watchlist:
            set_list(current_tab, [])
            st.rerun()

# Sort panel
if st.session_state.sort_open:
    s1, s2, s3, s4 = st.columns(4)
    for btn, lbl in [(s1, "Default"), (s2, "Status"), (s3, "Symbol"), (s4, "Distance")]:
        with btn:
            key = lbl.lower()
            if st.button(lbl, use_container_width=True, key=f"sort_{key}",
                        type="primary" if st.session_state.sort_by == key else "secondary"):
                st.session_state.sort_by = key
                st.rerun()

# Sound toggle
col1, col2, col3 = st.columns([4, 1, 1])
with col3:
    if st.button(f"{'🔊' if st.session_state.sound_enabled else '🔇'} Sound", use_container_width=True, key="sound_toggle"):
        st.session_state.sound_enabled = not st.session_state.sound_enabled
        st.rerun()

# Fetch prices
if watchlist and refresh:
    updated = []
    progress = st.progress(0, text="Fetching...")
    for i, stock in enumerate(watchlist):
        ltp, source = fetch_ltp(stock["symbol"], stock.get("exchange","NS"))
        s = stock.copy()
        s["lastPrice"] = ltp
        old_status = stock.get("status", "WATCHING")
        if ltp:
            s["status"] = compute_status(s, ltp)
            st.session_state.price_source[s["symbol"]] = source
            
            if st.session_state.sound_enabled and s["status"] != old_status:
                if s["status"] == "SL_HIT":
                    play_alert_sound("sl_hit")
                elif s["status"] in ["TARGET1", "TARGET2"]:
                    play_alert_sound("target")
                elif s["status"] == "TRIGGERED":
                    play_alert_sound("triggered")
        updated.append(s)
        progress.progress((i+1)/len(watchlist))
    progress.empty()
    set_list(current_tab, updated)
    watchlist = updated

# Sort Data
def sort_list(lst, by):
    order = {"SL_HIT":0,"TRIGGERED":1,"NEAR":2,"TARGET1":3,"TARGET2":4,"WATCHING":5}
    if by == "status":
        return sorted(lst, key=lambda s: order.get(s.get("status","WATCHING"), 9))
    if by == "symbol":
        return sorted(lst, key=lambda s: s.get("symbol",""))
    if by == "distance":
        def dist(s):
            ltp = s.get("lastPrice"); e = s.get("entry")
            return abs(ltp-e)/e if ltp and e else 999
        return sorted(lst, key=dist)
    return lst

watchlist = sort_list(watchlist, st.session_state.sort_by)

# Empty state
if not watchlist:
    st.markdown(
        '<div class="ts-card" style="text-align:center;padding:40px">'
        '<div style="font-size:32px">📭</div>'
        '<div style="color:var(--text2);margin-top:8px">No stocks in <b>' + current_tab + '</b></div>'
        '</div>',
        unsafe_allow_html=True
    )
    st.stop()


# ══════════════════════════════════════════
#  SINGLE ROW CARD DISPLAY
# ══════════════════════════════════════════

for stock_idx, stock in enumerate(watchlist):
    sym = stock.get("symbol","")
    dirn = stock.get("direction","BUY")
    status = stock.get("status","WATCHING")
    ltp = stock.get("lastPrice")
    entry = stock.get("entry")
    sl = stock.get("sl")
    t1 = stock.get("target1")
    t2 = stock.get("target2")
    note = stock.get("note", "")
    src = st.session_state.price_source.get(sym,"")

    pct_val = ""
    pct_color = "#7a8394"
    if ltp and entry:
        p = (ltp - entry) / entry * 100
        pct_val = f"{'+' if p >= 0 else ''}{p:.2f}%"
        pct_color = "#00a854" if p >= 0 else "#e53935"

    src_badge = "⚡" if src == "angel" else ("yf" if src == "yfinance" else "")
    status_color = STATUS_COLOR.get(status, "#f59e0b")
    status_text = STATUS_LABEL.get(status, "")

    if st.session_state.edit_idx == stock_idx and st.session_state.edit_tab == current_tab:
        # ── EDIT MODE ──
        st.markdown(f'<div class="ts-section-label">Edit — {sym}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            e1, e2 = st.columns(2)
            with e1:
                ne = st.number_input("Entry", value=int(stock.get("entry") or 0), format="%d", key=f"e_en_{stock_idx}")
                ns = st.number_input("SL", value=int(stock.get("sl") or 0), format="%d", key=f"e_sl_{stock_idx}")
            with e2:
                nt1 = st.number_input("T1", value=int(stock.get("target1") or 0), format="%d", key=f"e_t1_{stock_idx}")
                nt2 = st.number_input("T2", value=int(stock.get("target2") or 0), format="%d", key=f"e_t2_{stock_idx}")
            nn = st.text_input("Note", value=stock.get("note") or "", key=f"e_note_{stock_idx}")
            s1, s2 = st.columns(2)
            with s1:
                if st.button("💾 Save", use_container_width=True, type="primary", key=f"save_{stock_idx}"):
                    lst = get_list(current_tab)
                    lst[stock_idx].update({
                        "entry": ne if ne > 0 else stock.get("entry"),
                        "sl": ns if ns > 0 else None,
                        "target1": nt1 if nt1 > 0 else None,
                        "target2": nt2 if nt2 > 0 else None,
                        "note": nn.strip() or None,
                    })
                    set_list(current_tab, lst)
                    st.session_state.edit_idx = None
                    st.session_state.edit_tab = None
                    st.rerun()
            with s2:
                if st.button("Cancel", use_container_width=True, key=f"cancel_{stock_idx}"):
                    st.session_state.edit_idx = None
                    st.session_state.edit_tab = None
                    st.rerun()
    else:
        # ── DISPLAY MODE — SINGLE ROW ──
        buy_bg = "#f0faf5" if dirn == "BUY" else "#fff5f5"
        buy_color = "#00a854" if dirn == "BUY" else "#e53935"
        buy_text = "▲ BUY" if dirn == "BUY" else "▼ SELL"
        ltp_display = fmt(ltp) if ltp else "---"
        sector_name = stock.get("sector") or "NSE Stock"

        # Unified Clean Layout Row using pure CSS Flex alignment
        card_html = f"""
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; 
                    background: #ffffff; border: 1px solid #e0e3e8; border-left: 4px solid {status_color}; 
                    border-radius: 8px; margin-bottom: 4px; flex-wrap: nowrap; box-shadow: 0 1px 2px rgba(0,0,0,0.01);">
            
            <div style="display: flex; align-items: center; gap: 14px;">
                <div style="display: flex; flex-direction: column; min-width: 110px;">
                    <span style="font-family: monospace; font-weight: 800; font-size: 15px; color: #0f1117; letter-spacing: 0.2px;">{sym}</span>
                    <span style="font-size: 10px; color: #7a8394; margin-top: 1px;">{sector_name}</span>
                </div>
                
                <span style="font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; background: {buy_bg}; color: {buy_color}; white-space: nowrap;">
                    {buy_text}
                </span>
                
                <div style="display: flex; align-items: baseline; gap: 6px; min-width: 90px; margin-left: 2px;">
                    <span style="font-family: monospace; font-weight: 700; font-size: 15px; color: #0f1117;">{ltp_display}</span>
                    <span style="color: {pct_color}; font-family: monospace; font-weight: 600; font-size: 11px;">{pct_val}</span>
                </div>
            </div>

            <div style="display: flex; align-items: center; gap: 8px; font-family: monospace; font-size: 11px; margin-left: 10px;">
                <div style="border: 1px solid #e0e3e8; background: #fafbfc; padding: 3px 8px; border-radius: 5px; white-space: nowrap;">
                    <span style="color: #7a8394; font-weight: 600;">Entry:</span> <span style="color: #0f1117; font-weight: 700;">{fmt(entry)}</span>
                </div>
                <div style="border: 1px solid #fcd9d7; background: #fff5f5; padding: 3px 8px; border-radius: 5px; white-space: nowrap;">
                    <span style="color: #e53935; font-weight: 600;">SL:</span> <span style="color: #e53935; font-weight: 700;">{fmt(sl)}</span>
                </div>
                <div style="border: 1px solid #d4f0de; background: #f5fdf8; padding: 3px 8px; border-radius: 5px; white-space: nowrap;">
                    <span style="color: #00a854; font-weight: 600;">T1:</span> <span style="color: #00a854; font-weight: 700;">{fmt(t1)}</span>
                </div>
                <div style="border: 1px solid #d4f0de; background: #f5fdf8; padding: 3px 8px; border-radius: 5px; white-space: nowrap;">
                    <span style="color: #00a854; font-weight: 600;">T2:</span> <span style="color: #00a854; font-weight: 700;">{fmt(t2)}</span>
                </div>
            </div>

            <div style="display: flex; align-items: center; margin-left: auto;">
                <span style="font-size: 10px; font-weight: 700; padding: 4px 10px; border-radius: 20px;
                             background: {status_color}12; color: {status_color}; border: 1px solid {status_color}25; white-space: nowrap;">
                    {status_text}
                </span>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        # Bottom Action Control Toolbar mapped cleanly under each line item
        ctrl_cols = st.columns([9.1, 0.3, 0.3, 0.3])
        with ctrl_cols[1]:
            if st.button("⟳", key=f"rst_{stock_idx}", use_container_width=True, help="Reset Status"):
                lst = get_list(current_tab)
                lst[stock_idx]["status"] = "WATCHING"
                lst[stock_idx]["lastPrice"] = None
                set_list(current_tab, lst)
                st.rerun()
        with ctrl_cols[2]:
            if st.button("✏", key=f"edt_{stock_idx}", use_container_width=True, help="Edit Trade"):
                st.session_state.edit_idx = stock_idx
                st.session_state.edit_tab = current_tab
                st.rerun()
        with ctrl_cols[3]:
            if st.button("✕", key=f"del_{stock_idx}", use_container_width=True, help="Delete Item"):
                lst = get_list(current_tab)
                lst.pop(stock_idx)
                set_list(current_tab, lst)
                st.rerun()

        # Contextual notes anchor
        if note:
            st.markdown(f'<div style="font-size: 11px; color: #7a8394; margin-left: 16px; margin-top: -6px; margin-bottom: 12px;">📝 {note}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="margin-bottom: 8px;"></div>', unsafe_allow_html=True)

# Footer
st.markdown('<hr class="ts-divider">', unsafe_allow_html=True)
angel_ok = get_angel_session() is not None
st.markdown(
    f'<div style="font-size:11px;color:var(--text3)">'
    f'{"🟢 Angel One" if angel_ok else "🟡 yfinance"} · watchlist.json</div>',
    unsafe_allow_html=True
)
