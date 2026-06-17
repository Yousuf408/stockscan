# angel_ws.py
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import threading
import time

# Latest ticks store karne ke liye
latest_ticks = {}
_sws = None
_thread = None

def on_data(wsapp, message):
    """Har tick aane par yahan aata hai"""
    try:
        token = str(message.get('token', ''))
        latest_ticks[token] = {
            "ltp"        : message.get('last_traded_price', 0) / 100,  # paise to rupees
            "open"       : message.get('open_price_of_the_day', 0) / 100,
            "high"       : message.get('high_price_of_the_day', 0) / 100,
            "low"        : message.get('low_price_of_the_day', 0) / 100,
            "close"      : message.get('closed_price', 0) / 100,
            "volume"     : message.get('volume_trade_for_the_day', 0),
            "change"     : message.get('net_change_value', 0) / 100,
            "change_pct" : message.get('net_change_percentage', 0),
            "timestamp"  : message.get('exchange_timestamp', '')
        }
        logger.info(f"Tick received: {token} → LTP: {latest_ticks[token]['ltp']}")
    except Exception as e:
        logger.error(f"on_data error: {e}")

def on_open(wsapp):
    logger.info("WebSocket Connected!")

def on_error(wsapp, error):
    logger.error(f"WebSocket Error: {error}")

def on_close(wsapp):
    logger.info("WebSocket Closed")

def start_websocket(jwt_token, api_key, client_id, feed_token, token_list):
    """
    WebSocket background thread mein start karo.

    token_list example:
    [{"exchangeType": 1, "tokens": ["26000", "2885"]}]
    """
    global _sws, _thread

    correlation_id = "stockscan_live"
    mode = 1  # 1 = LTP only | 2 = Quote | 3 = Snap Quote

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
            _sws.connect()
            time.sleep(1)
            _sws.subscribe(correlation_id, mode, token_list)
        except Exception as e:
            logger.error(f"WebSocket thread error: {e}")

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    logger.info("WebSocket thread started!")

def stop_websocket():
    global _sws
    if _sws:
        try:
            _sws.close_connection()
            logger.info("WebSocket stopped.")
        except Exception as e:
            logger.error(f"Stop error: {e}")

def get_latest_ticks():
    """Streamlit page se call karo latest data lene ke liye"""
    return latest_ticks
