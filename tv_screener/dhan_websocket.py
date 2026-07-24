# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — DHAN WEBSOCKET MODULE
#
# Real-time LTP streaming via DhanHQ WebSocket API.
# Runs in background thread, updates st.session_state with live prices.
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import threading
import time
import json
import websocket
import ssl
from datetime import datetime
import pytz

from .quantity_calculator import get_access_token, DHAN_CLIENT_ID

IST = pytz.timezone('Asia/Kolkata')

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: WEBSOCKET CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

DHAN_WS_URL = "wss://api.dhan.co/websocket"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: WEBSOCKET MANAGER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class DhanWebSocketManager:
    """
    Manages WebSocket connection to DhanHQ for real-time LTP streaming.
    Runs in a background daemon thread.
    """
    
    def __init__(self):
        self.ws = None
        self.is_running = False
        self.is_connected = False
        self.thread = None
        self.subscribed_symbols = set()
        self.security_id_map = {}
        self.last_message = None
        self.reconnect_count = 0
        self.max_reconnect_attempts = 10
        
        # Initialize session state for live prices
        self._init_session_state()
    
    def _init_session_state(self):
        """Initialize session state for live price storage"""
        if 'live_prices' not in st.session_state:
            st.session_state['live_prices'] = {}  # symbol -> {'ltp': float, 'timestamp': str}
        if 'ws_connected' not in st.session_state:
            st.session_state['ws_connected'] = False
        if 'ws_last_update' not in st.session_state:
            st.session_state['ws_last_update'] = None
        if 'ws_subscribed_count' not in st.session_state:
            st.session_state['ws_subscribed_count'] = 0
    
    def _get_security_id_map(self):
        """Get security ID map from quantity_calculator module"""
        try:
            from .quantity_calculator import get_security_id_map
            self.security_id_map = get_security_id_map()
            return self.security_id_map
        except Exception as e:
            print(f"Error loading security ID map: {e}")
            return {}
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            
            # Handle different message types
            if isinstance(data, dict):
                # Subscribed securities response
                if 'securityIds' in data:
                    st.session_state['ws_subscribed_count'] = len(data.get('securityIds', []))
                    print(f"✅ Subscribed to {len(data.get('securityIds', []))} securities")
                    return
                
                # Price update message
                security_id = data.get('securityId')
                ltp = data.get('ltp')
                last_trade_time = data.get('lastTradeTime')
                
                if security_id and ltp is not None:
                    # Find symbol from security_id (reverse lookup)
                    symbol = None
                    for sym, sid in self.security_id_map.items():
                        if str(sid) == str(security_id):
                            symbol = sym
                            break
                    
                    if symbol:
                        # Update session state
                        st.session_state['live_prices'][symbol] = {
                            'ltp': float(ltp),
                            'timestamp': last_trade_time or datetime.now(IST).strftime("%H:%M:%S"),
                            'security_id': security_id
                        }
                        st.session_state['ws_last_update'] = datetime.now(IST)
                
                # Error message
                if 'error' in data:
                    print(f"⚠️ WebSocket error: {data.get('error')}")
                    
            elif isinstance(data, list):
                # Batch message
                for item in data:
                    security_id = item.get('securityId')
                    ltp = item.get('ltp')
                    
                    if security_id and ltp is not None:
                        symbol = None
                        for sym, sid in self.security_id_map.items():
                            if str(sid) == str(security_id):
                                symbol = sym
                                break
                        
                        if symbol:
                            st.session_state['live_prices'][symbol] = {
                                'ltp': float(ltp),
                                'timestamp': datetime.now(IST).strftime("%H:%M:%S"),
                                'security_id': security_id
                            }
                            st.session_state['ws_last_update'] = datetime.now(IST)
                            
        except json.JSONDecodeError:
            # Ignore non-JSON messages (heartbeats)
            pass
        except Exception as e:
            print(f"WebSocket message error: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"⚠️ WebSocket error: {error}")
        st.session_state['ws_connected'] = False
        self.is_connected = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        print(f"🔌 WebSocket closed: {close_status_code} - {close_msg}")
        st.session_state['ws_connected'] = False
        self.is_connected = False
        self.is_running = False
        
        # Attempt reconnection if still should be running
        if self.reconnect_count < self.max_reconnect_attempts:
            self.reconnect_count += 1
            print(f"🔄 Reconnection attempt {self.reconnect_count}/{self.max_reconnect_attempts}")
            time.sleep(2 * self.reconnect_count)
            self.start()
    
    def _on_open(self, ws):
        """Handle WebSocket open"""
        print("✅ WebSocket connected")
        st.session_state['ws_connected'] = True
        self.is_connected = True
        self.reconnect_count = 0
        
        # Subscribe to symbols if any
        if self.subscribed_symbols:
            self._subscribe_symbols()
    
    def _subscribe_symbols(self):
        """Subscribe to symbols"""
        if not self.ws or not self.is_connected:
            return
        
        try:
            # Build subscription payload
            securities = []
            for symbol in self.subscribed_symbols:
                security_id = self.security_id_map.get(symbol)
                if security_id:
                    securities.append({
                        "securityId": int(security_id),
                        "exchangeSegment": "NSE_EQ"
                    })
            
            if securities:
                payload = {
                    "action": "subscribe",
                    "securities": securities
                }
                self.ws.send(json.dumps(payload))
                print(f"📡 Subscribed to {len(securities)} securities")
                
        except Exception as e:
            print(f"Subscription error: {e}")
    
    def start(self, symbols=None):
        """Start WebSocket connection"""
        if self.is_running:
            print("WebSocket already running")
            return
        
        # Get security ID map
        self._get_security_id_map()
        
        # Update symbols to subscribe
        if symbols:
            self.subscribed_symbols = set(symbols)
        
        # Get access token
        access_token = get_access_token()
        if not access_token:
            print("❌ Cannot start WebSocket: No access token")
            return
        
        # Build WebSocket URL with auth
        ws_url = f"{DHAN_WS_URL}?clientId={DHAN_CLIENT_ID}&accessToken={access_token}"
        
        # Set up WebSocket
        self.is_running = True
        self.reconnect_count = 0
        
        # Create WebSocket connection in daemon thread
        self.thread = threading.Thread(target=self._run_websocket, args=(ws_url,), daemon=True)
        self.thread.start()
        print("🚀 WebSocket thread started")
    
    def _run_websocket(self, ws_url):
        """Run WebSocket connection (in separate thread)"""
        while self.is_running and self.reconnect_count < self.max_reconnect_attempts:
            try:
                # Create WebSocket with SSL
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                # Run with SSL context
                self.ws.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                    ping_interval=30,
                    ping_timeout=10
                )
                
                # If connection drops, wait before reconnect
                if self.is_running:
                    time.sleep(1)
                    
            except Exception as e:
                print(f"WebSocket run error: {e}")
                time.sleep(2 * self.reconnect_count)
                self.reconnect_count += 1
        
        self.is_running = False
        st.session_state['ws_connected'] = False
    
    def stop(self):
        """Stop WebSocket connection"""
        self.is_running = False
        self.is_connected = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        st.session_state['ws_connected'] = False
        print("🔌 WebSocket stopped")
    
    def subscribe(self, symbols):
        """Subscribe to additional symbols"""
        if not symbols:
            return
        
        self.subscribed_symbols.update(symbols)
        
        if self.is_connected and self.ws:
            self._subscribe_symbols()
    
    def get_live_price(self, symbol):
        """Get latest LTP for a symbol"""
        price_data = st.session_state['live_prices'].get(symbol, {})
        return price_data.get('ltp')


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: GLOBAL WEBSOCKET INSTANCE
# ─────────────────────────────────────────────────────────────────────────────

_ws_manager = None

def get_websocket_manager():
    """Get or create WebSocket manager singleton"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = DhanWebSocketManager()
    return _ws_manager

def start_websocket(symbols=None):
    """Start WebSocket connection with given symbols"""
    manager = get_websocket_manager()
    manager.start(symbols)
    return manager

def stop_websocket():
    """Stop WebSocket connection"""
    global _ws_manager
    if _ws_manager:
        _ws_manager.stop()
        _ws_manager = None

def update_live_prices_in_df(df):
    """
    Update DataFrame with live prices from WebSocket.
    Adds 'Live Price' column showing real-time LTP.
    """
    df_copy = df.copy()
    
    # Add Live Price column
    live_prices = []
    for _, row in df_copy.iterrows():
        symbol = row.get('Symbol', '')
        live_price = get_live_price(symbol)
        
        if live_price:
            live_prices.append(f"₹{live_price:.2f}")
        else:
            live_prices.append("N/A")
    
    df_copy['Live Price'] = live_prices
    return df_copy

def get_live_price(symbol):
    """Get latest LTP for a symbol"""
    price_data = st.session_state.get('live_prices', {}).get(symbol, {})
    return price_data.get('ltp')