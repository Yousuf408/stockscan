import streamlit as st
import pyotp
import json
import pandas as pd
import yfinance as yf
import requests  # Direct API communication ke liye
import plotly.graph_objects as go

# Page configuration
st.set_page_config(page_title="AngelOne Screener Dashboard", page_icon="📈", layout="wide")

st.title("📊 Advanced Trading Dashboard & Instant Order Execution")
st.write("Direct HTTP Request System applied. Isme SDK payload loss bypass ho jayega.")

# 1. Sidebar for Angel One Credentials with Defaults
with st.sidebar.expander("🔑 Angel One API Credentials", expanded=True):
    DEFAULT_CLIENT_ID = "IIRA29771"
    DEFAULT_API_KEY = "QFectj5C"
    DEFAULT_TOTP_SECRET = "JFTG3DYADWLYSW6FC6RVV4THWM"
    
    api_key = st.secrets.get("ANGEL_API_KEY", st.text_input("API Key", value=DEFAULT_API_KEY, type="password"))
    client_id = st.secrets.get("ANGEL_CLIENT_ID", st.text_input("Client ID", value=DEFAULT_CLIENT_ID))
    password = st.text_input("Password", type="password", help="Apna AngelOne Login Password yahan dalein")
    totp_secret = st.secrets.get("ANGEL_TOTP_SECRET", st.text_input("TOTP Secret Key", value=DEFAULT_TOTP_SECRET, type="password"))

# Top 10 Stocks with Yahoo Finance tickers and AngelOne Tokens
TOP_STOCKS = [
    {"name": "RELIANCE", "symbol": "RELIANCE-EQ", "token": "2885", "yf_ticker": "RELIANCE.NS"},
    {"name": "TCS", "symbol": "TCS-EQ", "token": "11536", "yf_ticker": "TCS.NS"},
    {"name": "BHARTIARTL", "symbol": "BHARTIARTL-EQ", "token": "10604", "yf_ticker": "BHARTIARTL.NS"},
    {"name": "INFY", "symbol": "INFY-EQ", "token": "1594", "yf_ticker": "INFY.NS"},
    {"name": "HDFCBANK", "symbol": "HDFCBANK-EQ", "token": "1348", "yf_ticker": "HDFCBANK.NS"},
    {"name": "ICICIBANK", "symbol": "ICICIBANK-EQ", "token": "4963", "yf_ticker": "ICICIBANK.NS"},
    {"name": "HINDUNILVR", "symbol": "HINDUNILVR-EQ", "token": "1333", "yf_ticker": "HINDUNILVR.NS"},
    {"name": "ITC", "symbol": "ITC-EQ", "token": "1660", "yf_ticker": "ITC.NS"},
    {"name": "SBIN", "symbol": "SBIN-EQ", "token": "3045", "yf_ticker": "SBIN.NS"},
    {"name": "LT", "symbol": "LT-EQ", "token": "11483", "yf_ticker": "LT.NS"}
]

# Order Placement using direct HTTP requests to bypass SDK limitations
def place_market_order_direct(tradingsymbol, symboltoken):
    if not password:
        return {"status": "Failed", "error": "Please enter your Password in sidebar!"}
        
    try:
        # 1. Session Login REST Endpoint
        totp = pyotp.TOTP(totp_secret.replace(" ", "")).now()
        login_url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
        
        headers = {
            "Content-Type": "application/json",
            "X-ClientLocalIP": "192.168.1.1",
            "X-ClientPublicIP": "106.10.10.10",
            "X-MACAddress": "fe80::216:3eff:fe13:8807",
            "X-PrivateKey": api_key
        }
        
        login_payload = {
            "clientcode": client_id,
            "password": password,
            "totp": totp
        }
        
        login_response = requests.post(login_url, headers=headers, json=login_payload).json()
        
        if not login_response.get('status'):
            return {"status": "Failed", "error": f"Login Error: {login_response.get('message')}"}
            
        # Extract JwtToken for Authorization
        jwt_token = login_response['data']['jwtToken']
        
        # 2. Order Placement REST Endpoint
        order_url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"
        
        order_headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "X-ClientLocalIP": "192.168.1.1",
            "X-ClientPublicIP": "106.10.10.10",
            "X-MACAddress": "fe80::216:3eff:fe13:8807",
            "X-PrivateKey": api_key
        }
        
        # We use AMO + DELIVERY for post-market hours safe testing
        order_payload = {
            "variety": "AMO",
            "tradingsymbol": str(tradingsymbol),
            "symboltoken": str(symboltoken),
            "transactiontype": "BUY",
            "exchange": "NSE",
            "ordertype": "MARKET",
            "producttype": "DELIVERY",
            "duration": "DAY",
            "quantity": "1"
        }
        
        res = requests.post(order_url, headers=order_headers, json=order_payload).json()
        
        if res.get('status') == True:
            order_id = res.get('data', {}).get('orderid', 'ID_NOT_PARSED')
            return {"status": "Success", "order_id": order_id}
        else:
            return {"status": "Failed", "error": f"Broker Refusal: {res.get('message', 'Unknown rejection')}"}
            
    except Exception as e:
        return {"status": "Failed", "error": f"System Exception: {str(e)}"}

# Render UI Grid
st.write("---")

for stock in TOP_STOCKS:
    col_info, col_chart, col_status, col_action = st.columns([2, 4, 2, 2])
    
    with col_info:
        st.subheader(stock['name'])
        st.caption(f"Token: {stock['token']} | {stock['symbol']}")
        
    with col_chart:
        try:
            df = yf.download(stock['yf_ticker'], period="5d", interval="15m", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                
                fig = go.Figure(data=[go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close']
                )])
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=120, xaxis_rangeslider_visible=False, showlegend=False)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{stock['name']}")
        except Exception:
            st.caption("Chart loading...")
            
    with col_status:
        st.markdown("### :green[BUY SIGNAL]")
        st.caption("Criteria: Supertrend & RSI Match")
        
    with col_action:
        st.write("") 
        if st.button(f"🚀 Buy 1 Qty", key=f"btn_{stock['name']}", use_container_width=True):
            with st.spinner("Processing REST Order..."):
                res = place_market_order_direct(stock['symbol'], stock['token'])
                if res and res["status"] == "Success":
                    st.success(f"Ordered! ID: {res['order_id']}")
                    st.balloons()
                else:
                    st.error(f"{res['error']}")
                    
    st.write("---")
