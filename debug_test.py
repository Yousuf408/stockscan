# ══════════════════════════════════════════
#  TRADESENTRY — debug_test.py
#  Run this to diagnose exact WebSocket issue
#  python debug_test.py
# ══════════════════════════════════════════

import pyotp
import pytz
import json
import struct
import time
import os
from datetime import datetime
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

# ══════════════════════════════════════════
#  HARDCODE YOUR SECRETS HERE FOR TESTING
# ══════════════════════════════════════════
API_KEY     = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD    = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"

# ══════════════════════════════════════════
#  IST TIME
# ══════════════════════════════════════════
IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(pytz.utc).astimezone(IST)

def t():
    return now_ist().strftime("%H:%M:%S IST")

# ══════════════════════════════════════════
#  STEP 1 — CHECK IST TIME
# ══════════════════════════════════════════
print("\n" + "="*50)
print("  TRADESENTRY — Debug Test")
print("="*50)

print(f"\n[STEP 1] Timezone Check")
print(f"  UTC time : {datetime.now(pytz.utc).strftime('%H:%M:%S')}")
print(f"  IST time : {now_ist().strftime('%H:%M:%S')}")
print(f"  Weekday  : {now_ist().strftime('%A')}")

ist_now   = now_ist()
curr_mins = ist_now.hour * 60 + ist_now.minute
mkt_open  = 9 * 60 + 15
mkt_close = 15 * 60 + 30
market_open = ist_now.weekday() < 5 and mkt_open <= curr_mins <= mkt_close
print(f"  Market   : {'🟢 OPEN' if market_open else '🔴 CLOSED'}")

# ══════════════════════════════════════════
#  STEP 2 — ANGEL ONE LOGIN
# ══════════════════════════════════════════
print(f"\n[STEP 2] Angel One Login")
try:
    obj  = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    print(f"  TOTP     : {totp}")

    sess = obj.generateSession(CLIENT_CODE, PASSWORD, totp)
    print(f"  Status   : {sess.get('status')}")
    print(f"  Message  : {sess.get('message', 'N/A')}")

    if not sess.get("status"):
        print(f"  ❌ LOGIN FAILED — Check credentials!")
        exit(1)

    auth_token = sess["data"]["jwtToken"]
    feed_token = sess["data"].get("feedToken") or obj.getfeedToken()

    print(f"  ✅ Login OK")
    print(f"  Auth token : {auth_token[:30]}...")
    print(f"  Feed token : {str(feed_token)[:30] if feed_token else '❌ MISSING!'}")

    if not feed_token:
        print("  ❌ FEED TOKEN IS MISSING — WebSocket will NEVER work!")
        exit(1)

except Exception as e:
    print(f"  ❌ Login error: {e}")
    exit(1)

# ══════════════════════════════════════════
#  STEP 3 — CHECK WATCHLIST
# ══════════════════════════════════════════
print(f"\n[STEP 3] Watchlist Check")

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")
if not os.path.exists(WATCHLIST_FILE):
    print(f"  ❌ watchlist.json NOT FOUND at {WATCHLIST_FILE}")
else:
    with open(WATCHLIST_FILE) as f:
        data = json.load(f)
    total = 0
    for tab in ["watchlist_Today", "watchlist_Yesterday", "watchlist_New"]:
        count = len(data.get(tab, []))
        print(f"  {tab}: {count} stocks")
        total += count
    print(f"  Total: {total} stocks")

# ══════════════════════════════════════════
#  STEP 4 — CHECK STOCK TOKEN
# ══════════════════════════════════════════
print(f"\n[STEP 4] Token Check (TCS)")
try:
    from stocks import get_stock_token
    token = get_stock_token("TCS")
    print(f"  TCS token : {token}")
    if not token:
        print("  ❌ Token is None — stocks.py get_stock_token() not working!")
    else:
        print(f"  ✅ Token OK: {token}")
except Exception as e:
    print(f"  ❌ Token fetch error: {e}")
    token = None

