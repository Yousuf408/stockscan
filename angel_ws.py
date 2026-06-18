# angel_ws.py - FIXED for multi-user with proper (user_id, symbol) matching
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
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jamt0c21tIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDU2Mjg4NywiZXhwIjoyMDk2MTM4ODg3fQ.w3PiYb4G09QAam7hZ1rkZPjrHy934ywc8BUfDR77syo"

# ── Global state — shared across all threads ──────────────────
latest_ticks    = {}          # {token: {ltp, volume, open, high, low, close, ...}}
token_metadata  = {}          # {token: {user_id, symbol}} — THE FIX!
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
# SECTION 2 — FETCH TOKENS FROM swing_live_data WITH METADATA
# ─────────────────────────────────────────────────────────────

def _fetch_tokens_from_db() -> dict:
    """
    Fetch tokens WITH user_id and symbol.
    Returns: {token_str: {"user_id": "...", "symbol": "..."}, ...}
    
    WHY: swing_live_data's unique constraint is (user_id, symbol).
    We need both to update the correct row.
    """
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/swing_live_data",
            headers=_get_supabase_headers(),
            params={
                "select": "token,user_id,symbol",
                "token": "not.is.null",  # Only fetch rows with non-null token
            },
            timeout=15,
        )
        r.raise_for_status()
        rows = r.json()
        
        # Build mapping: token → (user_id, symbol)
        token_map = {}
        for row in rows:
            token = str(row.get("token", ""))
            user_id = row.get("user_id")
            symbol = row.get("symbol")
            
            if token and user_id and symbol:
                token_map[token] = {
                    "user_id": user_id,
                    "symbol": symbol
                }
        
        logger.info(f"✓ Fetched {len(token_map)} tokens with metadata from swing_live_data")
        for token, meta in list(token_map.items())[:3]:
            logger.debug(f"  Example: token={token}, symbol={meta['symbol']}, user={meta['user_id'][:8]}...")
        
        return token_map

    except Exception as e:
        logger.error(f"_fetch_tokens_from_db error: {e}", exc_info=True)
        return {}


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
# SECTION 4 — BATCH SYNC TO SUPABASE (every 5 sec)
# ─────────────────────────────────────────────────────────────

def _batch_sync_to_supabase():
    """
    Background thread — every 5 sec, sync latest_ticks to Supabase.
    
    KEY FIX: Use (user_id, symbol) as the unique filter, not token.
    Because swing_live_data.unique = (user_id, symbol).
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
                    # ═══ THE FIX ═══
                    # Get user_id and symbol for this token
                    meta = token_metadata.get(token)
                    if not meta:
                        logger.warning(f"⚠️  No metadata for token {token} (not in token_metadata)")
                        errors += 1
                        continue
                    
                    user_id = meta["user_id"]
                    symbol = meta["symbol"]
                    # ═══════════════

                    # PATCH using (user_id, symbol) — the UNIQUE constraint!
                    r = requests.patch(
                        f"{SUPABASE_URL}/rest/v1/swing_live_data",
                        headers=headers,
                        params={
                            "user_id": f"eq.{user_id}",
                            "symbol": f"eq.{symbol}",
                        },
                        json={
                            "token": int(token),  # Ensure stored as integer
                            "open": round(tick.get("open", 0), 2),
                            "high": round(tick.get("high", 0), 2),
                            "low": round(tick.get("low", 0), 2),
                            "close": round(tick.get("ltp", 0), 2),
                            "volume": tick.get("volume", 0),
                            "updated_at": now_ist,
                        },
                        timeout=10,
                    )
                    
                    if r.status_code in (200, 204):
                        updated += 1
                        logger.debug(f"✓ Synced {symbol} (user={user_id[:8]}..., token={token})")
                    else:
                        errors += 1
                        logger.error(
                            f"✗ Sync failed {symbol} (user={user_id[:8]}...): {r.status_code} {r.text[:150]}"
                        )

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

        # Check if this token has metadata
        meta = token_metadata.get(token)
        symbol_label = meta.get("symbol", "?") if meta else "?"

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

        logger.info(f"TICK [{token}] {symbol_label} LTP={ltp} | chng%={chng_pct:.2f} | vol={volume} | time={timestamp}")

    except Exception as e:
        logger.error(f"on_data error: {e}")


def on_open(wsapp):
    """Called when WebSocket opens — fetch tokens from DB and subscribe."""
    global _connected, token_metadata
    _connected = True
    logger.info("🔗 WebSocket Connected! Fetching tokens from DB...")

    try:
        # ═══ THE FIX ═══
        # Fetch tokens WITH user_id and symbol
        token_map = _fetch_tokens_from_db()
        # ═══════════════

        if not token_map:
            logger.warning("⚠️  No tokens from DB — using fallback tokens")
            token_metadata = {
                "2885": {"user_id": "fallback-uid", "symbol": "SBIN"},
                "1594": {"user_id": "fallback-uid", "symbol": "HDFC"},
                "11536": {"user_id": "fallback-uid", "symbol": "AXISBANK"},
                "1333": {"user_id": "fallback-uid", "symbol": "INFY"},
            }
            _sws.subscribe(_correlation_id, 1, [
                {"exchangeType": 1, "tokens": ["26000", "26009"]}
            ])
            _sws.subscribe(_correlation_id, 2, [
                {"exchangeType": 1, "tokens": ["2885", "1594", "11536", "1333"]}
            ])
            logger.info("Fallback tokens subscribed")
            return

        # Store metadata for sync thread
        token_metadata = token_map

        # Extract just token IDs for subscription
        all_tokens = list(token_map.keys())

        # Subscribe in batches (Angel One limit: 1000 per session)
        BATCH_SIZE = 950
        for i in range(0, len(all_tokens), BATCH_SIZE):
            batch = all_tokens[i:i + BATCH_SIZE]
            _sws.subscribe(_correlation_id, 2, [
                {"exchangeType": 1, "tokens": batch}
            ])
            logger.info(f"✓ Subscribed batch {i//BATCH_SIZE + 1}: {len(batch)} tokens")

        logger.info(f"✓ Total {len(all_tokens)} tokens ready for sync")

    except Exception as e:
        logger.error(f"Subscribe error: {e}", exc_info=True)


def on_error(wsapp, error):
    logger.error(f"🔴 WebSocket Error: {error}")


def on_close(wsapp):
    global _connected
    _connected = False
    logger.info("🔌 WebSocket Closed")


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
            logger.info("🔗 WebSocket connecting...")
            _sws.connect()
        except Exception as e:
            logger.error(f"WebSocket _run error: {e}")

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    logger.info("✓ WebSocket thread started!")

    _sync_thread = threading.Thread(target=_batch_sync_to_supabase, daemon=True)
    _sync_thread.start()
    logger.info("✓ Batch sync thread started!")


def stop_websocket():
    """Close WebSocket — sync thread bhi automatically stop hoga."""
    global _sws, _connected
    _connected = False
    if _sws:
        try:
            _sws.close_connection()
            logger.info("🛑 WebSocket stopped.")
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

def get_token_metadata():
    """Debug: see what metadata was fetched"""
    return token_metadata
