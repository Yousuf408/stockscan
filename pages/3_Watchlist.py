# ══════════════════════════════════════════
#   TRADESENTRY — pages/3_Watchlist.py  v3.1
#   Dynamic watchlists — create/rename/delete
#   v3.1: Fixed get_angel_session() — os.environ fallback for Railway
# ══════════════════════════════════════════

import streamlit as st
import os, pytz, yfinance as yf, time
from datetime import datetime

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from stocks import get_stock_token, get_stock_sector
from styles import apply_styles, sidebar_brand, page_header
from chart import render_chart
from core import (
    load_watchlist,
    save_watchlist,
    add_to_watchlist,
    delete_from_watchlist,
    update_watchlist_stock,
    clear_watchlist_tab,
    get_user_watchlist_names,
    create_user_watchlist,
    rename_user_watchlist,
    delete_user_watchlist,
    MAX_WATCHLISTS,
)

st.set_page_config(
    page_title="Watchlist · TradeSentry",
    layout="wide",
    page_icon="👁",
    initial_sidebar_state="collapsed"
)


apply_styles()
sidebar_brand("Watchlist")
page_header("Watchlist", "Track your trades")

# ══════════════════════════════════════════
#   TIMEZONE
# ══════════════════════════════════════════

IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(pytz.utc).astimezone(IST)

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    mins = n.hour * 60 + n.minute
    return (9*60+15) <= mins <= (15*60+30)

# ══════════════════════════════════════════
#   WATCHLIST STORAGE
# ══════════════════════════════════════════

def get_list(tab: str) -> list:
    try:
        return load_watchlist(tab)
    except Exception as e:
        st.error(f"Load error: {e}")
        return []

def set_list(tab: str, lst: list):
    try:
        all_data = load_watchlist()
        all_data[f"watchlist_{tab}"] = lst
        save_watchlist(all_data)
    except Exception as e:
        st.error(f"Save error: {e}")

# ══════════════════════════════════════════
#   SOUND ALERT
# ══════════════════════════════════════════

def play_alert_sound(alert_type="triggered"):
    if alert_type == "triggered":  freq, dur = 800, 300
    elif alert_type == "sl_hit":   freq, dur = 400, 500
    else:                          freq, dur = 1200, 200
    st.components.v1.html(f"""<script>
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ac.createOscillator(), gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.frequency.value = {freq}; osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ac.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ac.currentTime + {dur/1000});
    osc.start(ac.currentTime); osc.stop(ac.currentTime + {dur/1000});
    </script>""", height=0)

# ══════════════════════════════════════════
#   PRICE FETCH
# ══════════════════════════════════════════

AUTO_REFRESH_SECS = 300

@st.cache_resource
def get_angel_session():
    try:
        import pyotp
        from SmartApi import SmartConnect
        
        # Try st.secrets first, fall back to os.environ
        try:
            api_key     = st.secrets["API_KEY"]
            client_code = st.secrets["CLIENT_CODE"]
            password    = st.secrets["PASSWORD"]
            totp_secret = st.secrets["TOTP_SECRET"]
        except Exception:
            api_key     = os.environ.get("API_KEY", "")
            client_code = os.environ.get("CLIENT_CODE", "")
            password    = os.environ.get("PASSWORD", "")
            totp_secret = os.environ.get("TOTP_SECRET", "")
        
        if not all([api_key, client_code, password, totp_secret]):
            return None
        
        obj  = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        sess = obj.generateSession(client_code, password, totp)
        return obj if sess.get("status") else None
    except:
        return None

def clean_symbol(symbol: str) -> str:
    return symbol.lstrip("$").strip().upper().replace(".NS", "").replace(".BO", "")

def fetch_price_angel(symbol: str, exchange: str):
    try:
        obj = get_angel_session()
        if not obj: return None, "no_session"
        sym   = clean_symbol(symbol)
        token = get_stock_token(sym)
        if not token: return None, "no_token"
        resp  = obj.ltpData("NSE" if exchange == "NS" else "BSE", sym, str(token))
        if resp and resp.get("status"):
            return float(resp["data"]["ltp"]), "http"
    except:
        pass
    return None, "angel_failed"

