import requests
import json
from pathlib import Path
from datetime import datetime

# ------------------- Symbol Resolver -------------------

def fetch_instrument_master(jwt_token, api_key):
    """
    Download instrument master from mStock API
    Returns: List of all instruments with tokens
    """
    url = "https://api.mstock.trade/openapi/typeb/instruments/OpenAPIScripMaster"
    
    headers = {
        'X-Mirae-Version': '1',
        'Authorization': f'Bearer {jwt_token}',
        'X-PrivateKey': api_key,
        'Content-Type': 'application/json'
    }
    
    try:
        print("📥 Downloading instrument master...")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            instruments = response.json()
            print(f"✅ Downloaded {len(instruments)} instruments")
            return instruments
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Download error: {str(e)}")
        return None


def build_symbol_token_map(instruments):
    """
    Filter NSE/EQ stocks and build symbol→token lookup dict
    """
    if not instruments:
        return {}
    
    symbol_map = {}
    nse_eq_count = 0
    
    for instrument in instruments:
        # Filter: Only NSE EQ segment stocks
        if instrument.get('exch_seg') == 'NSE' and instrument.get('instrumenttype') == 'EQ':
            symbol = instrument.get('symbol', '').strip().upper()
            token = instrument.get('token', '').strip()
            
            if symbol and token:
                symbol_map[symbol] = {
                    'token': token,
                    'name': instrument.get('name', ''),
                    'lotsize': instrument.get('lotsize', '1'),
                    'tick_size': instrument.get('tick_size', '0.05')
                }
                nse_eq_count += 1
    
    print(f"✅ Filtered {nse_eq_count} NSE EQ stocks")
    return symbol_map


def cache_symbol_map(symbol_map, cache_file='mstock_symbols.json'):
    """
    Save symbol→token mapping to local cache file
    """
    try:
        cache_path = Path(cache_file)
        cache_path.write_text(json.dumps(symbol_map, indent=2))
        print(f"💾 Cached {len(symbol_map)} symbols to {cache_file}")
        return True
    except Exception as e:
        print(f"❌ Cache error: {str(e)}")
        return False


def load_cached_symbols(cache_file='mstock_symbols.json'):
    """
    Load symbol→token mapping from local cache
    """
    try:
        cache_path = Path(cache_file)
        if cache_path.exists():
            symbol_map = json.loads(cache_path.read_text())
            print(f"✅ Loaded {len(symbol_map)} symbols from cache")
            return symbol_map
        else:
            print(f"⚠️ Cache file not found: {cache_file}")
            return None
    except Exception as e:
        print(f"❌ Load error: {str(e)}")
        return None


def get_token(symbol, symbol_map=None, cache_file='mstock_symbols.json'):
    """
    Get token for a symbol (from cache or argument)
    """
    if symbol_map is None:
        symbol_map = load_cached_symbols(cache_file)
    
    if symbol_map is None:
        return None
    
    symbol = symbol.strip().upper()
    result = symbol_map.get(symbol)
    
    if result:
        return result.get('token')
    else:
        print(f"⚠️ Symbol not found: {symbol}")
        return None


def download_and_cache(jwt_token, api_key, cache_file='mstock_symbols.json'):
    """
    Complete workflow: Download → Filter → Cache
    """
    print("=" * 60)
    print("🚀 mStock Symbol Resolver - Download & Cache")
    print("=" * 60)
    
    # Step 1: Download
    instruments = fetch_instrument_master(jwt_token, api_key)
    if not instruments:
        print("❌ Failed to download instruments")
        return False
    
    # Step 2: Filter & Build Map
    symbol_map = build_symbol_token_map(instruments)
    if not symbol_map:
        print("❌ No NSE EQ stocks found")
        return False
    
    # Step 3: Cache
    cache_ok = cache_symbol_map(symbol_map, cache_file)
    
    print("=" * 60)
    print(f"✅ Complete! Cache file: {cache_file}")
    print(f"   Total symbols: {len(symbol_map)}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return True


# ------------------- Test / Usage -------------------

if __name__ == "__main__":
    # Example usage
    jwt_token = "YOUR_JWT_TOKEN_HERE"
    api_key = "YOUR_API_KEY_HERE"
    
    # Download and cache
    success = download_and_cache(jwt_token, api_key)
    
    if success:
        # Test lookup
        print("\n🔍 Testing symbol lookups:")
        symbol_map = load_cached_symbols()
        
        test_symbols = ["GABRIEL", "RUBICON", "KMEW", "TIMETECHNO"]
        for sym in test_symbols:
            token = get_token(sym, symbol_map)
            if token:
                print(f"   {sym:15} → Token: {token}")
            else:
                print(f"   {sym:15} → NOT FOUND")
