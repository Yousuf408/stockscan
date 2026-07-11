# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER ALGOMOJO MODULE
# Place orders via AlgoMojo multi-broker unified API
# ═══════════════════════════════════════════════════════════════════════════════

import requests
import time

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: ALGOMOJO CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

ALGOMOJO_API_KEY = "b9a4a6c79371870b9b5d34dd47b8d26b"
ALGOMOJO_API_SECRET = "d50dbbac39c8aba0d0495205d3933c2b"
ALGOMOJO_API_URL = "https://amapi.algomojo.com/v1/PlaceOrder"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SINGLE ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────────────────────

def place_buy_order(symbol, quantity=1, broker="DHAN", exchange="NSE"):
    """
    Place a standard Delivery (CNC) Market BUY order via AlgoMojo.
    
    Supports multi-broker order placement through unified endpoint.
    Current implementation targets DHAN, but can support Angel One, 
    Shoonya, Finvasia, etc. via same API.
    
    Args:
        symbol (str): Stock symbol (e.g., "RELIANCE", "INFY")
        quantity (int): Order quantity (default 1)
        broker (str): Broker code (default "DHAN")
        exchange (str): Exchange (default "NSE")
    
    Returns:
        dict: {
            "success": bool,
            "order_id": str (if success),
            "error": str (if failed),
            "symbol": str
        }
    """
    payload = {
        "api_key": ALGOMOJO_API_KEY,
        "api_secret": ALGOMOJO_API_SECRET,
        "data": {
            "broker": str(broker).upper(),
            "strategy": "TV_Screener",
            "exchange": str(exchange).upper(),
            "symbol": str(symbol).upper(),
            "action": "BUY",
            "product": "CNC",              # Cash and Carry / Delivery
            "pricetype": "MARKET",         # Market order
            "quantity": str(quantity),
            "price": "0",                  # Market order ignores price
            "disclosed_quantity": "0",
            "trigger_price": "0",
            "amo": "NO",                   # After-market order: NO
            "splitorder": "NO",
            "split_quantity": "1"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(ALGOMOJO_API_URL, json=payload, headers=headers, timeout=10)
        
        # Guard rail for non-200 server HTTP status codes
        if response.status_code != 200:
            return {
                "success": False, 
                "error": f"HTTP Server Error: {response.status_code}", 
                "symbol": symbol
            }
            
        result = response.json()
        
        # Verify both common variants of success responses from AlgoMojo endpoints
        if result.get("status") == "success" or result.get("status") == "true":
            # Extract order ID securely across alternative response key conventions
            data_payload = result.get("data", {})
            order_id = data_payload.get("orderid") or data_payload.get("order_id") or "SUCCESS_NO_ID"
            return {"success": True, "order_id": order_id, "symbol": symbol}
            
        # Catch explicit API level validation errors (e.g., "invalid user API key")
        error_reason = result.get("error_msg") or result.get("message") or "Validation Rejected"
        return {"success": False, "error": error_reason, "symbol": symbol}
        
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": symbol}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: BULK ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────────────────────

def place_bulk_buy_orders(symbols_list, quantity_per_stock=1):
    """
    Place buy orders for multiple stocks sequentially (with rate limiting).
    
    Processes symbols one-by-one with 0.4s delay between requests to avoid
    API throttling / broker rate limits.
    
    Args:
        symbols_list (list): List of stock symbols (e.g., ["RELIANCE", "INFY"])
        quantity_per_stock (int): Quantity for each order (default 1)
    
    Returns:
        list: List of result dicts from place_buy_order()
              [
                {"success": True, "order_id": "...", "symbol": "RELIANCE"},
                {"success": False, "error": "...", "symbol": "INFY"},
                ...
              ]
    """
    results = []
    for symbol in symbols_list:
        if not symbol: 
            continue
        res = place_buy_order(symbol, quantity_per_stock)
        results.append(res)
        time.sleep(0.4)  # Rate limiter — prevent parallel thread request blocks
    return results

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: ORDER RESULT SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def summarize_order_results(results):
    """
    Summarize bulk order results for display.
    
    Args:
        results (list): List of result dicts from place_bulk_buy_orders()
    
    Returns:
        dict: {
            "total": int,
            "successful": int,
            "failed": int,
            "success_symbols": list,
            "failed_symbols": list,
            "errors": dict
        }
    """
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    summary = {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "success_symbols": [r["symbol"] for r in successful],
        "failed_symbols": [r["symbol"] for r in failed],
        "errors": {r["symbol"]: r.get("error", "Unknown error") for r in failed}
    }
    
    return summary
