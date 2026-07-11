# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTATION MATCHED ALGOMOJO PIPELINE (100% STRICT PARAMETERS)
# ═══════════════════════════════════════════════════════════════════════════════

import requests
import time

# Official API Configuration
ALGOMOJO_API_KEY = "b9a4a6c79371870b9b5d34dd47b8d26b"
ALGOMOJO_API_SECRET = "d50dbbac39c8aba0d0495205d3933c2b"
ALGOMOJO_API_URL = "https://amapi.algomojo.com/v1/PlaceOrder"

def place_buy_order(symbol, quantity=1, broker="DHANHQ", exchange="NSE", product="MIS"):
    """
    Strictly follows official AlgoMojo REST API structure.
    All parameter fields in data are strictly typed as Strings.
    """
    
    # ─── SYMBOL COMPLIANCE CHECK ───
    # AlgoMojo standard requires "-EQ" suffix for NSE Cash/Equity orders (e.g. RELIANCE-EQ)
    clean_symbol = str(symbol).split('-')[0].strip().upper()
    if exchange.upper() == "NSE" and not clean_symbol.endswith("-EQ"):
        formatted_symbol = f"{clean_symbol}-EQ"
    else:
        formatted_symbol = clean_symbol

    # Official JSON structure exactly matching the API docs
    payload = {
        "api_key": str(ALGOMOJO_API_KEY),
        "api_secret": str(ALGOMOJO_API_SECRET),
        "data": {
            "broker": str(broker).upper(),            # "DHANHQ"
            "strategy": "TV_Screener",                # Custom identifier string
            "exchange": str(exchange).upper(),        # "NSE"
            "symbol": str(formatted_symbol),          # Checked formatted string (e.g. "GAIL-EQ")
            "action": "BUY",                          # "BUY" or "SELL"
            "product": str(product).upper(),          # "MIS" for Intraday, "CNC" for Delivery
            "pricetype": "MARKET",                    # "MARKET" execution
            "quantity": str(int(quantity)),           # CRITICAL: Must be string format
            "price": "0",                             # Market ignores price, but parameter string required
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
            
        # Parse exact failure message forwarded by the server
        error_reason = result.get("error_msg") or result.get("message") or "Parameters Validation Failed"
        return {"success": False, "error": error_reason, "symbol": clean_symbol}
        
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": clean_symbol}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DYNAMIC PIPELINE FOR DASHBOARD SCANNED DATA
# ─────────────────────────────────────────────────────────────────────────────

def place_bulk_buy_orders(symbols_list, quantity_per_stock=1, product="MIS"):
    """
    Takes live symbols from the dashboard table and maps them via the correct 
    documentation constraints.
    """
    results = []
    for symbol in symbols_list:
        if not symbol or str(symbol).strip() == "": 
            continue
            
        # Place single strict order
        res = place_buy_order(
            symbol=symbol, 
            quantity=quantity_per_stock, 
            broker="DHANHQ", 
            exchange="NSE", 
            product=product
        )
        results.append(res)
        
        # 0.4s safe pacing interval
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
