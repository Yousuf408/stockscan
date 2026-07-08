import streamlit as st
import os
import time
import pyotp
import pandas as pd
import requests
from SmartApi import SmartConnect

# 1. Page Config
st.set_page_config(page_title="Intraday Trader Pro", layout="wide")

# 2. Proxy Configuration
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"

# 3. Fixed Watchlist
stocks_data = {
    "Stock": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "LT", "ITC", "BHARTIARTL", "AXISBANK",
              "KOTAKBANK", "MARUTI", "HINDUNILVR", "TATAMOTORS", "SUNPHARMA", "BAJFINANCE", "ASIANPAINT", "WIPRO", "HCLTECH", "TITAN"],
    "Token": ["2885", "11536", "1594", "1333", "4963", "3045", "11483", "1660", "10604", "5900",
              "1922", "1856", "1394", "3456", "15083", "317", "236", "11532", "7229", "35006"]
}
df_stocks = pd.DataFrame(stocks_data)

# Helper: Show Order Book
def show_order_book(container, obj):
    try:
        resp = obj.orderBook()
        if resp.get("status") and resp.get("data"):
            orders_df = pd.DataFrame(resp["data"])
            display_cols = ["orderid", "tradingsymbol", "transactiontype", "quantity", "price", "orderstatus"]
            container.dataframe(orders_df[display_cols], use_container_width=True)
        else:
            container.info("No orders found.")
    except Exception as e:
        container.error(f"Error: {e}")

# Session State
if "obj" not in st.session_state: st.session_state.obj = None

# Sidebar Login
st.sidebar.header("🔑 Login Credentials")
api_key = st.sidebar.text_input("API Key", value="QFectj5C", type="password")
client_id = st.sidebar.text_input("Client ID", value="IIRA29771")
password = st.sidebar.text_input("Password", type="password")
totp_key = st.sidebar.text_input("TOTP Key", value="JFTG3DYADWLYSW6FC6RVV4THWM", type="password")

if st.sidebar.button("Login"):
    with st.spinner("Establishing stable 30s connection..."):
        try:
            obj = SmartConnect(api_key=api_key)
            # Custom Session for 30s Timeout
            session = requests.Session()
            session.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            # Injecting timeout into session
            obj.http_session = session 
            
            totp = pyotp.TOTP(totp_key.replace(" ", ""))
            data = obj.generateSession(client_id, password, totp.now())
            
            if data.get("status"):
                st.session_state.obj = obj
                st.sidebar.success("✅ Logged In!")
            else:
                st.sidebar.error(f"Failed: {data.get('message')}")
        except Exception as e:
            st.sidebar.error(f"Network Error: {e}")

# Main UI
st.title("🚀 Real-Time Autonomous Trader")
if st.session_state.obj:
    selected_stock = st.selectbox("Choose Stock", df_stocks["Stock"].tolist())
    token_id = df_stocks[df_stocks["Stock"] == selected_stock]["Token"].values[0]
    
    qty = st.number_input("Quantity", min_value=1, value=1)
    action = st.radio("Action", ["BUY", "SELL"])
    
    if st.button(f"🔥 Place {action} Order"):
        try:
            params = {
                "variety": "NORMAL", "tradingsymbol": f"{selected_stock}-EQ",
                "symboltoken": str(token_id), "exchange": "NSE",
                "transactiontype": action, "ordertype": "MARKET",
                "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
            }
            order_id = st.session_state.obj.placeOrder(params)
            st.success(f"🎉 Order Placed! ID: {order_id}")
            
            # Auto-Refresh Order Book
            time.sleep(1)
            show_order_book(st.container(), st.session_state.obj)
        except Exception as e:
            st.error(f"Execution Error: {e}")

    st.markdown("---")
    if st.button("🔄 Refresh Order Book"):
        show_order_book(st.container(), st.session_state.obj)
else:
    st.info("Pehle Login karo.")
