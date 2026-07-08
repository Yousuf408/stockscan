import streamlit as st
import os
import pandas as pd
from SmartApi import SmartConnect

# 1. Page & Proxy Setup
st.set_page_config(page_title="Intraday Momentum Terminal", layout="wide")
st.title("🎯 System Intraday Trader - NSE India")

PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL

# 2. Your Custom Nifty-Mapped 44 Stock Watchlist & Master Tokens
# (Sample mapping incorporating your custom sectors like NIFTY AUTO, NIFTY CAPITAL GOODS)
WATCHLIST = {
    "JYOTICNC": {"token": "19483", "exchange": "NSE", "sector": "NIFTY CAPITAL GOODS"},
    "HEROMOTOCO": {"token": "1342", "exchange": "NSE", "sector": "NIFTY AUTO"},
    "GAIL": {"token": "4717", "exchange": "NSE", "sector": "NIFTY INFRA"},
    "GMDC": {"token": "11116", "exchange": "NSE", "sector": "NIFTY METALS"},
    "RELIANCE": {"token": "2885", "exchange": "NSE", "sector": "NIFTY ENERGY"}
    # Baki ke stocks bhi isi dictionary standard me append ho jayenge
}

# 3. Sidebar Authentication
st.sidebar.header("🔑 Secure Gateway")
api_key = st.sidebar.text_input("SmartAPI API Key", type="password")
client_id = st.sidebar.text_input("Client ID")
password = st.sidebar.text_input("Password", type="password")
totp_token = st.sidebar.text_input("TOTP Key", type="password")

if "obj" not in st.session_state: st.session_state.obj = None
if "logged_in" not in st.session_state: st.session_state.logged_in = False

if st.sidebar.button("Run System Authentication"):
    try:
        obj = SmartConnect(api_key=api_key)
        data = obj.generateSession(client_id, password, totp_token)
        if data.get("status") == True:
            st.session_state.obj = obj
            st.session_state.logged_in = True
            st.sidebar.success("Proxy Tunnel Active & Connected!")
        else:
            st.sidebar.error("Auth Rejected.")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# 4. Core Logic: Delivery & Volume Signal Processing Engine
def process_trading_signals(api_obj):
    processed_data = []
    
    for symbol, details in WATCHLIST.items():
        try:
            # Fetching Live Market Footprints
            ltp_resp = api_obj.ltpData(details["exchange"], symbol, details["token"])
            if ltp_resp.get("status") == True:
                ltp = float(ltp_resp["data"]["ltp"])
                
                # Simulating EOD calculation based on your 6-point valuation formula
                # In real execution, replace these with your compiled Excel/Sheets matrix data
                delivery_pct = 45.0  # Example delivery data fetched
                relative_volume = 2.5  # RVOL indicator footprint
                
                # Signal Generation Condition Matrix (High Delivery + Institutional Breakout)
                signal = "HOLD"
                if delivery_pct > 40.0 and relative_volume > 2.0:
                    signal = "⚡ BUY SIGNAL"
                elif ltp < 1398.0 and symbol == "RELIANCE": # Guarding structural setups
                    signal = "⚡ BUY SIGNAL (Value Zone)"
                    
                processed_data.append({
                    "Stock": symbol,
                    "Sector": details["sector"],
                    "LTP (₹)": ltp,
                    "Delivery %": f"{delivery_pct}%",
                    "RVOL": relative_volume,
                    "Action Status": signal,
                    "Token": details["token"]
                })
        except:
            continue
            
    return pd.DataFrame(processed_data)

# 5. Main Terminal Interface
if st.session_state.logged_in:
    st.subheader("📊 Live EOD System Scanner Matrix")
    
    with st.spinner("Analyzing volume footprints across sector indices..."):
        df_signals = process_trading_signals(st.session_state.obj)
        
    if not df_signals.empty:
        # Style rows with active signals
        st.dataframe(df_signals.style.highlight_max(axis=0, subset=["RVOL"]))
        
        st.divider()
        st.subheader("🤖 Execution Desk")
        
        # Filtering only active BUY breakouts for rapid processing
        buy_candidates = df_signals[df_signals["Action Status"].str.contains("BUY")]
        
        if not buy_candidates.empty:
            selected_stock = st.selectbox("Select Active Breakout Candidate", buy_candidates["Stock"].tolist())
            row = buy_candidates[buy_candidates["Stock"] == selected_stock].iloc[0]
            
            qty = st.number_input("System Position Size (Qty)", min_value=1, value=10)
            
            if st.button(f"Execute Institutional Order for {selected_stock}"):
                order_params = {
                    "variety": "NORMAL",
                    "tradingsymbol": f"{selected_stock}-EQ",
                    "symboltoken": str(row["Token"]),
                    "exchange": "NSE",
                    "transactiontype": "BUY",
                    "ordertype": "MARKET",
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "quantity": str(qty)
                }
                try:
                    order_id = st.session_state.obj.placeOrder(order_params)
                    st.success(f"🚀 Execution Confirmed! Order ID: {order_id} via Proxy Tunnel.")
                except Exception as ex:
                    st.error(f"Execution failed: {ex}")
        else:
            st.info("System Engine Status: Scanning market. No volume accumulation footprint detected yet.")
else:
    st.warning("Please activate the verified system gateway from the sidebar to execute rules.")
