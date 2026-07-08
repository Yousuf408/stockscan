import streamlit as st
import os
import pyotp
import pandas as pd
from SmartApi import SmartConnect

# 1. Page Config
st.set_page_config(page_title="Intraday Trader", layout="wide")

# 2. Proxy Configuration
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL

# 3. 20 Stocks Fixed Watchlist
stocks_data = {
    "Stock": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "LT", "ITC", "BHARTIARTL", "AXISBANK",
              "KOTAKBANK", "MARUTI", "HINDUNILVR", "TATAMOTORS", "SUNPHARMA", "BAJFINANCE", "ASIANPAINT", "WIPRO", "HCLTECH", "TITAN"],
    "Token": ["2885", "11536", "1594", "1333", "4963", "3045", "11483", "1660", "10604", "5900",
              "1922", "1856", "1394", "3456", "15083", "317", "236", "11532", "7229", "35006"]
}
df_stocks = pd.DataFrame(stocks_data)

st.title("🚀 Real-Time Autonomous Trader")

# 4. Sidebar: Credentials
st.sidebar.header("🔑 Login Credentials")
api_key = st.sidebar.text_input("API Key", value="QFectj5C", type="password")
client_id = st.sidebar.text_input("Client ID", value="IIRA29771")
password = st.sidebar.text_input("Password", type="password")
totp_key = st.sidebar.text_input("TOTP Key", value="JFTG3DYADWLYSW6FC6RVV4THWM", type="password")

if "obj" not in st.session_state: st.session_state.obj = None

if st.sidebar.button("Login"):
    with st.spinner("Authenticating..."):
        try:
            obj = SmartConnect(api_key=api_key)
            obj.proxy = {"http": PROXY_URL, "https": PROXY_URL}
            totp = pyotp.TOTP(totp_key.replace(" ", ""))
            data = obj.generateSession(client_id, password, totp.now())
            if data.get("status"):
                st.session_state.obj = obj
                st.sidebar.success("Logged In!")
            else:
                st.sidebar.error(f"Login Failed: {data.get('message')}")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# 5. Trading Logic
if st.session_state.obj:
    st.subheader("Select from Watchlist")
    selected_stock = st.selectbox("Choose Stock", df_stocks["Stock"].tolist())
    
    # Get token for selected stock
    token_id = df_stocks[df_stocks["Stock"] == selected_stock]["Token"].values[0]
    st.write(f"Selected: **{selected_stock}** | Token: **{token_id}**")
    
    col1, col2 = st.columns(2)
    qty = col1.number_input("Quantity", min_value=1, value=1)
    action = col2.radio("Action", ["BUY", "SELL"])
    
    if st.button(f"Place {action} Order"):
        try:
            params = {
                "variety": "NORMAL", "tradingsymbol": f"{selected_stock}-EQ",
                "symboltoken": str(token_id), "exchange": "NSE",
                "transactiontype": action, "ordertype": "MARKET",
                "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
            }
            order_id = st.session_state.obj.placeOrder(params)
            st.success(f"🎉 Order Placed! ID: {order_id}")
        except Exception as e:
            st.error(f"Execution Error: {e}")
else:
    st.info("Pehle Login karo.")
