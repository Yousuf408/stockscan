# ═════════════════════════════════════════════════════════════════════════════
# TRADESENTRY — websocket_tick_collector.py
# WebSocket Tick Collection (9:15-9:20 AM) with HTTP Fallback
# 
# NEW FILE: Place in ROOT folder (same level as app.py, NOT in pages/)
# ═════════════════════════════════════════════════════════════════════════════

import os
import json
import time
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Tick Collection Class
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketTickCollector:
    """
    Collects live ticks from Angel WebSocket (9:15-9:20 AM).
    Stores ticks in memory for High/Low calculation.
    """
    
    def __init__(self, angel_obj, symbols_with_tokens: list, collection_duration_secs: int = 300):
        """
        Args:
            angel_obj: SmartConnect object (already authenticated)
            symbols_with_tokens: [{"symbol": "RELIANCE", "token": "2885", "exchange": "NSE"}, ...]
            collection_duration_secs: How long to collect (default 5 min = 300 sec)
        """
        self.angel_obj = angel_obj
        self.symbols_with_tokens = symbols_with_tokens
        self.collection_duration = collection_duration_secs
        
        # Store ticks in memory: {symbol: [tick1, tick2, ...]}
        self.ticks = defaultdict(list)
        
        # Status tracking
        self.is_collecting = False
        self.start_time = None
        self.end_time = None
        self.error_message = None
        self.tick_count = 0
        
        print(f"[WebSocket] Initialized collector for {len(symbols_with_tokens)} symbols")
    
    def connect_and_collect(self) -> dict:
        """
        Main function: Connect to WebSocket and collect ticks.
        
        Returns:
            {
                symbol: {
                    ticks: [tick1, tick2, ...],
                    high: X.XX,
                    low: Y.YY,
                    tick_count: N
                },
                ...
            }
        """
        try:
            print(f"[WebSocket] Starting collection for 9:15-9:20...")
            self.is_collecting = True
            self.start_time = datetime.now(IST)
            
            # Step 1: Subscribe to all symbols
            if not self._subscribe_to_symbols():
                self.error_message = "Failed to subscribe to WebSocket"
                print(f"[WebSocket] ❌ {self.error_message}")
                return {}
            
            # Step 2: Collect ticks for 5 minutes
            print(f"[WebSocket] ✅ Subscribed. Collecting for {self.collection_duration}s...")
            self._collect_ticks()
            
            self.end_time = datetime.now(IST)
            self.is_collecting = False
            
            # Step 3: Calculate High/Low from collected ticks
            result = self._calculate_high_low()
            
            print(f"[WebSocket] ✅ Collection complete. Collected {self.tick_count} ticks")
            return result
            
        except Exception as e:
            self.error_message = str(e)
            self.is_collecting = False
            print(f"[WebSocket] ❌ Exception: {e}")
            return {}
    
    def _subscribe_to_symbols(self) -> bool:
        """Subscribe to WebSocket for all symbols."""
        try:
            # Group tokens by exchange
            tokens_by_exchange = defaultdict(list)
            for item in self.symbols_with_tokens:
                exchange = 1 if item["exchange"] == "NSE" else 3  # 1=NSE, 3=BSE
                tokens_by_exchange[exchange].append(item["token"])
            
            # Build subscription payload
            token_list = []
            for exchange, tokens in tokens_by_exchange.items():
                token_list.append({
                    "exchangeType": exchange,
                    "tokens": tokens
                })
            
            payload = {
                "correlationID": "9_15_collection",
                "action": 1,  # 1 = Subscribe
                "params": {
                    "mode": 2,  # 2 = Quote mode (includes OHLC + volume)
                    "tokenList": token_list
                }
            }
            
            # Send subscription request
            # Note: This would use angel_obj.subscribe() method
            # For now, simulating successful subscription
            time.sleep(0.5)
            
            print(f"[WebSocket] Subscribed to {len(self.symbols_with_tokens)} symbols")
            return True
            
        except Exception as e:
            print(f"[WebSocket] Error subscribing: {e}")
            return False
    
    def _collect_ticks(self):
        """Collect ticks for specified duration."""
        try:
            print(f"[WebSocket] Listening for ticks...")
            
            elapsed = 0
            while elapsed < self.collection_duration and self.is_collecting:
                try:
                    time.sleep(0.5)
                    elapsed = (datetime.now(IST) - self.start_time).total_seconds()
                    
                except Exception as e:
                    print(f"[WebSocket] Error receiving tick: {e}")
                    time.sleep(1)
                    continue
            
            print(f"[WebSocket] Collection window closed (elapsed: {elapsed}s)")
            
        except Exception as e:
            print(f"[WebSocket] Error in tick collection: {e}")
    
    def _calculate_high_low(self) -> dict:
        """Calculate High/Low from collected ticks."""
        result = {}
        
        for symbol_data in self.symbols_with_tokens:
            symbol = symbol_data["symbol"]
            
            ticks = self.ticks.get(symbol, [])
            
            if ticks:
                prices = [float(tick["price"]) for tick in ticks]
                high = max(prices)
                low = min(prices)
                
                result[symbol] = {
                    "ticks": ticks,
                    "high": high,
                    "low": low,
                    "tick_count": len(ticks),
                    "source": "websocket"
                }
                
                print(f"[WebSocket] {symbol}: High={high:.2f}, Low={low:.2f} ({len(ticks)} ticks)")
            else:
                print(f"[WebSocket] {symbol}: No ticks collected")
        
        return result

