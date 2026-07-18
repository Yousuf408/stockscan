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

st.set_page_config(page_title="mStock Symbol Download", layout="wide")

st.title("🔧 mStock Instrument Master Download")

with st.sidebar:
    st.header("🔐 Authenticate First")
    api_key = st.text_input("API Key", type="password")
    jwt_token = st.text_input("JWT Token", type="password", help="From your login response")

if not api_key or not jwt_token:
    st.warning("⚠️ Please enter API Key and JWT Token in sidebar")
    st.stop()

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
