# ══════════════════════════════════════════
#  TRADESENTRY — app.py
#  v2: Fixed Railway deployment — removed st.secrets for AngelOne credentials
#      Now reads directly from os.environ (Railway environment variables)
# ══════════════════════════════════════════

import sys
import streamlit as st
import pyotp
import json
import os
import threading
import time
import struct
import pytz
from datetime import datetime
from auth_session import restore_session

print(f"[BOOT] Python {sys.version}")
print("[BOOT] app.py loading...")

try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    print("[BOOT] SmartApi OK")
except Exception as _e:
    print(f"[BOOT] SmartApi FAILED: {_e}")
    SmartConnect = None
    SmartWebSocketV2 = None

try:
    sys.path.append(os.path.dirname(__file__))
    from styles import apply_styles, sidebar_brand, page_header
    print("[BOOT] styles OK")
except Exception as _e:
    print(f"[BOOT] styles FAILED: {_e}")

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)
# Yahan se code paste karein
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# Yahan tak

# ── Auth guard ──
restore_session()
if not st.session_state.get("user_id"):
    st.warning("Please login to access this page.")
    if st.button("Go to Login →", type="primary"):
        st.switch_page("pages/0_Login.py")
    st.stop()

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
MARKET_OPEN  = (9,  15)
MARKET_CLOSE = (15, 30)


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

def _minutes_since_last_update(time_str: str) -> int:
    try:
        now = now_ist()
        clean = time_str.replace(" IST", "").strip()
        t = datetime.strptime(clean, "%H:%M:%S")
        t_ist = IST.localize(
            t.replace(year=now.year, month=now.month, day=now.day)
        )
        diff = (now - t_ist).total_seconds() / 60
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
        print("🚨 [CRITICAL SHUTDOWN] 2 continuous failures reached. Tripping Circuit Breaker!")
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
    import yfinance as yf
    print("[yfinance Fallback] Batch fetching all stocks...")
    stocks = get_all_watchlist_stocks()
    if not stocks:
        return

    ns_tickers = []
    bo_tickers = []
    ticker_map = {}

    for stock in stocks:
        sym    = stock.get("symbol", "").lstrip("$").strip().upper().replace(".NS","").replace(".BO","")
        exch   = stock.get("exchange", "NS")
        suffix = ".NS" if exch == "NS" else ".BO"
        t      = f"{sym}{suffix}"
        ticker_map[t] = (stock.get("symbol", sym), exch)
        if exch == "NS": ns_tickers.append(t)
        else:            bo_tickers.append(t)

    all_tickers = ns_tickers + bo_tickers
    if not all_tickers:
        return

    try:
        print(f"[yfinance Batch] Downloading {len(all_tickers)} tickers...")
        data = yf.download(
            tickers=" ".join(all_tickers),
            period="2d",
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=True
        )
        fetched = 0
        for ticker, (orig_symbol, exch) in ticker_map.items():
            try:
                if len(all_tickers) == 1:
                    price = float(data["Close"].iloc[-1])
                else:
                    price = float(data["Close"][ticker].dropna().iloc[-1])
                if price:
                    update_price(orig_symbol, exch, price, "yfinance")
                    fetched += 1
            except:
                run_single_yfinance_patch(orig_symbol, exch)
        print(f"[yfinance Batch] Done — {fetched}/{len(all_tickers)} prices fetched.")
    except Exception as e:
        print(f"[yfinance Batch] Failed: {e} — falling back to one by one...")
        for stock in stocks:
            run_single_yfinance_patch(stock.get("symbol"), stock.get("exchange", "NS"))