def fetch_price_yfinance(symbol: str, exchange: str):
    try:
        sym    = clean_symbol(symbol)
        suffix = ".NS" if exchange == "NS" else ".BO"
        ticker = yf.Ticker(f"{sym}{suffix}")
        price  = (ticker.fast_info.get("last_price") or
                  ticker.fast_info.get("regularMarketPrice"))
        if not price:
            hist = ticker.history(period="2d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price:
            return float(price), "yfinance"
    except:
        pass
    return None, "yfinance_failed"

def fetch_all_prices(watchlist: list) -> dict:
    prices = {}
    if not watchlist:
        return prices
    if is_market_open():
        for stock in watchlist:
            sym  = stock.get("symbol", "")
            exch = stock.get("exchange", "NS")
            key  = f"{sym}_{exch}"
            price, source = fetch_price_angel(sym, exch)
            if price:
                prices[key] = {"price": price, "source": source,
                               "time": now_ist().strftime("%H:%M:%S")}
    missing = []
    for stock in watchlist:
        sym  = stock.get("symbol", "")
        exch = stock.get("exchange", "NS")
        key  = f"{sym}_{exch}"
        if key not in prices:
            missing.append((sym, exch))
    if not missing:
        return prices
    if len(missing) == 1:
        sym, exch = missing[0]
        key = f"{sym}_{exch}"
        price, source = fetch_price_yfinance(sym, exch)
        if price:
            prices[key] = {"price": price, "source": source,
                           "time": now_ist().strftime("%H:%M:%S")}
        return prices
    try:
        ns_syms  = [f"{clean_symbol(s)}.NS" for s, e in missing if e == "NS"]
        bo_syms  = [f"{clean_symbol(s)}.BO" for s, e in missing if e == "BO"]
        all_syms = ns_syms + bo_syms
        if all_syms:
            dl_period, dl_interval = ("1d", "1m") if is_market_open() else ("2d", "1d")
            data = yf.download(
                tickers=" ".join(all_syms), period=dl_period, interval=dl_interval,
                progress=False, auto_adjust=True, threads=True
            )
            for sym, exch in missing:
                key    = f"{sym}_{exch}"
                ticker = f"{clean_symbol(sym)}.{'NS' if exch == 'NS' else 'BO'}"
                try:
                    if hasattr(data.columns, "levels"):
                        price = float(data["Close"][ticker].dropna().iloc[-1])
                    else:
                        price = float(data["Close"].dropna().iloc[-1])
                    if price:
                        prices[key] = {"price": price, "source": "yfinance",
                                       "time": now_ist().strftime("%H:%M:%S")}
                except:
                    price, source = fetch_price_yfinance(sym, exch)
                    if price:
                        prices[key] = {"price": price, "source": source,
                                       "time": now_ist().strftime("%H:%M:%S")}
    except Exception as e:
        for sym, exch in missing:
            key = f"{sym}_{exch}"
            price, source = fetch_price_yfinance(sym, exch)
            if price:
                prices[key] = {"price": price, "source": source,
                               "time": now_ist().strftime("%H:%M:%S")}
    return prices

# ══════════════════════════════════════════
#   STATUS LOGIC
# ══════════════════════════════════════════

def compute_status(stock: dict, ltp: float) -> str:
    entry, sl, t1, t2 = stock.get("entry"), stock.get("sl"), stock.get("target1"), stock.get("target2")
    d = stock.get("direction", "BUY")
    if not entry: return "WATCHING"
    if d == "BUY":
        if sl and ltp <= sl:             return "SL_HIT"
        if t2 and ltp >= t2:             return "TARGET2"
        if t1 and ltp >= t1:             return "TARGET1"
        if ltp >= entry:                 return "TRIGGERED"
        if abs(ltp-entry)/entry <= 0.01: return "NEAR"
    else:
        if sl and ltp >= sl:             return "SL_HIT"
        if t2 and ltp <= t2:             return "TARGET2"
        if t1 and ltp <= t1:             return "TARGET1"
        if ltp <= entry:                 return "TRIGGERED"
        if abs(ltp-entry)/entry <= 0.01: return "NEAR"
    return "WATCHING"

STATUS_LABEL = {
    "WATCHING": "Watching", "NEAR": "Near Entry",
    "TRIGGERED": "Entry Triggered", "SL_HIT": "SL Hit",
    "TARGET1": "T1 Hit", "TARGET2": "T2 Hit"
}
STATUS_COLOR = {
    "WATCHING": "#f59e0b", "NEAR": "#f59e0b",
    "TRIGGERED": "#00a854", "SL_HIT": "#e53935",
    "TARGET1": "#2563eb", "TARGET2": "#7c3aed"
}

def fmt(v) -> str:
    if v is None: return "---"
    try: return f"₹{float(v):,.0f}"
    except: return "---"

SOURCE_ICON = {
    "websocket": "🟢", "http": "🟡",
    "yfinance": "🟠", "close_price": "🟠", "offline": "⚪"
}

# ══════════════════════════════════════════
#   SESSION STATE
# ══════════════════════════════════════════

for k, v in [
    ("wl_names",         None),
    ("current_tab",      None),
    ("direction",        "BUY"),
    ("exchange",         "NS"),
    ("f_symbol",         ""),
    ("f_entry",          0.0),
    ("f_sl",             0.0),
    ("f_t1",             0.0),
    ("f_t2",             0.0),
    ("edit_idx",         None),
    ("edit_tab",         None),
    ("sort_by",          "default"),
    ("sort_open",        False),
    ("sound_enabled",    True),
    ("selected_symbol",  ""),
    ("selected_exchange","NS"),
    ("show_add_form",    False),
    ("prices",           {}),
    ("last_fetch_time",  None),
    ("fetching",         False),
    ("show_new_wl",      False),
    ("manage_wl",        None),   # which watchlist is being managed
]:
    if k not in st.session_state:
        st.session_state[k] = v

# Load watchlist names from Supabase once per session
if st.session_state.wl_names is None:
    st.session_state.wl_names = get_user_watchlist_names()

WATCHLIST_NAMES = st.session_state.wl_names

# Set default tab
if st.session_state.current_tab not in WATCHLIST_NAMES:
    st.session_state.current_tab = WATCHLIST_NAMES[0]

# ══════════════════════════════════════════
#   AUTO REFRESH LOGIC
# ══════════════════════════════════════════

def should_auto_refresh() -> bool:
    if not st.session_state.prices:
        return True
    if st.session_state.last_fetch_time is None:
        return True
    elapsed = (now_ist() - st.session_state.last_fetch_time).total_seconds()
    return elapsed >= AUTO_REFRESH_SECS

def do_price_fetch(watchlist: list):
    if not watchlist:
        return
    prices = fetch_all_prices(watchlist)
    st.session_state.prices.update(prices)
    st.session_state.last_fetch_time = now_ist()

# ══════════════════════════════════════════
#   MAIN LAYOUT
# ══════════════════════════════════════════

left_col, right_col = st.columns([3, 7], gap="small")

with left_col:

    # ── TOP CONTROLS ──
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        if st.button("➕", use_container_width=True, help="Add Trade", key="add_toggle"):
            st.session_state.show_add_form = not st.session_state.show_add_form
            st.rerun()
    with ctrl2:
        refresh = st.button("↺", use_container_width=True, help="Refresh prices", key="refresh_btn")
    with ctrl3:
        if st.button(f"{'🔊' if st.session_state.sound_enabled else '🔇'}", use_container_width=True, key="sound_toggle"):
            st.session_state.sound_enabled = not st.session_state.sound_enabled
            st.rerun()

    # ── ADD TRADE FORM ──
    if st.session_state.show_add_form:
        with st.expander("➕ ADD TRADE", expanded=True):
            st.markdown(
                '<div style="font-size:11px;color:var(--text3);font-family:var(--mono);'
                'background:var(--bg3);border-radius:6px;padding:8px 12px;margin-bottom:12px">'
                '⚡ Smart paste: <b>RELIANCE 2800 2750 2900 2950</b></div>',
                unsafe_allow_html=True
            )
            d1, d2 = st.columns(2)
            with d1:
                if st.button("▲ BUY", use_container_width=True, key="add_buy",
                             type="primary" if st.session_state.direction == "BUY" else "secondary"):
                    st.session_state.direction = "BUY"; st.rerun()
            with d2:
                if st.button("▼ SELL", use_container_width=True, key="add_sell",
                             type="primary" if st.session_state.direction == "SELL" else "secondary"):
                    st.session_state.direction = "SELL"; st.rerun()

            raw_input = st.text_input("Symbol", value=st.session_state.f_symbol,
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
                    if len(nums) >= 2: st.session_state.f_sl    = nums[1]
                    if len(nums) >= 3: st.session_state.f_t1    = nums[2]
                    if len(nums) >= 4: st.session_state.f_t2    = nums[3]

            symbol = clean_symbol(st.session_state.f_symbol)

            ex1, ex2 = st.columns(2)
            with ex1:
                if st.button("NSE", use_container_width=True, key="add_nse",
                             type="primary" if st.session_state.exchange == "NS" else "secondary"):
                    st.session_state.exchange = "NS"; st.rerun()
            with ex2:
                if st.button("BSE", use_container_width=True, key="add_bse",
                             type="primary" if st.session_state.exchange == "BO" else "secondary"):
                    st.session_state.exchange = "BO"; st.rerun()

            entry_val = st.number_input("Entry Price", value=st.session_state.f_entry,
                                        min_value=0.0, format="%.0f", key="add_entry")
            sl_col, t1_col = st.columns(2)
            with sl_col:
                sl_val = st.number_input("SL", value=st.session_state.f_sl,
                                         min_value=0.0, format="%.0f", key="add_sl")
            with t1_col:
                t1_val = st.number_input("T1", value=st.session_state.f_t1,
                                         min_value=0.0, format="%.0f", key="add_t1")
            t2_val   = st.number_input("T2 (optional)", value=st.session_state.f_t2,
                                       min_value=0.0, format="%.0f", key="add_t2")
            note_val = st.text_input("Notes", placeholder="e.g. Breakout", key="add_note")

            if st.button(f"{'▲ ADD LONG' if st.session_state.direction=='BUY' else '▼ ADD SHORT'} → {st.session_state.current_tab}",
                         use_container_width=True, type="primary", key="add_submit"):
                if not symbol:
                    st.error("Symbol required")
                elif entry_val <= 0:
                    st.error("Entry required")
                else:
                    lst = get_list(st.session_state.current_tab)
                    dup = [s for s in lst if s.get("symbol") == symbol
                           and s.get("exchange") == st.session_state.exchange
                           and s.get("direction") == st.session_state.direction]
                    if dup:
                        st.error(f"⚠ {symbol} {st.session_state.direction} already exists")
                    else:
                        new_stock = {
                            "symbol":    symbol,
                            "exchange":  st.session_state.exchange,
                            "direction": st.session_state.direction,
                            "entry":     entry_val,
                            "sl":        sl_val  if sl_val  > 0 else None,
                            "target1":   t1_val  if t1_val  > 0 else None,
                            "target2":   t2_val  if t2_val  > 0 else None,
                            "note":      note_val.strip() or None,
                            "sector":    get_stock_sector(symbol),
                            "status":    "WATCHING",
                            "lastPrice": None,
                            "added_at":  datetime.now().isoformat(),
                             "token":     get_stock_token(symbol) or "",
                        }
                        try:
                            add_to_watchlist(st.session_state.current_tab, new_stock)
                            for k in ["f_symbol","f_entry","f_sl","f_t1","f_t2"]:
                                st.session_state[k] = "" if k=="f_symbol" else 0.0
                            st.session_state.show_add_form = False
                            st.session_state.prices = {}
                            st.success(f"✅ {symbol} added!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add: {e}")

    # ══════════════════════════════════════════
    #   WATCHLIST TABS — dynamic with + and ⚙
    # ══════════════════════════════════════════

    st.markdown('<hr style="margin:6px 0;border:none;border-top:1px solid #e0e3e8">', unsafe_allow_html=True)

    # ── Tab row with + button ──
    tab_cols = st.columns(len(WATCHLIST_NAMES) + 1)

    for i, tab_name in enumerate(WATCHLIST_NAMES):
        with tab_cols[i]:
            cnt       = len(get_list(tab_name))
            is_active = st.session_state.current_tab == tab_name
            label     = f"{'●' if is_active else ''}{tab_name}({cnt})"
            if st.button(label, key=f"tab_{i}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.current_tab = tab_name
                st.session_state.prices      = {}
                st.session_state.manage_wl   = None
                st.rerun()

    with tab_cols[-1]:
        if len(WATCHLIST_NAMES) < MAX_WATCHLISTS:
            if st.button("＋", use_container_width=True, help="New watchlist", key="new_wl_btn"):
                st.session_state.show_new_wl = not st.session_state.show_new_wl
                st.rerun()
        else:
            st.markdown(f'<div style="font-size:9px;color:#aaa;padding-top:8px;">Max {MAX_WATCHLISTS}</div>',
                        unsafe_allow_html=True)

    # ── New watchlist form ──
    if st.session_state.show_new_wl:
        with st.container(border=True):
            st.markdown("**Create new watchlist**")
            with st.form("new_wl_form"):
                new_name = st.text_input("Name", placeholder="e.g. Swing Trades", max_chars=30)
                c1, c2   = st.columns(2)
                with c1: create_btn = st.form_submit_button("Create", use_container_width=True, type="primary")
                with c2: cancel_btn = st.form_submit_button("Cancel", use_container_width=True)
            if cancel_btn:
                st.session_state.show_new_wl = False
                st.rerun()
            if create_btn:
                if not new_name.strip():
                    st.error("Enter a name.")
                else:
                    ok, msg = create_user_watchlist(new_name.strip())
                    if ok:
                        st.session_state.wl_names    = get_user_watchlist_names()
                        st.session_state.current_tab = new_name.strip()
                        st.session_state.show_new_wl = False
                        st.success(f"'{new_name}' created!")
                        st.rerun()
                    else:
                        st.error(msg)

    # ── ⚙ Manage current watchlist (rename/delete) ──
    current_tab = st.session_state.current_tab

    manage_col1, manage_col2 = st.columns([5, 1])
    with manage_col2:
        if st.button("⚙", key="manage_wl_btn", use_container_width=True,
                     help=f"Manage '{current_tab}'"):
            if st.session_state.manage_wl == current_tab:
                st.session_state.manage_wl = None
            else:
                st.session_state.manage_wl = current_tab
            st.rerun()

    if st.session_state.manage_wl == current_tab:
        with st.container(border=True):
            st.markdown(f"**⚙ Manage: {current_tab}**")

            # Rename
            with st.form("rename_wl_form"):
                st.markdown("**Rename**")
                new_wl_name  = st.text_input("New name", value=current_tab, max_chars=30)
                rename_btn   = st.form_submit_button("Rename", use_container_width=True)
            if rename_btn:
                if new_wl_name.strip() == current_tab:
                    st.info("Same name — no change.")
                elif not new_wl_name.strip():
                    st.error("Enter a name.")
                else:
                    ok, msg = rename_user_watchlist(current_tab, new_wl_name.strip())
                    if ok:
                        st.session_state.wl_names    = get_user_watchlist_names()
                        st.session_state.current_tab = new_wl_name.strip()
                        st.session_state.manage_wl   = None
                        st.success(f"Renamed to '{new_wl_name}'!")
                        st.rerun()
                    else:
                        st.error(msg)

            st.markdown("---")

            # Delete
            st.markdown("**Delete this watchlist**")
            st.caption("⚠️ All stocks in this watchlist will be deleted permanently.")
            if st.button(f"🗑 Delete '{current_tab}'", use_container_width=True,
                         type="primary", key="delete_wl_confirm"):
                ok, msg = delete_user_watchlist(current_tab)
                if ok:
                    st.session_state.wl_names    = get_user_watchlist_names()
                    st.session_state.current_tab = st.session_state.wl_names[0]
                    st.session_state.manage_wl   = None
                    st.session_state.prices      = {}
                    st.success("Deleted!")
                    st.rerun()
                else:
                    st.error(msg)

    st.markdown('<hr style="margin:6px 0;border:none;border-top:1px solid #e0e3e8">', unsafe_allow_html=True)

    watchlist = get_list(current_tab)

    # ── SORT + CLEAR ──
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        if st.button("Sort", use_container_width=True, key="sort_btn"):
            st.session_state.sort_open = not st.session_state.sort_open
            st.rerun()
    with sc2:
        st.markdown(
            f'<div style="font-size:11px;color:#7a8394;padding-top:8px;text-align:center;">'
            f'{len(watchlist)} stocks</div>', unsafe_allow_html=True)
    with sc3:
        if st.button("🗑", use_container_width=True, help="Clear all", key="clear_btn"):
            if watchlist:
                try:
                    clear_watchlist_tab(current_tab)
                    st.session_state.prices = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"Clear failed: {e}")

    if st.session_state.sort_open:
        s1, s2 = st.columns(2)
        s3, s4 = st.columns(2)
        for btn, lbl in [(s1,"Default"),(s2,"Status"),(s3,"Symbol"),(s4,"Distance")]:
            with btn:
                key = lbl.lower()
                if st.button(lbl, use_container_width=True, key=f"sort_{key}",
                             type="primary" if st.session_state.sort_by==key else "secondary"):
                    st.session_state.sort_by = key
                    st.rerun()

    # ── SOURCE STATUS ──
    market_now = is_market_open()
    src_label  = "🟢 Live" if market_now else "🟠 Close Price"
    if st.session_state.last_fetch_time:
        elapsed   = (now_ist() - st.session_state.last_fetch_time).total_seconds()
        mins_left = max(0, int((AUTO_REFRESH_SECS - elapsed) / 60))
        secs_left = max(0, int((AUTO_REFRESH_SECS - elapsed) % 60))
        refresh_info = f" · Next refresh in {mins_left}m {secs_left}s"
    else:
        refresh_info = " · Fetching..."
    st.markdown(
        f'<div style="font-size:10px;font-weight:600;margin:6px 0;padding:4px 8px;'
        f'background:#f5f5f5;border-radius:4px;color:{"#00a854" if market_now else "#ff6b35"};">'
        f'{src_label}{refresh_info}</div>',
        unsafe_allow_html=True
    )

    # ── AUTO FETCH ──
    if watchlist and should_auto_refresh() and not refresh:
        with st.spinner("Loading prices..."):
            do_price_fetch(watchlist)

    if watchlist and refresh:
        st.session_state.prices = {}
        with st.spinner(f"Fetching {len(watchlist)} stocks..."):
            new_prices = fetch_all_prices(watchlist)
            st.session_state.prices.update(new_prices)
            st.session_state.last_fetch_time = now_ist()
        st.success(f"✅ {len(new_prices)} prices updated!")

    # ── SORT ──
    def sort_list(lst, by):
        order = {"SL_HIT":0,"TRIGGERED":1,"NEAR":2,"TARGET1":3,"TARGET2":4,"WATCHING":5}
        if by == "status":
            return sorted(lst, key=lambda s: order.get(s.get("status","WATCHING"),9))
        if by == "symbol":
            return sorted(lst, key=lambda s: s.get("symbol",""))
        if by == "distance":
            def dist(s):
                k    = f"{s.get('symbol','')}_{s.get('exchange','NS')}"
                data = st.session_state.prices.get(k, {})
                ltp  = data.get("price")
                e    = s.get("entry")
                return abs(ltp-e)/e if ltp and e else 999
            return sorted(lst, key=dist)
        return lst

    watchlist = sort_list(watchlist, st.session_state.sort_by)

    if not watchlist:
        st.markdown(
            '<div style="text-align:center;padding:40px 10px">'
            '<div style="font-size:32px">📭</div>'
            '<div style="color:#7a8394;margin-top:8px;font-size:13px">'
            'No stocks in <b>' + current_tab + '</b></div></div>',
            unsafe_allow_html=True
        )
    else:
        for stock_idx, stock in enumerate(watchlist):
            sym      = stock.get("symbol","")
            dirn     = stock.get("direction","BUY")
            entry    = stock.get("entry")
            sl       = stock.get("sl")
            t1       = stock.get("target1")
            t2       = stock.get("target2")
            note     = stock.get("note","")
            exchange = stock.get("exchange","NS")
            db_id    = stock.get("_db_id")

            price_key  = f"{sym}_{exchange}"
            price_data = st.session_state.prices.get(price_key, {})
            ltp        = price_data.get("price")
            source     = price_data.get("source", "offline")

            pct_val   = ""
            pct_color = "#7a8394"
            if ltp and entry:
                p         = (ltp - entry) / entry * 100
                pct_val   = f"{'+' if p>=0 else ''}{p:.2f}%"
                pct_color = "#00a854" if p >= 0 else "#e53935"

            old_status = stock.get("status","WATCHING")
            new_status = old_status

            if ltp:
                new_status = compute_status(stock, ltp)
                if new_status != old_status and db_id:
                    try:
                        update_watchlist_stock(db_id, {"status": new_status, "lastPrice": ltp})
                    except Exception as e:
                        print(f"Status update failed for {sym}: {e}")
                    if st.session_state.sound_enabled:
                        if new_status == "SL_HIT":                play_alert_sound("sl_hit")
                        elif new_status in ["TARGET1","TARGET2"]: play_alert_sound("target")
                        elif new_status == "TRIGGERED":           play_alert_sound("triggered")

            status       = new_status
            status_color = STATUS_COLOR.get(status,"#f59e0b")
            status_text  = STATUS_LABEL.get(status,"")
            buy_color    = "#00a854" if dirn=="BUY" else "#e53935"
            ltp_display  = fmt(ltp) if ltp else "---"
            is_selected  = (st.session_state.selected_symbol == sym
                            and st.session_state.selected_exchange == exchange)
            src_icon     = SOURCE_ICON.get(source,"⚪")

            if st.session_state.edit_idx==stock_idx and st.session_state.edit_tab==current_tab:
                with st.container(border=True):
                    e1, e2 = st.columns(2)
                    with e1:
                        ne  = st.number_input("Entry", value=int(stock.get("entry") or 0), format="%d", key=f"e_en_{stock_idx}")
                        ns  = st.number_input("SL",    value=int(stock.get("sl")    or 0), format="%d", key=f"e_sl_{stock_idx}")
                    with e2:
                        nt1 = st.number_input("T1", value=int(stock.get("target1") or 0), format="%d", key=f"e_t1_{stock_idx}")
                        nt2 = st.number_input("T2", value=int(stock.get("target2") or 0), format="%d", key=f"e_t2_{stock_idx}")
                    nn = st.text_input("Note", value=stock.get("note") or "", key=f"e_note_{stock_idx}")
                    sv1, sv2 = st.columns(2)
                    with sv1:
                        if st.button("💾 Save", use_container_width=True, type="primary", key=f"save_{stock_idx}"):
                            if db_id:
                                try:
                                    update_watchlist_stock(db_id, {
                                        "entry":   ne  if ne  > 0 else stock.get("entry"),
                                        "sl":      ns  if ns  > 0 else None,
                                        "target1": nt1 if nt1 > 0 else None,
                                        "target2": nt2 if nt2 > 0 else None,
                                        "note":    nn.strip() or None,
                                    })
                                    st.session_state.edit_idx = None
                                    st.session_state.edit_tab = None
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Save failed: {e}")
                    with sv2:
                        if st.button("Cancel", use_container_width=True, key=f"cancel_{stock_idx}"):
                            st.session_state.edit_idx = None
                            st.session_state.edit_tab = None
                            st.rerun()
            else:
                selected_border = "2px solid #2563eb" if is_selected else "1px solid #e0e3e8"
                selected_bg     = "#f0f5ff" if is_selected else "#fff"
                card_html = (
                    '<div style="padding:10px 12px;background:' + selected_bg + ';'
                    'border:' + selected_border + ';'
                    'border-left:4px solid ' + status_color + ';'
                    'border-radius:8px;margin-bottom:6px;">'
                    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
                    '<div style="display:flex;align-items:center;gap:6px;">'
                    '<span style="font-family:monospace;font-weight:700;font-size:14px;color:#0f1117;">' + sym + '</span>'
                    '<span style="font-size:9px;font-weight:700;color:' + buy_color + ';">' + ('▲' if dirn=='BUY' else '▼') + '</span>'
                    '</div>'
                    '<span style="font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px;background:rgba(25,63,155,0.08);color:' + status_color + ';">' + status_text + '</span>'
                    '</div>'
                    '<div style="display:flex;align-items:baseline;gap:8px;">'
                    '<span style="font-family:monospace;font-weight:700;font-size:15px;color:#0f1117;">' + ltp_display + '</span>'
                    '<span style="font-family:monospace;font-size:11px;color:' + pct_color + ';">' + pct_val + '</span>'
                    '<span style="font-size:10px;color:#7a8394;">' + src_icon + '</span>'
                    '</div>'
                    '<div style="display:flex;gap:4px;margin-top:6px;flex-wrap:wrap;">'
                    '<div style="display:flex;flex-direction:column;align-items:center;padding:2px 7px;border-radius:4px;border:0.5px solid #b4b2a9;background:#f1efe8;">'
                    '<span style="font-size:8px;color:#5f5e5a;font-weight:600;">E</span>'
                    '<span style="font-family:monospace;font-size:11px;font-weight:600;color:#2c2c2a;">' + fmt(entry) + '</span>'
                    '</div>'
                    '<div style="display:flex;flex-direction:column;align-items:center;padding:2px 7px;border-radius:4px;border:0.5px solid #f09595;background:#fcebeb;">'
                    '<span style="font-size:8px;color:#a32d2d;font-weight:600;">SL</span>'
                    '<span style="font-family:monospace;font-size:11px;font-weight:600;color:#a32d2d;">' + fmt(sl) + '</span>'
                    '</div>'
                    '<div style="display:flex;flex-direction:column;align-items:center;padding:2px 7px;border-radius:4px;border:0.5px solid #85b7eb;background:#e6f1fb;">'
                    '<span style="font-size:8px;color:#185fa5;font-weight:600;">T1</span>'
                    '<span style="font-family:monospace;font-size:11px;font-weight:600;color:#185fa5;">' + fmt(t1) + '</span>'
                    '</div>'
                    '<div style="display:flex;flex-direction:column;align-items:center;padding:2px 7px;border-radius:4px;border:0.5px solid #afa9ec;background:#eeedfe;">'
                    '<span style="font-size:8px;color:#534ab7;font-weight:600;">T2</span>'
                    '<span style="font-family:monospace;font-size:11px;font-weight:600;color:' + ('#534ab7' if t2 else '#aaa') + ';">' + fmt(t2) + '</span>'
                    '</div>'
                    '</div></div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

                btn_cols = st.columns([2, 0.6, 0.6, 0.6])
                with btn_cols[0]:
                    btn_label = f"📈 {sym}" if not is_selected else f"✅ {sym} (active)"
                    if st.button(btn_label, key=f"chart_{stock_idx}", use_container_width=True,
                                 type="primary" if is_selected else "secondary"):
                        st.session_state.selected_symbol   = sym
                        st.session_state.selected_exchange = exchange
                        st.rerun()
                with btn_cols[1]:
                    if st.button("↺", key=f"rst_{stock_idx}", use_container_width=True, help="Reset"):
                        if db_id:
                            try:
                                update_watchlist_stock(db_id, {"status": "WATCHING", "lastPrice": None})
                                st.session_state.prices.pop(f"{sym}_{exchange}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Reset failed: {e}")
                with btn_cols[2]:
                    if st.button("✏", key=f"edt_{stock_idx}", use_container_width=True, help="Edit"):
                        st.session_state.edit_idx = stock_idx
                        st.session_state.edit_tab = current_tab
                        st.rerun()
                with btn_cols[3]:
                    if st.button("✕", key=f"del_{stock_idx}", use_container_width=True, help="Delete"):
                        if db_id:
                            try:
                                delete_from_watchlist(db_id)
                                st.session_state.prices.pop(f"{sym}_{exchange}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete failed: {e}")

                if note:
                    st.markdown(
                        f'<div style="font-size:10px;color:#7a8394;margin-left:4px;'
                        f'margin-top:-4px;margin-bottom:4px;">📝 {note}</div>',
                        unsafe_allow_html=True
                    )

    st.markdown('<hr style="margin:8px 0;border:none;border-top:1px solid #e0e3e8">', unsafe_allow_html=True)
    mkt_label = "🟢 Market Open" if market_now else "🔴 Market Closed"
    ist_now   = now_ist().strftime("%I:%M %p IST")
    st.markdown(
        f'<div style="font-size:10px;color:#7a8394">{mkt_label} · {ist_now}</div>',
        unsafe_allow_html=True
    )

# ══════════════════════════════════════════
#   RIGHT PANEL — CHART
# ══════════════════════════════════════════

with right_col:
    if not st.session_state.selected_symbol:
        st.markdown(
            '<div style="display:flex;flex-direction:column;align-items:center;'
            'justify-content:center;height:680px;border:1px dashed #e0e3e8;'
            'border-radius:12px;background:#fafafa;">'
            '<div style="font-size:48px">📈</div>'
            '<div style="font-size:16px;font-weight:600;color:#0f1117;margin-top:12px;">'
            'Select a stock to view chart</div>'
            '<div style="font-size:13px;color:#7a8394;margin-top:6px;">'
            'Click any stock card on the left</div></div>',
            unsafe_allow_html=True
        )
    else:
        symbol     = st.session_state.selected_symbol
        exchange   = st.session_state.selected_exchange
        exch_label = "NSE" if exchange == "NS" else "BSE"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;padding:8px 0;margin-bottom:12px;">'
            f'<span style="font-family:monospace;font-weight:700;font-size:18px;color:#0f1117;">{symbol}</span>'
            f'<span style="font-size:11px;font-weight:600;padding:3px 8px;border-radius:6px;background:#e6f1fb;color:#185fa5;">{exch_label}</span>'
            f'<span style="font-size:12px;color:#7a8394;">1Y Chart</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        render_chart(symbol, exchange)

if is_market_open() and st.session_state.edit_idx is None:
    time.sleep(60)
    st.rerun()