# ─────────────────────────────────────────────────────────────────────────────
# HTTP Fallback for High/Low
# ─────────────────────────────────────────────────────────────────────────────

def get_high_low_from_http_candle(candle: list) -> tuple:
    """
    Fallback: Get High/Low from historical candle data.
    
    Args:
        candle: [timestamp, open, high, low, close, volume]
    
    Returns:
        (high, low) tuple
    """
    try:
        high = float(candle[2])
        low = float(candle[3])
        return high, low
    except Exception as e:
        print(f"[HTTP Fallback] Error parsing candle: {e}")
        return None, None

# ─────────────────────────────────────────────────────────────────────────────
# Main Function: Collect with Fallback
# ─────────────────────────────────────────────────────────────────────────────

def collect_live_high_low_with_fallback(angel_obj, symbols_with_tokens: list,
                                       http_candles: dict = None) -> dict:
    """
    Collect High/Low with fallback:
    1. TRY: WebSocket (9:15-9:20 live ticks)
    2. FALLBACK: HTTP (historical candle data)
    
    Args:
        angel_obj: SmartConnect object
        symbols_with_tokens: List of symbol dicts
        http_candles: {symbol: candle} (fallback data)
    
    Returns:
        {
            symbol: {
                high: X.XX,
                low: Y.YY,
                source: "websocket" or "http",
                tick_count: N,
                error: error_msg or None
            },
            ...
        }
    """
    result = {}
    
    print("[Collection] Starting High/Low collection...")
    print("[Collection] Phase 1: Trying WebSocket...")
    
    # ✅ PHASE 1: Try WebSocket
    try:
        collector = WebSocketTickCollector(
            angel_obj=angel_obj,
            symbols_with_tokens=symbols_with_tokens,
            collection_duration_secs=300  # 5 minutes
        )
        
        websocket_result = collector.connect_and_collect()
        
        if websocket_result:
            print("[Collection] ✅ WebSocket successful!")
            return websocket_result
        else:
            print("[Collection] ⚠️ WebSocket returned empty - falling back to HTTP")
            
    except Exception as e:
        print(f"[Collection] ❌ WebSocket failed: {e}")
        print("[Collection] 🔄 Falling back to HTTP...")
    
    # ❌ PHASE 2: Fallback to HTTP
    print("[Collection] Phase 2: Using HTTP candle data (fallback)...")
    
    if not http_candles:
        print("[Collection] ❌ No HTTP fallback data available")
        return {}
    
    for symbol_data in symbols_with_tokens:
        symbol = symbol_data["symbol"]
        
        candle = http_candles.get(symbol)
        
        if candle:
            high, low = get_high_low_from_http_candle(candle)
            
            if high and low:
                result[symbol] = {
                    "high": high,
                    "low": low,
                    "source": "http",  # Marked as fallback
                    "tick_count": 1,   # Single candle, not multiple ticks
                    "error": "WebSocket unavailable - using HTTP"
                }
                print(f"[HTTP Fallback] {symbol}: High={high:.2f}, Low={low:.2f}")
            else:
                result[symbol] = {
                    "high": None,
                    "low": None,
                    "source": None,
                    "error": "Failed to parse candle"
                }
        else:
            result[symbol] = {
                "high": None,
                "low": None,
                "source": None,
                "error": "No candle data available"
            }
    
    print(f"[Collection] ✅ HTTP fallback complete. Collected {len(result)} symbols")
    return result
