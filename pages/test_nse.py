import pyotp
import pandas as pd
from SmartApi.smartConnect import SmartConnect

# =====================================================================
# 1. ENTER YOUR ANGEL ONE CREDENTIALS HERE
# =====================================================================
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"  # Alphanumeric secret key string

# =====================================================================
# 2. HARDCODED TOP 10 NSE STOCKS (NO JSON PARSING REQUIRED)
# =====================================================================
# These specific numerical mapping IDs do not change arbitrarily.
HARDCODED_STOCKS = {
    "1398": "RELIANCE-EQ",
    "1333": "HDFCBANK-EQ",
    "11536": "TCS-EQ",
    "1594": "INFY-EQ",
    "4124": "ICICIBANK-EQ",
    "3045": "SBIN-EQ",
    "10604": "BHARTIARTL-EQ",
    "1660": "ITC-EQ",
    "3456": "TATAMOTORS-EQ",
    "11630": "NIFTY-BEES" # High volume ETF for tracking benchmark
}

def verify_direct_connection():
    # Convert keys to a clean string list for the API payload
    tokens = list(HARDCODED_STOCKS.keys())
    
    # Initialize SDK Connection
    obj = SmartConnect(api_key=API_KEY)
    
    try:
        # Generate current 2FA code dynamically
        totp_auth = pyotp.TOTP(TOTP_SECRET).now()
        
        print("🔐 Sending authentication packet directly to Angel One servers...")
        session_data = obj.generateSession(CLIENT_CODE, PASSWORD, totp_auth)
        
        if session_data.get('status') is False:
            print(f"❌ Connection Handshake Denied: {session_data.get('message')}")
            return
            
        print("✅ Session active! Fetching live price & volume matrix...")
        
        # Requesting FULL snapshot (Provides Price + Accumulated Day Volume)
        market_data = obj.getMarketData("FULL", {"NSE": tokens})
        
        if market_data.get('status') and 'data' in market_data:
            fetched_list = market_data['data'].get('fetched', [])
            
            dashboard_rows = []
            for item in fetched_list:
                token_id = item.get('symbolToken')
                dashboard_rows.append({
                    "Stock Ticker": HARDCODED_STOCKS.get(token_id, item.get('tradingSymbol')),
                    "Token": token_id,
                    "Live LTP (₹)": item.get('ltp'),
                    "Volume Traded": item.get('volume'),
                    "Day High (₹)": item.get('high'),
                    "Day Low (₹)": item.get('low')
                })
            
            # Print layout output
            df_dashboard = pd.DataFrame(dashboard_rows)
            print("\n" + "="*72)
            print("         🟢 TEST PASSED: ANGEL ONE API COMMUNICATING FLAWLESSLY")
            print("="*72)
            print(df_dashboard.to_string(index=False))
            print("="*72)
            
        else:
            print(f"⚠️ Authenticated, but could not extract instrument data: {market_data.get('message')}")
            
    except Exception as e:
        print(f"💥 Runtime Exception: {str(e)}")

if __name__ == "__main__":
    verify_direct_connection()
