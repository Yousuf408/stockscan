# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Starts WebSocket price streamer as background thread
#  Writes live prices to price_cache.json
# ══════════════════════════════════════════

import streamlit as st
import pyotp
import json
import os
import threading
import time
import struct
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

WATCHLIST_FILE  = os.path.join(os.path.dirname(__file__), "watchlist.json")
PRICE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "price_cache.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

MARKET_OPEN  = 9 * 60 + 15   # 9:15 AM
MARKET_CLOSE = 15 * 60 + 30  # 3:30 PM


# ══════════════════════════════════════════
#  MARKET HOURS
# ══════════════════════════════════════════

def is_market_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return MARKET_OPEN <= mins <= MARKET_CLOSE


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
        print(f"Cache save error: {e}")

def update_price(symbol: str, exchange: str, price: float, source: str):
    cache = load_cache()
    cache["stocks"][symbol] = {
        "price": price,
        "source": source,
        "time": datetime.now().strftime("%H:%M:%S"),
        "exchange": exchange
    }
    cache["last_update"] = datetime.now().strftime("%H:%M:%S")
    save_cache(cache)

def set_mode(mode: str):
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)


# ══════════════════════════════════════════
#  LOAD ALL WATCHLIST STOCKS
# ══════════════════════════════════════════

def get_all_watchlist_stocks() -> list:
    """Get unique stocks from all 3 watchlists"""
    try:
        if not os.path.exists(WATCHLIST_FILE):
            return []
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        all_stocks = []
        for tab in [f"watchlist_{n}" for n in WATCHLIST_NAMES]:
            all_stocks.extend(data.get(tab, []))
        # Remove duplicates by symbol+exchange
        seen = set()
        unique = []
        for s in all_stocks:
            key = (s.get("symbol"), s.get("exchange","NS"))
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return []


# ══════════════════════════════════════════
#  TOKEN MAPPING
# ══════════════════════════════════════════

def build_token_map(stocks: list) -> dict:
    """Build token → (symbol, exchange) mapping"""
    from stocks import get_stock_token
    token_map = {}
    nse_tokens = []
    bse_tokens = []

    for stock in stocks:
        symbol   = stock.get("symbol")
        exchange = stock.get("exchange", "NS")
        token    = get_stock_token(symbol)
        if not token:
            continue
        token_map[token] = (symbol, exchange)
        if exchange == "NS":
            nse_tokens.append(token)
        else:
            bse_tokens.append(token)

    return token_map, nse_tokens, bse_tokens


# ══════════════════════════════════════════
#  WEBSOCKET PRICE STREAMER
# ══════════════════════════════════════════

class PriceStreamer:
    def __init__(self, auth_token, api_key, client_code, feed_token):
        self.auth_token   = auth_token
        self.api_key      = api_key
        self.client_code  = client_code
        self.feed_token   = feed_token
        self.sws          = None
        self.token_map    = {}
        self.nse_tokens   = []
        self.bse_tokens   = []

    def on_data(self, wsapp, message):
        """Receive live price tick from Angel One WebSocket"""
        try:
            if isinstance(message, bytes):
                # Parse binary LTP packet
                if len(message) < 51:
                    return
                token = message[2:27].decode("utf-8").rstrip("\x00")
                ltp   = struct.unpack("<i", message[43:47])[0] / 100.0

                if token in self.token_map:
                    symbol, exchange = self.token_map[token]
                    update_price(symbol, exchange, ltp, "websocket")
            else:
                # Text message (subscription confirmation etc.)
                print(f"WS text: {message}")
        except Exception as e:
            print(f"on_data error: {e}")

    def on_open(self, wsapp):
        """Subscribe to all watchlist stocks on open"""
        print("✓ WebSocket connected")
        set_mode("websocket")

        token_list = []
        if self.nse_tokens:
            token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens:
            token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})

        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)  # mode 1 = LTP
            print(f"✓ Subscribed {len(self.nse_tokens)} NSE + {len(self.bse_tokens)} BSE stocks")

    def on_error(self, wsapp, error):
        print(f"✗ WebSocket error: {error}")
        set_mode("offline")

    def on_close(self, wsapp):
        print("✗ WebSocket closed")
        set_mode("offline")

    def start(self):
        """Start WebSocket streaming"""
        try:
            # Load watchlist stocks
            stocks = get_all_watchlist_stocks()
            if not stocks:
                print("No stocks in watchlist")
                return

            self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
            print(f"📊 Loaded {len(self.token_map)} stocks for streaming")

            # Create SmartWebSocketV2 instance
            self.sws = SmartWebSocketV2(
                self.auth_token,
                self.api_key,
                self.client_code,
                self.feed_token
            )

            # Assign callbacks
            self.sws.on_open  = self.on_open
            self.sws.on_data  = self.on_data
            self.sws.on_error = self.on_error
            self.sws.on_close = self.on_close

            # Connect (blocking call, runs in background thread)
            self.sws.connect()

        except Exception as e:
            print(f"✗ Streamer error: {e}")
            set_mode("offline")


# ══════════════════════════════════════════
#  HTTP POLLING FALLBACK
# ══════════════════════════════════════════

