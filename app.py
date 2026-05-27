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

MARKET_OPEN  = 9 * 60 + 15   # 9:15 AM IST
MARKET_CLOSE = 15 * 60 + 30  # 3:30 PM IST


# ══════════════════════════════════════════
#  MARKET HOURS
# ══════════════════════════════════════════

def is_market_open() -> bool:
    now  = datetime.now()
    if now.weekday() >= 5:  # Saturday / Sunday
        return False
    mins = now.hour * 60 + now.minute
    return MARKET_OPEN <= mins <= MARKET_CLOSE


# ══════════════════════════════════════════
#  PRICE CACHE HELPERS
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
        print(f"[Cache] Save error: {e}")

def update_price(symbol: str, exchange: str, price: float, source: str):
    cache = load_cache()
    cache["stocks"][symbol] = {
        "price":    price,
        "source":   source,
        "time":     datetime.now().strftime("%H:%M:%S"),
        "exchange": exchange
    }
    cache["last_update"] = datetime.now().strftime("%H:%M:%S")
    save_cache(cache)

def set_mode(mode: str):
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
        # Deduplicate
        seen, unique = set(), []
        for s in all_stocks:
            key = (s.get("symbol"), s.get("exchange", "NS"))
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
    except Exception as e:
        print(f"[Watchlist] Load error: {e}")
        return []


# ══════════════════════════════════════════
#  BUILD TOKEN MAP
# ══════════════════════════════════════════

def build_token_map(stocks: list):
    try:
        from stocks import get_stock_token
    except Exception as e:
        print(f"[Token] Import error: {e}")
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

    print("[HTTP] Starting HTTP polling fallback...")
    set_mode("http_polling")

    while True:
        try:
            stocks = get_all_watchlist_stocks()
            if not stocks:
                time.sleep(10)
                continue

            for i in range(0, len(stocks), 50):
                batch = stocks[i:i + 50]
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
                        print(f"[HTTP] {stock.get('symbol')}: {e}")
                time.sleep(1)  # 1 sec between batches

            time.sleep(5)  # 5 sec between full cycles

        except Exception as e:
            print(f"[HTTP] Polling error: {e}")
            time.sleep(10)


# ══════════════════════════════════════════
#  YFINANCE FALLBACK
# ══════════════════════════════════════════

def run_yfinance_fallback():
    import yfinance as yf
    print("[yfinance] Starting yfinance fallback...")
    set_mode("yfinance")

    while True:
        try:
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
                    print(f"[yfinance] {stock.get('symbol')}: {e}")
            time.sleep(10)
        except Exception as e:
            print(f"[yfinance] Error: {e}")
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
        self.running     = False

    def on_data(self, wsapp, message):
        try:
            if isinstance(message, bytes):
                if len(message) < 51:
                    return
                token = message[2:27].decode("utf-8").rstrip("\x00")
                ltp   = struct.unpack("<i", message[43:47])[0] / 100.0
                if token in self.token_map:
                    symbol, exchange = self.token_map[token]
                    update_price(symbol, exchange, ltp, "websocket")
        except Exception as e:
            print(f"[WS] on_data error: {e}")

    def on_open(self, wsapp):
        print("[WS] Connected!")
        set_mode("websocket")
        token_list = []
        if self.nse_tokens:
            token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens:
            token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)
            print(f"[WS] Subscribed {len(self.nse_tokens)} NSE + {len(self.bse_tokens)} BSE")

    def on_error(self, wsapp, error):
        print(f"[WS] Error: {error}")
        self.running = False

    def on_close(self, wsapp):
        print("[WS] Closed")
        self.running = False

    def start_websocket(self):
        """Try WebSocket, fallback to HTTP, fallback to yfinance"""
        while True:
            try:
                # ── Market open check ──
                if not is_market_open():
                    print("[Streamer] Market closed. Showing cached prices. Waiting...")
                    set_mode("offline")
                    time.sleep(60)  # Check every minute
                    continue

                # ── Load stocks ──
                stocks = get_all_watchlist_stocks()
                if not stocks:
                    print("[Streamer] No stocks in watchlist yet. Retrying...")
                    time.sleep(10)
                    continue

                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                print(f"[Streamer] {len(self.token_map)} stocks loaded")

                if not self.token_map:
                    print("[Streamer] No valid tokens found. Falling back to yfinance...")
                    run_yfinance_fallback()
                    return

                # ── Try WebSocket ──
                try:
                    print("[WS] Connecting...")
                    self.running = True
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
                    self.sws.connect()  # Blocking until disconnect

                except Exception as ws_err:
                    print(f"[WS] Failed: {ws_err}")

                # ── WebSocket ended → try HTTP ──
                print("[Streamer] WebSocket ended. Trying HTTP polling...")
                try:
                    run_http_polling(self.angel_obj)
                except Exception as http_err:
                    print(f"[HTTP] Failed: {http_err}")

                # ── HTTP also failed → try yfinance ──
                print("[Streamer] HTTP failed. Falling back to yfinance...")
                run_yfinance_fallback()

            except Exception as e:
                print(f"[Streamer] Loop error: {e}")
                time.sleep(10)


