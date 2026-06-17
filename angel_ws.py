# angel_ws.py
# Place this file in your ROOT folder (same level as app.py)

from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import threading
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ── Plain global dict — shared across all threads ──────────────
latest_ticks    = {}
_raw_messages   = []
_sws            = None
_thread         = None
_connected      = False
_correlation_id = "stockscan_live"
# ───────────────────────────────────────────────────────────────


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
    """Called when WebSocket connection opens — subscribe here."""
    global _connected
    _connected = True
    logger.info("WebSocket Connected! Subscribing now...")

    try:
        # Mode 1 = LTP only (Indices only support Mode 1)
        _sws.subscribe(_correlation_id, 1, [
            {"exchangeType": 1, "tokens": ["26000", "26009"]}
        ])
        logger.info("Subscribed Indices in Mode 1 (LTP)")

        # Mode 2 = Quote (LTP + OHLC + Volume + Change)
        _sws.subscribe(_correlation_id, 2, [
            {"exchangeType": 1, "tokens": ["2885", "1594", "11536", "1333"]}
        ])
        logger.info("Subscribed Stocks in Mode 2 (OHLC + Volume)")

    except Exception as e:
        logger.error(f"Subscribe error: {e}")


def on_error(wsapp, error):
    logger.error(f"WebSocket Error: {error}")


def on_close(wsapp):
    global _connected
    _connected = False
    logger.info("WebSocket Closed")


def start_websocket(jwt_token, api_key, client_id, feed_token, token_list=None):
    """Start WebSocket in a background daemon thread."""
    global _sws, _thread, latest_ticks

    # Reset ticks on new connection
    latest_ticks = {}

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


def stop_websocket():
    """Close the WebSocket connection."""
    global _sws, _connected
    if _sws:
        try:
            _sws.close_connection()
            _connected = False
            logger.info("WebSocket stopped.")
        except Exception as e:
            logger.error(f"Stop error: {e}")


def get_latest_ticks():
    return latest_ticks


def get_raw_messages():
    return _raw_messages


def is_connected():
    return _connected
