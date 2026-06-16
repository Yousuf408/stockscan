from smartapi import SmartConnect, SmartWebSocket
import json

STOCKS = {
    "RELIANCE": "2885", "TCS": "11536", "HDFCBANK": "1333", "INFY": "1594",
    "ICICIBANK": "4963", "BHARTIARTL": "10604", "SBIN": "3045", "ITC": "1660",
    "KOTAKBANK": "492", "LT": "1788", "AXISBANK": "590", "HINDUNILVR": "356",
    "BAJFINANCE": "317", "WIPRO": "3787", "ASIANPAINT": "236", "MARUTI": "2489",
    "SUNPHARMA": "335", "TITAN": "3506", "ULTRACEMCO": "11543", "NESTLEIND": "1749",
    "HCLTECH": "722", "TECHM": "3466", "POWERGRID": "14977", "NTPC": "11630",
    "ONGC": "2475", "COALINDIA": "4834", "ADANIPORTS": "9697", "ADANIENT": "13488",
    "JSWSTEEL": "11723", "TATASTEEL": "3499", "HINDALCO": "1344", "TATAMOTORS": "3456",
    "M&M": "2031", "BAJAJFINSV": "318", "BAJAJ-AUTO": "319", "EICHERMOT": "910",
    "HEROMOTOCO": "1348", "DRREDDY": "881", "CIPLA": "694", "DIVISLAB": "10940",
    "APOLLOHOSP": "157", "GRASIM": "1232", "BRITANNIA": "547", "INDUSINDBK": "525",
    "SBILIFE": "13174", "HDFCLIFE": "467", "BPCL": "526", "UPL": "11287",
    "SHREECEM": "3103", "DABUR": "772"
}

print("\n===== ANGEL ONE LOGIN =====")
API_KEY = input("QFectj5C: ").strip()
CLIENT_CODE = input("IIRA29771: ").strip()
PASSWORD = input("1993: ").strip()
TOTP = input("JFTG3DYADWLYSW6FC6RVV4THWM: ").strip()

obj = SmartConnect(api_key=API_KEY)
data = obj.generateSession(CLIENT_CODE, PASSWORD, TOTP)

feed_token = obj.getfeedToken()
jwt_token = data['data']['jwtToken']
tokens = list(STOCKS.values())
symbol_map = {v: k for k, v in STOCKS.items()}

sws = SmartWebSocket(feed_token, CLIENT_CODE, jwt_token)

def on_data(wsapp, msg):
    d = json.loads(msg)
    if 'last_traded_price' in d:
        sym = symbol_map.get(str(d.get('token', '')), '?')
        print(f"{sym}: ₹{d['last_traded_price']} | Vol: {d.get('volume_trade_for_the_day', 0)}")

def on_open(wsapp):
    sws.subscribe("mw", [{"exchangeType": 1, "tokens": tokens}], 2)

sws.on_open = on_open
sws.on_data = on_data
sws.connect()
