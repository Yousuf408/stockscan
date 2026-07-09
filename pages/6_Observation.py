"""
13_AutoTrader.py
Auto Trader — Reads today's signals from momentum_signal_times
and places buy orders via Angel One SmartAPI.
"""

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pyotp
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client
from SmartApi import SmartConnect

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
from angel_auth import API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET
from config import STOCKS_WATCHLIST

SUPABASE_URL = "https://pzdwmqjyuruxbfbkswib.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6ZHdtcWp5dXJ1eGJmYmtzd2liIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgyNTM3MTIsImV4cCI6MjA2MzgyOTcxMn0.ia1QfFMvQgqTRkOcODIZ3BKxPBKB0-kxCTkJ5sQXv5Y"

IST       = timezone(timedelta(hours=5, minutes=30))
PROXY_URL = "http://yousufshaikh420:cVTbJi6VVA@151.242.178.149:50100"

NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST}

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Auto Trader", page_icon="⚡", layout="wide")

st.markdown("""
<style>
.status-ok  { color: #00c851; font-weight: 700; }
.status-err { color: #ff4444; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────
# FRESH LOGIN — always fresh SmartConnect with proxy
# ─────────────────────────────────────────────────────────────
def do_angel_login():
    try:
        os.environ["HTTP_PROXY"]  = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL

        obj       = SmartConnect(api_key=API_KEY)
        obj.proxy = {"http": PROXY_URL, "https": PROXY_URL}
        totp      = pyotp.TOTP(TOTP_SECRET).now()
        data      = obj.generateSession(CLIENT_ID, PASSWORD, totp)

        os.environ.pop("HTTP_PROXY",  None)
        os.environ.pop("HTTPS_PROXY", None)

        if not data or data.get("status") == False:
            return None, f"Login failed: {data}"

        return obj, None

    except Exception as e:
        os.environ.pop("HTTP_PROXY",  None)
        os.environ.pop("HTTPS_PROXY", None)
        return None, str(e)

# ─────────────────────────────────────────────────────────────
# GET SMART API — login once per session
# ─────────────────────────────────────────────────────────────
def get_smart_api():
    # Already logged in this session?
    if "at_smart_api" in st.session_state and st.session_state["at_smart_api"]:
        return st.session_state["at_smart_api"], None

    obj, err = do_angel_login()
    if obj:
        st.session_state["at_smart_api"] = obj
    return obj, err

# ─────────────────────────────────────────────────────────────
# FETCH TODAY'S SIGNALS
# ─────────────────────────────────────────────────────────────
def fetch_today_signals():
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        resp = get_supabase().table("momentum_signal_times") \
            .select("stock, signal_time, signal_price, vol_ratio, vol_momentum, momentum, score, peak_ltp") \
            .eq("signal_date", today_str) \
            .order("signal_time", desc=False) \
            .execute()
        return resp.data or []
    except Exception as e:
        st.error(f"Supabase fetch error: {e}")
        return []

# ─────────────────────────────────────────────────────────────
# PLACE ORDER
# ─────────────────────────────────────────────────────────────
def place_buy_order(smart_api, symbol: str, qty: int) -> dict:
    token = NAME_TO_TOKEN.get(symbol)
    if not token:
        return {"status": "error", "msg": f"Token not found for {symbol}"}

    order_params = {
        "variety"         : "NORMAL",
        "tradingsymbol"   : f"{symbol}-EQ",
        "symboltoken"     : token,
        "transactiontype" : "BUY",
        "exchange"        : "NSE",
        "ordertype"       : "MARKET",
        "producttype"     : "INTRADAY",
        "duration"        : "DAY",
        "quantity"        : str(qty),
        "price"           : "0",
        "triggerprice"    : "0",
        "squareoff"       : "0",
        "stoploss"        : "0",
    }

    try:
        os.environ["HTTP_PROXY"]  = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL

        response = smart_api.placeOrder(order_params)

        os.environ.pop("HTTP_PROXY",  None)
        os.environ.pop("HTTPS_PROXY", None)

        # ── Debug: raw response dikhao ──
        st.caption(f"🔍 Raw response: `{response}`")

        # ── Extract order ID ──
        order_id = None
        if isinstance(response, dict):
            order_id = (response.get("data") or {}).get("orderid") \
                    or response.get("orderid")
        elif isinstance(response, str) and len(response) > 5:
            order_id = response  # SmartAPI kabhi kabhi direct string deta hai

        if order_id:
            return {"status": "success", "order_id": order_id}
        else:
            return {"status": "error", "msg": f"No order ID. Full response: {response}"}

    except Exception as e:
        os.environ.pop("HTTP_PROXY",  None)
        os.environ.pop("HTTPS_PROXY", None)
        return {"status": "error", "msg": str(e)}

# ─────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────
st.title("⚡ Auto Trader")
st.caption("Reads today's Momentum Scanner signals → Places Angel One orders")

# ── Angel One Connection ──
smart_api, err = get_smart_api()
if smart_api:
    st.success("🟢 Angel One Connected")
else:
    st.error(f"🔴 Angel One Not Connected — {err}")
    if st.button("🔁 Retry Login"):
        st.session_state.pop("at_smart_api", None)
        st.rerun()
    st.stop()

# ── Capital Settings ──
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    capital = st.number_input(
        "💰 Total Capital (₹)",
        min_value=10000, max_value=1000000,
        value=100000, step=5000, format="%d"
    )
with col2:
    splits    = st.selectbox("Split into", [2, 3, 4, 5], index=1)
    per_trade = int(capital / splits)
    st.metric("Per Trade", f"₹{per_trade:,}")
with col3:
    st.metric("Max Positions", splits)

# ── Signals ──
st.divider()
col_h, col_r = st.columns([4, 1])
with col_h:
    st.subheader("📊 Today's Signals")
with col_r:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

signals = fetch_today_signals()

if not signals:
    st.info("No signals today yet. MomentumScanner pe signal aane ka wait karo.")
    st.stop()

# ── Order Tracking ──
if "orders_placed" not in st.session_state:
    st.session_state["orders_placed"] = {}

# ── Live ticks ──
try:
    import angel_ws
    ticks = angel_ws.latest_ticks
except Exception:
    ticks = {}

# ── Signals Table ──
for sig in signals:
    stock        = sig["stock"]
    signal_price = sig.get("signal_price") or 0
    vol_ratio    = sig.get("vol_ratio") or 0
    vol_momentum = sig.get("vol_momentum") or "-"
    signal_time  = sig.get("signal_time") or "-"

    token = NAME_TO_TOKEN.get(stock)
    ltp   = ticks.get(token, {}).get("ltp", signal_price) if token else signal_price
    qty   = max(1, int(per_trade / ltp)) if ltp > 0 else 1
    move_pct = ((ltp - signal_price) / signal_price * 100) if signal_price > 0 else 0
    already_ordered = stock in st.session_state["orders_placed"]

    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5])

        with c1:
            st.markdown(f"**{stock}**")
            st.caption(f"Signal: {signal_time}")
        with c2:
            st.metric("Signal Price", f"₹{signal_price:.2f}")
        with c3:
            st.metric("LTP", f"₹{ltp:.2f}",
                      delta=f"{move_pct:+.2f}%",
                      delta_color="normal" if move_pct >= 0 else "inverse")
        with c4:
            st.metric("Vol Ratio", f"{vol_ratio:.1f}x")
            st.caption(vol_momentum)
        with c5:
            st.metric("Qty", f"{qty}")
            st.caption(f"~₹{qty * ltp:,.0f}")
        with c6:
            if already_ordered:
                oid = st.session_state["orders_placed"][stock]
                st.markdown(f'<span class="status-ok">✅ Placed<br><small>{oid}</small></span>',
                            unsafe_allow_html=True)
            else:
                if st.button(f"🚀 BUY {stock}", key=f"buy_{stock}", use_container_width=True):
                    with st.spinner(f"Placing order for {stock}..."):
                        result = place_buy_order(smart_api, stock, qty)
                    if result["status"] == "success":
                        st.session_state["orders_placed"][stock] = result["order_id"]
                        st.success(f"✅ Order placed! ID: {result['order_id']}")
                        st.rerun()
                    else:
                        st.error(f"❌ {result['msg']}")
        st.divider()

# ── Summary ──
if st.session_state["orders_placed"]:
    st.success(f"✅ {len(st.session_state['orders_placed'])} order(s) placed today")
    with st.expander("Order Log"):
        for stk, oid in st.session_state["orders_placed"].items():
            st.write(f"• **{stk}** → `{oid}`")
