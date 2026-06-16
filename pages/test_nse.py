from smartapi import SmartConnect, SmartWebSocket
import json
import time

# ========== 50 NSE STOCKS WITH TOKENS ==========
STOCKS = {
    "RELIANCE": "2885",
    "TCS": "11536",
    "HDFCBANK": "1333",
    "INFY": "1594",
    "ICICIBANK": "4963",
    "BHARTIARTL": "10604",
    "SBIN": "3045",
    "ITC": "1660",
    "KOTAKBANK": "492",
    "LT": "1788",
    "AXISBANK": "590",
    "HINDUNILVR": "356",
    "BAJFINANCE": "317",
    "WIPRO": "3787",
    "ASIANPAINT": "236",
    "MARUTI": "2489",
    "SUNPHARMA": "335",
    "TITAN": "3506",
    "ULTRACEMCO": "11543",
    "NESTLEIND": "1749",
    "HCLTECH": "722",
    "TECHM": "3466",
    "POWERGRID": "14977",
    "NTPC": "11630",
    "ONGC": "2475",
    "COALINDIA": "4834",
    "ADANIPORTS": "9697",
    "ADANIENT": "13488",
    "JSWSTEEL": "11723",
    "TATASTEEL": "3499",
    "HINDALCO": "1344",
    "TATAMOTORS": "3456",
    "M&M": "2031",
    "BAJAJFINSV": "318",
    "BAJAJ-AUTO": "319",
    "EICHERMOT": "910",
    "HEROMOTOCO": "1348",
    "DRREDDY": "881",
    "CIPLA": "694",
    "DIVISLAB": "10940",
    "APOLLOHOSP": "157",
    "GRASIM": "1232",
    "BRITANNIA": "547",
    "INDUSINDBK": "525",
    "SBILIFE": "13174",
    "HDFCLIFE": "467",
    "BPCL": "526",
    "UPL": "11287",
    "SHREECEM": "3103",
    "DABUR": "772",
}

# ========== LOGIN ==========
print("\n===== ANGEL ONE LOGIN =====")
API_KEY = input("API Key: ").strip()
CLIENT_CODE = input("Client Code: ").strip()
PASSWORD = input("Password: ").strip()
TOTP = input("TOTP: ").strip()

print("\n⏳ Logging in...")
obj = SmartConnect(api_key=API_KEY)
data = obj.generateSession(CLIENT_CODE, PASSWORD, TOTP)

feed_token = obj.getfeedToken()
jwt_token = data['data']['jwtToken']
print("✅ Login successful!\n")

# ========== BUILD SUBSCRIPTION ==========
tokens = list(STOCKS.values())
symbol_names = {v: k for k, v in STOCKS.items()}  # token → symbol mapping

print(f"📊 Loaded {len(STOCKS)} stocks\n")

# ========== WEBSOCKET ==========
sws = SmartWebSocket(feed_token, CLIENT_CODE, jwt_token)

def on_data(wsapp, message):
    try:
        data = json.loads(message)
        
        # Skip non-tick messages
        if 'subscription_mode' in data or 'request_id' in data:
            return
        
        token = str(data.get('token', ''))
        symbol = symbol_names.get(token, token)
        ltp = data.get('last_traded_price', 0)
        volume = data.get('volume_trade_for_the_day', 0)
        change = data.get('change_percentage', 0)
        
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] {symbol:15} │ LTP: ₹{ltp:>8.2f} │ Vol: {volume:>12,} │ Chg: {change:>+6.2f}%")
        
    except Exception as e:
        pass  # Ignore parse errors

def on_open(wsapp):
    print(f"🔗 Connected! Streaming {len(tokens)} stocks...\n")
    print(f"{'Time':<10} {'Symbol':15} │ {'LTP':>10} │ {'Volume':>12} │ {'Change':>8}")
    print("-" * 70)
    sws.subscribe("mw", [{"exchangeType": 1, "tokens": tokens}], 2)  # Mode 2 = Quote

def on_error(wsapp, error):
    print(f"❌ Error: {error}")

def on_close(wsapp, code, msg):
    print(f"\n🔒 Connection closed. Reconnecting in 3s...")
    time.sleep(3)
    sws.connect()

sws.on_open = on_open
sws.on_data = on_data
sws.on_error = on_error
sws.on_close = on_close

print("🚀 Starting live feed... Press Ctrl+C to stop.\n")
sws.connect()