def http_polling_fallback(angel_obj):
    """Fallback: HTTP polling every 5 seconds if WebSocket fails"""
    from stocks import get_stock_token
    print("📡 Starting HTTP polling fallback...")
    set_mode("http_polling")

    while True:
        try:
            if not is_market_open():
                set_mode("offline")
                time.sleep(60)
                continue

            stocks = get_all_watchlist_stocks()
            # Fetch in batches of 50
            for i in range(0, len(stocks), 50):
                batch = stocks[i:i+50]
                for stock in batch:
                    try:
                        symbol   = stock.get("symbol")
                        exchange = stock.get("exchange", "NS")
                        token    = get_stock_token(symbol)
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
                        print(f"HTTP error {symbol}: {e}")
                time.sleep(1)  # 1 sec between batches
            time.sleep(5)  # 5 sec between full cycles
        except Exception as e:
            print(f"HTTP polling error: {e}")
            time.sleep(10)


# ══════════════════════════════════════════
#  YFINANCE FALLBACK
# ══════════════════════════════════════════

def yfinance_fallback():
    """Last resort: yfinance if both WebSocket and HTTP fail"""
    import yfinance as yf
    print("🔄 Starting yfinance fallback...")
    set_mode("yfinance")

    while True:
        try:
            if not is_market_open():
                set_mode("offline")
                time.sleep(60)
                continue

            stocks = get_all_watchlist_stocks()
            for stock in stocks:
                try:
                    symbol   = stock.get("symbol")
                    exchange = stock.get("exchange", "NS")
                    suffix   = ".NS" if exchange == "NS" else ".BO"
                    ticker   = yf.Ticker(f"{symbol}{suffix}")
                    price    = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
                    if price:
                        update_price(symbol, exchange, float(price), "yfinance")
                except Exception as e:
                    print(f"yfinance error {stock.get('symbol')}: {e}")
            time.sleep(10)
        except Exception as e:
            print(f"yfinance fallback error: {e}")
            time.sleep(10)


# ══════════════════════════════════════════
#  BACKGROUND THREAD LAUNCHER
# ══════════════════════════════════════════

def start_price_streamer(auth_token, api_key, client_code, feed_token, angel_obj):
    """Main background loop: WebSocket → HTTP → yfinance"""
    while True:
        try:
            if not is_market_open():
                set_mode("offline")
                time.sleep(300)
                continue

            print("📡 Starting WebSocket price streamer...")
            streamer = PriceStreamer(auth_token, api_key, client_code, feed_token)
            streamer.start()  # Blocking — runs until disconnect

            # WebSocket disconnected — try HTTP fallback
            print("⚠️ WebSocket disconnected, trying HTTP polling...")
            try:
                http_polling_fallback(angel_obj)
            except Exception:
                # HTTP also failed — try yfinance
                print("⚠️ HTTP polling failed, trying yfinance...")
                yfinance_fallback()

        except Exception as e:
            print(f"Streamer loop error: {e}")
            time.sleep(10)


# ══════════════════════════════════════════
#  STREAMLIT UI + SESSION INIT
# ══════════════════════════════════════════

# Init session state for streamer
if "streamer_started" not in st.session_state:
    st.session_state.streamer_started = False

if "angel_connected" not in st.session_state:
    st.session_state.angel_connected = False

# ── AUTO-CONNECT ON APP LOAD ──
if not st.session_state.streamer_started:
    try:
        api_key      = st.secrets["API_KEY"]
        client_code  = st.secrets["CLIENT_CODE"]
        password     = st.secrets["PASSWORD"]
        totp_secret  = st.secrets["TOTP_SECRET"]

        angel_obj    = SmartConnect(api_key=api_key)
        totp         = pyotp.TOTP(totp_secret).now()
        session_data = angel_obj.generateSession(client_code, password, totp)

        if session_data.get("status"):
            auth_token = session_data["data"]["jwtToken"]
            feed_token = angel_obj.getfeedToken()

            # Start background thread
            thread = threading.Thread(
                target=start_price_streamer,
                args=(auth_token, api_key, client_code, feed_token, angel_obj),
                daemon=True
            )
            thread.start()

            st.session_state.streamer_started = True
            st.session_state.angel_connected  = True
            print("✅ Price streamer started in background!")
        else:
            print(f"❌ Angel One login failed: {session_data.get('message')}")
            st.session_state.angel_connected = False

    except Exception as e:
        print(f"❌ Streamer init error: {e}")
        st.session_state.angel_connected = False


# ── UI ──
cache = load_cache()
mode  = cache.get("mode", "offline")
last  = cache.get("last_update", "---")
total = len(cache.get("stocks", {}))

mode_badge = {
    "websocket":    "🟢 WebSocket Live",
    "http_polling": "🟡 HTTP Polling",
    "yfinance":     "🟠 yfinance",
    "offline":      "⚪ Offline"
}

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Connection", mode_badge.get(mode, "Unknown"))
with col2:
    st.metric("Last Update", last)
with col3:
    st.metric("Stocks Tracked", total)

if st.session_state.angel_connected:
    st.success("✅ Angel One connected · Price streamer running in background")
else:
    st.warning("⚠️ Could not connect to Angel One. Check secrets.")

st.info("💡 Price streamer runs automatically in background. Go to Watchlist to see live prices.")
