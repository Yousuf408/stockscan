# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  WebSocket price streamer using st.cache_resource
#  Persists across page changes + Streamlit reruns
# ══════════════════════════════════════════

import streamlit as st
import pyotp
import json
import os
import threading
import time
import struct
import pytz
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

WATCHLIST_FILE   = os.path.join(os.path.dirname(__file__), "watchlist.json")
PRICE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "price_cache.json")
WATCHLIST_NAMES  = ["Today", "Yesterday", "New"]

IST          = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = (9,  15)   # 9:15 AM IST
MARKET_CLOSE = (15, 30)   # 3:30 PM IST


# ══════════════════════════════════════════
#  TIMEZONE HELPERS (STRICT IST ENFORCEMENT)
# ══════════════════════════════════════════

def now_ist() -> datetime:
    """Always converts the current machine time accurately into IST"""
    return datetime.now(pytz.utc).astimezone(IST)

def ist_time_str() -> str:
    return now_ist().strftime("%H:%M:%S")

def is_market_open() -> bool:
    now = now_ist()
    # 5 = Saturday, 6 = Sunday
    if now.weekday() >= 5:
        return False
    open_mins  = MARKET_OPEN[0]  * 60 + MARKET_OPEN[1]
    close_mins = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    curr_mins  = now.hour * 60 + now.minute
    return open_mins <= curr_mins <= close_mins


# ══════════════════════════════════════════
#  PRICE CACHE
# ══════════════════════════════════════════

def load_cache() -> dict:
    if not os.path.exists(PRICE_CACHE_FILE):
        return {"mode": "offline", "last_update": "", "stocks": {}}
    try:
        with open(PRICE_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"mode": "offline", "last_update": "", "stocks": {}}

def save_cache(cache: dict):
    try:
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"[{ist_time_str()} IST] [Cache] Save error: {e}")

def update_price(symbol: str, exchange: str, price: float, source: str):
    cache = load_cache()
    cache["stocks"][symbol] = {
        "price":    price,
        "source":   source,
        "time":     f"{ist_time_str()} IST",
        "exchange": exchange
    }
    cache["last_update"] = f"{ist_time_str()} IST"
    save_cache(cache)

def set_mode(mode: str):
    cache = load_cache()
    current = cache.get("mode", "offline")
    active_modes = ["websocket", "http_polling", "yfinance"]
    
    if mode == "offline" and current in active_modes:
        stocks = cache.get("stocks", {})
        if stocks:
            last = cache.get("last_update", "")
            if last:
                try:
                    # Parse using clean string splits to completely avoid timezone conflicts
                    last_clean = last.replace(" IST", "").strip()
                    last_time = datetime.strptime(last_clean, "%H:%M:%S")
                    now_time  = now_ist()
                    
                    now_secs  = now_time.hour * 3600 + now_time.minute * 60 + now_time.second
                    last_secs = last_time.hour * 3600 + last_time.minute * 60 + last_time.second
                    diff = abs(now_secs - last_secs)
                    if diff < 30:
                        print(f"[{ist_time_str()} IST] [Cache] Skipping offline override — prices updated {diff}s ago")
                        return
                except Exception as e:
                    print(f"[Time Check Debug Error]: {e}")
                    pass
    cache["mode"] = mode
    save_cache(cache)

def force_set_mode(mode: str):
    """Force set mode regardless of current state"""
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)


# ══════════════════════════════════════════
#  LOAD WATCHLIST STOCKS
# ══════════════════════════════════════════

def get_all_watchlist_stocks() -> list:
    try:
        if not os.path.exists(WATCHLIST_FILE):
            return []
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        all_stocks = []
        for tab in [f"watchlist_{n}" for n in WATCHLIST_NAMES]:
            all_stocks.extend(data.get(tab, []))
        seen, unique = set(), []
        for s in all_stocks:
            key = (s.get("symbol"), s.get("exchange", "NS"))
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
    except Exception as e:
        print(f"[{ist_time_str()} IST] [Watchlist] Load error: {e}")
        return []


# ══════════════════════════════════════════
#  BUILD TOKEN MAP
# ══════════════════════════════════════════

