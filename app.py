# ══════════════════════════════════════════
#   TRADESENTRY — app.py
#   Hardened Production Build
#   VERSION: 3.3.0 (Instant Sync Engine)
# ══════════════════════════════════════════

import streamlit as st
import pyotp
import json
import os
import threading
import time
import struct
import pytz
import yfinance as yf
from datetime import datetime
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

import sys
sys.path.append(os.path.dirname(__file__))
from styles import apply_styles, sidebar_brand, page_header

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

apply_styles()
sidebar_brand()
page_header("Live Market Dashboard")

# ══════════════════════════════════════════
#   CONFIG
# ══════════════════════════════════════════

BASE_DIR         = os.path.dirname(__file__)
WATCHLIST_FILE   = os.path.join(BASE_DIR, "watchlist.json")
PRICE_CACHE_FILE = os.path.join(BASE_DIR, "price_cache.json")
WATCHLIST_NAMES  = ["Today", "Yesterday", "New"]

IST          = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = (9,  15)
MARKET_CLOSE = (15, 30)


# ══════════════════════════════════════════
#   TIME HELPERS
# ══════════════════════════════════════════

def now_ist():
    return datetime.now(pytz.utc).astimezone(IST)

def t():
    return now_ist().strftime("%H:%M:%S IST")

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    mins = n.hour * 60 + n.minute
    return (MARKET_OPEN[0]*60 + MARKET_OPEN[1]) <= mins <= (MARKET_CLOSE[0]*60 + MARKET_CLOSE[1])


# ══════════════════════════════════════════
#   CACHE HELPERS
# ══════════════════════════════════════════

def load_cache():
    try:
        if os.path.exists(PRICE_CACHE_FILE):
            with open(PRICE_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[{t()}] Cache load error: {e}")
    return {"mode": "offline", "last_update": "", "stocks": {}}

def save_cache(cache):
    try:
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"[{t()}] Cache save error: {e}")

def set_price(symbol, exchange, price, source):
    cache = load_cache()
    if "stocks" not in cache:
        cache["stocks"] = {}
    cache["stocks"][symbol] = {
        "price": float(price), "source": source,
        "time": t(), "exchange": exchange
    }
    cache["last_update"] = t()
    save_cache(cache)

def force_mode(mode):
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)


# ══════════════════════════════════════════
#   WATCHLIST HELPERS (CRASH PROOFED)
# ══════════════════════════════════════════

def get_all_stocks():
    try:
        if not os.path.exists(WATCHLIST_FILE):
            return []
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        
        all_stocks = []
        for name in WATCHLIST_NAMES:
            tab_key = f"watchlist_{name}"
            tab_data = data.get(tab_key, [])
            if isinstance(tab_data, list):
                all_stocks.extend(tab_data)
                
        seen, unique = set(), []
        for s in all_stocks:
            if not isinstance(s, dict) or not s.get("symbol"):
                continue
            sym = s.get("symbol")
            exch = s.get("exchange", "NS")
            k = (sym, exch)
            if k not in seen:
                seen.add(k)
                unique.append(s)
        return unique
    except Exception as e:
        print(f"[{t()}] Watchlist error: {e}")
        return []


# ══════════════════════════════════════════
#   AUTOMATED TARGET INTERCEPT SYNC PIPELINE
# ══════════════════════════════════════════

def fetch_single_ticker_immediate(symbol, exch="NS", label="close_price"):
    """
    Fires instantaneously from the frontend UI on asset registration.
    Eliminates the cache-mismatch gap completely without manual button intervention.
    """
    try:
        suffix = ".NS" if exch == "NS" else ".BO"
        ticker = yf.Ticker(f"{symbol}{suffix}")
        df = ticker.history(period="1d")
        
        if not df.empty:
            price = df['Close'].iloc[-1]
            set_price(symbol, exch, float(price), label)
            print(f"[{t()}] INSTANT ADDITION SYNC -> {symbol}: ₹{price:.2f}")
            return True
        else:
            price = ticker.info.get("regularMarketPreviousClose") or ticker.info.get("currentPrice")
            if price:
                set_price(symbol, exch, float(price), label)
                return True
    except Exception as e:
        print(f"[{t()}] Instant sync execution fault on token {symbol}: {e}")
    return False


def fetch_all_yfinance(label="yfinance"):
    stocks = get_all_stocks()
    if not stocks:
        print(f"[{t()}] No active stocks found in watchlist to process.")
        return 0
    fetched = 0
    for stock in stocks:
        try:
            sym    = stock.get("symbol")
            exch   = stock.get("exchange","NS")
            suffix = ".NS" if exch == "NS" else ".BO"
            
            ticker = yf.Ticker(f"{sym}{suffix}")
            df = ticker.history(period="1d")
            
            if not df.empty:
                price = df['Close'].iloc[-1]
                set_price(sym, exch, float(price), label)
                fetched += 1
                print(f"[{t()}] {label.upper()} -> {sym}: ₹{price:.2f}")
            else:
                price = ticker.info.get("regularMarketPreviousClose") or ticker.info.get("currentPrice")
                if price:
                    set_price(sym, exch, float(price), label)
                    fetched += 1
        except Exception as e:
            print(f"[{t()}] Structural yfinance error on token {stock.get('symbol')}: {e}")
    
    if fetched > 0:
        force_mode(label)
    return fetched


