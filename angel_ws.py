# angel_ws.py
# Place this file in your ROOT folder (same level as app.py)

from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import threading
import requests
import time
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

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
# SECTION 1 — SUPABASE HELPERS (imported from swing_core)
# ─────────────────────────────────────────────────────────────

def _get_supabase():
    """Get Supabase URL and headers from swing_core."""
    try:
        from swing_core import _get_config, _get_access_token, _get_user_id
        url, key   = _get_config()
        token      = _get_access_token()
        uid        = _get_user_id()
        headers    = {
            "apikey"       : key,
            "Authorization": f"Bearer {token or key}",
            "Content-Type" : "application/json",
            "Prefer"       : "return=minimal",
        }
        return url, headers, uid
    except Exception as e:
        logger.error(f"_get_supabase error: {e}")
        return None, None, None


# ─────────────────────────────────────────────────────────────
# SECTION 2 — FETCH TOKENS FROM swing_live_data
# ─────────────────────────────────────────────────────────────

def _fetch_tokens_from_db() -> list:
    """
    Fetch all tokens from swing_live_data table.
    Returns list of token strings.
    """
    try:
        url, headers, uid = _get_supabase()
        if not url or not uid:
            logger.error("Supabase config missing — cannot fetch tokens")
            return []

        r = requests.get(
            f"{url}/rest/v1/swing_live_data",
            headers=headers,
            params={
                "select"  : "token",
                "user_id" : f"eq.{uid}",
                "token"   : "not.is.null",  # sirf filled tokens
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
# SECTION 3 — BATCH SYNC TO SUPABASE (har 5 sec)
# ─────────────────────────────────────────────────────────────

def _is_market_open() -> bool:
    """Check if NSE market is open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
    now  = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)


def _batch_sync_to_supabase():
    """
    Background thread — har 5 sec mein latest_ticks → Supabase UPDATE.
    Sirf market hours mein chalega (9:15 AM - 3:30 PM IST).
    Token se match karke swing_live_data mein update karega.
    """
    logger.info("Batch sync thread started!")

    while _connected:
        try:
            time.sleep(5)

            if not _connected:
                break

            if not latest_ticks:
                continue

            # Market hours check
            if not _is_market_open():
                logger.info("Market closed — skipping sync")
                time.sleep(60)
                continue

            url, headers, uid = _get_supabase()
            if not url or not uid:
                continue

            now_ist = datetime.now(IST).isoformat()

            # Har token ke liye ek update request
            # Batch mein karte hain — 50 at a time
            tokens_snapshot = dict(latest_ticks)  # thread-safe copy
            updated = 0

            for token, tick in tokens_snapshot.items():
                try:
                    r = requests.patch(
                        f"{url}/rest/v1/swing_live_data",
                        headers=headers,
                        params={
                            "user_id": f"eq.{uid}",
                            "token"  : f"eq.{token}",
                        },
                        json={
                            "open"      : round(tick.get("open", 0), 2),
                            "high"      : round(tick.get("high", 0), 2),
                            "low"       : round(tick.get("low", 0), 2),
                            "close"     : round(tick.get("ltp", 0), 2),  # LTP → close column
                            "volume"    : tick.get("volume", 0),
                            "updated_at": now_ist,
                        },
                        timeout=10,
                    )
                    if r.status_code in (200, 204):
                        updated += 1
                    else:
                        logger.warning(f"Sync failed token {token}: {r.status_code} {r.text}")

                except Exception as e:
                    logger.error(f"Sync error token {token}: {e}")

            logger.info(f"Batch sync done — {updated}/{len(tokens_snapshot)} tokens updated")

        except Exception as e:
            logger.error(f"_batch_sync_to_supabase error: {e}")
            time.sleep(5)

    logger.info("Batch sync thread stopped.")


# ─────────────────────────────────────────────────────────────
# SECTION 4 — WEBSOCKET CALLBACKS (same as before)
# ─────────────────────────────────────────────────────────────

def on_data(wsapp, message):
    """Called on every tick from Angel One WebSocket."""
    global latest_ticks, _raw_messages

    try:
        # Store raw message for debugging (last 5 only)
        _raw_messages.append(message)
        if len(_raw_messages) > 5:
            _raw_messages.pop(0)

        token = str(message.get('token', ''))
        if not token:
            logger.warning(f"No token in message: {message}")
            return

        # Angel One sends prices in paise → divide by 100
        ltp        = message.get('last_traded_price', 0) / 100
        open_price = message.get('open_price_of_the_day', 0) / 100
        high_price = message.get('high_price_of_the_day', 0) / 100
        low_price  = message.get('low_price_of_the_day', 0) / 100
        close      = message.get('closed_price', 0) / 100
        volume     = message.get('volume_trade_for_the_day', 0)
        change     = message.get('net_change_value', 0) / 100
        chng_pct   = ((ltp - close) / close * 100) if close > 0 else 0

        # Timestamp: epoch milliseconds → IST HH:MM:SS
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
        logger.error(f"on_data error: {e} | raw msg: {message}")


def on_open(wsapp):
    """
    Called when WebSocket connection opens.
    Tokens fetch from swing_live_data → subscribe in batches of 950.
    """
    global _connected
    _connected = True
    logger.info("WebSocket Connected! Fetching tokens from DB...")

    try:
        # DB se tokens fetch karo
        all_tokens = _fetch_tokens_from_db()

        if not all_tokens:
            # Fallback — hardcoded indices + stocks (5_LiveFeed.py ke liye)
            logger.warning("No tokens from DB — using fallback tokens")
            _sws.subscribe(_correlation_id, 1, [
                {"exchangeType": 1, "tokens": ["26000", "26009"]}
            ])
            _sws.subscribe(_correlation_id, 2, [
                {"exchangeType": 1, "tokens": ["2885", "1594", "11536", "1333"]}
            ])
            logger.info("Fallback tokens subscribed")
            return

        # Angel One limit: 1000 per session
        # Mode 2 = 1 subscription per token
        # 950 safe limit rakhte hain
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
# SECTION 5 — START / STOP
# ─────────────────────────────────────────────────────────────

def start_websocket(jwt_token, api_key, client_id, feed_token, token_list=None):
    """Start WebSocket + batch sync thread in background."""
    global _sws, _thread, _sync_thread, latest_ticks, _connected

    # Reset ticks on new connection
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

    # WebSocket thread
    def _run():
        try:
            logger.info("WebSocket connecting...")
            _sws.connect()
        except Exception as e:
            logger.error(f"WebSocket _run error: {e}")

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    logger.info("WebSocket thread started!")

    # Batch sync thread — har 5 sec Supabase update
    _sync_thread = threading.Thread(target=_batch_sync_to_supabase, daemon=True)
    _sync_thread.start()
    logger.info("Batch sync thread started!")


def stop_websocket():
    """Close WebSocket — sync thread bhi automatically stop hoga."""
    global _sws, _connected
    _connected = False  # sync thread bhi ruk jayega
    if _sws:
        try:
            _sws.close_connection()
            logger.info("WebSocket stopped.")
        except Exception as e:
            logger.error(f"Stop error: {e}")


# ─────────────────────────────────────────────────────────────
# SECTION 6 — GETTERS (same as before)
# ─────────────────────────────────────────────────────────────

def get_latest_ticks():
    return latest_ticks


def get_raw_messages():
    return _raw_messages


def is_connected():
    return _connected