def build_token_map(stocks: list):
    try:
        from stocks import get_stock_token
    except Exception as e:
        print(f"[{ist_time_str()} IST] [Token] Import error: {e}")
        return {}, [], []

    token_map, nse_tokens, bse_tokens = {}, [], []
    for stock in stocks:
        symbol   = stock.get("symbol")
        exchange = stock.get("exchange", "NS")
        try:
            token = get_stock_token(symbol)
        except:
            token = None
        if not token:
            continue
        token = str(token)
        token_map[token] = (symbol, exchange)
        if exchange == "NS":
            nse_tokens.append(token)
        else:
            bse_tokens.append(token)

    return token_map, nse_tokens, bse_tokens


# ══════════════════════════════════════════
#  HTTP POLLING FALLBACK
# ══════════════════════════════════════════

def run_http_polling(angel_obj):
    try:
        from stocks import get_stock_token
    except:
        return

    print(f"[{ist_time_str()} IST] [HTTP] Starting HTTP polling...")
    force_set_mode("http_polling")

    while True:
        try:
            if not is_market_open():
                print(f"[{ist_time_str()} IST] [HTTP] Market closed. Exiting HTTP polling.")
                return

            stocks = get_all_watchlist_stocks()
            if not stocks:
                time.sleep(5)
                continue

            for i in range(0, len(stocks), 50):
                batch = stocks[i:i + 50]
                for stock in batch:
                    try:
                        symbol   = stock.get("symbol")
                        exchange = stock.get("exchange", "NS")
                        token    = str(get_stock_token(symbol) or "")
                        if not token:
                            continue
                        resp = angel_obj.ltpData(
                            "NSE" if exchange == "NS" else "BSE",
                            symbol, token
                        )
                        if resp and resp.get("status"):
                            ltp = float(resp["data"]["ltp"])
                            update_price(symbol, exchange, ltp, "http")
                    except Exception as e:
                        print(f"[{ist_time_str()} IST] [HTTP] {stock.get('symbol')}: {e}")
                time.sleep(1)

            force_set_mode("http_polling")
            time.sleep(5)

        except Exception as e:
            print(f"[{ist_time_str()} IST] [HTTP] Polling error: {e}")
            time.sleep(5)


# ══════════════════════════════════════════
#  YFINANCE FALLBACK
# ══════════════════════════════════════════

def run_yfinance_fallback():
    import yfinance as yf
    print(f"[{ist_time_str()} IST] [yfinance] Starting yfinance fallback...")
    force_set_mode("yfinance")

    while True:
        try:
            if not is_market_open():
                print(f"[{ist_time_str()} IST] [yfinance] Market closed. Exiting yfinance.")
                return

            stocks = get_all_watchlist_stocks()
            for stock in stocks:
                try:
                    symbol   = stock.get("symbol")
                    exchange = stock.get("exchange", "NS")
                    suffix   = ".NS" if exchange == "NS" else ".BO"
                    ticker   = yf.Ticker(f"{symbol}{suffix}")
                    price    = (ticker.fast_info.get("last_price")
                                or ticker.fast_info.get("regularMarketPrice"))
                    if price:
                        update_price(symbol, exchange, float(price), "yfinance")
                except Exception as e:
                    print(f"[{ist_time_str()} IST] [yfinance] {stock.get('symbol')}: {e}")

            force_set_mode("yfinance")
            time.sleep(10)

        except Exception as e:
            print(f"[{ist_time_str()} IST] [yfinance] Error: {e}")
            time.sleep(10)


# ══════════════════════════════════════════
#  WEBSOCKET STREAMER CLASS
# ══════════════════════════════════════════

