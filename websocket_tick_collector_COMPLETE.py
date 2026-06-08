# ═════════════════════════════════════════════════════════════════════════════
# TRADESENTRY — websocket_tick_collector.py v3.1
# FIXED: SmartWebSocketV2 import moved INSIDE function (prevents module crash)
# ═════════════════════════════════════════════════════════════════════════════

import os
import json
import time
import threading
from datetime import datetime
import pytz
from collections import defaultdict

IST = pytz.timezone("Asia/Kolkata")

print("[WebSocket Module] ✅ websocket_tick_collector.py loaded successfully")


def collect_live_high_low_with_fallback(angel_obj, symbols_with_tokens: list,
                                        http_candles: dict = None) -> dict:
    """
    Collect High/Low using Angel One SmartWebSocketV2.
    Falls back to HTTP candles if WebSocket fails.
    """

    print("\n" + "="*70)
    print("[Collection] STARTING HIGH/LOW COLLECTION")
    print(f"[Collection] Time      : {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[Collection] Symbols   : {len(symbols_with_tokens)}")
    print("="*70 + "\n")

    # ── PHASE 1: Try SmartWebSocketV2 ────────────────────────────────────────
    print("[Collection] PHASE 1: Attempting SmartWebSocketV2...")
    print("-"*70)

    try:
        result = _collect_via_smartwebsocket(angel_obj, symbols_with_tokens)

        valid = {k: v for k, v in result.items() if v.get("tick_count", 0) > 0}
        print(f"[Collection] WebSocket valid symbols: {len(valid)} / {len(symbols_with_tokens)}")

        if valid:
            print("[Collection] ✅ PHASE 1 SUCCESS!")
            return result
        else:
            print("[Collection] ⚠️ PHASE 1: No ticks collected → falling back to HTTP")

    except Exception as e:
        import traceback
        print(f"[Collection] ❌ PHASE 1 FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()

    # ── PHASE 2: HTTP Fallback ────────────────────────────────────────────────
    print("\n[Collection] PHASE 2: Using HTTP Fallback...")
    print("-"*70)

    result = {}

    if not http_candles:
        print("[Collection] ❌ No HTTP candle data provided — returning empty")
        return result

    for s in symbols_with_tokens:
        symbol = s["symbol"]
        candle = http_candles.get(symbol)
        if candle:
            try:
                high = float(candle[2])
                low  = float(candle[3])
                result[symbol] = {
                    "high":      high,
                    "low":       low,
                    "http_high": high,
                    "http_low":  low,
                    "source":    "http",
                    "tick_count": 1,
                    "error":     "WebSocket unavailable - using HTTP",
                }
                print(f"[HTTP] ✅ {symbol}: H={high:.2f} L={low:.2f}")
            except Exception as e:
                print(f"[HTTP] ❌ {symbol}: Parse error — {e}")
        else:
            print(f"[HTTP] ❌ {symbol}: No candle data")

    print(f"\n[Collection] PHASE 2 COMPLETE: {len(result)} symbols")
    return result


def _collect_via_smartwebsocket(angel_obj, symbols_with_tokens: list,
                                duration_secs: int = 300) -> dict:
    """
    Real Angel One WebSocket using SmartWebSocketV2.
    Import is INSIDE function to prevent module-level crash.
    """

    # ── Step 1: Import INSIDE function (safe) ────────────────────────────────
    print("[WebSocket] 🔌 Importing SmartWebSocketV2...")
    try:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        print("[WebSocket] ✅ SmartWebSocketV2 imported successfully")
    except ImportError as e:
        print(f"[WebSocket] ❌ Import failed: {e}")
        print("[WebSocket] Run: pip install smartapi-python --upgrade")
        raise

    # ── Step 2: Get credentials ───────────────────────────────────────────────
    print("[WebSocket] 🔑 Getting credentials...")
    try:
        api_key     = os.environ.get("ANGEL_API_KEY", "")
        client_code = os.environ.get("ANGEL_CLIENT_ID", "")
        feed_token  = angel_obj.feed_token
        auth_token  = angel_obj.access_token

        print(f"[WebSocket] api_key     = {'✅ SET' if api_key     else '❌ NOT SET'}")
        print(f"[WebSocket] client_code = {'✅ SET' if client_code else '❌ NOT SET'}")
        print(f"[WebSocket] feed_token  = {'✅ SET' if feed_token  else '❌ NOT SET'}")
        print(f"[WebSocket] auth_token  = {'✅ SET' if auth_token  else '❌ NOT SET'}")

        if not all([api_key, client_code, feed_token, auth_token]):
            raise Exception("Missing credentials for WebSocket")

    except Exception as e:
        print(f"[WebSocket] ❌ Credentials error: {type(e).__name__}: {e}")
        raise

    # ── Step 3: Build token list ──────────────────────────────────────────────
    tokens_by_exchange = defaultdict(list)
    token_to_symbol    = {}

    for s in symbols_with_tokens:
        ex_type = 1 if s.get("exchange", "NSE") in ("NSE", "NS") else 3
        tokens_by_exchange[ex_type].append(s["token"])
        token_to_symbol[s["token"]] = s["symbol"]

    token_list = [
        {"exchangeType": ex, "tokens": toks}
        for ex, toks in tokens_by_exchange.items()
    ]

    print(f"[WebSocket] 📊 Tokens:")
    for item in token_list:
        ex_name = "NSE" if item["exchangeType"] == 1 else "BSE"
        print(f"[WebSocket]    {ex_name}: {len(item['tokens'])} tokens")

    # ── Step 4: Storage ───────────────────────────────────────────────────────
    ticks_storage = defaultdict(list)
    ws_connected  = threading.Event()
    ws_error      = {"msg": None}

    # ── Step 5: Callbacks ─────────────────────────────────────────────────────
    def on_open(wsapp):
        print(f"[WebSocket] ✅ CONNECTED at {datetime.now(IST).strftime('%H:%M:%S')}")
        ws_connected.set()

    def on_data(wsapp, message, data_type, continue_flag):
        try:
            if isinstance(message, dict):
                token = str(message.get("token", ""))
                ltp   = message.get("last_traded_price", 0)
                if ltp and ltp > 0:
                    price  = ltp / 100.0
                    symbol = token_to_symbol.get(token)
                    if symbol:
                        ticks_storage[symbol].append(price)
                        count = len(ticks_storage[symbol])
                        if count <= 3 or count % 20 == 0:
                            print(f"[WebSocket] 📈 {symbol}: ₹{price:.2f} ({count} ticks)")
        except Exception as e:
            print(f"[WebSocket] ⚠️ Tick parse error: {e}")

    def on_error(wsapp, error):
        print(f"[WebSocket] ❌ ERROR: {type(error).__name__}: {error}")
        ws_error["msg"] = str(error)

    def on_close(wsapp):
        print(f"[WebSocket] 🔌 CLOSED at {datetime.now(IST).strftime('%H:%M:%S')}")

    # ── Step 6: Create & Connect ──────────────────────────────────────────────
    print(f"[WebSocket] 🔌 Creating SmartWebSocketV2...")
    try:
        sws = SmartWebSocketV2(
            auth_token=auth_token,
            api_key=api_key,
            client_code=client_code,
            feed_token=feed_token,
            on_open=on_open,
            on_data=on_data,
            on_error=on_error,
            on_close=on_close,
            max_retry_attempt=3,
        )
        print(f"[WebSocket] ✅ SmartWebSocketV2 object created")
    except Exception as e:
        print(f"[WebSocket] ❌ Creation failed: {type(e).__name__}: {e}")
        raise

    # ── Step 7: Start in thread ───────────────────────────────────────────────
    def run_ws():
        try:
            print(f"[WebSocket] ▶ WebSocket thread starting...")
            sws.connect()
        except Exception as e:
            print(f"[WebSocket] ❌ Thread error: {type(e).__name__}: {e}")
            ws_error["msg"] = str(e)

    ws_thread = threading.Thread(target=run_ws, daemon=True)
    ws_thread.start()

    # ── Step 8: Wait for connection ───────────────────────────────────────────
    print(f"[WebSocket] ⏳ Waiting for connection (max 15s)...")
    connected = ws_connected.wait(timeout=15)

    if not connected:
        err = ws_error.get("msg", "Unknown")
        print(f"[WebSocket] ❌ TIMEOUT after 15s!")
        print(f"[WebSocket] Last error: {err}")
        print(f"[WebSocket] Likely causes:")
        print(f"[WebSocket]   1. Railway IP ({os.environ.get('RAILWAY_STATIC_URL','unknown')}) not whitelisted")
        print(f"[WebSocket]   2. feed_token invalid/expired")
        print(f"[WebSocket]   3. Firewall blocking WebSocket port")
        try:
            sws.close_connection()
        except:
            pass
        raise Exception(f"WebSocket timeout. Error: {err}")

    # ── Step 9: Subscribe ─────────────────────────────────────────────────────
    print(f"[WebSocket] 📡 Subscribing to {len(symbols_with_tokens)} symbols...")
    try:
        sws.subscribe("tradesentry_9_15", 2, token_list)
        print(f"[WebSocket] ✅ Subscribed!")
    except Exception as e:
        print(f"[WebSocket] ❌ Subscribe failed: {type(e).__name__}: {e}")
        try:
            sws.close_connection()
        except:
            pass
        raise

    # ── Step 10: Collect ──────────────────────────────────────────────────────
    print(f"[WebSocket] ⏱ Collecting for {duration_secs}s...")
    start_time    = time.time()
    last_log_time = start_time

    while time.time() - start_time < duration_secs:
        time.sleep(1)
        elapsed = time.time() - start_time

        if time.time() - last_log_time >= 30:
            total = sum(len(v) for v in ticks_storage.values())
            syms  = len([s for s in ticks_storage if ticks_storage[s]])
            print(f"[WebSocket] ⏱ {elapsed:.0f}s | {total} ticks | {syms} symbols")
            last_log_time = time.time()

        if ws_error["msg"] and not ticks_storage:
            print(f"[WebSocket] ❌ Error with no data: {ws_error['msg']} — stopping")
            break

    # ── Step 11: Close ────────────────────────────────────────────────────────
    print(f"[WebSocket] 🔌 Closing...")
    try:
        sws.close_connection()
    except Exception as e:
        print(f"[WebSocket] ⚠️ Close error (non-fatal): {e}")

    total = sum(len(v) for v in ticks_storage.values())
    print(f"[WebSocket] ✅ Done. Total ticks: {total}")

    # ── Step 12: Build result ─────────────────────────────────────────────────
    result = {}
    for s in symbols_with_tokens:
        symbol = s["symbol"]
        prices = ticks_storage.get(symbol, [])
        if prices:
            result[symbol] = {
                "high":       max(prices),
                "low":        min(prices),
                "source":     "websocket",
                "tick_count": len(prices),
            }
            print(f"[WebSocket] ✅ {symbol}: H={max(prices):.2f} L={min(prices):.2f} ({len(prices)} ticks)")
        else:
            result[symbol] = {
                "high": None, "low": None,
                "source": "websocket", "tick_count": 0,
                "error": "No ticks received",
            }
            print(f"[WebSocket] ⚠️ {symbol}: No ticks")

    return result
