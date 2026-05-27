# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Clean rewrite - no cache_resource
#  VERSION: 3.0
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
#  CONFIG
# ══════════════════════════════════════════

BASE_DIR         = os.path.dirname(__file__)
WATCHLIST_FILE   = os.path.join(BASE_DIR, "watchlist.json")
PRICE_CACHE_FILE = os.path.join(BASE_DIR, "price_cache.json")
WATCHLIST_NAMES  = ["Today", "Yesterday", "New"]

IST          = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = (9,  15)
MARKET_CLOSE = (15, 30)


# ══════════════════════════════════════════
#  TIME HELPERS
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
#  CACHE HELPERS
# ══════════════════════════════════════════

def load_cache():
    try:
        if os.path.exists(PRICE_CACHE_FILE):
            with open(PRICE_CACHE_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"mode": "offline", "last_update": "", "stocks": {}}

def save_cache(cache):
    try:
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"[{t()}] Cache save error: {e}")

def set_price(symbol, exchange, price, source):
    cache = load_cache()
    cache["stocks"][symbol] = {
        "price": price, "source": source,
        "time": t(), "exchange": exchange
    }
    cache["last_update"] = t()
    save_cache(cache)

def set_mode(mode):
    cache = load_cache()
    # Never set offline if stocks exist in cache
    if mode == "offline" and cache.get("stocks"):
        return
    cache["mode"] = mode
    save_cache(cache)

def force_mode(mode):
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)


# ══════════════════════════════════════════
#  WATCHLIST HELPERS
# ══════════════════════════════════════════

def get_all_stocks():
    try:
        if not os.path.exists(WATCHLIST_FILE):
            return []
        with open(WATCHLIST_FILE) as f:
            data = json.load(f)
        all_stocks = []
        for tab in [f"watchlist_{n}" for n in WATCHLIST_NAMES]:
            all_stocks.extend(data.get(tab, []))
        seen, unique = set(), []
        for s in all_stocks:
            k = (s.get("symbol"), s.get("exchange","NS"))
            if k not in seen:
                seen.add(k)
                unique.append(s)
        return unique
    except Exception as e:
        print(f"[{t()}] Watchlist error: {e}")
        return []


# ══════════════════════════════════════════
#  FETCH PRICES - YFINANCE
# ══════════════════════════════════════════

def fetch_all_yfinance(label="yfinance"):
    stocks = get_all_stocks()
    if not stocks:
        print(f"[{t()}] No stocks to fetch")
        return 0
    fetched = 0
    for stock in stocks:
        try:
            sym    = stock.get("symbol")
            exch   = stock.get("exchange","NS")
            suffix = ".NS" if exch == "NS" else ".BO"
            ticker = yf.Ticker(f"{sym}{suffix}")
            price  = (ticker.fast_info.get("last_price")
                      or ticker.fast_info.get("regularMarketPrice"))
            if price:
                set_price(sym, exch, float(price), label)
                fetched += 1
                print(f"[{t()}] {sym}: ₹{price:.2f}")
        except Exception as e:
            print(f"[{t()}] yfinance error {stock.get('symbol')}: {e}")
    force_mode(label)
    print(f"[{t()}] Fetched {fetched}/{len(stocks)} stocks via {label}")
    return fetched


# ══════════════════════════════════════════
#  FETCH PRICES - HTTP (Angel One)
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
    force_mode("http_polling")
    return fetched


# ══════════════════════════════════════════
#  WEBSOCKET STREAMER
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
                    print(f"[{t()}] WS {sym}: ₹{ltp:.2f}")
        except Exception as e:
            print(f"[{t()}] WS data error: {e}")

    def on_open(self, wsapp):
        print(f"[{t()}] WS Connected!")
        force_mode("websocket")
        nse, bse = self.build_tokens()
        token_list = []
        if nse: token_list.append({"exchangeType":1,"tokens":nse})
        if bse: token_list.append({"exchangeType":3,"tokens":bse})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)
            print(f"[{t()}] WS Subscribed: {len(nse)} NSE + {len(bse)} BSE")

    def on_error(self, wsapp, err):
        print(f"[{t()}] WS Error: {err}")

    def on_close(self, wsapp):
        print(f"[{t()}] WS Closed")

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
            print(f"[{t()}] WS connect error: {e}")

    def run(self):
        """Main streamer loop"""
        close_fetched_date = None

        while True:
            try:
                now       = now_ist()
                market_on = is_market_open()

                # ── MARKET CLOSED ──
                if not market_on:
                    today = now.date()
                    # Fetch close price once per day
                    if close_fetched_date != today:
                        print(f"[{t()}] Market closed. Fetching close prices via yfinance...")
                        fetch_all_yfinance("close_price")
                        close_fetched_date = today
                    else:
                        print(f"[{t()}] Market closed. Sleeping 60s...")
                    time.sleep(60)
                    continue

                # ── MARKET OPEN ──
                close_fetched_date = None  # Reset for next close

                stocks = get_all_stocks()
                if not stocks:
                    print(f"[{t()}] No stocks in watchlist. Waiting...")
                    time.sleep(10)
                    continue

                print(f"[{t()}] Market open. Trying WebSocket...")

                # Try WebSocket
                try:
                    self.connect_ws()  # Blocking until disconnect
                except Exception as e:
                    print(f"[{t()}] WS failed: {e}")

                # WS ended — try HTTP
                if is_market_open():
                    print(f"[{t()}] WS ended. Trying HTTP polling...")
                    force_mode("http_polling")
                    while is_market_open():
                        try:
                            fetch_all_http(self.angel)
                        except Exception as e:
                            print(f"[{t()}] HTTP failed: {e}")
                            break
                        time.sleep(5)

                # HTTP ended — try yfinance
                if is_market_open():
                    print(f"[{t()}] HTTP ended. Trying yfinance...")
                    while is_market_open():
                        try:
                            fetch_all_yfinance()
                        except Exception as e:
                            print(f"[{t()}] yfinance failed: {e}")
                            break
                        time.sleep(10)

                time.sleep(5)

            except Exception as e:
                print(f"[{t()}] Streamer loop error: {e}")
                time.sleep(10)