class PriceStreamer:
    def __init__(self, auth_token, api_key, client_code, feed_token, angel_obj):
        self.auth_token  = auth_token
        self.api_key     = api_key
        self.client_code = client_code
        self.feed_token  = feed_token
        self.angel_obj   = angel_obj
        self.token_map   = {}
        self.nse_tokens  = []
        self.bse_tokens  = []
        self.sws         = None

    def on_data(self, wsapp, message):
        try:
            if isinstance(message, bytes):
                if len(message) < 51:
                    return
                token = message[2:27].decode("utf-8").rstrip("\x00").strip()
                ltp   = struct.unpack("<i", message[43:47])[0] / 100.0
                if token in self.token_map:
                    symbol, exchange = self.token_map[token]
                    update_price(symbol, exchange, ltp, "websocket")
                    print(f"[{ist_time_str()} IST] [WS] {symbol}: ₹{ltp:.2f}")
        except Exception as e:
            print(f"[{ist_time_str()} IST] [WS] on_data error: {e}")

    def on_open(self, wsapp):
        print(f"[{ist_time_str()} IST] [WS] Connected Successfully!")
        force_set_mode("websocket")
        token_list = []
        if self.nse_tokens:
            token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens:
            token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)
            print(f"[{ist_time_str()} IST] [WS] Subscribed: {len(self.nse_tokens)} NSE + {len(self.bse_tokens)} BSE")

    def on_error(self, wsapp, error):
        print(f"[{ist_time_str()} IST] [WS] Error: {error}")

    def on_close(self, wsapp):
        print(f"[{ist_time_str()} IST] [WS] Closed")

    def start_websocket(self):
        while True:
            try:
                if not is_market_open():
                    print(f"[{ist_time_str()} IST] [Streamer] Market closed. Checking again in 10s...")
                    cache = load_cache()
                    if not cache.get("stocks"):
                        force_set_mode("offline")
                    time.sleep(10)
                    continue

                stocks = get_all_watchlist_stocks()
                if not stocks:
                    print(f"[{ist_time_str()} IST] [Streamer] Watchlist empty. Waiting 10s...")
                    time.sleep(10)
                    continue

                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                print(f"[{ist_time_str()} IST] [Streamer] {len(self.token_map)} stocks mapped.")

                if not self.token_map:
                    print(f"[{ist_time_str()} IST] [Streamer] Validating yfinance fallback...")
                    run_yfinance_fallback()
                    continue

                try:
                    print(f"[{ist_time_str()} IST] [WS] Connecting to Angel One Streamer...")
                    self.sws = SmartWebSocketV2(
                        self.auth_token,
                        self.api_key,
                        self.client_code,
                        self.feed_token
                    )
                    self.sws.on_open  = self.on_open
                    self.sws.on_data  = self.on_data
                    self.sws.on_error = self.on_error
                    self.sws.on_close = self.on_close
                    self.sws.connect()

                except Exception as ws_err:
                    print(f"[{ist_time_str()} IST] [WS] Failed: {ws_err}")

                if is_market_open():
                    print(f"[{ist_time_str()} IST] [Streamer] WS closed out. Triggering HTTP fallback...")
                    try:
                        run_http_polling(self.angel_obj)
                    except Exception as http_err:
                        print(f"[{ist_time_str()} IST] [HTTP] Failed: {http_err}")

                    if is_market_open():
                        print(f"[{ist_time_str()} IST] [Streamer] HTTP fallback failed. Triggering yfinance fallback...")
                        try:
                            run_yfinance_fallback()
                        except Exception as yf_err:
                            print(f"[{ist_time_str()} IST] [yfinance] Failed: {yf_err}")

                time.sleep(5)

            except Exception as e:
                print(f"[{ist_time_str()} IST] [Streamer] Loop anomaly: {e}")
                time.sleep(10)


# ══════════════════════════════════════════
#  INIT — st.cache_resource
# ══════════════════════════════════════════

