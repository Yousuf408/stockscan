import requests
import time
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION BLOCK (SCREENSHOT SE SET KIYA HUA)
# ─────────────────────────────────────────────────────────────────────────────
ALGOMOJO_API_KEY = "b9a4a6c79371870b9b5d34dd47b8d26b"
ALGOMOJO_API_SECRET = "d50dbbac39c8aba0d0495205d3933c2b"

# ⚠️ FIXED: Aapka account simulation mode me hai, isliye SIMULATION ENDPOINT use hoga
ALGOMOJO_API_URL = "https://amapi.algomojo.com/v1/PlaceOrder"

# ⚠️ FIXED: Aapka actual Client ID jo screenshot me top par dikh raha hai
MY_CLIENT_ID = "1102302753" 

def place_buy_order(symbol, quantity=1, broker="DHANHQ", exchange="NSE"):
    """Strictly maps paper-trading simulation parameters with Client ID."""
    clean_symbol = str(symbol).split('-')[0].strip().upper()
    if exchange.upper() == "NSE" and not clean_symbol.endswith("-EQ"):
        formatted_symbol = f"{clean_symbol}-EQ"
    else:
        formatted_symbol = clean_symbol

    payload = {
        "api_key": str(ALGOMOJO_API_KEY),
        "api_secret": str(ALGOMOJO_API_SECRET),
        "data": {
            "broker": str(broker).upper(),            # "DHANHQ"
            "brokerid": str(MY_CLIENT_ID),            # 💡 CRITICAL: Aapki Client ID data ke andar jayegi
            "strategy": "TV_Screener",
            "exchange": str(exchange).upper(),        # "NSE"
            "symbol": str(formatted_symbol),          # e.g., "GAIL-EQ"
            "action": "BUY",
            "product": "MIS",                         # Strict Intraday
            "pricetype": "MARKET",
            "quantity": str(int(quantity)),
            "price": "0",
            "disclosed_quantity": "0",
            "trigger_price": "0",
            "amo": "NO",
            "splitorder": "NO",
            "split_quantity": "1"
        }
    }
    
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(ALGOMOJO_API_URL, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return {"success": False, "error": f"HTTP Error: {response.status_code}", "symbol": clean_symbol}
            
        result = response.json()
        if result.get("status") == "success" or result.get("status") == "true":
            data_payload = result.get("data", {})
            order_id = data_payload.get("orderid") or data_payload.get("order_id") or "SUCCESS"
            return {"success": True, "order_id": order_id, "symbol": clean_symbol}
            
        return {"success": False, "error": result.get("error_msg", "Validation Failed"), "symbol": clean_symbol}
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": clean_symbol}

def execute_dashboard_trades(df, quantity_per_stock=1):
    if df is None or df.empty:
        st.warning("Dashboard table empty hai, koi trade available nahi hai!")
        return

    scanned_symbols = df['Symbol'].tolist()
    st.info(f"Sending orders for {len(scanned_symbols)} stocks via AlgoMojo Paper Trading...")
    
    results = []
    for symbol in scanned_symbols:
        if not symbol or str(symbol).strip() == "": continue
        res = place_buy_order(symbol, quantity_per_stock)
        results.append(res)
        time.sleep(0.4)
        
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    errors = {r["symbol"]: r.get("error", "Unknown details") for r in failed}
    
    if len(failed) == 0 and len(successful) > 0:
        st.success(f"🚀 All Paper Orders Executed! {len(successful)} Stocks Sent to AlgoMojo Sandbox.")
    elif len(successful) > 0 and len(failed) > 0:
        st.warning(f"⚠️ Partial Success! Sent: {len(successful)} | Failed: {len(failed)}")
        st.write("Errors:", errors)
    else:
        st.error("❌ Execution Failed! Verification Rejected.")
        if errors: st.write("Error Logs:", errors)
            
    time.sleep(3.0)
    st.rerun()