# ══════════════════════════════════════════
#   FETCH PRICES - HTTP (Angel One REST Engine)
# ══════════════════════════════════════════

def fetch_all_http(angel_obj):
    from stocks import get_stock_token
    stocks = get_all_stocks()
    if not stocks:
        return 0
    fetched = 0
    for i in range(0, len(stocks), 50):
        batch = stocks[i:i+50]
        for stock in batch:
            try:
                sym   = stock.get("symbol")
                exch  = stock.get("exchange","NS")
                token = str(get_stock_token(sym) or "")
                if not token:
                    continue
                resp = angel_obj.ltpData(
                    "NSE" if exch=="NS" else "BSE", sym, token)
                if resp and resp.get("status"):
                    ltp = float(resp["data"]["ltp"])
                    set_price(sym, exch, ltp, "http")
                    fetched += 1
                    print(f"[{t()}] HTTP {sym}: ₹{ltp:.2f}")
            except Exception as e:
                print(f"[{t()}] HTTP error {stock.get('symbol')}: {e}")
        time.sleep(1)
    if fetched > 0:
        force_mode("http_polling")
    return fetched


# ══════════════════════════════════════════
#   BACKGROUND ORCHESTRATION ENGINE
# ══════════════════════════════════════════

class Streamer:
    def __init__(self, auth, api_key, client, feed, angel_obj):
        self.auth      = auth
        self.api_key   = api_key
        self.client    = client
        self.feed      = feed
        self.angel     = angel_obj
        self.token_map = {}
        self.sws       = None

    def build_tokens(self):
        from stocks import get_stock_token
        stocks = get_all_stocks()
        nse, bse = [], []
        self.token_map = {}
        for s in stocks:
            sym  = s.get("symbol")
            exch = s.get("exchange","NS")
            tok  = get_stock_token(sym)
            if not tok:
                continue
            tok = str(tok)
            self.token_map[tok] = (sym, exch)
            if exch == "NS": nse.append(tok)
            else:            bse.append(tok)
        return nse, bse

    def on_data(self, wsapp, msg):
        try:
            if isinstance(msg, bytes) and len(msg) >= 51:
                tok = msg[2:27].decode("utf-8").rstrip("\x00").strip()
                ltp = struct.unpack("<i", msg[43:47])[0] / 100.0
                if tok in self.token_map:
                    sym, exch = self.token_map[tok]
                    set_price(sym, exch, ltp, "websocket")
                    force_mode("websocket")
        except Exception as e:
            print(f"[{t()}] WS data execution parse failure: {e}")

    def on_open(self, wsapp):
        print(f"[{t()}] WS Connected successfully!")
        force_mode("websocket")
        nse, bse = self.build_tokens()
        token_list = []
        if nse: token_list.append({"exchangeType":1,"tokens":nse})
        if bse: token_list.append({"exchangeType":3,"tokens":bse})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)

    def on_error(self, wsapp, err):
        print(f"[{t()}] WS Core Pipeline Error: {err}")

    def on_close(self, wsapp):
        print(f"[{t()}] WS Channel Disconnected")

    def connect_ws(self):
        try:
            self.sws = SmartWebSocketV2(
                self.auth, self.api_key, self.client, self.feed)
            self.sws.on_open  = self.on_open
            self.sws.on_data  = self.on_data
            self.sws.on_error = self.on_error
            self.sws.on_close = self.on_close
            self.sws.connect()
        except Exception as e:
            print(f"[{t()}] WS Core connection loop failed: {e}")

    def run(self):
        """Main streamer loop running in complete safety isolate"""
        close_fetched_date = None

        while True:
            try:
                now = now_ist()
                market_on = is_market_open()
                cache = load_cache()
                cache_stocks = cache.get("stocks", {})
                cache_empty = len(cache_stocks) == 0
                watchlist_stocks = get_all_stocks()

                # ── DECOUPLED HANDLING FOR OFF-MARKET WINDOWS ──
                if not market_on:
                    today = now.date()
                    
                    # Watchlist hot-reload backup condition verification
                    mismatch_detected = len(watchlist_stocks) != len(cache_stocks)
                    
                    if close_fetched_date != today or cache_empty or mismatch_detected:
                        print(f"[{t()}] Configuration mismatch detected in background loop. Refreshing indices...")
                        fetched = fetch_all_yfinance("close_price")
                        if fetched > 0:
                            close_fetched_date = today
                        else:
                            print(f"[{t()}] Warning: No records written. System will loop re-verification.")
                    else:
                        print(f"[{t()}] Cache validation intact. Sleeping thread cycle.")
                    
                    time.sleep(5)
                    continue

                # ── LIVE SESSION HANDLING ──
                close_fetched_date = None 
                if not watchlist_stocks:
                    time.sleep(10)
                    continue

                try:
                    self.connect_ws()
                except Exception as e:
                    print(f"[{t()}] Live structural exception context: {e}")

                # Level 2 Pipeline Fallback via HTTP
                if is_market_open():
                    force_mode("http_polling")
                    while is_market_open():
                        try:
                            fetch_all_http(self.angel)
                        except Exception as e:
                            print(f"[{t()}] REST polling crash trace: {e}")
                            break
                        time.sleep(5)

                # Level 3 Data Scraping Core
                if is_market_open():
                    while is_market_open():
                        try:
                            fetch_all_yfinance()
                        except Exception as e:
                            print(f"[{t()}] Fallback engine pipeline fault: {e}")
                            break
                        time.sleep(10)

                time.sleep(5)

            except Exception as e:
                print(f"[{t()}] Core execution worker thread isolated fault: {e}")
                time.sleep(10)