# ══════════════════════════════════════════
#  st.cache_resource — PERSISTS ACROSS PAGES
#  This is the KEY fix — thread won't die
#  when user switches pages in Streamlit
# ══════════════════════════════════════════

@st.cache_resource
def init_price_streamer():
    """
    Called ONCE per Streamlit app lifetime.
    Starts background thread that persists across page changes.
    Returns status dict.
    """
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
        feed_token = angel_obj.getfeedToken()

        streamer = PriceStreamer(auth_token, api_key, client_code, feed_token, angel_obj)

        # Start background thread — daemon=True so it stops with app
        thread = threading.Thread(
            target=streamer.start_websocket,
            daemon=True
        )
        thread.start()

        status["connected"] = True
        print("✅ Price streamer thread started!")

    except Exception as e:
        status["error"] = str(e)
        print(f"❌ Streamer init error: {e}")

    return status


# ══════════════════════════════════════════
#  STREAMLIT UI
# ══════════════════════════════════════════

# This runs ONCE and persists — won't restart on page change
status = init_price_streamer()

# Load cache for display
cache      = load_cache()
mode       = cache.get("mode", "offline")
last       = cache.get("last_update", "---")
total      = len(cache.get("stocks", {}))
market_now = is_market_open()

mode_badge = {
    "websocket":    "🟢 WebSocket Live",
    "http_polling": "🟡 HTTP Polling",
    "yfinance":     "🟠 yfinance (Delayed)",
    "offline":      "⚪ Market Closed"
}

# ── Metrics ──
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Price Feed", mode_badge.get(mode, "Unknown"))
with col2:
    st.metric("Last Price Update", last if last else "Waiting...")
with col3:
    st.metric("Stocks Tracked", total)
with col4:
    st.metric("Market", "🟢 Open" if market_now else "🔴 Closed")

st.divider()

# ── Connection status ──
if status["connected"]:
    if market_now:
        st.success("✅ Angel One connected · WebSocket price streamer running in background")
    else:
        st.warning("⏰ Angel One connected · Market is closed (9:15 AM - 3:30 PM IST). Showing cached close prices in Watchlist.")
else:
    st.error(f"❌ Connection failed: {status.get('error', 'Unknown error')}")
    st.info("Check your API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET in Streamlit secrets.")

# ── Info ──
st.info("💡 Go to **Watchlist** to see live prices. The price streamer runs automatically in background across all pages.")

# ── Debug panel (only when market closed, for testing) ──
if not market_now:
    with st.expander("🔧 Debug — Force fetch prices (for testing outside market hours)"):
        st.warning("Market is closed. Use this to test if price fetching works.")
        if st.button("🔄 Force fetch via yfinance (test)", type="primary"):
            import yfinance as yf
            stocks = get_all_watchlist_stocks()
            if not stocks:
                st.error("No stocks in watchlist!")
            else:
                progress = st.progress(0, text="Fetching...")
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
                    except Exception as e:
                        st.write(f"Error {stock.get('symbol')}: {e}")
                    progress.progress((i + 1) / len(stocks))
                set_mode("yfinance")
                st.success(f"✅ Fetched prices for {len(stocks)} stocks! Go to Watchlist.")
                st.rerun()