def run_single_yfinance_patch(symbol: str, exchange: str):
    import yfinance as yf
    try:
        clean = symbol.lstrip("$").strip().upper()
        clean = clean.replace(".NS", "").replace(".BO", "")
        if clean == "BSE":
            clean = "BSE" if exchange == "NS" else "540073"
        suffix = ".NS" if exchange == "NS" else ".BO"
        ticker = yf.Ticker(f"{clean}{suffix}")
        price = (ticker.fast_info.get("last_price") or
                 ticker.fast_info.get("regularMarketPrice"))
        if not price:
            hist = ticker.history(period="2d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price:
            update_price(symbol, exchange, float(price), "yfinance")
            print(f"[yfinance] ✅ {clean} = {price}")
        else:
            print(f"[yfinance] ❌ No price for {clean}{suffix}")
    except Exception as e:
        print(f"[yfinance Patch Error] {symbol}: {e}")


# ══════════════════════════════════════════
#  WEBSOCKET STREAMER
# ══════════════════════════════════════════

class PriceStreamer:
    def __init__(self, auth_token, api_key, client_code, feed_token, angel_obj):
        self.auth_token      = auth_token
        self.api_key         = api_key
        self.client_code     = client_code
        self.feed_token      = feed_token
        self.angel_obj       = angel_obj
        self.token_map       = {}
        self.nse_tokens      = []
        self.bse_tokens      = []
        self.sws             = None
        self.is_ws_connected = False

    def refresh_angel_session(self):
        cache = load_cache()
        if cache.get("circuit_broken", False): return False
        try:
            print("[Engine] Regenerating verification tokens...")

            # ── Direct os.environ read — no st.secrets ──
            password    = os.environ.get("ANGEL_PASSWORD", "")
            totp_secret = os.environ.get("ANGEL_TOTP_SECRET", "")

            if not password or not totp_secret:
                print("[Engine] ❌ ANGEL_PASSWORD or ANGEL_TOTP_SECRET not set in environment")
                return False

            self.angel_obj = SmartConnect(api_key=self.api_key)
            totp           = pyotp.TOTP(totp_secret).now()
            session_data   = self.angel_obj.generateSession(self.client_code, password, totp)

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
        last_yf_refresh = None
        YF_REFRESH_MINS = 15

        while True:
            try:
                print(f"[LOOP] tick at {ist_time_str()} | market_open={is_market_open()}")

                if not is_market_open():
                    self.is_ws_connected = False
                    now          = now_ist()
                    should_fetch = (
                        last_yf_refresh is None or
                        (now - last_yf_refresh).total_seconds() / 60 >= YF_REFRESH_MINS
                    )
                    if should_fetch:
                        stocks = get_all_watchlist_stocks()
                        if stocks:
                            print(f"[After Hours] Fetching EOD prices via yfinance at {ist_time_str()}")
                            try:
                                run_yfinance_fallback()
                                last_yf_refresh = now
                            except Exception as e:
                                force_set_mode("offline")
                                print(f"[After Hours] yfinance failed: {e}")
                        else:
                            force_set_mode("offline")
                    time.sleep(60)
                    continue

                last_yf_refresh = None
                stocks = get_all_watchlist_stocks()
                if not stocks:
                    time.sleep(10)
                    continue

                cache = load_cache()
                if cache.get("circuit_broken", False):
                    print("[Anti-Ban] Circuit broken — using HTTP polling...")
                    try:
                        run_http_polling(self.angel_obj)
                    except Exception as e:
                        print(f"[Anti-Ban] HTTP also failed: {e}")
                        run_yfinance_fallback()
                    time.sleep(15)
                    continue

                self.token_map, self.nse_tokens, self.bse_tokens = build_token_map(stocks)

                from stocks import get_stock_token
                for stock in stocks:
                    try:    t = get_stock_token(stock.get("symbol", "").lstrip("$").strip().upper())
                    except: t = None
                    if not t:
                        run_single_yfinance_patch(stock.get("symbol"), stock.get("exchange", "NS"))

                if not self.token_map:
                    print("[Market Hours] No mapped tokens — using yfinance for all stocks")
                    run_yfinance_fallback()
                    time.sleep(15)
                    continue

                self.refresh_angel_session()

                print(f"[WS Engine] Connecting WebSocket at {ist_time_str()}...")
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
                time.sleep(5)

                while self.is_ws_connected and is_market_open():
                    time.sleep(1)

                if is_market_open() and not self.is_ws_connected:
                    fail_count = increment_failure_count()
                    print(f"[WS Engine] WebSocket dropped. Failures: {fail_count}/2")
                    http_ok = False
                    try:
                        run_http_polling(self.angel_obj)
                        http_ok = True
                    except Exception as e:
                        print(f"[WS Engine] HTTP fallback failed: {e}")
                    if not http_ok:
                        try:
                            run_yfinance_fallback()
                        except Exception as e:
                            print(f"[WS Engine] yfinance fallback also failed: {e}")

                time.sleep(15)

            except Exception as e:
                print(f"[Master Safety Framework Trap] Error: {e}")
                self.is_ws_connected = False
                time.sleep(20)


# ══════════════════════════════════════════
#  INIT ENGINE — v2: direct os.environ read
# ══════════════════════════════════════════

def init_price_streamer():
    print("[STARTUP] init_price_streamer() called")
    status = {"connected": False, "error": ""}
    try:
        # ── Direct os.environ read — no st.secrets ──
        api_key     = os.environ.get("ANGEL_API_KEY", "")
        client_code = os.environ.get("ANGEL_CLIENT_ID", "")
        password    = os.environ.get("ANGEL_PASSWORD", "")
        totp_secret = os.environ.get("ANGEL_TOTP_SECRET", "")

        # Debug log
        print(f"[STARTUP] ANGEL_API_KEY   = {'SET' if api_key     else 'NOT SET ❌'}")
        print(f"[STARTUP] ANGEL_CLIENT_ID = {'SET' if client_code else 'NOT SET ❌'}")
        print(f"[STARTUP] ANGEL_PASSWORD  = {'SET' if password    else 'NOT SET ❌'}")
        print(f"[STARTUP] ANGEL_TOTP      = {'SET' if totp_secret else 'NOT SET ❌'}")

        if not all([api_key, client_code, password, totp_secret]):
            status["error"] = "One or more AngelOne credentials missing in environment variables"
            print(f"[STARTUP] ❌ {status['error']}")
            return status

        angel_obj    = SmartConnect(api_key=api_key)
        totp         = pyotp.TOTP(totp_secret).now()
        session_data = angel_obj.generateSession(client_code, password, totp)

        if not session_data or not session_data.get("status"):
            status["error"] = session_data.get("message", "Login failed") if session_data else "No response"
            print(f"[STARTUP] ❌ AngelOne login failed: {status['error']}")
            return status

        auth_token = session_data["data"]["jwtToken"]
        feed_token = session_data["data"].get("feedToken") or angel_obj.getfeedToken()

        if not feed_token:
            status["error"] = "Feed token missing"
            return status

        print("[STARTUP] ✅ AngelOne login successful")
        streamer = PriceStreamer(auth_token, api_key, client_code, feed_token, angel_obj)
        thread   = threading.Thread(target=streamer.start_websocket, daemon=True)
        thread.start()
        status["connected"] = True

    except Exception as e:
        status["error"] = str(e)
        print(f"[STARTUP] ❌ Exception: {e}")

    return status


# ══════════════════════════════════════════
#  STREAMLIT DASHBOARD UI
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
        st.warning("⏰ System Active · Market Closed · Engine idling until opening bell.")
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
