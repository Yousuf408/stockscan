# ══════════════════════════════════════════
#  TRADESENTRY — price_streamer.py
#  Background WebSocket service for 700+ stocks
#  Fetches live prices and updates price_cache.json
# ══════════════════════════════════════════

import json
import os
import websocket
import struct
import pyotp
import time
import threading
from datetime import datetime
from SmartApi import SmartConnect

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")
PRICE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "price_cache.json")

# Market hours
MARKET_OPEN = 9 * 60 + 15  # 9:15 AM in minutes
MARKET_CLOSE = 15 * 60 + 30  # 3:30 PM in minutes

# ══════════════════════════════════════════
#  PRICE CACHE MANAGEMENT
# ══════════════════════════════════════════

def load_cache():
    """Load price cache from file"""
    if not os.path.exists(PRICE_CACHE_FILE):
        return {"mode": "offline", "last_update": "", "stocks": {}}
    try:
        with open(PRICE_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"mode": "offline", "last_update": "", "stocks": {}}

def save_cache(cache):
    """Save price cache to file"""
    try:
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

def update_price(symbol, exchange, price, source):
    """Update a single stock price in cache"""
    cache = load_cache()
    if symbol not in cache["stocks"]:
        cache["stocks"][symbol] = {}
    
    cache["stocks"][symbol].update({
        "price": price,
        "source": source,
        "time": datetime.now().strftime("%H:%M:%S"),
        "exchange": exchange
    })
    cache["last_update"] = datetime.now().strftime("%H:%M:%S")
    save_cache(cache)

def set_mode(mode):
    """Update cache mode (websocket, http_polling, yfinance, offline)"""
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)

# ══════════════════════════════════════════
#  MARKET HOURS CHECK
# ══════════════════════════════════════════

def is_market_open():
    """Check if market is open (9:15 AM - 3:30 PM)"""
    now = datetime.now()
    # Skip weekends
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    current_minutes = now.hour * 60 + now.minute
    return MARKET_OPEN <= current_minutes <= MARKET_CLOSE

# ══════════════════════════════════════════
#  ANGEL ONE SESSION
# ══════════════════════════════════════════

def get_angel_session():
    """Get Angel One session"""
    try:
        # Import secrets from environment or config
        api_key = os.getenv("ANGEL_API_KEY")
        client_code = os.getenv("ANGEL_CLIENT_CODE")
        password = os.getenv("ANGEL_PASSWORD")
        totp_secret = os.getenv("ANGEL_TOTP_SECRET")
        
        if not all([api_key, client_code, password, totp_secret]):
            print("ERROR: Angel One credentials not found in environment variables")
            return None
        
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        sess = obj.generateSession(client_code, password, totp)
        
        if sess.get("status"):
            print(f"✓ Angel One session created. Token: {sess.get('data', {}).get('jwtToken')[:20]}...")
            return obj
        else:
            print(f"✗ Angel One session failed: {sess}")
            return None
    except Exception as e:
        print(f"✗ Angel One connection error: {e}")
        return None

# ══════════════════════════════════════════
#  GET STOCK TOKENS
# ══════════════════════════════════════════

def get_stock_token(symbol):
    """Get stock token from your existing function"""
    try:
        # Import from your stocks module
        from stocks import get_stock_token as get_token
        return get_token(symbol)
    except:
        # Fallback: return symbol (won't work, but prevents crash)
        print(f"Warning: Could not get token for {symbol}")
        return None

def build_token_list(watchlist_stocks):
    """Build token list for WebSocket subscription"""
    token_list = {"1": [], "3": []}  # 1=NSE, 3=BSE
    
    for stock in watchlist_stocks:
        symbol = stock.get("symbol")
        exchange = stock.get("exchange", "NS")
        
        token = get_stock_token(symbol)
        if not token:
            continue
        
        exch_code = "1" if exchange == "NS" else "3"
        token_list[exch_code].append(token)
    
    return token_list

# ══════════════════════════════════════════
#  WEBSOCKET HANDLER
# ══════════════════════════════════════════

