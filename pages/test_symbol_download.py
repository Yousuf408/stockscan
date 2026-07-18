import streamlit as st
import json
from pathlib import Path
from mstock_symbol_resolver import (
    fetch_instrument_master, 
    build_symbol_token_map, 
    cache_symbol_map,
    load_cached_symbols,
    get_token
)

# ------------------- SDK Setup -------------------
try:
    from tradingapi_b.mconnect import MConnectB
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ------------------- Helper: set token on client -------------------
def set_client_token(client, jwt_token):
    """Try multiple ways to set the JWT token on the client."""
    if hasattr(client, 'set_jwt_token'):
        client.set_jwt_token(jwt_token)
        return True
    elif hasattr(client, 'set_access_token'):
        client.set_access_token(jwt_token)
        return True
    elif hasattr(client, 'set_bearer_token'):
        client.set_bearer_token(jwt_token)
        return True
    elif hasattr(client, 'headers'):
        client.headers['Authorization'] = f'Bearer {jwt_token}'
        return True
    else:
        setattr(client, '_jwt_token', jwt_token)
        return False

# ------------------- Authentication -------------------
def authenticate_type_b(api_key, user_id, password, otp):
    """
    Type-B authentication
    """
    if not SDK_AVAILABLE:
        st.error("❌ mStock Type-B SDK not installed.")
        return None, None, None

    try:
        client = MConnectB()
        login_response = client.login(user_id, password)
        login_data = login_response.json()

        if not login_data.get('status', False):
            st.error(f"Login failed: {login_data.get('message', 'Unknown')}")
            return None, None, None

        jwt_token = login_data.get('data', {}).get('jwtToken')
        if not jwt_token:
            st.error("No JWT token received. Check credentials.")
            return None, None, None

        set_client_token(client, jwt_token)
        st.success("✅ Authentication successful!")
        return client, jwt_token, api_key

    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None, None, None

st.set_page_config(page_title="mStock Symbol Download", layout="wide")

st.title("🔧 mStock Instrument Master Download")

with st.sidebar:
    st.header("🔐 Authenticate First")
    
    if not SDK_AVAILABLE:
        st.error("❌ Type-B SDK not installed")
        st.code("pip install mStock-TradingApi-B")
        st.stop()
    
    st.subheader("Login Credentials")
    api_key = st.text_input("API Key", type="password")
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type="password")
    otp = st.text_input("OTP (6-digit)", type="password", help="If 2FA enabled")
    
    if st.button("🔑 Login & Get JWT Token"):
        if not all([api_key, user_id, password]):
            st.error("API Key, User ID, and Password are required")
        else:
            with st.spinner("Authenticating..."):
                client, jwt_token, api_key = authenticate_type_b(api_key, user_id, password, otp)
                if client or jwt_token:
                    st.session_state['jwt_token'] = jwt_token
                    st.session_state['api_key'] = api_key
                    st.session_state['authenticated'] = True

if not st.session_state.get('authenticated'):
    st.warning("⚠️ Please login first using the sidebar")
    st.stop()

jwt_token = st.session_state.get('jwt_token')
api_key = st.session_state.get('api_key')

# Main area
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Download & Cache")
    
    if st.button("🚀 Download Instrument Master", key="download_btn"):
        with st.spinner("Downloading instruments..."):
            instruments = fetch_instrument_master(jwt_token, api_key)
        
        if instruments:
            st.success(f"✅ Downloaded {len(instruments)} instruments")
            
            with st.spinner("Filtering NSE/EQ stocks..."):
                symbol_map = build_symbol_token_map(instruments)
            
            if symbol_map:
                st.success(f"✅ Filtered {len(symbol_map)} NSE/EQ stocks")
                
                with st.spinner("Caching..."):
                    cache_ok = cache_symbol_map(symbol_map, 'mstock_symbols.json')
                
                if cache_ok:
                    st.success("✅ Cached successfully!")
                    st.balloons()
            else:
                st.error("❌ No NSE/EQ stocks found")
        else:
            st.error("❌ Failed to download instruments")

with col2:
    st.subheader("🔍 Test Lookup")
    
    # Load cache
    symbol_map = load_cached_symbols('mstock_symbols.json')
    
    if symbol_map:
        st.success(f"✅ Cache loaded: {len(symbol_map)} symbols")
        
        # Test input
        test_symbol = st.text_input("Enter symbol to lookup:", value="GABRIEL")
        
        if test_symbol:
            token = get_token(test_symbol, symbol_map)
            if token:
                st.success(f"✅ {test_symbol} → Token: {token}")
                
                # Show full data
                full_data = symbol_map.get(test_symbol.upper())
                st.json(full_data)
            else:
                st.error(f"❌ {test_symbol} not found")
    else:
        st.warning("⚠️ No cache found. Download first!")

# Show cache stats
st.markdown("---")
st.subheader("📊 Cache Statistics")

cache_path = Path('mstock_symbols.json')
if cache_path.exists():
    cache_size = cache_path.stat().st_size / 1024  # KB
    symbol_map = load_cached_symbols('mstock_symbols.json')
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Symbols", len(symbol_map))
    with col2:
        st.metric("Cache Size", f"{cache_size:.1f} KB")
    with col3:
        st.metric("Status", "✅ Ready")
else:
    st.warning("Cache file not created yet")

# Show sample data
if symbol_map:
    st.subheader("📋 Sample Symbols")
    
    sample_symbols = list(symbol_map.keys())[:10]
    sample_data = {sym: symbol_map[sym] for sym in sample_symbols}
    
    st.json(sample_data)
