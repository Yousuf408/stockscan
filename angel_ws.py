# angel_ws.py
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import threading
import streamlit as st

_sws = None
_thread = None
_correlation_id = "stockscan_live"

def _get_ticks():
    if 'latest_ticks' not in st.session_state:
        st.session_state['latest_ticks'] = {}
    return st.session_state['latest_ticks']

def on_data(wsapp, message):
    try:
        token = str(message.get('token', ''))
        ticks = _get_ticks()
        ticks[token] = {
            "ltp"        : message.get('last_traded_price', 0) / 100,
            "open"       : message.get('open_price_of_the_day', 0) / 100,
            "high"       : message.get('high_price_of_the_day', 0) / 100,
            "low"        : message.get('low_price_of_the_day', 0) / 100,
            "close"      : message.get('closed_price', 0) / 100,
            "volume"     : message.get('volume_trade_for_the_day', 0),
            "change"     : message.get('net_change_value', 0) / 100,
            "change_pct" : message.get('net_change_percentage', 0),
            "timestamp"  : message.get('exchange_timestamp', '')
        }
        st.session_state['latest_ticks'] = ticks
        logger.info(f"Tick: {token} → LTP: {ticks[token]['ltp']}")
    except Exception as e:
        logger.error(f"on_data error: {e}")

def on_open(wsapp):
    logger.info("WebSocket Connected! Subscribing...")
    try:
        index_tokens = {
            "exchangeType": 1,
            "tokens": ["26000", "26009"]
        }
        _sws.subscribe(_correlation_id, 1, [index_tokens])
        logger.info("Indices subscribed Mode 1")

        stock_tokens = {
            "exchangeType": 1,
            "tokens": ["2885", "1594", "11536", "1333"]
        }
        _sws.subscribe(_correlation_id, 2, [stock_tokens])
        logger.info("Stocks subscribed Mode 2")

    except Exception as e:
        logger.error(f"Subscribe error: {e}")

def on_error(wsapp, error):
    logger.error(f"WebSocket Error: {error}")

def on_close(wsapp):
    logger.info("WebSocket Closed")

def stop_websocket():
    global _sws
    if _sws:
        try:
            _sws.close_connection()
            logger.info("WebSocket stopped.")
        except Exception as e:
            logger.error(f"Stop error: {e}")

def get_latest_ticks():
    if 'latest_ticks' not in st.session_state:
        return {}
    return st.session_state['latest_ticks']

def start_websocket(jwt_token, api_key, client_id, feed_token, token_list):
    global _sws, _thread

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
            logger.info("Connecting WebSocket...")
            _sws.connect()
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    logger.info("WebSocket thread started!")
