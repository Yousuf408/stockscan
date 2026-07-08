import math
import requests
from datetime import datetime, timezone, timedelta
from logzero import logger

# Configuration
IST = timezone(timedelta(hours=5, minutes=30))

# ─── HELPER: Build Token Map ────────────────────────────────
def build_symbol_to_token(stocks_watchlist: list) -> dict:
    return {name: token for name, token, kind in stocks_watchlist}

# ─── CORE: Momentum Filter ──────────────────────────────────
def get_2pct_trigger_stocks(df, already_bought: set) -> list:
    triggers = []
    for _, row in df.iterrows():
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought: continue
        try:
            ltp = float(row["LTP"])
            prev_close = float(row["Prev Close"])
            if prev_close <= 0: continue
            move_pct = ((ltp - prev_close) / prev_close) * 100
            if move_pct >= 5.0:
                triggers.append({"symbol": symbol, "ltp": ltp, "move_pct": round(move_pct, 2)})
        except Exception: continue
    return triggers

# ─── CORE: Quantity Calculation ─────────────────────────────
def calculate_qty(capital_per_trade: float, ltp: float) -> int:
    if ltp <= 0: return 0
    qty = math.floor(capital_per_trade / ltp)
    return max(qty, 1)

# ─── CORE: Order Execution (Senior Dev Grade) ──────────────
def place_buy_order(smart_api, symbol: str, token: str, qty: int) -> dict:
    """
    Robust order placement with transport layer diagnostics.
    """
    # 1. Validate inputs before calling API
    if not token or token == "None":
        err = f"Invalid Token for {symbol}: {token}"
        logger.error(err)
        return {"success": False, "order_id": None, "error": err}

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
        logger.info(f"DEBUG: Executing order for {symbol} with token {token}")
        
        # 2. Attempt API Call
        response = smart_api.placeOrder(params)
        
        # 3. Diagnostic Logging
        if response is None:
            logger.error(f"CRITICAL: API returned None (Empty Response) for {symbol}. Check Proxy/Session.")
            return {"success": False, "order_id": None, "error": "API returned empty response"}
        
        logger.info(f"DEBUG: Raw API Response: {response}")

        # 4. Success Parsing
        if isinstance(response, str): # Direct ID
            return {"success": True, "order_id": response, "error": None}
        
        if isinstance(response, dict):
            if response.get("status") == True:
                oid = response.get("data", {}).get("orderid")
                return {"success": True, "order_id": oid, "error": None}
            else:
                return {"success": False, "order_id": None, "error": response.get("message", "Unknown API error")}

    except Exception as e:
        logger.error(f"Exception for {symbol}: {str(e)}")
        return {"success": False, "order_id": None, "error": str(e)}

# ─── MAIN: Pipeline ─────────────────────────────────────────
def run_auto_trade(df, smart_api, symbol_to_token: dict, total_capital: float, already_bought: set, max_positions: int = 3) -> list:
    results = []
    slots_left = max_positions - len(already_bought)
    if slots_left <= 0: return results

    capital_per_trade = total_capital / 4
    triggers = get_2pct_trigger_stocks(df, already_bought)

    for trigger in triggers[:slots_left]:
        symbol = trigger["symbol"]
        token = symbol_to_token.get(symbol)
        
        # Order Execution
        qty = calculate_qty(capital_per_trade, trigger["ltp"])
        order_res = place_buy_order(smart_api, symbol, token, qty)
        
        results.append({
            "symbol": symbol, 
            "success": order_res["success"],
            "order_id": order_res["order_id"],
            "error": order_res["error"],
            "qty": qty,
            "ltp": trigger["ltp"],
            "time": datetime.now(IST).strftime("%H:%M:%S")
        })
        
        if order_res["success"]:
            already_bought.add(symbol)
            logger.info(f"Successfully placed order for {symbol}")

    return results
