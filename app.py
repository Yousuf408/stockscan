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
#  TIMEZONE HELPERS
# ══════════════════════════════════════════

def now_ist() -> datetime:
    return datetime.now(pytz.utc).astimezone(IST)

def ist_time_str() -> str:
    return now_ist().strftime("%H:%M:%S IST")

def is_market_open() -> bool:
    now = now_ist()
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
        print(f"[Cache] Save error: {e}")

def update_price(symbol: str, exchange: str, price: float, source: str):
    cache = load_cache()
    cache["stocks"][symbol] = {
        "price":    price,
        "source":   source,
        "time":     ist_time_str(),
        "exchange": exchange
    }
    cache["last_update"] = ist_time_str()
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
        token = str(token)
        token_map[token] = (symbol, exchange)
        if exchange == "NS":
            nse_tokens.append(token)
        else:
            bse_tokens.append(token)

    return token_map, nse_tokens, bse_tokens


# ══════════════════════════════════════════
#  HTTP POLLING FALLBACK (SINGLE round)
# ══════════════════════════════════════════

def run_http_polling(angel_obj):
    try:
        from stocks import get_stock_token
    except:
        return

    print("[HTTP] Running single HTTP polling pass...")
    force_set_mode("http_polling")

    stocks = get_all_watchlist_stocks()
    if not stocks:
        return

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
                print(f"[HTTP] {stock.get('symbol')}: {e}")
        time.sleep(1)


# ══════════════════════════════════════════
#  YFINANCE FALLBACK (SINGLE round)
# ══════════════════════════════════════════

def run_yfinance_fallback():
    import yfinance as yf
    print("[yfinance] Running single yfinance fallback pass...")
    force_set_mode("yfinance")

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
        self.is_ws_connected = False  # Track state explicitly

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
                    # If data arrives but cache mode flipped away, restore it
                    cache = load_cache()
                    if cache.get("mode") != "websocket":
                        force_set_mode("websocket")
        except Exception as e:
            print(f"[WS] on_data error: {e}")

    def on_open(self, wsapp):
        print("[WS] Connected successfully!")
        self.is_ws_connected = True
        force_set_mode("websocket")
        token_list = []
        if self.nse_tokens:
            token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens:
            token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)
            print(f"[WS] Subscribed to tokens successfully.")

    def on_error(self, wsapp, error):
        print(f"[WS] Error hook triggered: {error}")
        self.is_ws_connected = False

    def on_close(self, wsapp, close_status_code=None, close_msg=None):
        print(f"[WS] Connection closed: {close_status_code} - {close_msg}")
        self.is_ws_connected = False

    def start_websocket(self):
        """Robust Supervisor loop tracking state directly"""
        while True:
            try:
                # ── Market closed handling ──
                if not is_market_open():
                    print(f"[Streamer] Market closed ({ist_time_str()}). Sleeping 60s...")
                    self.is_ws_connected = False
                    cache = load_cache()
                    if not cache.get("stocks"):
                        force_set_mode("offline")
                    time.sleep(60)
                    continue

                # ── Watchlist validation ──
                stocks = get_all_watchlist_stocks()
                if not stocks:
                    print("[Streamer] Watchlist empty. Retrying in 10s...")
                    time.sleep(10)
                    continue

                # ── Direct Connection Attempt ──
                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                
                if not self.token_map:
                    print("[Streamer] Mapping failed. Running yfinance fallback pass...")
                    run_yfinance_fallback()
                    time.sleep(10)
                    continue

                print(f"[WS] Initializing connection sequence at {ist_time_str()}...")
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
                
                # Run connection in an isolated thread or directly block safely
                # Depending on SmartApi internal updates, we add a keepalive check
                self.sws.connect()
                
                # Give it a 3-second window to switch self.is_ws_connected to True via on_open
                time.sleep(3)

                # Keep loop context alive here while connection flag remains active
                while self.is_ws_connected and is_market_open():
                    time.sleep(1)

                # ── Fallback Path (Triggers only if socket is explicitly unflagged) ──
                if is_market_open() and not self.is_ws_connected:
                    print("[Streamer] Connection dead or exited. Initiating fallback cycle...")
                    try:
                        run_http_polling(self.angel_obj)
                    except Exception as http_err:
                        print(f"[HTTP] Pass failed: {http_err}")
                        try:
                            run_yfinance_fallback()
                        except Exception as yf_err:
                            print(f"[yfinance] Pass failed: {yf_err}")

                time.sleep(5)

            except Exception as e:
                print(f"[Streamer] Super Loop error: {e}")
                self.is_ws_connected = False
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

        if not feed_token:
            status["error"] = "Feed token missing — WebSocket will not work"
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

    except Exception as e:
        status["error"] = str(e)

    return status


# ══════════════════════════════════════════
#  STREAMLIT UI
# ══════════════════════════════════════════

status     = init_price_streamer()
cache      = load_cache()
mode       = cache.get("mode", "offline")
last       = cache.get("last_update", "---")
total      = len(cache.get("stocks", {}))
market_now = is_market_open()
ist_now    = now_ist().strftime("%I:%M %p IST")

mode_badge = {
    "websocket":    "🟢 WebSocket Live",
    "http_polling": "🟡 HTTP Polling",
    "yfinance":     "🟠 yfinance (Delayed)",
    "offline":      "⚪ Market Closed"
}

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Price Feed", mode_badge.get(mode, "Unknown"))
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

st.info("💡 Go to **Watchlist** to see live prices. Streamer runs automatically across all pages.")

with st.expander("🔧 Debug — Force fetch prices (works anytime)"):
    st.write(f"**IST Time:** {ist_now}")
    st.write(f"**Market Open:** {market_now}")
    st.write(f"**Cache Mode:** `{mode}`")
    
    if st.button("🔄 Force fetch via yfinance", type="primary"):
        import yfinance as yf
        stocks = get_all_watchlist_stocks()
        if stocks:
            progress = st.progress(0, text="Fetching...")
            fetched  = 0
            for i, stock in enumerate(stocks):
                try:
                    symbol   = stock.get("symbol")
                    exchange = stock.get("exchange", "NS")
                    suffix   = ".NS" if exchange == "NS" else ".BO"
                    ticker   = yf.Ticker(f"{symbol}{suffix}")
                    price    = (ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice"))
                    if price:
                        update_price(symbol, exchange, float(price), "yfinance")
                        fetched += 1
                except:
                    pass
                progress.progress((i + 1) / len(stocks))
            force_set_mode("yfinance")
            st.rerun()