# ══════════════════════════════════════════
#  STEP 5 — HTTP LTP TEST
# ══════════════════════════════════════════
print(f"\n[STEP 5] HTTP LTP Test (TCS)")
if token:
    try:
        resp = obj.ltpData("NSE", "TCS", str(token))
        print(f"  Response : {resp}")
        if resp and resp.get("status"):
            ltp = float(resp["data"]["ltp"])
            print(f"  ✅ TCS LTP via HTTP: ₹{ltp:.2f}")
        else:
            print(f"  ❌ HTTP LTP failed: {resp}")
    except Exception as e:
        print(f"  ❌ HTTP LTP error: {e}")
else:
    print("  ⏭ Skipped — no token")

# ══════════════════════════════════════════
#  STEP 6 — WEBSOCKET TEST
# ══════════════════════════════════════════
print(f"\n[STEP 6] WebSocket Connection Test")
print(f"  Connecting to Angel One WebSocket...")

ws_events = []

def on_data(wsapp, message):
    if isinstance(message, bytes) and len(message) >= 51:
        try:
            tok = message[2:27].decode("utf-8").rstrip("\x00").strip()
            ltp = struct.unpack("<i", message[43:47])[0] / 100.0
            print(f"  ✅ LIVE PRICE RECEIVED! Token: {tok}, LTP: ₹{ltp:.2f}")
            ws_events.append(("data", tok, ltp))
        except Exception as e:
            print(f"  ⚠ Parse error: {e}")
    else:
        print(f"  WS message (text): {message}")

def on_open(wsapp):
    print(f"  ✅ WebSocket CONNECTED!")
    ws_events.append(("open",))
    if token:
        token_list = [{"exchangeType": 1, "tokens": [str(token)]}]
        wsapp.subscribe("debug_01", 1, token_list)
        print(f"  ✅ Subscribed to TCS (token: {token})")
    else:
        print(f"  ⚠ No token to subscribe")

def on_error(wsapp, error):
    print(f"  ❌ WebSocket ERROR: {error}")
    ws_events.append(("error", str(error)))

def on_close(wsapp):
    print(f"  ❌ WebSocket CLOSED")
    ws_events.append(("close",))

try:
    sws = SmartWebSocketV2(auth_token, API_KEY, CLIENT_CODE, feed_token)
    sws.on_open  = on_open
    sws.on_data  = on_data
    sws.on_error = on_error
    sws.on_close = on_close

    print(f"  Running WebSocket for 15 seconds...")
    import threading
    def run_ws():
        sws.connect()

    t1 = threading.Thread(target=run_ws, daemon=True)
    t1.start()
    time.sleep(15)

    print(f"\n[STEP 6 RESULT]")
    print(f"  Events captured: {ws_events}")
    if any(e[0] == "data" for e in ws_events):
        print(f"  ✅ WebSocket is WORKING! Live prices received.")
    elif any(e[0] == "open" for e in ws_events):
        print(f"  ⚠ WebSocket connected but NO data received.")
        print(f"  → Check if token is correct or market is open")
    elif any(e[0] == "error" for e in ws_events):
        print(f"  ❌ WebSocket FAILED with error")
        print(f"  → Check auth_token and feed_token")
    else:
        print(f"  ❌ WebSocket did not connect at all")

except Exception as e:
    print(f"  ❌ WebSocket test error: {e}")

# ══════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════
print("\n" + "="*50)
print("  SUMMARY")
print("="*50)
print(f"  1. IST Time     : {now_ist().strftime('%H:%M:%S IST')}")
print(f"  2. Market Open  : {'✅ YES' if market_open else '❌ NO (closed)'}")
print(f"  3. Login        : ✅ OK")
print(f"  4. Feed Token   : {'✅ OK' if feed_token else '❌ MISSING'}")
print(f"  5. Stock Token  : {'✅ OK - ' + str(token) if token else '❌ MISSING'}")
print(f"  6. WebSocket    : {'✅ WORKING' if any(e[0] in ['open','data'] for e in ws_events) else '❌ FAILING'}")
print("="*50 + "\n")
