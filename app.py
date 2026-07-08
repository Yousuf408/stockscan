import streamlit as st
import os
import time
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
    "Stock": [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "LT", "ITC", "BHARTIARTL", "AXISBANK",
        "KOTAKBANK", "MARUTI", "HINDUNILVR", "TATAMOTORS", "SUNPHARMA",
        "BAJFINANCE", "ASIANPAINT", "WIPRO", "HCLTECH", "TITAN"
    ],
    "Token": [
        "2885", "11536", "1594", "1333", "4963",
        "3045", "11483", "1660", "10604", "5900",
        "1922", "1856", "1394", "3456", "15083",
        "317", "236", "11532", "7229", "35006"
    ]
}
df_stocks = pd.DataFrame(stocks_data)

# ─── Helper: fetch & display order book ───────────────────────────────────────
def show_order_book(container, obj):
    """Fetch orderBook from Angel One API and render inside `container`."""
    try:
        resp = obj.orderBook()
        if resp.get("status") and resp.get("data"):
            orders_df = pd.DataFrame(resp["data"])

            # columns that are always present; pick what's available
            want_cols = ["orderid", "tradingsymbol", "transactiontype",
                         "quantity", "price", "orderstatus", "updatetime"]
            cols = [c for c in want_cols if c in orders_df.columns]

            display_df = orders_df[cols].copy()

            # Rename for readability
            rename_map = {
                "orderid": "Order ID",
                "tradingsymbol": "Symbol",
                "transactiontype": "Side",
                "quantity": "Qty",
                "price": "Price",
                "orderstatus": "Status",
                "updatetime": "Time"
            }
            display_df.rename(columns={k: v for k, v in rename_map.items() if k in cols}, inplace=True)

            container.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            container.info("No orders found in order book.")
    except Exception as e:
        container.error(f"Order book fetch error: {e}")


# ─── Session state init ────────────────────────────────────────────────────────
if "obj" not in st.session_state:
    st.session_state.obj = None
if "last_order_id" not in st.session_state:
    st.session_state.last_order_id = None

# ─── Sidebar: Login ────────────────────────────────────────────────────────────
st.sidebar.header("🔑 Login Credentials")
api_key  = st.sidebar.text_input("API Key",   value="QFectj5C",                    type="password")
client_id = st.sidebar.text_input("Client ID", value="IIRA29771")
password  = st.sidebar.text_input("Password",                                       type="password")
totp_key  = st.sidebar.text_input("TOTP Key",  value="JFTG3DYADWLYSW6FC6RVV4THWM", type="password")

if st.sidebar.button("Login"):
    with st.spinner("Authenticating..."):
        try:
            obj = SmartConnect(api_key=api_key)
            obj.proxy = {"http": PROXY_URL, "https": PROXY_URL}
            totp = pyotp.TOTP(totp_key.replace(" ", ""))
            data = obj.generateSession(client_id, password, totp.now())
            if data.get("status"):
                st.session_state.obj = obj
                st.sidebar.success("✅ Logged In!")
            else:
                st.sidebar.error(f"Login Failed: {data.get('message')}")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# ─── Sidebar: Live Order Book ──────────────────────────────────────────────────
if st.session_state.obj:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Order Book")

    ob_container = st.sidebar.empty()

    if st.sidebar.button("🔄 Refresh Orders"):
        show_order_book(ob_container, st.session_state.obj)

# ─── Main: Title ───────────────────────────────────────────────────────────────
st.title("🚀 Real-Time Autonomous Trader")

# ─── Main: Trading UI ─────────────────────────────────────────────────────────
if st.session_state.obj:
    st.subheader("Select from Watchlist")

    selected_stock = st.selectbox("Choose Stock", df_stocks["Stock"].tolist())
    token_id = df_stocks[df_stocks["Stock"] == selected_stock]["Token"].values[0]
    st.write(f"Selected: **{selected_stock}** | Token: **{token_id}**")

    col1, col2 = st.columns(2)
    qty    = col1.number_input("Quantity", min_value=1, value=1)
    action = col2.radio("Action", ["BUY", "SELL"])

    if st.button(f"Place {action} Order"):
        try:
            params = {
                "variety":         "NORMAL",
                "tradingsymbol":   f"{selected_stock}-EQ",
                "symboltoken":     str(token_id),
                "exchange":        "NSE",
                "transactiontype": action,
                "ordertype":       "MARKET",
                "producttype":     "INTRADAY",
                "duration":        "DAY",
                "quantity":        str(qty)
            }
            order_id = st.session_state.obj.placeOrder(params)
            st.session_state.last_order_id = order_id
            st.success(f"🎉 Order Placed! ID: {order_id}")

            # ── Auto-fetch order book after placement ──
            time.sleep(1)   # 1 sec: give Angel One time to register the order
            st.markdown("#### 📋 Latest Orders")
            ob_main = st.empty()
            show_order_book(ob_main, st.session_state.obj)

        except Exception as e:
            st.error(f"Execution Error: {e}")

    # ── Standalone order book viewer in main area ──────────────────────────────
    st.markdown("---")
    col_title, col_btn = st.columns([4, 1])
    col_title.subheader("📊 Order Book (Manual Refresh)")
    
    ob_main_manual = st.empty()

    if col_btn.button("🔄 Refresh", key="main_refresh"):
        show_order_book(ob_main_manual, st.session_state.obj)

else:
    st.info("Pehle Login karo.")
