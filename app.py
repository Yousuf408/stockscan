import streamlit as st
import os
import pyotp
import pandas as pd
from SmartApi import SmartConnect

# 1. Page Config
st.set_page_config(page_title="Real-Time Autonomous Trader", layout="wide")

# 2. Proxy Configuration
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL

# 3. Master Data Resolver
@st.cache_data
def get_master_data():
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    return pd.read_json(url)

st.title("🚀 Real-Time Autonomous Trader")

# 4. Sidebar: Default Credentials Added
st.sidebar.header("🔑 Login Credentials")
api_key = st.sidebar.text_input("API Key", value="QFectj5C", type="password")
client_id = st.sidebar.text_input("Client ID", value="IIRA29771")
password = st.sidebar.text_input("Password", type="password") # Yeh aap manually daaloge
totp_key = st.sidebar.text_input("TOTP Key", value="JFTG3DYADWLYSW6FC6RVV4THWM", type="password")

if "obj" not in st.session_state: st.session_state.obj = None

# Login Logic
if st.sidebar.button("Login"):
    with st.spinner("Authenticating..."):
        try:
            obj = SmartConnect(api_key=api_key)
            obj.proxy = {"http": PROXY_URL, "https": PROXY_URL}
            totp = pyotp.TOTP(totp_key.replace(" ", ""))
            data = obj.generateSession(client_id, password, totp.now())
            if data.get("status"):
                st.session_state.obj = obj
                st.sidebar.success("Logged In Successfully!")
            else:
                st.sidebar.error(f"Login Failed: {data.get('message')}")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# 5. Trading Logic
if st.session_state.obj:
    master_df = get_master_data()
    symbol_input = st.text_input("Enter NSE Symbol (e.g., RELIANCE):").upper().strip()
    
    if symbol_input:
        match = master_df[(master_df['symbol'] == symbol_input) & (master_df['exch_seg'] == 'NSE')]
        if not match.empty:
            token = match.iloc[0]['token']
            st.success(f"✅ Resolved: {symbol_input} (Token: {token})")
            
            qty = st.number_input("Quantity", min_value=1, value=1)
            action = st.radio("Action", ["BUY", "SELL"])
            
            if st.button(f"Place {action} Order"):
                try:
                    params = {
                        "variety": "NORMAL", "tradingsymbol": f"{symbol_input}-EQ",
                        "symboltoken": str(token), "exchange": "NSE",
                        "transactiontype": action, "ordertype": "MARKET",
                        "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
                    }
                    order_id = st.session_state.obj.placeOrder(params)
                    st.success(f"🎉 Order Placed! ID: {order_id}")
                except Exception as e:
                    st.error(f"Execution Error: {e}")
        else:
            st.warning("Symbol nahi mila. Sahi spelling check karo.")
else:
    st.info("Pehle sidebar me Password daal kar Login button dabayein.")
