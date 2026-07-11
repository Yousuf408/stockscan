# ═══════════════════════════════════════════════════════════════════════════════
# STRICT INTRADAY (MIS) ALGOMOJO PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

import requests
import time

# Official API Configuration
ALGOMOJO_API_KEY = "b9a4a6c79371870b9b5d34dd47b8d26b"
ALGOMOJO_API_SECRET = "d50dbbac39c8aba0d0495205d3933c2b"
ALGOMOJO_API_URL = "https://amapi.algomojo.com/v1/PlaceOrder"

def place_buy_order(symbol, quantity=1, broker="DHANHQ", exchange="NSE"):
    """
    Strictly follows official AlgoMojo REST API structure for INTRADAY (MIS) orders.
    All parameter values are properly cast as strings.
    """
    
    # ─── SYMBOL COMPLIANCE CHECK ───
    # AlgoMojo standard requires "-EQ" suffix for NSE Cash/Equity orders (e.g. RELIANCE-EQ)
    clean_symbol = str(symbol).split('-')[0].strip().upper()
    if exchange.upper() == "NSE" and not clean_symbol.endswith("-EQ"):
        formatted_symbol = f"{clean_symbol}-EQ"
    else:
        formatted_symbol = clean_symbol

    # Official JSON structure EXACTLY matching documentation names but optimized for Intraday
    payload = {
        "api_key": str(ALGOMOJO_API_KEY),
        "api_secret": str(ALGOMOJO_API_SECRET),
        "data": {
            "broker": str(broker).upper(),            # "DHANHQ"
            "strategy": "TV_Screener",                # Identifier
            "exchange": str(exchange).upper(),        # "NSE"
            "symbol": str(formatted_symbol),          # e.g., "GAIL-EQ"
            "action": "BUY",                          # "BUY" or "SELL"
            
            # ─── FIXED FOR INTRADAY EXECUTION ───
            "product": "MIS",                         # Explicitly set to MIS for Intraday margin
            
            "pricetype": "MARKET",                    # MARKET execution
            "quantity": str(int(quantity)),           # Strict string required
            "price": "0",                             # Market ignores price, but string needed
            "disclosed_quantity": "0",                # Required field as string
            "trigger_price": "0",                     # Required field as string
            "amo": "NO",                              # "NO" for normal market hours
            "splitorder": "NO",                       # "NO"
            "split_quantity": "1"                     # Required field as string
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(ALGOMOJO_API_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {
                "success": False, 
                "error": f"HTTP Gateway Error: {response.status_code}", 
                "symbol": clean_symbol
            }
            
        result = response.json()
        
        # Verify success criteria exactly per response docs
        if result.get("status") == "success" or result.get("status") == "true":
            data_payload = result.get("data", {})
            order_id = data_payload.get("orderid") or data_payload.get("order_id") or "SUCCESS"
            return {"success": True, "order_id": order_id, "symbol": clean_symbol}
            
        error_reason = result.get("error_msg") or result.get("message") or "Parameters Validation Failed"
        return {"success": False, "error": error_reason, "symbol": clean_symbol}
        
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": clean_symbol}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DYNAMIC PIPELINE FOR DASHBOARD SCANNED DATA
# ─────────────────────────────────────────────────────────────────────────────

def place_bulk_buy_orders(symbols_list, quantity_per_stock=1):
    """
    Takes live symbols from the dashboard table and processes them for Intraday.
    """
    results = []
    for symbol in symbols_list:
        if not symbol or str(symbol).strip() == "": 
            continue
            
        res = place_buy_order(
            symbol=symbol, 
            quantity=quantity_per_stock, 
            broker="DHANHQ", 
            exchange="NSE"
        )
        results.append(res)
        
        # 0.4s safe pacing interval to avoid rate throttling
        time.sleep(0.4)  
    return results

def summarize_order_results(results):
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    return {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "success_symbols": [r["symbol"] for r in successful],
        "failed_symbols": [r["symbol"] for r in failed],
        "errors": {r["symbol"]: r.get("error", "Unknown details") for r in failed}
    }