# ══════════════════════════════════════════
#   STARTUP SYSTEM RESOURCE SINGLETON
# ══════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def start_streamer(_version):
    result = {"ok": False, "error": ""}
    try:
        api_key = st.secrets["API_KEY"]
        client  = st.secrets["CLIENT_CODE"]
        pwd     = st.secrets["PASSWORD"]
        totp_s  = st.secrets["TOTP_SECRET"]

        obj  = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_s).now()
        sess = obj.generateSession(client, pwd, totp)

        if not sess.get("status"):
            result["error"] = sess.get("message","Login failed")
            return result

        auth = sess["data"]["jwtToken"]
        feed = sess["data"].get("feedToken") or obj.getfeedToken()

        if not feed:
            result["error"] = "Feed token missing from terminal session response"
            return result

        streamer = Streamer(auth, api_key, client, feed, obj)
        th = threading.Thread(
            target=streamer.run, daemon=True, name="TradeSentryStreamerWorker")
        th.start()

        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


# ══════════════════════════════════════════
#   RENDER UI CONTROLS
# ══════════════════════════════════════════

APP_VERSION = "3.3.0"

result     = start_streamer(APP_VERSION)

# ─── FRONTEND REALTIME ADDITION TRACKER INTERCEPT ───
# If your watchlist file handler exists inside another file or script, 
# this block catches addition deltas right as they land.
current_stocks = get_all_stocks()
current_cache  = load_cache()
cached_keys    = current_cache.get("stocks", {}).keys()

for stock_obj in current_stocks:
    sym = stock_obj.get("symbol")
    exch = stock_obj.get("exchange", "NS")
    if sym and sym not in cached_keys:
        # Pull metric parameters immediately for the newly discovered token
        fetch_single_ticker_immediate(sym, exch, label="close_price" if not is_market_open() else "yfinance")

# Reload clean localized cache state vectors post-intercept processing
cache      = load_cache()
mode       = cache.get("mode","offline")
last       = cache.get("last_update","---")
total      = len(cache.get("stocks",{}))
market_now = is_market_open()
ist_now    = now_ist().strftime("%I:%M %p IST")

mode_badge = {
    "websocket":    "🟢 WebSocket Live",
    "http_polling": "🟡 HTTP Polling",
    "yfinance":      "🟠 yfinance",
    "close_price":  "🟠 Close Price",
    "offline":      "⚪ Offline"
}

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Price Feed",        mode_badge.get(mode,"Unknown"))
with c2: st.metric("Last Update",       last or "Waiting...")
with c3: st.metric("Stocks Tracked",    total)
with c4: st.metric("Market",            f"{'🟢 Open' if market_now else '🔴 Closed'} · {ist_now}")

st.divider()

if result["ok"]:
    if market_now:
        st.success("✅ Engine Online · Live pipelines running.")
    else:
        st.warning(f"⏰ Session Closed · Internal engines parked · System running on background fallbacks.")
else:
    st.error(f"❌ Handshake Fault: {result.get('error','Unknown')}")

st.info("💡 Go to **Watchlist** to see prices.")

with st.expander("🔧 Diagnostics Desk"):
    st.write(f"**Engine Framework Version:** {APP_VERSION}")
    st.write(f"**Thread Strategy State Mode:** `{mode}`")
    st.write(f"**Local Storage Cache Stack Counter:** {total}")
    st.write(f"**Watchlist Target Stock Array:** {len(get_all_stocks())}")

    if st.button("🔄 Force Immediate yfinance Overwrite", type="primary"):
        if len(get_all_stocks()) == 0:
            st.error("Engine failure: Target watchlist array contains no actionable components.")
        else:
            with st.spinner("Executing hard data synchronization overrides..."):
                fetched = fetch_all_yfinance("yfinance")
            if fetched > 0:
                st.success(f"Successfully processed and written {fetched} records into registry.")
                st.rerun()
            else:
                st.error("Scraper interface rejection: Yahoo system rejected requested metrics or returned blank frames.")
