# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Production-Grade Safe WebSocket Streamer
#  Strict Max-2-Retry Strict Circuit Breaker
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
#  PERSISTENT STATE SYSTEM (FILE BASED)
# ══════════════════════════════════════════

def load_cache() -> dict:
    if not os.path.exists(PRICE_CACHE_FILE):
        return {"mode": "offline", "last_update": "", "stocks": {}, "failures": 0, "circuit_broken": False}
    try:
        with open(PRICE_CACHE_FILE, "r") as f:
            data = json.load(f)
            if "failures" not in data: data["failures"] = 0
            if "circuit_broken" not in data: data["circuit_broken"] = False
            return data
    except:
        return {"mode": "offline", "last_update": "", "stocks": {}, "failures": 0, "circuit_broken": False}

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

def increment_failure_count() -> int:
    cache = load_cache()
    current_fails = cache.get("failures", 0) + 1
    cache["failures"] = current_fails
    
    # STRICT RULE: Hard shutdown on exactly 2 failed attempts
    if current_fails >= 2:
        cache["circuit_broken"] = True
        cache["mode"] = "http_polling"
        print("🚨 [CRITICAL SHUTDOWN] 2 continuous failures reached. Tripping Circuit Breaker to prevent API Ban!")
    save_cache(cache)
    return current_fails

def reset_failure_count():
    cache = load_cache()
    cache["failures"] = 0
    cache["circuit_broken"] = False
    save_cache(cache)


# ══════════════════════════════════════════
#  DATA FETCH HANDLING
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
        try: token = get_stock_token(symbol)
        except: token = None
        if not token: continue
        token = str(token)
        token_map[token] = (symbol, exchange)
        if exchange == "NS": nse_tokens.append(token)
        else: bse_tokens.append(token)

    return token_map, nse_tokens, bse_tokens


# ══════════════════════════════════════════
#  THROTTLED FALLBACK MODES
# ══════════════════════════════════════════

def run_http_polling(angel_obj):
    try:
        from stocks import get_stock_token
    except:
        return

    print("[HTTP Fallback] Fetching prices over safe REST channels...")
    force_set_mode("http_polling")
    stocks = get_all_watchlist_stocks()
    if not stocks: return

    for i in range(0, len(stocks), 50):
        batch = stocks[i:i + 50]
        for stock in batch:
            try:
                symbol   = stock.get("symbol")
                exchange = stock.get("exchange", "NS")
                token    = str(get_stock_token(symbol) or "")
                if not token: continue
                resp = angel_obj.ltpData("NSE" if exchange == "NS" else "BSE", symbol, token)
                if resp and resp.get("status"):
                    ltp = float(resp["data"]["ltp"])
                    update_price(symbol, exchange, ltp, "http")
            except Exception as e:
                print(f"[HTTP] API Sleep State: {e}")
        time.sleep(1)

def run_yfinance_fallback():
    import yfinance as yf
    print("[yfinance Fallback] Fetching cloud data feed...")
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
            print(f"[yfinance] Error: {e}")


