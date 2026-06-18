# simple_batch_insert.py
# Just insert live data to swing_live_data table every tick

from datetime import datetime
from logzero import logger
from config import STOCKS_WATCHLIST
import time

# Create token → symbol mapping
TOKEN_TO_SYMBOL = {}
for symbol, token, kind in STOCKS_WATCHLIST:
    TOKEN_TO_SYMBOL[token] = symbol

logger.info(f"✓ Token mapping: {len(TOKEN_TO_SYMBOL)} symbols")


def insert_live_data_to_db(latest_ticks, supabase_client, user_id):
    """
    Simple: Insert all current ticks to swing_live_data table
    
    Args:
        latest_ticks: dict from angel_ws {token: {open, high, low, close, volume}}
        supabase_client: Supabase client
        user_id: User UUID
    """
    
    if not latest_ticks:
        return False
    
    rows = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Convert memory ticks to DB format
    for token, tick_data in latest_ticks.items():
        symbol = TOKEN_TO_SYMBOL.get(token)
        
        if not symbol:
            continue
        
        row = {
            "user_id": user_id,
            "symbol": symbol,
            "trade_date": today,
            "open": float(tick_data.get('open', 0)),
            "high": float(tick_data.get('high', 0)),
            "low": float(tick_data.get('low', 0)),
            "close": float(tick_data.get('ltp', 0)),
            "volume": int(tick_data.get('volume', 0)),
            "token": int(token),
        }
        rows.append(row)
    
    if not rows:
        return False
    
    # Upsert to DB (insert or update if exists)
    try:
        result = supabase_client.table('swing_live_data').upsert(
            rows,
            ignore_duplicates=False
        ).execute()
        
        logger.info(f"✅ Inserted {len(rows)} rows to swing_live_data")
        return True
        
    except Exception as e:
        logger.error(f"❌ Insert failed: {e}")
        return False
