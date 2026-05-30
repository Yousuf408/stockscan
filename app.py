# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  Production-Grade Safe WebSocket Streamer
#  With Unmapped Token UI Fallback Core Engine
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
#  NEW HELPER — minutes since last update
#  Used ONLY by the offline fallback block.
#  Does NOT affect any live market logic.
# ══════════════════════════════════════════

def _minutes_since_last_update(time_str: str) -> int:
    """
    Returns how many minutes have passed since a 'HH:MM:SS IST' timestamp.
    Returns 999 on any parse failure so a refresh is always triggered safely.
    """
    try:
        now = now_ist()
        clean = time_str.replace(" IST", "").strip()
        t = datetime.strptime(clean, "%H:%M:%S")
        # Attach today's date and IST timezone
        t_ist = IST.localize(
            t.replace(year=now.year, month=now.month, day=now.day)
        )
        diff = (now - t_ist).total_seconds() / 60
        # If diff is negative the update was yesterday — treat as very stale
        return int(diff) if diff >= 0 else 999
    except Exception as e:
        print(f"[OfflineTimer] Could not parse '{time_str}': {e}")
        return 999


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

    # ── Auto-reflect actual fetch source in mode badge ──
    # This is the single source of truth for what the UI shows.
    # websocket → 🟢  |  http → 🟡  |  yfinance → 🟠
    source_to_mode = {
        "websocket": "websocket",
        "http":      "http_polling",
        "yfinance":  "yfinance",
    }
    if source in source_to_mode:
        cache["mode"] = source_to_mode[source]

    save_cache(cache)

def force_set_mode(mode: str):
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)

def increment_failure_count() -> int:
    cache = load_cache()
    current_fails = cache.get("failures", 0) + 1
    cache["failures"] = current_fails
    
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
        try: 
            token = get_stock_token(symbol)
        except: 
            token = None
            
        if not token: 
            print(f"[Token Warning] No valid active mapping found for symbol: {symbol}")
            continue
            
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
                token    = get_stock_token(symbol)
                
                if not token:
                    run_single_yfinance_patch(symbol, exchange)
                    continue
                    
                resp = angel_obj.ltpData("NSE" if exchange == "NS" else "BSE", symbol, str(token))
                if resp and resp.get("status"):
                    ltp = float(resp["data"]["ltp"])
                    update_price(symbol, exchange, ltp, "http")
            except Exception as e:
                print(f"[HTTP] API Routing Exception: {e}")
        time.sleep(1)

def run_yfinance_fallback():
    print("[yfinance Fallback] Fetching comprehensive cloud data feed...")
    stocks = get_all_watchlist_stocks()
    for stock in stocks:
        run_single_yfinance_patch(stock.get("symbol"), stock.get("exchange", "NS"))

