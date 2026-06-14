import streamlit as pd_st
import streamlit as st
import pyotp
import pandas as pd
from SmartApi.smartConnect import SmartConnect

# Page configuration
st.set_page_config(page_title="Angel One API Test", page_icon="🟢", layout="wide")

st.title("📊 Angel One API Connection Test")
st.markdown("This page verifies if your credentials and live token handshakes are operating properly.")

# =====================================================================
# 1. ENTER YOUR ANGEL ONE CREDENTIALS HERE
# =====================================================================
API_KEY = "QFectj5C"
CLIENT_CODE = "IIRA29771"
PASSWORD = "1993"
TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"  # Alphanumeric secret key string


# Hardcoded tokens for instant validation
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
    "11630": "NIFTY-BEES"
}

# Add a manual trigger button on the dashboard
if st.button("🚀 Run Live Connection Test"):
    tokens = list(HARDCODED_STOCKS.keys())
    obj = SmartConnect(api_key=API_KEY)
    
    with st.spinner("🔐 Authenticating and connecting to Angel One Servers..."):
        try:
            # Generate TOTP 2FA
            totp_auth = pyotp.TOTP(TOTP_SECRET).now()
            session_data = obj.generateSession(CLIENT_CODE, PASSWORD, totp_auth)
            
            if session_data.get('status') is False:
                st.error(f"❌ Connection Handshake Denied: {session_data.get('message')}")
            else:
                st.success("✅ Session Authenticated Successfully! Fetching live rates...")
                
                # Request Data
                market_data = obj.getMarketData("FULL", {"NSE": tokens})
                
                if market_data.get('status') and 'data' in market_data:
                    fetched_list = market_data['data'].get('fetched', [])
                    
                    dashboard_rows = []
                    for item in fetched_list:
                        token_id = item.get('symbolToken')
                        dashboard_rows.append({
                            "Stock Ticker": HARDCODED_STOCKS.get(token_id, item.get('tradingSymbol')),
                            "Token ID": token_id,
                            "Live LTP (₹)": item.get('ltp'),
                            "Volume Traded": item.get('volume'),
                            "Day High (₹)": item.get('high'),
                            "Day Low (₹)": item.get('low')
                        })
                    
                    # Create Dataframe and render it visually on screen
                    df = pd.DataFrame(dashboard_rows)
                    
                    st.subheader("🟢 Live Market Feed Matrix")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning(f"⚠️ Authenticated, but data fetch empty: {market_data.get('message')}")
                    
        except Exception as e:
            st.error(f"💥 Runtime Error: {str(e)}")
else:
    st.info("Click the 'Run Live Connection Test' button above to initialize the API handshake.")
