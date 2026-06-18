# angel_ws.py
# Place this file in your ROOT folder (same level as app.py)

from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import threading
import requests
import time
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ── Supabase config — Service Key bypasses RLS ─────────────────
SUPABASE_URL         = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDU2Mjg4NywiZXhwIjoyMDk2MTM4ODg3fQ.w3PiYb4G09QAam7hZ1rkZPjrHy934ywc8BUfDR77syo"

# ── Plain global dict — shared across all threads ──────────────
latest_ticks    = {}
_raw_messages   = []
_sws            = None
_thread         = None
_sync_thread    = None
_connected      = False
_correlation_id = "stockscan_live"
# ───────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# SECTION 1 — SUPABASE HELPERS
# ─────────────────────────────────────────────────────────────

def _get_supabase_headers():
    return {
        "apikey"       : SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type" : "application/json",
        "Prefer"       : "return=minimal",
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — FETCH TOKENS FROM swing_live_data
# ─────────────────────────────────────────────────────────────

def _fetch_tokens_from_db() -> list:
    """
    Fetch all tokens from swing_live_data.
    Service Key used — no user_id filter needed (RLS bypassed).
    """
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/swing_live_data",
            headers=_get_supabase_headers(),
            params={
                "select": "token",
                "token" : "not.is.null",
            },
            timeout=15,
        )
        r.raise_for_status()
        rows   = r.json()
        tokens = [str(row["token"]) for row in rows if row.get("token")]
        logger.info(f"Fetched {len(tokens)} tokens from swing_live_data")
        return tokens

    except Exception as e:
        logger.error(f"_fetch_tokens_from_db error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# SECTION 3 — MARKET HOURS CHECK
# ─────────────────────────────────────────────────────────────

def _is_market_open() -> bool:
    """Check if NSE market is open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
    now  = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)


# ─────────────────────────────────────────────────────────────
# SECTION 4 — BATCH SYNC TO SUPABASE (har 5 sec)
# ─────────────────────────────────────────────────────────────

def _batch_sync_to_supabase():
    """
    Background thread — har 5 sec mein latest_ticks → Supabase PATCH.
    Service Key use karta hai — no user_id needed (RLS bypassed).
    Token se match karke swing_live_data rows update karta hai.
    """
    logger.info("Batch sync thread started!")

    while _connected:
        try:
            time.sleep(5)

            if not _connected:
                break

            if not latest_ticks:
                continue

            if not _is_market_open():
                logger.info("Market closed — skipping sync")
                time.sleep(60)
                continue

            headers         = _get_supabase_headers()
            now_ist         = datetime.now(IST).isoformat()
            tokens_snapshot = dict(latest_ticks)
            updated         = 0
            errors          = 0

            for token, tick in tokens_snapshot.items():
                try:
                    r = requests.patch(
                        f"{SUPABASE_URL}/rest/v1/swing_live_data",
                        headers=headers,
                        params={
                            "token": f"eq.{token}",
                        },
                        json={
                            "open"      : round(tick.get("open", 0), 2),
                            "high"      : round(tick.get("high", 0), 2),
                            "low"       : round(tick.get("low", 0), 2),
                            "close"     : round(tick.get("ltp", 0), 2),
                            "volume"    : tick.get("volume", 0),
                            "updated_at": now_ist,
                        },
                        timeout=10,
                    )
                    if r.status_code in (200, 204):
                        updated += 1
                    else:
                        errors += 1
                        logger.warning(f"Sync failed token {token}: {r.status_code} {r.text[:100]}")

                except Exception as e:
                    errors += 1
                    logger.error(f"Sync error token {token}: {e}")

            logger.info(f"Batch sync done — {updated} updated, {errors} errors")

        except Exception as e:
            logger.error(f"_batch_sync_to_supabase error: {e}")
            time.sleep(5)

    logger.info("Batch sync thread stopped.")


# ─────────────────────────────────────────────────────────────
# SECTION 5 — WEBSOCKET CALLBACKS
# ─────────────────────────────────────────────────────────────

def on_data(wsapp, message):
    """Called on every tick from Angel One WebSocket."""
    global latest_ticks, _raw_messages

    try:
        _raw_messages.append(message)
        if len(_raw_messages) > 5:
            _raw_messages.pop(0)

        token = str(message.get('token', ''))
        if not token:
            return

        ltp        = message.get('last_traded_price', 0) / 100
        open_price = message.get('open_price_of_the_day', 0) / 100
        high_price = message.get('high_price_of_the_day', 0) / 100
        low_price  = message.get('low_price_of_the_day', 0) / 100
        close      = message.get('closed_price', 0) / 100
        volume     = message.get('volume_trade_for_the_day', 0)
        change     = message.get('net_change_value', 0) / 100
        chng_pct   = ((ltp - close) / close * 100) if close > 0 else 0

        raw_ts    = message.get('exchange_timestamp', 0)
        timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=IST).strftime('%H:%M:%S') if raw_ts else '-'

        latest_ticks[token] = {
            "ltp"        : ltp,
            "open"       : open_price,
            "high"       : high_price,
            "low"        : low_price,
            "close"      : close,
            "volume"     : volume,
            "change"     : change,
            "change_pct" : chng_pct,
            "timestamp"  : timestamp,
        }

        logger.info(f"TICK [{token}] LTP={ltp} | chng%={chng_pct:.2f} | time={timestamp}")

    except Exception as e:
        logger.error(f"on_data error: {e}")


def on_open(wsapp):
    """Called when WebSocket opens — fetch tokens from DB and subscribe."""
    global _connected
    _connected = True
    logger.info("WebSocket Connected! Fetching tokens from DB...")

    try:
        all_tokens = _fetch_tokens_from_db()

        if not all_tokens:
            logger.warning("No tokens from DB — using fallback tokens")
            _sws.subscribe(_correlation_id, 1, [
                {"exchangeType": 1, "tokens": ["26000", "26009"]}
            ])
            _sws.subscribe(_correlation_id, 2, [
                {"exchangeType": 1, "tokens": ["2885", "1594", "11536", "1333"]}
            ])
            logger.info("Fallback tokens subscribed")
            return

        # Angel One limit: 1000 per session — 950 safe limit
        BATCH_SIZE = 950
        for i in range(0, len(all_tokens), BATCH_SIZE):
            batch = all_tokens[i:i + BATCH_SIZE]
            _sws.subscribe(_correlation_id, 2, [
                {"exchangeType": 1, "tokens": batch}
            ])
            logger.info(f"Subscribed batch {i//BATCH_SIZE + 1}: {len(batch)} tokens")

        logger.info(f"Total {len(all_tokens)} tokens subscribed in Mode 2")

    except Exception as e:
        logger.error(f"Subscribe error: {e}")


def on_error(wsapp, error):
    logger.error(f"WebSocket Error: {error}")


def on_close(wsapp):
    global _connected
    _connected = False
    logger.info("WebSocket Closed")


# ─────────────────────────────────────────────────────────────
# SECTION 6 — START / STOP
# ─────────────────────────────────────────────────────────────

def start_websocket(jwt_token, api_key, client_id, feed_token, token_list=None):
    """Start WebSocket + batch sync thread in background."""
    global _sws, _thread, _sync_thread, latest_ticks, _connected

    latest_ticks = {}
    _connected   = True

    _sws = SmartWebSocketV2(
        auth_token  = jwt_token,
        api_key     = api_key,
        client_code = client_id,
        feed_token  = feed_token
    )

    _sws.on_open  = on_open
    _sws.on_data  = on_data
    _sws.on_error = on_error
    _sws.on_close = on_close

    def _run():
        try:
            logger.info("WebSocket connecting...")
            _sws.connect()
        except Exception as e:
            logger.error(f"WebSocket _run error: {e}")

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    logger.info("WebSocket thread started!")

    _sync_thread = threading.Thread(target=_batch_sync_to_supabase, daemon=True)
    _sync_thread.start()
    logger.info("Batch sync thread started!")


def stop_websocket():
    """Close WebSocket — sync thread bhi automatically stop hoga."""
    global _sws, _connected
    _connected = False
    if _sws:
        try:
            _sws.close_connection()
            logger.info("WebSocket stopped.")
        except Exception as e:
            logger.error(f"Stop error: {e}")


# ─────────────────────────────────────────────────────────────
# SECTION 7 — GETTERS
# ─────────────────────────────────────────────────────────────

def get_latest_ticks():
    return latest_ticks

def get_raw_messages():
    return _raw_messages

def is_connected():
    return _connected
