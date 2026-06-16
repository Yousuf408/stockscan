import requests
import pandas as pd

# Get NSE session cookie
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# Get fresh cookie
session.get("https://www.nseindia.com")

# Fetch single stock
resp = session.get("https://www.nseindia.com/api/quote-equity?symbol=RELIANCE")
data = resp.json()

print(data['priceInfo']['lastPrice'])
print(data['priceInfo']['totalTradedVolume'])
