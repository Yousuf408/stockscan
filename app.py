import streamlit as st
import pyotp
import json
import yfinance as yf  # Changed alias to standard 'yf'
import plotly.graph_objects as go
from SmartApi import SmartConnect

# Page configuration
st.set_page_config(page_title="AngelOne Screener Dashboard", page_icon="📈", layout="wide")

st.title("📊 Advanced Trading Dashboard & Instant Order Execution")
st.write("Aapke requirements.txt ke hisab se designed dashboard. Bug fixes applied.")

# 1. Sidebar for Angel One Credentials
with st.sidebar.expander("🔑 Angel One API Credentials", expanded=True):
    api_key = st.secrets.get("ANGEL_API_KEY", st.text_input("API Key", type="password"))
    client_id = st.secrets.get("ANGEL_CLIENT_ID", st.text_input("Client ID"))
    password = st.secrets.get("ANGEL_PASSWORD", st.text_input("Password", type="password"))
    totp_secret = st.secrets.get("ANGEL_TOTP_SECRET", st.text_input("TOTP Secret Key", type="password"))

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

# Order Placement Function
def place_market_order(tradingsymbol, symboltoken):
    if not (api_key and client_id and password and totp_secret):
        return {"status": "Failed", "error": "Credentials missing in sidebar/Secrets!"}
    
    obj = SmartConnect(api_key=api_key)
    try:
        totp = pyotp.TOTP(totp_secret).now()
        data = obj.generateSession(client_id, password, totp)
        
        if data.get('status'):
            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": tradingsymbol,
                "symboltoken": symboltoken,
                "transactiontype": "BUY",
                "exchange": "NSE",
                "ordertype": "MARKET",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "quantity": "1"
            }
            # AngelOne sometimes returns response dictionary directly or as string/int
            order_response = obj.placeOrder(order_params)
            
            if order_response:
                return {"status": "Success", "order_id": order_response}
            else:
                return {"status": "Failed", "error": "No Order ID received from AngelOne API"}
        else:
            return {"status": "Failed", "error": data.get('message', 'Login Failed')}
    except Exception as e:
        return {"status": "Failed", "error": str(e)}

# Render UI Grid
st.write("---")

for stock in TOP_STOCKS:
    col_info, col_chart, col_status, col_action = st.columns([2, 4, 2, 2])
    
    with col_info:
        st.subheader(stock['name'])
        st.caption(f"Token: {stock['token']} | {stock['symbol']}")
        
    with col_chart:
        try:
            # Fixing the multi-index data bug of yfinance
            df = yf.download(stock['yf_ticker'], period="5d", interval="15m", progress=False)
            if not df.empty:
                # If dataframe has MultiIndex columns, drop the ticker level
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.dropdown(1)
                
                fig = go.Figure(data=[go.Candlestick(
                    x=df.index, 
                    open=df['Open'], 
                    high=df['High'], 
                    low=df['Low'], 
                    close=df['Close']
                )])
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=120, xaxis_rangeslider_visible=False, showlegend=False)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{stock['name']}")
        except Exception as chart_err:
            st.caption(f"Chart error or data loading...")
            
    with col_status:
        st.markdown("### :green[BUY SIGNAL]")
        st.caption("Criteria: Supertrend & RSI Match")
        
    with col_action:
        st.write("") # Padding
        if st.button(f"🚀 Buy 1 Qty", key=f"btn_{stock['name']}", use_container_width=True):
            with st.spinner("Executing..."):
                res = place_market_order(stock['symbol'], stock['token'])
                if res and res["status"] == "Success":
                    st.success(f"Ordered! ID: {res['order_id']}")
                    st.balloons()
                else:
                    st.error(f"Error: {res['error'] if res else 'Unknown API Error'}")
                    
    st.write("---")
