# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Production-Grade WebSocket Price Streamer
#  With Anti-Ban Circuit Breaker & Rate Limiter
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
#  HTTP POLLING FALLBACK (THROTTLED PASS)
# ══════════════════════════════════════════

def run_http_polling(angel_obj):
    try:
        from stocks import get_stock_token
    except:
        return

    print("[HTTP] Executing safe fallback price poll...")
    force_set_mode("http_polling")

    stocks = get_all_watchlist_stocks()
    if not stocks:
        return

    # Process batch with sleep spacing to avoid HTTP rate limits
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
                print(f"[HTTP] API Error for {stock.get('symbol')}: {e}")
        time.sleep(1)


# ══════════════════════════════════════════
#  YFINANCE FALLBACK
# ══════════════════════════════════════════

def run_yfinance_fallback():
    import yfinance as yf
    print("[yfinance] Executing backup yfinance pass...")
    force_set_mode("yfinance")

    stocks = get_all_watchlist_stocks()
    for stock in stocks:
        try:
            symbol   = stock.get("symbol")
            exchange = stock.get("exchange", "NS")
            suffix   = ".NS" if exchange == "NS" else ".BO"
            ticker   = yf.Ticker(f"{symbol}{suffix}")
            price    = (ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice"))
            if price:
                update_price(symbol, exchange, float(price), "yfinance")
        except Exception as e:
            print(f"[yfinance] Ticker Error {stock.get('symbol')}: {e}")


# ══════════════════════════════════════════
#  WEBSOCKET STREAMER CLASS (WITH CIRCUIT BREAKER)
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
        
        # Runtime State Controller Flags
        self.is_ws_connected = False
        self.connection_failures = 0
        self.circuit_broken = False  # Protection lock flag

    def refresh_angel_session(self):
        """Safely re-authenticates to grab clean authorization tokens"""
        if self.circuit_broken:
            return False
        try:
            print("[Engine] Refreshing API session credentials...")
            password    = st.secrets["PASSWORD"]
            totp_secret = st.secrets["TOTP_SECRET"]
            
            self.angel_obj = SmartConnect(api_key=self.api_key)
            totp = pyotp.TOTP(totp_secret).now()
            session_data = self.angel_obj.generateSession(self.client_code, password, totp)
            
            if session_data and session_data.get("status"):
                self.auth_token = session_data["data"]["jwtToken"]
                self.feed_token = session_data["data"].get("feedToken") or self.angel_obj.getfeedToken()
                return True
            return False
        except Exception as e:
            print(f"[Engine] Session re-auth error: {e}")
            return False

    def on_data(self, wsapp, message):
        try:
            if isinstance(message, bytes) and len(message) >= 51:
                token = message[2:27].decode("utf-8").rstrip("\x00").strip()
                ltp   = struct.unpack("<i", message[43:47])[0] / 100.0
                if token in self.token_map:
                    symbol, exchange = self.token_map[token]
                    update_price(symbol, exchange, ltp, "websocket")
                    
                    # Reset failure memory upon a valid message frame receipt
                    self.connection_failures = 0
                    
                    cache = load_cache()
                    if cache.get("mode") != "websocket":
                        force_set_mode("websocket")
        except Exception as e:
            print(f"[WS Data] Parsing exception: {e}")

    def on_open(self, wsapp):
        print("[WS Stream] Socket handshake accepted by remote host!")
        self.is_ws_connected = True
        self.connection_failures = 0
        force_set_mode("websocket")
        
        token_list = []
        if self.nse_tokens:
            token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens:
            token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})
        if token_list:
            wsapp.subscribe("ts_001", 1, token_list)

    def on_error(self, wsapp, error):
        print(f"[WS Stream] Error state caught: {error}")
        self.is_ws_connected = False

    def on_close(self, wsapp, close_status_code=None, close_msg=None):
        print("[WS Stream] Connection offline.")
        self.is_ws_connected = False

    def start_websocket(self):
        """Supervisor loop carrying an API ban-protection circuit breaker"""
        while True:
            try:
                if not is_market_open():
                    print(f"[Streamer] Market closed. Sleeping 60s...")
                    self.is_ws_connected = False
                    force_set_mode("offline")
                    time.sleep(60)
                    continue

                stocks = get_all_watchlist_stocks()
                if not stocks:
                    time.sleep(10)
                    continue

                # ── CRITICAL CIRCUIT BREAKER CHECK ──
                if self.circuit_broken:
                    # WebSocket is locked out. Fallback safely to HTTP polling mode on a timed interval.
                    print("[GUARD] Circuit broken to prevent API ban! Running safe HTTP poll every 10s...")
                    run_http_polling(self.angel_obj)
                    time.sleep(10)
                    continue

                # Prepare tracking tokens
                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                if not self.token_map:
                    run_yfinance_fallback()
                    time.sleep(10)
                    continue

                # Throttle and check connection history logs
                if self.connection_failures >= 3:
                    print("❌ [GUARD] 3 consecutive connection failures dropped by Angel One. Tripping Circuit Breaker to save your API keys!")
                    self.circuit_broken = True
                    continue

                # Refresh variables right before starting the connection engine
                self.refresh_angel_session()
                self.connection_failures += 1  # Optimistically count attempt
                
                print(f"[WS Engine] Launching network socket thread... Attempt #{self.connection_failures}")
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
                
                # Spawn network client loop in an isolated system worker thread
                network_worker = threading.Thread(target=self.sws.connect, daemon=True)
                network_worker.start()
                
                # Allow a 5-second setup window to let connection confirm stability
                time.sleep(5)

                # Keep thread scope anchored while connection flag holds stable
                while self.is_ws_connected and is_market_open():
                    time.sleep(1)

                # ── Post-Crash Single Cleanup Cycle ──
                if is_market_open() and not self.is_ws_connected:
                    print("[WS Engine] Connection broke. Executing single round fallback loop...")
                    try:
                        run_http_polling(self.angel_obj)
                    except:
                        try:
                            run_yfinance_fallback()
                        except:
                            pass

                # Back off connection request cycle to avoid token spam flags
                time.sleep(10)

            except Exception as e:
                print(f"[Streamer Master] Fatal exception loop error: {e}")
                self.is_ws_connected = False
                time.sleep(15)


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
            status["error"] = "Feed token missing"
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

    except Exception as e:
        status["error"] = str(e)

    return status


# ══════════════════════════════════════════
#  STREAMLIT INTERFACE CORE
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
        st.success("✅ Angel One Session Operational · Core Background Streamer Processing Prices")
    else:
        st.warning(f"⏰ System Active · Market Closed · Engine idling until next open standard window.")
else:
    st.error(f"❌ Initial Connection Failure: {status.get('error', 'Unknown Error')}")

st.info("💡 Navigation Tip: Open the **Watchlist** route to view real-time data calculations.")