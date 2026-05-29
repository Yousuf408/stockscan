import streamlit as st
import pyotp
import requests
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import sys, os
sys.path.append(os.path.dirname(__file__))
from styles import apply_styles, sidebar_brand, page_header

st.set_page_config(
    page_title="TradeSentry",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

apply_styles()
sidebar_brand()
page_header("Live Market Dashboard")

start_btn = st.button("🚀 Connect To Live Market")
data_placeholder = st.empty()

# 1. Helper function to fetch the complete master token list from Angel One
@st.cache_data
def get_token_map():
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    response = requests.get(url)
    data = response.json()
    # Create a fast lookup dictionary matching trading symbol to token ID
    # e.g., {"SBIN-EQ": "3045", "RELIANCE-EQ": "2885"}
    token_map = {item['symbol']: item['token'] for item in data if item['exch_seg'] == 'NSE'}
    return token_map

def on_data(wsapp, message):
    with data_placeholder.container():
        st.subheader("📈 Live Watchlist Feed")
        st.json(message)

def on_open(wsapp):
    # 4. Use the dynamic tokens fetched into session state
    dynamic_tokens = st.session_state.get('watchlist_tokens', [])
    
    if dynamic_tokens:
        token_list = [{"exchangeType": 1, "tokens": dynamic_tokens}]
        wsapp.subscribe("screener_01", 3, token_list)
    else:
        st.error("No tokens found to subscribe to.")

if start_btn:
    st.info("🔄 Connecting to Angel One...")
    try:
        api_key     = st.secrets["API_KEY"]
        username    = st.secrets["CLIENT_CODE"]
        password    = st.secrets["PASSWORD"]
        totp_secret = st.secrets["TOTP_SECRET"]
        
        smartApi = SmartConnect(api_key=api_key)
        current_totp = pyotp.TOTP(totp_secret).now()
        session_data = smartApi.generateSession(username, password, current_totp)
        
        if session_data['status']:
            st.success("✅ Login Successful!")
            auth_token = session_data['data']['jwtToken']
            feed_token = smartApi.getfeedToken()
            
            # 2. Fetch your actual Angel One Watchlist
            # Documentation Note: smartApi.getWatchList() retrieves your profile's watchlists
            watchlist_response = smartApi.getWatchList()
            
            watchlist_tokens = []
            if watchlist_response.get('status') and watchlist_response.get('data'):
                # Load the global token map to convert symbols into IDs
                token_map = get_token_map()
                
                # Loop through the stocks present in your Angel One watchlist
                # Note: Adjust ['scrip'] or keys based on your specific watchlist API structure
                for item in watchlist_response['data']:
                    symbol = item.get('tradingsymbol') or item.get('symbol')
                    
                    # Match symbol to find its numeric token ID
                    if symbol in token_map:
                        watchlist_tokens.append(token_map[symbol])
            
            # If your profile watchlist is empty, fall back to a couple of safety stocks
            if not watchlist_tokens:
                st.warning("⚠️ Watchlist empty or could not map symbols. Using defaults.")
                watchlist_tokens = ["3045", "2885"] 
                
            # Store tokens in session state so on_open can read them
            st.session_state['watchlist_tokens'] = watchlist_tokens
            st.write(f"Tracking {len(watchlist_tokens)} stocks from your watchlist!")

            # 3. Start the continuous live connection
            sws = SmartWebSocketV2(auth_token, api_key, username, feed_token)
            sws.on_open = on_open
            sws.on_data = on_data
            sws.connect()
            
        else:
            st.error(f"❌ Login Failed: {session_data['message']}")
    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")