# ══════════════════════════════════════════
#  WEBSOCKET STREAMER (OVERIDDEN RETRY LOOP)
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
        self.is_ws_connected = False

    def refresh_angel_session(self):
        cache = load_cache()
        if cache.get("circuit_broken", False): return False
        try:
            print("[Engine] Regenerating verification tokens...")
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
            print(f"[Engine] Session refresh failed: {e}")
            return False

    def on_data(self, wsapp, message):
        try:
            if isinstance(message, bytes) and len(message) >= 51:
                token = message[2:27].decode("utf-8").rstrip("\x00").strip()
                ltp   = struct.unpack("<i", message[43:47])[0] / 100.0
                if token in self.token_map:
                    symbol, exchange = self.token_map[token]
                    update_price(symbol, exchange, ltp, "websocket")
                    reset_failure_count()
                    
                    cache = load_cache()
                    if cache.get("mode") != "websocket":
                        force_set_mode("websocket")
        except Exception as e:
            print(f"[WS Data Parsing Error] {e}")

    def on_open(self, wsapp):
        print("[WS Stream] Protocol approved. Socket active.")
        self.is_ws_connected = True
        reset_failure_count()
        force_set_mode("websocket")
        
        token_list = []
        if self.nse_tokens: token_list.append({"exchangeType": 1, "tokens": self.nse_tokens})
        if self.bse_tokens: token_list.append({"exchangeType": 3, "tokens": self.bse_tokens})
        if token_list: wsapp.subscribe("ts_001", 1, token_list)

    def on_error(self, wsapp, error):
        print(f"[WS Stream] Network boundary error: {error}")
        self.is_ws_connected = False

    def on_close(self, wsapp, close_status_code=None, close_msg=None):
        print("[WS Stream] Socket safely disconnected.")
        self.is_ws_connected = False

    def start_websocket(self):
        """Supervisor loop carrying overriden SDK configuration properties"""
        while True:
            try:
                if not is_market_open():
                    self.is_ws_connected = False
                    force_set_mode("offline")
                    time.sleep(60)
                    continue

                stocks = get_all_watchlist_stocks()
                if not stocks:
                    time.sleep(10)
                    continue

                # ── FILE PERMANENT STATE BLOCK CHECK ──
                cache = load_cache()
                if cache.get("circuit_broken", False):
                    print("[ANTI-BAN ACTIVATED] Polling cleanly via HTTP every 15s to guarantee account protection...")
                    run_http_polling(self.angel_obj)
                    time.sleep(15)
                    continue

                # Prepare assets
                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                if not self.token_map:
                    run_yfinance_fallback()
                    time.sleep(10)
                    continue

                self.refresh_angel_session()
                
                # Register attempt to permanent storage
                current_fail_count = increment_failure_count()
                print(f"[WS Engine] Attempting WebSocket Connection... Persistent Trace Count: {current_fail_count}/2")
                
                self.sws = SmartWebSocketV2(
                    self.auth_token,
                    self.api_key,
                    self.client_code,
                    self.feed_token
                )
                
                # ── FORCE OVERRIDE ANGEL ONE INTERNAL RETRY LOOP ──
                self.sws.max_retry_attempt = 1  # Stop internal SDK looping!
                
                self.sws.on_open  = self.on_open
                self.sws.on_data  = self.on_data
                self.sws.on_error = self.on_error
                self.sws.on_close = self.on_close
                
                # Run connection in isolated background thread
                network_worker = threading.Thread(target=self.sws.connect, daemon=True)
                network_worker.start()
                
                # Wait 5 seconds to verify if handshake is accepted
                time.sleep(5)

                # Maintain context anchor while connection stays up
                while self.is_ws_connected and is_market_open():
                    time.sleep(1)

                # If connection dropped, execute single-pass fallback
                if is_market_open() and not self.is_ws_connected:
                    print("[WS Engine] Connection failed or ended. Processing safe fallback route...")
                    try: run_http_polling(self.angel_obj)
                    except:
                        try: run_yfinance_fallback()
                        except: pass

                # Enforce a 15-second delay before attempting another loop iteration
                time.sleep(15)

            except Exception as e:
                print(f"[Master Safety Framework Trap] Error: {e}")
                self.is_ws_connected = False
                time.sleep(20)


# ══════════════════════════════════════════
#  INIT ENGINE RESOURCE
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

        streamer = PriceStreamer(auth_token, api_key, client_code, feed_token, angel_obj)
        thread = threading.Thread(target=streamer.start_websocket, daemon=True)
        thread.start()
        status["connected"] = True

    except Exception as e:
        status["error"] = str(e)

    return status


# ══════════════════════════════════════════
#  STREAMLIT DASHBOARD UI VIEW
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
    if cache.get("circuit_broken", False):
        st.error("🔒 Anti-Ban Protection Active: The background WebSocket was permanently shut down after 2 failed connection handshakes. Secure, throttled HTTP Polling fallback is active to safeguard your credentials.")
    elif market_now:
        st.success("✅ Angel One Session Operational · Streamer actively processing prices")
    else:
        st.warning(f"⏰ System Active · Market Closed · Engine idling until opening bell.")
else:
    st.error(f"❌ Initial Connection Failure: {status.get('error', 'Unknown Error')}")

# Diagnostic Panel Admin Reset Area
with st.expander("🔧 System Diagnostic Admin Panel"):
    st.write(f"**Persistent Failures counted on disk:** `{cache.get('failures', 0)} / 2`")
    st.write(f"**Circuit Breaker Status:** `{cache.get('circuit_broken', False)}`")
    if st.button("♻️ Reset Circuit Breaker & Retry WebSocket Connection", type="primary"):
        reset_failure_count()
        force_set_mode("offline")
        st.success("State clean complete. App will safely attempt connection in next loop pass.")
        st.rerun()