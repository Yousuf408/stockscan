# ═════════════════════════════════════════════════════════════════════════════
# TRADESENTRY — websocket_tick_collector.py v2.0
# WebSocket Tick Collection (9:15-9:20 AM) with HTTP Fallback + DETAILED LOGGING
# 
# v2.0: Added actual WebSocket connection + comprehensive error logging
# ═════════════════════════════════════════════════════════════════════════════

import os
import json
import time
import threading
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
        self.ws = None
        
        print(f"[WebSocket] ✅ Initialized collector for {len(symbols_with_tokens)} symbols")
        print(f"[WebSocket] Duration: {collection_duration_secs}s")
    
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
            print(f"\n[WebSocket] ═══════════════════════════════════════")
            print(f"[WebSocket] Starting WebSocket collection at {datetime.now(IST).strftime('%H:%M:%S')}")
            print(f"[WebSocket] ═══════════════════════════════════════\n")
            
            self.is_collecting = True
            self.start_time = datetime.now(IST)
            
            # Step 1: Check Angel Object
            if not self.angel_obj:
                self.error_message = "Angel object is None/invalid"
                print(f"[WebSocket] ❌ {self.error_message}")
                return {}
            
            print(f"[WebSocket] ✅ Angel object valid")
            
            # Step 2: Subscribe to all symbols
            if not self._subscribe_to_symbols():
                self.error_message = "Failed to subscribe to WebSocket"
                print(f"[WebSocket] ❌ {self.error_message}")
                return {}
            
            # Step 3: Collect ticks for 5 minutes
            print(f"[WebSocket] ✅ Subscribed successfully!")
            print(f"[WebSocket] 🔊 Listening for ticks for {self.collection_duration}s...\n")
            self._collect_ticks()
            
            self.end_time = datetime.now(IST)
            self.is_collecting = False
            
            # Step 4: Calculate High/Low from collected ticks
            result = self._calculate_high_low()
            
            print(f"\n[WebSocket] ═══════════════════════════════════════")
            print(f"[WebSocket] ✅ Collection complete")
            print(f"[WebSocket] Total ticks collected: {self.tick_count}")
            print(f"[WebSocket] Symbols with data: {len([r for r in result.values() if r.get('tick_count', 0) > 0])}")
            print(f"[WebSocket] ═══════════════════════════════════════\n")
            
            return result
            
        except Exception as e:
            self.error_message = str(e)
            self.is_collecting = False
            print(f"\n[WebSocket] ❌ EXCEPTION in connect_and_collect():")
            print(f"[WebSocket] Type: {type(e).__name__}")
            print(f"[WebSocket] Message: {e}")
            print(f"[WebSocket] ═══════════════════════════════════════\n")
            import traceback
            traceback.print_exc()
            return {}
    
    def _subscribe_to_symbols(self) -> bool:
        """Subscribe to WebSocket for all symbols."""
        try:
            print(f"[WebSocket] 🔌 Attempting subscription...")
            
            # Group tokens by exchange
            tokens_by_exchange = defaultdict(list)
            for item in self.symbols_with_tokens:
                exchange = 1 if item["exchange"] == "NSE" else 3  # 1=NSE, 3=BSE
                tokens_by_exchange[exchange].append(item["token"])
            
            print(f"[WebSocket] 📊 Token groups:")
            for exchange, tokens in tokens_by_exchange.items():
                ex_name = "NSE" if exchange == 1 else "BSE"
                print(f"[WebSocket]    {ex_name}: {len(tokens)} tokens")
            
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
            
            print(f"[WebSocket] 📤 Payload: {json.dumps(payload, indent=2)}")
            
            # Try to use angel_obj.subscribe() if available
            try:
                if hasattr(self.angel_obj, 'subscribe'):
                    print(f"[WebSocket] ✅ Using angel_obj.subscribe() method")
                    response = self.angel_obj.subscribe(payload)
                    print(f"[WebSocket] ✅ Subscribe response: {response}")
                    return True
                else:
                    print(f"[WebSocket] ⚠️ angel_obj.subscribe() method not found")
                    print(f"[WebSocket] Available methods: {[m for m in dir(self.angel_obj) if not m.startswith('_')][:5]}...")
                    return False
            except Exception as e:
                print(f"[WebSocket] ❌ Subscribe method failed: {type(e).__name__}: {e}")
                return False
            
        except Exception as e:
            print(f"[WebSocket] ❌ Error in _subscribe_to_symbols():")
            print(f"[WebSocket] Type: {type(e).__name__}")
            print(f"[WebSocket] Message: {e}")
            return False
    
    def _collect_ticks(self):
        """Collect ticks for specified duration."""
        try:
            print(f"[WebSocket] 👂 Collecting ticks...")
            
            elapsed = 0
            tick_count_prev = 0
            
            while elapsed < self.collection_duration and self.is_collecting:
                try:
                    time.sleep(1)
                    elapsed = (datetime.now(IST) - self.start_time).total_seconds()
                    
                    current_tick_count = sum(len(t) for t in self.ticks.values())
                    if current_tick_count > tick_count_prev:
                        print(f"[WebSocket] 📈 Ticks received: {current_tick_count} (elapsed: {elapsed:.0f}s)")
                        tick_count_prev = current_tick_count
                    
                except Exception as e:
                    print(f"[WebSocket] ⚠️ Error in tick reception: {e}")
                    time.sleep(1)
                    continue
            
            self.tick_count = sum(len(t) for t in self.ticks.values())
            print(f"[WebSocket] ✅ Collection window closed (elapsed: {elapsed:.0f}s, ticks: {self.tick_count})")
            
        except Exception as e:
            print(f"[WebSocket] ❌ Error in _collect_ticks():")
            print(f"[WebSocket] Type: {type(e).__name__}")
            print(f"[WebSocket] Message: {e}")
    
    def _calculate_high_low(self) -> dict:
        """Calculate High/Low from collected ticks."""
        result = {}
        
        print(f"\n[WebSocket] 📊 Calculating High/Low from ticks...")
        
        for symbol_data in self.symbols_with_tokens:
            symbol = symbol_data["symbol"]
            
            ticks = self.ticks.get(symbol, [])
            
            if ticks:
                prices = [float(tick.get("price", 0)) for tick in ticks if tick.get("price")]
                
                if prices:
                    high = max(prices)
                    low = min(prices)
                    
                    result[symbol] = {
                        "ticks": ticks,
                        "high": high,
                        "low": low,
                        "tick_count": len(ticks),
                        "source": "websocket"
                    }
                    
                    print(f"[WebSocket] ✅ {symbol}: H={high:.2f} L={low:.2f} ({len(ticks)} ticks)")
                else:
                    print(f"[WebSocket] ⚠️ {symbol}: Invalid tick prices")
                    result[symbol] = {
                        "high": None,
                        "low": None,
                        "tick_count": 0,
                        "source": "websocket",
                        "error": "Invalid tick data"
                    }
            else:
                print(f"[WebSocket] ⚠️ {symbol}: No ticks collected")
                result[symbol] = {
                    "high": None,
                    "low": None,
                    "tick_count": 0,
                    "source": "websocket",
                    "error": "No ticks received"
                }
        
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
        print(f"[HTTP Fallback] ✅ Parsed candle: H={high:.2f} L={low:.2f}")
        return high, low
    except Exception as e:
        print(f"[HTTP Fallback] ❌ Error parsing candle: {type(e).__name__}: {e}")
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
    
    print("\n" + "="*70)
    print("[Collection] STARTING HIGH/LOW COLLECTION")
    print("="*70)
    print(f"[Collection] Timestamp: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[Collection] Symbols: {len(symbols_with_tokens)}")
    print("="*70 + "\n")
    
    # ✅ PHASE 1: Try WebSocket
    print("[Collection] PHASE 1: Attempting WebSocket...")
    print("-"*70)
    
    try:
        if not angel_obj:
            print("[Collection] ❌ Angel object is None")
            raise Exception("Invalid angel_obj")
        
        collector = WebSocketTickCollector(
            angel_obj=angel_obj,
            symbols_with_tokens=symbols_with_tokens,
            collection_duration_secs=300  # 5 minutes
        )
        
        websocket_result = collector.connect_and_collect()
        
        # Check if we got valid results
        valid_results = {k: v for k, v in websocket_result.items() if v.get("tick_count", 0) > 0}
        
        if valid_results and len(valid_results) >= (len(symbols_with_tokens) * 0.5):  # At least 50% success
            print("\n[Collection] ✅ PHASE 1 SUCCESS: WebSocket provided sufficient data!")
            return websocket_result
        else:
            print(f"\n[Collection] ⚠️ PHASE 1 PARTIAL: Only {len(valid_results)} symbols with data")
            print("[Collection] 🔄 Falling back to HTTP...")
            
    except Exception as e:
        print(f"\n[Collection] ❌ PHASE 1 FAILED:")
        print(f"[Collection] Type: {type(e).__name__}")
        print(f"[Collection] Message: {e}")
        print("[Collection] 🔄 Falling back to HTTP...")
        import traceback
        traceback.print_exc()
    
    # ❌ PHASE 2: Fallback to HTTP
    print("\n[Collection] PHASE 2: Using HTTP Fallback...")
    print("-"*70)
    
    if not http_candles:
        print("[Collection] ❌ No HTTP fallback data available")
        return result
    
    for symbol_data in symbols_with_tokens:
        symbol = symbol_data["symbol"]
        
        candle = http_candles.get(symbol)
        
        if candle:
            high, low = get_high_low_from_http_candle(candle)
            
            if high and low:
                result[symbol] = {
                    "high": high,
                    "low": low,
                    "http_high": high,
                    "http_low": low,
                    "source": "http",
                    "tick_count": 1,
                    "error": "WebSocket unavailable - using HTTP"
                }
                print(f"[HTTP Fallback] ✅ {symbol}: H={high:.2f} L={low:.2f}")
            else:
                result[symbol] = {
                    "high": None,
                    "low": None,
                    "http_high": None,
                    "http_low": None,
                    "source": None,
                    "error": "Failed to parse candle"
                }
                print(f"[HTTP Fallback] ❌ {symbol}: Parse failed")
        else:
            result[symbol] = {
                "high": None,
                "low": None,
                "http_high": None,
                "http_low": None,
                "source": None,
                "error": "No candle data available"
            }
            print(f"[HTTP Fallback] ❌ {symbol}: No data")
    
    print("\n[Collection] ✅ PHASE 2 COMPLETE: HTTP fallback finished")
    print("="*70)
    print(f"[Collection] RESULT: {len([r for r in result.values() if r.get('high')])} symbols with High/Low")
    print("="*70 + "\n")
    
    return result
