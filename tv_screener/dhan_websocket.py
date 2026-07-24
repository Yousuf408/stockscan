# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — DHAN WEBSOCKET MODULE (FIXED v2.2.0)
#
# Real-time LTP streaming via DhanHQ's MarketFeed class using v2.2.0 API.
# Uses get_data() loop instead of broken callbacks.
# Runs in background thread, updates st.session_state with live prices.
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import threading
import time
from datetime import datetime
import pytz
import traceback

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
_symbol_to_id = {}  # Reverse map: security_id -> symbol

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
    if 'ws_last_update' not in st.session_state:
        st.session_state['ws_last_update'] = None
    if 'ws_debug' not in st.session_state:
        st.session_state['ws_debug'] = []

_init_session_state()

# ─────────────────────────────────────────────────────────────────────────────
# DEBUG LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def _log_debug(msg):
    """Add debug message to session state"""
    _init_session_state()
    timestamp = datetime.now(IST).strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    st.session_state['ws_debug'].append(full_msg)
    # Keep only last 50 messages
    if len(st.session_state['ws_debug']) > 50:
        st.session_state['ws_debug'] = st.session_state['ws_debug'][-50:]
    print(full_msg)

# ─────────────────────────────────────────────────────────────────────────────
# MARKET DATA PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _process_market_data(data):
    """
    Process market data from MarketFeed.get_data()
    
    Data structure (v2.2.0 Ticker mode):
    {
        "securityId": "1333",
        "ltp": 2456.25,
        "lastTradeTime": "09:30:45",
        "lastTradeQty": 1,
        ...
    }
    or list of dicts
    """
    global _symbol_to_id
    
    if not data:
        return
    
    try:
        # Handle both single dict and list of dicts
        items = data if isinstance(data, list) else [data]
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            _process_single_item(item)
    except Exception as e:
        _log_debug(f"❌ Process error: {str(e)}")