@st.cache_resource
def init_price_streamer():
    status = {"connected": False, "error": ""}
    try:
        api_key     = st.secrets["API_KEY"]
        client_code = st.secrets["CLIENT_CODE"]
        password    = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"]

        angel_obj    = SmartConnect(api_key=api_key)
        totp         = pyotp.TOTP(totp_secret).now()
        session_data = angel_obj.generateSession(client_code, password, totp)

        if not session_data.get("status"):
            status["error"] = session_data.get("message", "Login failed")
            return status

        auth_token = session_data["data"]["jwtToken"]
        feed_token = session_data["data"].get("feedToken") or angel_obj.getfeedToken()

        print(f"[{ist_time_str()} IST] [Init] Client initialized: {client_code}")

        if not feed_token:
            status["error"] = "Feed token missing — WebSocket will not work"
            print(f"[{ist_time_str()} IST] ❌ Feed token missing!")
            return status

        streamer = PriceStreamer(
            auth_token, api_key, client_code, feed_token, angel_obj
        )

        thread = threading.Thread(
            target=streamer.start_websocket,
            daemon=True
        )
        thread.start()
        status["connected"] = True
        status["feed_token_ok"] = True
        print(f"[{ist_time_str()} IST] ✅ Background Price Streamer Started!")

    except Exception as e:
        status["error"] = str(e)
        print(f"[{ist_time_str()} IST] ❌ Init error: {e}")

    return status


# ══════════════════════════════════════════
#  STREAMLIT UI & LIVE RERUN FRAGMENT
# ══════════════════════════════════════════

# Wrap the metrics and core engine activation inside a safe timezone fragment
@st.fragment(run_every=3)
def render_dashboard():
    # Instantiating inside the execution scope to guarantee it forces local machine calculation
    status     = init_price_streamer()
    cache      = load_cache()
    mode       = cache.get("mode", "offline")
    last       = cache.get("last_update", "---")
    total      = len(cache.get("stocks", {}))
    market_now = is_market_open()
    ist_now    = now_ist().strftime("%I:%M %p IST")

    # Mapping raw values straight to metrics to avoid truncation misleading the feed state
    mode_badge = {
        "websocket":    "🟢 Live WS",
        "http_polling": "🟡 Polling",
        "yfinance":     "🟠 yfinance",
        "offline":      "⚪ Closed"
    }

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Price Feed", mode_badge.get(mode, f"Status: {mode}"))
    with col2:
        st.metric("Last Price Update", last if last else "Waiting...")
    with col3:
        st.metric("Stocks Tracked", total)
    with col4:
        st.metric("Market Status", f"{'🟢 Open' if market_now else '🔴 Closed'} · {ist_now}")

    st.divider()

    if status["connected"]:
        if market_now:
            st.success("✅ Angel One connected · Streamer running · Live prices flowing to Watchlist")
        else:
            st.warning(f"⏰ Angel One connected · Market closed · Will auto-start at 9:15 AM IST · Now: {ist_now}")
    else:
        st.error(f"❌ Connection failed: {status.get('error', 'Unknown error')}")
        st.info("Check API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET in Streamlit secrets.")

    st.info("💡 Go to **Watchlist** to see live prices. Streamer runs automatically across all pages.")

    with st.expander("🔧 Debug — Force fetch prices (works anytime)"):
        st.write(f"**IST Time:** {ist_now}")
        st.write(f"**Market Open:** {market_now}")
        st.write(f"**Cache Mode:** `{mode}`")
        st.write(f"**Stocks in cache:** {total}")
        st.write(f"**Stocks in watchlist:** {len(get_all_watchlist_stocks())}")

        if st.button("🔄 Force fetch via yfinance", type="primary"):
            import yfinance as yf
            stocks = get_all_watchlist_stocks()
            if not stocks:
                st.error("No stocks in watchlist! Add stocks first.")
            else:
                progress = st.progress(0, text="Fetching...")
                fetched  = 0
                for i, stock in enumerate(stocks):
                    try:
                        symbol   = stock.get("symbol")
                        exchange = stock.get("exchange", "NS")
                        suffix   = ".NS" if exchange == "NS" else ".BO"
                        ticker   = yf.Ticker(f"{symbol}{suffix}")
                        price    = (ticker.fast_info.get("last_price")
                                    or ticker.fast_info.get("regularMarketPrice"))
                        if price:
                            update_price(symbol, exchange, float(price), "yfinance")
                            fetched += 1
                    except Exception as e:
                        st.write(f"⚠ {stock.get('symbol')}: {e}")
                    progress.progress((i + 1) / len(stocks))
                force_set_mode("yfinance")
                st.success(f"✅ Fetched {fetched}/{len(stocks)} stocks! Go to Watchlist.")
                st.rerun()

render_dashboard()