# ══════════════════════════════════════════
#  STARTUP — Use st.cache_resource with
#  version key to force re-run on deploy
# ══════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def start_streamer(_version):
    """Starts background streamer thread ONCE per process"""
    result = {"ok": False, "error": ""}
    try:
        api_key = st.secrets["API_KEY"]
        client  = st.secrets["CLIENT_CODE"]
        pwd     = st.secrets["PASSWORD"]
        totp_s  = st.secrets["TOTP_SECRET"]

        print(f"[{t()}] ══ TRADESENTRY v3.0 STARTING ══")
        print(f"[{t()}] Client: {client}")
        print(f"[{t()}] IST: {t()}")
        print(f"[{t()}] Market: {'OPEN' if is_market_open() else 'CLOSED'}")

        obj  = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_s).now()
        sess = obj.generateSession(client, pwd, totp)

        print(f"[{t()}] Login: {sess.get('status')} — {sess.get('message','')}")

        if not sess.get("status"):
            result["error"] = sess.get("message","Login failed")
            return result

        auth = sess["data"]["jwtToken"]
        feed = sess["data"].get("feedToken") or obj.getfeedToken()

        print(f"[{t()}] Auth: {auth[:25]}...")
        print(f"[{t()}] Feed: {str(feed)[:25] if feed else 'MISSING!'}")

        if not feed:
            result["error"] = "Feed token missing"
            return result

        streamer = Streamer(auth, api_key, client, feed, obj)

        th = threading.Thread(
            target=streamer.run, daemon=True, name="TradeSentryStreamer")
        th.start()

        print(f"[{t()}] ✅ Streamer thread started: {th.name}")
        result["ok"] = True

    except Exception as e:
        result["error"] = str(e)
        print(f"[{t()}] ❌ Start error: {e}")

    return result


# ══════════════════════════════════════════
#  UI
# ══════════════════════════════════════════

# VERSION KEY — change this to force cache clear on next deploy
APP_VERSION = "3.0.0"

result     = start_streamer(APP_VERSION)
cache      = load_cache()
mode       = cache.get("mode","offline")
last       = cache.get("last_update","---")
total      = len(cache.get("stocks",{}))
market_now = is_market_open()
ist_now    = now_ist().strftime("%I:%M %p IST")

mode_badge = {
    "websocket":    "🟢 WebSocket Live",
    "http_polling": "🟡 HTTP Polling",
    "yfinance":     "🟠 yfinance",
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
        st.success("✅ Connected · Streamer running · Live prices flowing")
    else:
        st.warning(f"⏰ Connected · Market closed · Auto-starts 9:15 AM IST · Now: {ist_now}")
else:
    st.error(f"❌ Failed: {result.get('error','Unknown')}")

st.info("💡 Go to **Watchlist** to see prices.")

with st.expander("🔧 Debug"):
    st.write(f"**Version:** {APP_VERSION}")
    st.write(f"**IST:** {ist_now}")
    st.write(f"**Market:** {market_now}")
    st.write(f"**Mode:** `{mode}`")
    st.write(f"**Cache stocks:** {total}")
    st.write(f"**Watchlist stocks:** {len(get_all_stocks())}")

    if st.button("🔄 Force fetch via yfinance now", type="primary"):
        stocks = get_all_stocks()
        if not stocks:
            st.error("No stocks in watchlist!")
        else:
            with st.spinner("Fetching prices..."):
                fetched = fetch_all_yfinance()
            st.success(f"✅ Fetched {fetched} stocks!")
            st.rerun()
