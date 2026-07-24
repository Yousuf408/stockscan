# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — DHAN WEBSOCKET MODULE (Using Official DhanHQ-py Library)
#
# Real-time LTP streaming via DhanHQ's MarketFeed class.
# Runs in background thread, updates st.session_state with live prices.
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import threading
import time
from datetime import datetime
import pytz

from dhanhq import DhanContext, MarketFeed
from .quantity_calculator import get_access_token, DHAN_CLIENT_ID, get_security_id_map

IST = pytz.timezone('Asia/Kolkata')

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL VARIABLES
# ─────────────────────────────────────────────────────────────────────────────

_feed = None
_is_running = False
_thread = None
_security_map = {}

# ─────────────────────────────────────────────────────────────────────────────
# INIT SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

def _init_session_state():
    if 'live_prices' not in st.session_state:
        st.session_state['live_prices'] = {}
    if 'ws_connected' not in st.session_state:
        st.session_state['ws_connected'] = False
    if 'ws_subscribed_count' not in st.session_state:
        st.session_state['ws_subscribed_count'] = 0

_init_session_state()

# ─────────────────────────────────────────────────────────────────────────────
# MARKET DATA PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _process_market_data(data):
    """Process market data from MarketFeed"""
    global _security_map
    
    try:
        if not _security_map:
            _security_map = get_security_id_map()
        
        if isinstance(data, list):
            for item in data:
                _process_single_item(item)
        elif isinstance(data, dict):
            _process_single_item(data)
    except Exception as e:
        print(f"Process error: {e}")

def _process_single_item(item):
    """Process a single market data item"""
    global _security_map
    
    try:
        security_id = item.get('securityId')
        ltp = item.get('ltp')
        last_trade_time = item.get('lastTradeTime')
        
        if security_id and ltp is not None:
            # Find symbol from security_id
            symbol = None
            for sym, sid in _security_map.items():
                if str(sid) == str(security_id):
                    symbol = sym
                    break
            
            if symbol:
                st.session_state['live_prices'][symbol] = {
                    'ltp': float(ltp),
                    'timestamp': last_trade_time or datetime.now(IST).strftime("%H:%M:%S"),
                    'security_id': security_id
                }
                st.session_state['ws_last_update'] = datetime.now(IST)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def start_websocket(symbols=None):
    """Start WebSocket connection using DhanHQ-py MarketFeed"""
    global _feed, _is_running, _thread, _security_map
    
    if _is_running:
        print("WebSocket already running")
        return
    
    if not symbols:
        print("No symbols provided")
        return
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        print("❌ Cannot start WebSocket: No access token")
        return
    
    try:
        # Get security ID map
        _security_map = get_security_id_map()
        
        # Create DhanContext
        dhan_context = DhanContext(DHAN_CLIENT_ID, access_token)
        
        # Build instruments list: [(exchange_segment, security_id, subscription_type)]
        instruments = []
        for symbol in symbols:
            security_id = _security_map.get(symbol)
            if security_id:
                instruments.append((MarketFeed.NSE, str(security_id), MarketFeed.Ticker))
        
        if not instruments:
            print("❌ No valid instruments to subscribe")
            return
        
        print(f"📡 Subscribing to {len(instruments)} instruments...")
        st.session_state['ws_subscribed_count'] = len(instruments)
        
        # Create MarketFeed instance
        _feed = MarketFeed(dhan_context, instruments, "v2")
        
        # Set callback for data
        _feed.on_update = _process_market_data
        
        _is_running = True
        st.session_state['ws_connected'] = True
        
        # Run in background thread
        _thread = threading.Thread(target=_run_feed, daemon=True)
        _thread.start()
        
        print("✅ MarketFeed connected")
        
    except Exception as e:
        print(f"❌ MarketFeed error: {e}")
        st.session_state['ws_connected'] = False
        _is_running = False

def _run_feed():
    """Run MarketFeed in thread"""
    global _feed, _is_running
    
    try:
        if _feed:
            _feed.run_forever()
    except Exception as e:
        print(f"❌ Feed error: {e}")
    finally:
        st.session_state['ws_connected'] = False
        _is_running = False

def stop_websocket():
    """Stop WebSocket connection"""
    global _feed, _is_running
    
    _is_running = False
    if _feed:
        try:
            _feed.close_connection()
        except:
            pass
    st.session_state['ws_connected'] = False
    print("🔌 WebSocket stopped")

def get_live_price(symbol):
    """Get latest LTP for a symbol"""
    price_data = st.session_state.get('live_prices', {}).get(symbol, {})
    return price_data.get('ltp')

def get_ws_status():
    """Get WebSocket connection status"""
    return {
        'connected': st.session_state.get('ws_connected', False),
        'subscribed_count': st.session_state.get('ws_subscribed_count', 0),
        'last_update': st.session_state.get('ws_last_update')
    }