def run_single_yfinance_patch(symbol: str, exchange: str):
    """Safely patches missing token data slots using a public web interface"""
    import yfinance as yf
    try:
        ticker_symbol = symbol
        if symbol.upper() == "BSE":
            ticker_symbol = "BSE" if exchange == "NS" else "540073"
            
        suffix = ".NS" if exchange == "NS" else ".BO"
        ticker = yf.Ticker(f"{ticker_symbol}{suffix}")
        price = (ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice"))
        if price:
            update_price(symbol, exchange, float(price), "yfinance")
    except Exception as e:
        print(f"[yfinance Patch Error] Failed to resolve value for {symbol}: {e}")


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

        # ── OFFLINE REFRESH STATE ──────────────────────────────────────────
        # Tracks when we last ran yfinance during market-closed hours.
        # Stored here (in-process) so we don't hammer yfinance every 60s.
        # This variable is intentionally LOCAL to the thread — it resets
        # on every app restart which is fine; yfinance will just run once
        # on startup and then every OFFLINE_REFRESH_MINS minutes.
        last_offline_refresh_time = None
        OFFLINE_REFRESH_MINS = 60   # refresh EOD prices once per hour

        while True:
            try:
                # ══════════════════════════════════════════════════════════
                #  OFFLINE BLOCK  (market closed or weekend)
                #  ── ONLY this block was changed. ──
                #  Everything below the offline block is original, untouched.
                # ══════════════════════════════════════════════════════════
                if not is_market_open():
                    self.is_ws_connected = False
                    # NOTE: do NOT force_set_mode("offline") here —
                    # update_price() will set mode to "yfinance" when it fetches,
                    # so the badge correctly shows 🟠 yfinance during offline refresh.
                    # We only set offline if yfinance itself fails (no data at all).

                    now = now_ist()

                    # Decide whether enough time has passed to refresh again
                    should_refresh = False

                    if last_offline_refresh_time is None:
                        # First iteration after startup — always refresh once
                        should_refresh = True
                    else:
                        mins_since = (now - last_offline_refresh_time).total_seconds() / 60
                        if mins_since >= OFFLINE_REFRESH_MINS:
                            should_refresh = True

                    if should_refresh:
                        print(f"[Offline EOD] Market closed — refreshing EOD prices via yfinance at {ist_time_str()}")
                        try:
                            run_yfinance_fallback()
                            # mode is now "yfinance" (set by update_price inside run_yfinance_fallback)
                            last_offline_refresh_time = now
                            print(f"[Offline EOD] Refresh complete. Next refresh in {OFFLINE_REFRESH_MINS} min.")
                        except Exception as yf_err:
                            # yfinance fully crashed — nothing fetched — show offline
                            force_set_mode("offline")
                            print(f"[Offline EOD] yfinance refresh failed: {yf_err}. Will retry next cycle.")
                    else:
                        mins_left = int(OFFLINE_REFRESH_MINS - (now - last_offline_refresh_time).total_seconds() / 60)
                        print(f"[Offline EOD] Sleeping... next refresh in ~{mins_left} min.")

                    time.sleep(60)
                    continue
                # ══════════════════════════════════════════════════════════
                #  END OFFLINE BLOCK — everything below is original & untouched
                # ══════════════════════════════════════════════════════════

                stocks = get_all_watchlist_stocks()
                if not stocks:
                    time.sleep(10)
                    continue

                # ── FILE PERMANENT STATE BLOCK CHECK ──
                cache = load_cache()
                if cache.get("circuit_broken", False):
                    print("[ANTI-BAN ACTIVATED] Polling safely via HTTP...")
                    run_http_polling(self.angel_obj)
                    time.sleep(15)
                    continue

                # Prepare assets and capture unmapped tickers
                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)
                
                # Check for unmapped assets like 'BSE' to run parallel yfinance patches
                for stock in stocks:
                    from stocks import get_stock_token
                    try: t = get_stock_token(stock.get("symbol"))
                    except: t = None
                    if not t:
                        run_single_yfinance_patch(stock.get("symbol"), stock.get("exchange", "NS"))

                if not self.token_map:
                    run_yfinance_fallback()
                    time.sleep(15)
                    continue

                self.refresh_angel_session()

                # ── Attempt WebSocket (failure count NOT incremented yet) ──
                print(f"[WS Engine] Attempting WebSocket connection...")
                self.sws = SmartWebSocketV2(
                    self.auth_token,
                    self.api_key,
                    self.client_code,
                    self.feed_token
                )

                self.sws.max_retry_attempt = 1
                self.sws.on_open  = self.on_open
                self.sws.on_data  = self.on_data
                self.sws.on_error = self.on_error
                self.sws.on_close = self.on_close

                network_worker = threading.Thread(target=self.sws.connect, daemon=True)
                network_worker.start()
                time.sleep(5)   # give WS time to handshake

                # ── Wait while WS is healthy ──
                while self.is_ws_connected and is_market_open():
                    time.sleep(1)

                # ── WS dropped during market hours → count as real failure ──
                if is_market_open() and not self.is_ws_connected:
                    current_fail_count = increment_failure_count()
                    print(f"[WS Engine] WebSocket lost. Failure count: {current_fail_count}/2. Running fallback...")

                    # Tier 1 fallback → HTTP polling
                    http_ok = False
                    try:
                        run_http_polling(self.angel_obj)
                        http_ok = True
                    except Exception as http_err:
                        print(f"[WS Engine] HTTP fallback also failed: {http_err}")

                    # Tier 2 fallback → yfinance (only if HTTP failed)
                    if not http_ok:
                        print("[WS Engine] Falling back to yfinance...")
                        try:
                            run_yfinance_fallback()
                        except Exception as yf_err:
                            print(f"[WS Engine] yfinance fallback failed too: {yf_err}")

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
    "yfinance":     "🟠 yfinance (Hybrid)",
    "offline":      "⚪ Market Closed"
}

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Price Feed Status", mode_badge.get(mode, "Unknown"))
with col2:
    st.metric("Last Price Update", last if last else "Waiting...")
with col3:
    st.metric("Total Unique Items Tracked", total)
with col4:
    st.metric("Market Status", f"{'🟢 Open' if market_now else '🔴 Closed'} · {ist_now}")

st.divider()

if status["connected"]:
    if cache.get("circuit_broken", False):
        st.error("🔒 Anti-Ban Protection Active: Core safe HTTP polling fallback processing active.")
    elif market_now:
        st.success("✅ Angel One Session Operational · Streamer processing prices across multi-channel fallbacks")
    else:
        st.warning(f"⏰ System Active · Market Closed · Engine idling until opening bell.")
else:
    st.error(f"❌ Initial Connection Failure: {status.get('error', 'Unknown Error')}")

with st.expander("🔧 System Diagnostic Admin Panel"):
    st.write(f"**Persistent Failures counted on disk:** `{cache.get('failures', 0)} / 2`")
    st.write(f"**Circuit Breaker Status:** `{cache.get('circuit_broken', False)}`")
    if st.button("♻️ Reset Circuit Breaker & Retry WebSocket Connection", type="primary"):
        reset_failure_count()
        force_set_mode("offline")
        st.success("State clean complete. App will safely attempt connection in next loop pass.")
        st.rerun()
