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
from angel_auth import API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET, PROXY_URL
from config import STOCKS_WATCHLIST

SUPABASE_URL = "https://pzdwmqjyuruxbfbkswib.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6ZHdtcWp5dXJ1eGJmYmtzd2liIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgyNTM3MTIsImV4cCI6MjA2MzgyOTcxMn0.ia1QfFMvQgqTRkOcODIZ3BKxPBKB0-kxCTkJ5sQXv5Y"

IST          = timezone(timedelta(hours=5, minutes=30))
PROXIES      = {"http": PROXY_URL, "https": PROXY_URL}

# Token lookup from config
NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST}

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Auto Trader", page_icon="⚡", layout="wide")

st.markdown("""
<style>
body { background: #0e1117; }
.metric-card {
    background: #1a1d26; border-radius: 10px;
    padding: 14px 20px; margin-bottom: 8px;
    border-left: 3px solid #00d4aa;
}
.buy-btn button {
    background: #00c851 !important; color: white !important;
    font-weight: 700 !important; border-radius: 6px !important;
}
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
# ANGEL ONE SESSION — reuse from session_state
# ─────────────────────────────────────────────────────────────
def get_smart_api():
    """
    Reuse existing angel_auth session if available.
    If not, create fresh SmartConnect with proxy.
    """
    # Reuse existing session from MomentumScanner
    if "angel_auth" in st.session_state and st.session_state["angel_auth"]:
        auth = st.session_state["angel_auth"]
        if "smart_api" in auth and auth["smart_api"]:
            return auth["smart_api"], None

    # Fresh login with proxy
    try:
        obj = SmartConnect(api_key=API_KEY)

        # ✅ Proxy sirf SmartAPI ke liye — os.environ mat set karo
        session = requests.Session()
        session.proxies.update(PROXIES)
        obj.reqsession = session

        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)

        if not data or data.get("status") == False:
            return None, f"Login failed: {data}"

        # Save to session_state for reuse
        if "angel_auth" not in st.session_state:
            st.session_state["angel_auth"] = {}
        st.session_state["angel_auth"]["smart_api"] = obj

        return obj, None

    except Exception as e:
        return None, str(e)

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

    try:
        order_params = {
            "variety"         : "NORMAL",
            "tradingsymbol"   : symbol,
            "symboltoken"     : token,
            "transactiontype" : "BUY",
            "exchange"        : "NSE",
            "ordertype"       : "MARKET",   # Speed ke liye MARKET
            "producttype"     : "INTRADAY",
            "duration"        : "DAY",
            "quantity"        : str(qty),
            "price"           : "0",
            "triggerprice"    : "0",
            "squareoff"       : "0",
            "stoploss"        : "0",
        }
        response = smart_api.placeOrder(order_params)

        # Response string ya dict dono handle karo
        if isinstance(response, dict):
            order_id = response.get("data", {}).get("orderid") or response.get("orderid")
        else:
            order_id = str(response) if response else None

        if order_id:
            return {"status": "success", "order_id": order_id}
        else:
            return {"status": "error", "msg": f"No order ID returned: {response}"}

    except Exception as e:
        return {"status": "error", "msg": str(e)}

# ─────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────
st.title("⚡ Auto Trader")
st.caption("Reads today's Momentum Scanner signals → Places Angel One orders")

# ── Angel One Connection Status ──
smart_api, err = get_smart_api()
if smart_api:
    st.success("🟢 Angel One Connected")
else:
    st.error(f"🔴 Angel One Not Connected — {err}")
    st.stop()

# ── Capital Settings ──
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    capital = st.number_input(
        "💰 Total Capital (₹)",
        min_value=10000, max_value=1000000,
        value=100000, step=5000,
        format="%d"
    )
with col2:
    splits   = st.selectbox("Split into", [2, 3, 4, 5], index=1)
    per_trade = int(capital / splits)
    st.metric("Per Trade", f"₹{per_trade:,}")
with col3:
    st.metric("Max Positions", splits)

# ── Fetch Signals ──
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
    st.session_state["orders_placed"] = {}   # {stock: order_id}

# ── Live ticks for current LTP ──
try:
    import angel_ws
    ticks = angel_ws.latest_ticks
except Exception:
    ticks = {}

NAME_TO_TOKEN_LOOKUP = NAME_TO_TOKEN  # already built above

# ── Signals Table ──
for sig in signals:
    stock        = sig["stock"]
    signal_price = sig.get("signal_price") or 0
    vol_ratio    = sig.get("vol_ratio") or 0
    vol_momentum = sig.get("vol_momentum") or "-"
    momentum     = sig.get("momentum") or "-"
    score        = sig.get("score") or 0
    signal_time  = sig.get("signal_time") or "-"
    peak_ltp     = sig.get("peak_ltp") or signal_price

    # Current LTP from WebSocket
    token = NAME_TO_TOKEN_LOOKUP.get(stock)
    if token and token in ticks:
        ltp = ticks[token].get("ltp", signal_price)
    else:
        ltp = signal_price

    # Qty calculation
    qty = max(1, int(per_trade / ltp)) if ltp > 0 else 1

    # Move since signal
    move_pct = ((ltp - signal_price) / signal_price * 100) if signal_price > 0 else 0

    # Already ordered?
    already_ordered = stock in st.session_state["orders_placed"]

    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5])

        with c1:
            st.markdown(f"**{stock}**")
            st.caption(f"Signal: {signal_time}")

        with c2:
            st.metric("Signal Price", f"₹{signal_price:.2f}")

        with c3:
            color = "normal" if move_pct >= 0 else "inverse"
            st.metric("LTP", f"₹{ltp:.2f}", delta=f"{move_pct:+.2f}%", delta_color=color)

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
total_placed = len(st.session_state["orders_placed"])
if total_placed > 0:
    st.success(f"✅ {total_placed} order(s) placed today")
    with st.expander("Order Log"):
        for stk, oid in st.session_state["orders_placed"].items():
            st.write(f"• **{stk}** → Order ID: `{oid}`")
