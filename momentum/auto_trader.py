import math
import time
from datetime import datetime, timezone, timedelta
from logzero import logger

# Essential constants for your existing project
IST = timezone(timedelta(hours=5, minutes=30))

# 1. Required by pages/8_MomentumScanner.py
def build_symbol_to_token(stocks_watchlist: list) -> dict:
    """Creates a mapping for quick lookup."""
    return {name: token for name, token, kind in stocks_watchlist}

# 2. Momentum Logic
def get_2pct_trigger_stocks(df, already_bought: set) -> list:
    triggers = []
    for _, row in df.iterrows():
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought: continue
        try:
            ltp = float(row["LTP"])
            prev_close = float(row["Prev Close"])
            if prev_close <= 0: continue
            
            # Logic: Using 5.0 as per your testing request
            move_pct = ((ltp - prev_close) / prev_close) * 100
            if move_pct >= 5.0:
                triggers.append({
                    "symbol": symbol, 
                    "ltp": ltp, 
                    "move_pct": round(move_pct, 2)
                })
        except Exception as e:
            continue
    return triggers

# 3. Calculation
def calculate_qty(capital_per_trade: float, ltp: float) -> int:
    if ltp <= 0: return 0
    return max(math.floor(capital_per_trade / ltp), 1)

# 4. Critical: API Order Execution
def place_buy_order(smart_api, symbol: str, token: str, qty: int) -> dict:
    params = {
        "variety": "NORMAL",
        "tradingsymbol": f"{symbol}-EQ",
        "symboltoken": str(token),
        "exchange": "NSE",
        "transactiontype": "BUY",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "quantity": str(qty),
    }

    try:
        # Request
        response = smart_api.placeOrder(params)
        
        # Diagnostic Check
        if response is None:
            logger.error(f"CRITICAL: API returned None for {symbol}")
            return {"success": False, "order_id": None, "error": "API returned empty response"}
        
        # Response parsing (Matching your old structure)
        if isinstance(response, str):
            return {"success": True, "order_id": response, "error": None}
        elif isinstance(response, dict):
            if response.get("status") == True:
                return {"success": True, "order_id": response.get("data", {}).get("orderid"), "error": None}
            else:
                return {"success": False, "order_id": None, "error": response.get("message", "API Error")}
        
        return {"success": False, "order_id": None, "error": "Unknown API Response"}

    except Exception as e:
        logger.error(f"Execution Error for {symbol}: {str(e)}")
        return {"success": False, "order_id": None, "error": str(e)}

# 5. Main Execution Loop (Required by your Streamlit page)
def run_auto_trade(df, smart_api, symbol_to_token: dict, total_capital: float, already_bought: set, max_positions: int = 3) -> list:
    results = []
    if len(already_bought) >= max_positions:
        return results

    capital_per_trade = total_capital / 4
    triggers = get_2pct_trigger_stocks(df, already_bought)
    
    for trigger in triggers:
        if len(already_bought) >= max_positions: break
        
        symbol = trigger["symbol"]
        token = symbol_to_token.get(symbol)
        
        if not token: continue
        
        qty = calculate_qty(capital_per_trade, trigger["ltp"])
        
        # Execute
        order_res = place_buy_order(smart_api, symbol, token, qty)
        
        results.append({
            "symbol": symbol,
            "success": order_res["success"],
            "order_id": order_res["order_id"],
            "error": order_res["error"],
            "ltp": trigger["ltp"],
            "time": datetime.now(IST).strftime("%H:%M:%S")
        })
        
        if order_res["success"]:
            already_bought.add(symbol)
            
    return results
