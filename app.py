import streamlit as st
import os
import pyotp
import pandas as pd
from SmartApi import SmartConnect

# 1. Page Config
st.set_page_config(page_title="ORBScanner", layout="wide")

# 2. Hardcoded Proxy Configuration (Dedicated IP Tunnel)
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL

st.title("🎯 System Intraday Trader - NSE India")

# 3. Sidebar: Secure Gateway with Auto-Load from Secrets
st.sidebar.header("🔑 Secure Gateway")
api_key = st.sidebar.text_input("SmartAPI API Key", value=st.secrets.get("API_KEY", ""), type="password")
client_id = st.sidebar.text_input("Client ID", value=st.secrets.get("CLIENT_ID", "IIRA29711"))
password = st.sidebar.text_input("Password", value=st.secrets.get("PASSWORD", ""), type="password")
totp_key = st.sidebar.text_input("TOTP Key", value=st.secrets.get("TOTP_KEY", ""), type="password")

if "obj" not in st.session_state: st.session_state.obj = None
if "logged_in" not in st.session_state: st.session_state.logged_in = False

# 4. Authentication Logic
if st.sidebar.button("Run System Authentication"):
    if not (api_key and client_id and password and totp_key):
        st.sidebar.error("All fields are mandatory!")
    else:
        with st.spinner("Connecting via dedicated proxy..."):
            try:
                obj = SmartConnect(api_key=api_key, proxies={"http": PROXY_URL, "https": PROXY_URL})
                totp = pyotp.TOTP(totp_key.replace(" ", ""))
                data = obj.generateSession(client_id, password, totp.now())
                
                if data.get("status") == True:
                    st.session_state.obj = obj
                    st.session_state.logged_in = True
                    st.sidebar.success("✅ Auth Successful!")
                    st.rerun()
                else:
                    st.sidebar.error(f"Auth Rejected: {data.get('message')}")
            except Exception as e:
                st.sidebar.error(f"Error: {str(e)}")

# 5. Trading Desk Logic
if st.session_state.logged_in:
    st.success("🔒 System Active via Proxy: 151.242.178.149")
    
    # Example Watchlist
    stocks_data = pd.DataFrame({
        "Stock Name": ["JYOTICNC", "HEROMOTOCO", "GAIL", "GMDC", "RELIANCE"],
        "Token": ["19483", "1342", "4717", "11116", "2885"]
    })
    
    selected_stock = st.selectbox("Select Candidate", stocks_data["Stock Name"].tolist())
    token_id = stocks_data[stocks_data["Stock Name"] == selected_stock].iloc[0]["Token"]
    qty = st.number_input("Quantity", min_value=1, value=10)
    
    if st.button(f"🔥 Place BUY Order for {selected_stock}"):
        try:
            params = {
                "variety": "NORMAL", "tradingsymbol": f"{selected_stock}-EQ",
                "symboltoken": str(token_id), "exchange": "NSE",
                "transactiontype": "BUY", "ordertype": "MARKET",
                "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
            }
            order_id = st.session_state.obj.placeOrder(params)
            st.success(f"🎉 Order Placed! ID: {order_id}")
        except Exception as e:
            st.error(f"Execution Failed: {str(e)}")
else:
    st.info("⚠️ Please authenticate via sidebar.")