class PriceStreamer:
    def __init__(self):
        self.ws = None
        self.angel_obj = None
        self.is_connected = False
        self.token_to_symbol = {}  # Map token to symbol
        self.heartbeat_thread = None
        self.subscription_active = False

    def on_message(self, ws, message):
        """Handle WebSocket messages"""
        try:
            if isinstance(message, bytes):
                # Binary message - parse LTP data
                self.parse_ltp_data(message)
            else:
                # Text message
                data = json.loads(message)
                print(f"WS Message: {data}")
        except Exception as e:
            print(f"Error parsing message: {e}")

    def parse_ltp_data(self, data):
        """Parse binary LTP data from Angel One"""
        try:
            if len(data) < 51:  # LTP packet minimum size
                return
            
            # Parse binary packet
            mode = struct.unpack('b', data[0:1])[0]  # Subscription mode
            exchange = struct.unpack('b', data[1:2])[0]  # Exchange type
            token = data[2:27].decode('utf-8').rstrip('\x00')  # Token
            ltp = struct.unpack('i', data[43:51])[0] / 100  # LTP in paise, convert to rupees
            
            # Find symbol from token
            if token in self.token_to_symbol:
                symbol, exchange_code = self.token_to_symbol[token]
                update_price(symbol, exchange_code, ltp, "websocket")
                print(f"✓ {symbol}: ₹{ltp:.2f}")
        except Exception as e:
            print(f"Error parsing LTP: {e}")

    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"✗ WebSocket error: {error}")
        self.is_connected = False
        set_mode("http_polling")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        print(f"✗ WebSocket closed: {close_msg}")
        self.is_connected = False
        self.subscription_active = False

    def on_open(self, ws):
        """Handle WebSocket open"""
        print("✓ WebSocket connected")
        self.is_connected = True
        self.heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        self.heartbeat_thread.start()
        self.subscribe_to_stocks()

    def send_heartbeat(self):
        """Send heartbeat every 30 seconds"""
        while self.is_connected:
            try:
                self.ws.send("ping")
                time.sleep(30)
            except:
                break

    def subscribe_to_stocks(self):
        """Subscribe to all 700+ stocks"""
        try:
            # Load watchlist
            with open(WATCHLIST_FILE, "r") as f:
                watchlist_data = json.load(f)
            
            all_stocks = []
            for tab in ["watchlist_Today", "watchlist_Yesterday", "watchlist_New"]:
                all_stocks.extend(watchlist_data.get(tab, []))
            
            # Remove duplicates
            seen = set()
            unique_stocks = []
            for stock in all_stocks:
                key = (stock.get("symbol"), stock.get("exchange"))
                if key not in seen:
                    seen.add(key)
                    unique_stocks.append(stock)
            
            print(f"📊 Subscribing to {len(unique_stocks)} unique stocks...")
            
            # Build token list
            nse_tokens = []
            bse_tokens = []
            
            for stock in unique_stocks:
                symbol = stock.get("symbol")
                exchange = stock.get("exchange", "NS")
                token = get_stock_token(symbol)
                
                if not token:
                    continue
                
                if exchange == "NS":
                    nse_tokens.append(token)
                else:
                    bse_tokens.append(token)
                
                self.token_to_symbol[token] = (symbol, exchange)
            
            # Build subscription request
            token_list = []
            if nse_tokens:
                token_list.append({
                    "exchangeType": 1,  # NSE
                    "tokens": nse_tokens
                })
            if bse_tokens:
                token_list.append({
                    "exchangeType": 3,  # BSE
                    "tokens": bse_tokens
                })
            
            request = {
                "correlationID": "ts_sub_001",
                "action": 1,  # Subscribe
                "params": {
                    "mode": 1,  # LTP mode
                    "tokenList": token_list
                }
            }
            
            self.ws.send(json.dumps(request))
            self.subscription_active = True
            set_mode("websocket")
            print(f"✓ Subscribed to {len(nse_tokens)} NSE + {len(bse_tokens)} BSE stocks")
        except Exception as e:
            print(f"✗ Subscription error: {e}")
            set_mode("http_polling")

    def connect(self):
        """Connect to WebSocket"""
        try:
            websocket_url = "wss://smartapisocket.angelone.in/smart-stream"
            
            # Get auth credentials
            self.angel_obj = get_angel_session()
            if not self.angel_obj:
                print("✗ Could not get Angel One session")
                return False
            
            # Get feed token from login
            # Note: You need to extract feed token from session
            # For now, we'll use query params approach
            
            self.ws = websocket.WebSocketApp(
                websocket_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            
            self.ws.run_forever()
            return True
        except Exception as e:
            print(f"✗ WebSocket connection error: {e}")
            return False

# ══════════════════════════════════════════
#  HTTP POLLING FALLBACK
# ══════════════════════════════════════════

def http_polling_fallback():
    """Fallback to HTTP polling if WebSocket fails"""
    from stocks import get_stock_token
    
    print("📡 Starting HTTP polling fallback...")
    set_mode("http_polling")
    
    try:
        angel_obj = get_angel_session()
        if not angel_obj:
            print("✗ Could not get Angel One session for HTTP polling")
            return False
        
        with open(WATCHLIST_FILE, "r") as f:
            watchlist_data = json.load(f)
        
        all_stocks = []
        for tab in ["watchlist_Today", "watchlist_Yesterday", "watchlist_New"]:
            all_stocks.extend(watchlist_data.get(tab, []))
        
        # Remove duplicates
        seen = set()
        unique_stocks = []
        for stock in all_stocks:
            key = (stock.get("symbol"), stock.get("exchange"))
            if key not in seen:
                seen.add(key)
                unique_stocks.append(stock)
        
        while True:
            if not is_market_open():
                print(f"⏰ Market closed at {datetime.now().strftime('%H:%M:%S')}. Waiting for next open...")
                time.sleep(60)
                continue
            
            print(f"📊 HTTP polling {len(unique_stocks)} stocks at {datetime.now().strftime('%H:%M:%S')}")
            
            # Fetch in batches of 50 to avoid rate limits
            for i in range(0, len(unique_stocks), 50):
                batch = unique_stocks[i:i+50]
                
                for stock in batch:
                    try:
                        symbol = stock.get("symbol")
                        exchange = stock.get("exchange", "NS")
                        token = get_stock_token(symbol)
                        
                        if not token:
                            continue
                        
                        resp = angel_obj.ltpData(
                            "NSE" if exchange == "NS" else "BSE",
                            symbol,
                            token
                        )
                        
                        if resp and resp.get("status"):
                            ltp = float(resp["data"]["ltp"])
                            update_price(symbol, exchange, ltp, "http")
                            print(f"✓ {symbol}: ₹{ltp:.2f}")
                    except Exception as e:
                        print(f"✗ Error fetching {symbol}: {e}")
                
                # Wait 1 second between batches
                time.sleep(1)
            
            # Wait 5 seconds before next polling cycle
            time.sleep(5)
    
    except Exception as e:
        print(f"✗ HTTP polling error: {e}")
        return False

# ══════════════════════════════════════════
#  YFINANCE FALLBACK
# ══════════════════════════════════════════

def yfinance_fallback():
    """Fallback to yfinance if both WebSocket and HTTP fail"""
    import yfinance as yf
    
    print("🔄 Starting yfinance fallback...")
    set_mode("yfinance")
    
    try:
        with open(WATCHLIST_FILE, "r") as f:
            watchlist_data = json.load(f)
        
        all_stocks = []
        for tab in ["watchlist_Today", "watchlist_Yesterday", "watchlist_New"]:
            all_stocks.extend(watchlist_data.get(tab, []))
        
        # Remove duplicates
        seen = set()
        unique_stocks = []
        for stock in all_stocks:
            key = (stock.get("symbol"), stock.get("exchange"))
            if key not in seen:
                seen.add(key)
                unique_stocks.append(stock)
        
        while True:
            if not is_market_open():
                print(f"⏰ Market closed at {datetime.now().strftime('%H:%M:%S')}. Waiting for next open...")
                time.sleep(60)
                continue
            
            print(f"📊 yfinance polling {len(unique_stocks)} stocks at {datetime.now().strftime('%H:%M:%S')}")
            
            for stock in unique_stocks:
                try:
                    symbol = stock.get("symbol")
                    exchange = stock.get("exchange", "NS")
                    suffix = ".NS" if exchange == "NS" else ".BO"
                    
                    ticker = yf.Ticker(f"{symbol}{suffix}")
                    price = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
                    
                    if price:
                        update_price(symbol, exchange, float(price), "yfinance")
                        print(f"✓ {symbol}: ₹{price:.2f}")
                except Exception as e:
                    print(f"✗ Error fetching {symbol}: {e}")
            
            # Wait 10 seconds before next polling cycle
            time.sleep(10)
    
    except Exception as e:
        print(f"✗ yfinance fallback error: {e}")

# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════

def main():
    """Main service loop"""
    print("=" * 50)
    print("  TRADESENTRY — Price Streamer 2.0")
    print("  WebSocket → HTTP Polling → yfinance")
    print("=" * 50)
    
    streamer = PriceStreamer()
    
    while True:
        try:
            if not is_market_open():
                print(f"⏰ Market closed. Next open: 9:15 AM IST")
                set_mode("offline")
                time.sleep(300)  # Check every 5 minutes
                continue
            
            print(f"\n📡 Starting price streamer at {datetime.now().strftime('%H:%M:%S')}")
            
            # Try WebSocket first
            if streamer.connect():
                print("✓ WebSocket connection successful")
            else:
                print("✗ WebSocket failed, trying HTTP polling...")
                http_polling_fallback()
        
        except KeyboardInterrupt:
            print("\n✓ Price streamer stopped")
            set_mode("offline")
            break
        except Exception as e:
            print(f"✗ Error in main loop: {e}")
            print("⏳ Retrying in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
