# websocket_to_json.py
# Simple: Save WebSocket ticks to JSON file every 30 seconds

import json
import os
from datetime import datetime
from logzero import logger
from config import STOCKS_WATCHLIST
import time

# Token to symbol mapping
TOKEN_TO_SYMBOL = {}
for symbol, token, kind in STOCKS_WATCHLIST:
    TOKEN_TO_SYMBOL[token] = symbol

JSON_FILE = "live_data.json"


def save_ticks_to_json(latest_ticks):
    """
    Save all WebSocket ticks to JSON file
    Simple, reliable, no database needed
    """
    
    if not latest_ticks:
        return
    
    data = {
        "last_updated": datetime.now().isoformat(),
        "ticks": {}
    }
    
    for token, tick in latest_ticks.items():
        symbol = TOKEN_TO_SYMBOL.get(token)
        if symbol:
            data["ticks"][symbol] = {
                "open": float(tick.get('open', 0)),
                "high": float(tick.get('high', 0)),
                "low": float(tick.get('low', 0)),
                "close": float(tick.get('ltp', 0)),
                "volume": int(tick.get('volume', 0)),
                "timestamp": tick.get('timestamp', ''),
            }
    
    try:
        with open(JSON_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"✅ Saved {len(data['ticks'])} ticks to {JSON_FILE}")
    except Exception as e:
        logger.error(f"❌ Failed to save JSON: {e}")


def load_ticks_from_json():
    """
    Load live data from JSON file
    """
    
    if not os.path.exists(JSON_FILE):
        return {}
    
    try:
        with open(JSON_FILE, 'r') as f:
            data = json.load(f)
        return data.get('ticks', {})
    except Exception as e:
        logger.error(f"❌ Failed to load JSON: {e}")
        return {}


def start_json_saver(angel_ws_module, interval_seconds=30):
    """
    Background thread that saves WebSocket data to JSON every N seconds
    
    Args:
        angel_ws_module: The angel_ws module (has latest_ticks)
        interval_seconds: How often to save (default 30s)
    """
    
    import threading
    
    def _save_loop():
        logger.info(f"🔄 JSON saver started (every {interval_seconds}s)")
        while True:
            try:
                time.sleep(interval_seconds)
                ticks = angel_ws_module.latest_ticks.copy()
                save_ticks_to_json(ticks)
            except Exception as e:
                logger.error(f"JSON save error: {e}")
    
    thread = threading.Thread(target=_save_loop, daemon=True)
    thread.start()
    logger.info("✓ JSON saver thread started")
