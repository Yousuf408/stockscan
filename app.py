import streamlit as st
import os
import pandas as pd
import pyotp
from SmartApi import SmartConnect

# 1. Page Setup
st.set_page_config(page_title="Real-Time Autonomous Trader", layout="wide")
st.title("🚀 Real-Time Autonomous Trader")

# 2. Proxy Configuration
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL

# 3. Sidebar: Login Credentials
st.sidebar.header("🔑 Login Credentials")
api_key = st.sidebar.text_input("API Key", type="password")
client_id = st.sidebar.text_input("Client ID")
password = st.sidebar.text_input("Password", type="password")
totp_key = st.sidebar.text_input("TOTP Key", type="password")

if "obj" not in st.session_state: st.session_state.obj = None

if st.sidebar.button("Login"):
    try:
        obj = SmartConnect(api_key=api_key)
        obj.proxy = {"http": PROXY_URL, "https": PROXY_URL}
        totp = pyotp.TOTP(totp_key.replace(" ", ""))
        data = obj.generateSession(client_id, password, totp.now())
        
        if data.get("status"):
            st.session_state.obj = obj
            st.sidebar.success("Logged In!")
        else:
            st.sidebar.error("Login Failed")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# 4. Master Token Resolver (Angel One API)
@st.cache_data
def get_master_data():
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    return pd.read_json(url)

# 5. Main Trader Logic
if st.session_state.obj:
    master_df = get_master_data()
    symbol_input = st.text_input("Enter Symbol (e.g., RELIANCE):").upper()
    
    if symbol_input:
        # Filter for NSE Equity
        match = master_df[(master_df['symbol'] == symbol_input) & (master_df['exch_seg'] == 'NSE')]
        
        if not match.empty:
            token = match.iloc[0]['token']
            st.write(f"✅ Found Token: **{token}**")
            
            qty = st.number_input("Quantity", min_value=1, value=1)
            if st.button("Place BUY Order"):
                try:
                    params = {
                        "variety": "NORMAL", "tradingsymbol": f"{symbol_input}-EQ",
                        "symboltoken": str(token), "exchange": "NSE",
                        "transactiontype": "BUY", "ordertype": "MARKET",
                        "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
                    }
                    order_id = st.session_state.obj.placeOrder(params)
                    st.success(f"🎉 Order Placed! ID: {order_id}")
                except Exception as e:
                    st.error(f"Execution Error: {e}")
        else:
            st.error("Symbol nahi mila. Check karo ki sahi naam daala hai (e.g., RELIANCE).")
else:
    st.info("Pehle sidebar se Login karo.")
