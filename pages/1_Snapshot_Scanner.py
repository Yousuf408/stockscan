import streamlit as st
import pyotp
import pandas as pd
from SmartApi import SmartConnect

# Page Setup
st.set_page_config(page_title="EOD Stock Scanner", layout="wide")
st.title("📊 Market-Close Snapshot Scanner (LTP Fetcher)")

# Credentials directly from Streamlit Secrets
api_key = st.secrets["API_KEY"]
username = st.secrets["CLIENT_CODE"]
password = st.secrets["PASSWORD"]
totp_secret = st.secrets["TOTP_SECRET"]

# List of Stocks to Scan (Token details for Angel One)
# Format: {"Stock_Name": {"token": "XYZ", "exchange": "NSE"}}
STOCKS_LIST = {
    "RELIANCE": {"token": "2885", "exchange": "NSE"},
    "GAIL": {"token": "4717", "exchange": "NSE"},
    "GMDC": {"token": "14299", "exchange": "NSE"},
    "SBIN": {"token": "3045", "exchange": "NSE"},
    "HEROMOTOCO": {"token": "1348", "exchange": "NSE"}
}

def fetch_closing_prices():
    try:
        # 1. Initialize & Login
        smartApi = SmartConnect(api_key=api_key)
        current_totp = pyotp.TOTP(totp_secret).now()
        data = smartApi.generateSession(username, password, current_totp)
        
        if data.get('status') == False:
            st.error(f"Login Failed: {data.get('message')}")
            return
            
        st.success("🔒 Secure Connection Established with Angel One!")
        
        # 2. Fetch LTP for each stock from the database
        rows = []
        with st.spinner("Fetching last traded prices from server..."):
            for name, info in STOCKS_LIST.items():
                response = smartApi.getLTP(info["exchange"], name, info["token"])
                
                if response.get("status") and response.get("data"):
                    stock_data = response["data"]
                    rows.append({
                        "Stock Symbol": stock_data.get("symbol"),
                        "Last Traded Price (LTP)": f"₹{stock_data.get('ltp'):,.2f}",
                        "Exchange": stock_data.get("exchange"),
                        "Token ID": stock_data.get("token")
                    })
                else:
                    rows.append({
                        "Stock Symbol": name,
                        "Last Traded Price (LTP)": "Fetch Error",
                        "Exchange": info["exchange"],
                        "Token ID": info["token"]
                    })
                    
        # 3. Render into a beautiful clean Table
        df = pd.DataFrame(rows)
        st.subheader("📋 Stock Snapshot Table (Last Available Prices)")
        st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")

# UI Button to trigger fetch
if st.button("🔄 Fetch Last Closing Prices"):
    fetch_closing_prices()