def _process_single_item(item):
    """Process a single market data item"""
    global _symbol_to_id
    
    try:
        security_id = str(item.get('securityId', '')).strip()
        ltp = item.get('ltp')
        
        if not security_id or ltp is None:
            return
        
        # Find symbol from security_id using reverse map
        symbol = _symbol_to_id.get(security_id)
        
        if symbol:
            st.session_state['live_prices'][symbol] = {
                'ltp': float(ltp),
                'timestamp': datetime.now(IST).strftime("%H:%M:%S"),
                'security_id': security_id,
            }
            st.session_state['ws_last_update'] = datetime.now(IST)
            
    except Exception as e:
        _log_debug(f"⚠️ Item processing error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def start_websocket(symbols=None):
    """
    Start WebSocket connection using DhanHQ-py v2.2.0 MarketFeed
    
    Proper usage:
      1. Create DhanContext with valid access_token
      2. Create MarketFeed with instruments list
      3. Call run_forever() to establish connection
      4. Call get_data() in a loop to receive updates
    """
    global _feed, _is_running, _thread, _security_map, _symbol_to_id
    
    if _is_running:
        _log_debug("⚠️ WebSocket already running")
        return
    
    if not symbols:
        _log_debug("⚠️ No symbols provided")
        return
    
    _log_debug(f"🚀 Starting WebSocket for {len(symbols)} symbols...")
    
    # Step 1: Get access token
    access_token = get_access_token()
    if not access_token:
        _log_debug("❌ Cannot start WebSocket: No valid access token")
        st.session_state['ws_connected'] = False
        return
    
    _log_debug(f"✅ Access token obtained")
    
    try:
        # Step 2: Get security ID map (symbol -> security_id)
        _security_map = get_security_id_map()
        if not _security_map:
            _log_debug("❌ No security map loaded")
            st.session_state['ws_connected'] = False
            return
        
        _log_debug(f"✅ Security map loaded: {len(_security_map)} symbols")
        
        # Step 3: Build reverse map (security_id -> symbol)
        _symbol_to_id = {str(sid): sym for sym, sid in _security_map.items()}
        _log_debug(f"✅ Reverse map built: {len(_symbol_to_id)} entries")
        
        # Step 4: Build instruments list for subscription
        # Format: (exchange_segment, security_id, subscription_type)
        instruments = []
        for symbol in symbols:
            security_id = _security_map.get(symbol)
            if security_id:
                instruments.append((MarketFeed.NSE, str(security_id), MarketFeed.Ticker))
        
        if not instruments:
            _log_debug("❌ No valid instruments to subscribe")
            st.session_state['ws_connected'] = False
            return
        
        _log_debug(f"✅ Prepared {len(instruments)} instruments for subscription")
        
        # Step 5: Create DhanContext and MarketFeed
        try:
            dhan_context = DhanContext(DHAN_CLIENT_ID, access_token)
            _log_debug(f"✅ DhanContext created with client_id: {DHAN_CLIENT_ID}")
        except Exception as e:
            _log_debug(f"❌ DhanContext error: {str(e)}")
            st.session_state['ws_connected'] = False
            return
        
        try:
            _feed = MarketFeed(dhan_context, instruments, "v2")
            _log_debug(f"✅ MarketFeed instance created")
        except Exception as e:
            _log_debug(f"❌ MarketFeed init error: {str(e)}")
            st.session_state['ws_connected'] = False
            return
        
        # Step 6: Start in background thread
        _is_running = True
        st.session_state['ws_connected'] = True
        st.session_state['ws_subscribed_count'] = len(instruments)
        
        _thread = threading.Thread(target=_run_feed, daemon=True)
        _thread.start()
        
        _log_debug(f"✅ WebSocket thread started")
        
    except Exception as e:
        _log_debug(f"❌ Start error: {str(e)}\n{traceback.format_exc()}")
        st.session_state['ws_connected'] = False
        _is_running = False


def _run_feed():
    """
    Run MarketFeed in background thread.
    
    Flow:
      1. Call run_forever() to establish WebSocket connection
      2. Call get_data() in a loop to pull updates
      3. Process each update immediately
    """
    global _feed, _is_running
    
    try:
        if not _feed:
            _log_debug("❌ Feed object is None")
            return
        
        # Establish connection
        _log_debug("📡 Calling run_forever() to establish connection...")
        _feed.run_forever()
        _log_debug("✅ Connection established via run_forever()")
        
        # Main loop: pull data continuously
        _log_debug("🔄 Starting get_data() loop...")
        consecutive_errors = 0
        
        while _is_running:
            try:
                # get_data() blocks until data is available, returns immediately if data exists
                data = _feed.get_data()
                
                if data:
                    consecutive_errors = 0  # Reset error counter on success
                    _process_market_data(data)
                else:
                    # No data available right now, small sleep before retry
                    time.sleep(0.1)
                    
            except Exception as e:
                consecutive_errors += 1
                _log_debug(f"⚠️ get_data() error #{consecutive_errors}: {str(e)}")
                
                if consecutive_errors > 10:
                    _log_debug("❌ Too many consecutive errors, stopping feed")
                    break
                
                time.sleep(1)
        
        _log_debug("🛑 Feed loop ended")
        
    except Exception as e:
        _log_debug(f"❌ Feed thread error: {str(e)}\n{traceback.format_exc()}")
    finally:
        st.session_state['ws_connected'] = False
        _is_running = False
        _log_debug("🔌 Feed thread cleanup complete")


def stop_websocket():
    """Stop WebSocket connection"""
    global _feed, _is_running
    
    _is_running = False
    
    if _feed:
        try:
            _feed.close_connection()
            _log_debug("✅ WebSocket connection closed")
        except Exception as e:
            _log_debug(f"⚠️ Close error: {str(e)}")
    
    st.session_state['ws_connected'] = False


def get_live_price(symbol):
    """
    Get latest LTP for a symbol.
    Returns float or None.
    """
    _init_session_state()
    price_data = st.session_state.get('live_prices', {}).get(symbol, {})
    return price_data.get('ltp')


def get_ws_status():
    """Get WebSocket connection status"""
    _init_session_state()
    return {
        'connected': st.session_state.get('ws_connected', False),
        'subscribed_count': st.session_state.get('ws_subscribed_count', 0),
        'last_update': st.session_state.get('ws_last_update'),
        'live_prices_count': len(st.session_state.get('live_prices', {})),
    }
