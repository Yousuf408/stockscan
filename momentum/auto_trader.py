import math
import requests
from datetime import datetime, timezone, timedelta
from logzero import logger

IST = timezone(timedelta(hours=5, minutes=30))

# ─── 1. Enhanced Symbol Mapping ────────────────────────────
def build_symbol_to_token(stocks_watchlist: list) -> dict:
    return {name: token for name, token, kind in stocks_watchlist}

# ─── 2. Trigger Logic (Maintains Momentum Strategy) ────────
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
            if move_pct >= 2.0:
                triggers.append({"symbol": symbol, "ltp": ltp, "move_pct": round(move_pct, 2)})
        except: continue
    return triggers

# ─── 3. Professional Order Placement (Debug & Validation) ──
def place_buy_order(smart_api, symbol: str, token: str, qty: int) -> dict:
    """
    Highly robust order placement with API response sanity check.
    """
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
        # Step A: Attempt the order
        response = smart_api.placeOrder(params)
        
        # Step B: Log the raw response for debugging
        logger.info(f"DEBUG: Params sent: {params}")
        logger.info(f"DEBUG: Response received: {response}")

        # Step C: Parse response safely
        # Sometimes API returns just the ID, sometimes a dict
        if not response:
            return {"success": False, "order_id": None, "error": "API returned empty response"}
        
        if isinstance(response, str): # Raw ID
            return {"success": True, "order_id": response, "error": None}
        
        if isinstance(response, dict):
            if response.get("status") == True:
                oid = response.get("data", {}).get("orderid")
                return {"success": True, "order_id": oid, "error": None}
            else:
                return {"success": False, "order_id": None, "error": response.get("message", "Unknown API error")}

    except Exception as e:
        logger.error(f"Critical Exception for {symbol}: {str(e)}")
        return {"success": False, "order_id": None, "error": str(e)}

# ─── 4. Main Auto-Trade Loop ────────────────────────────────
def run_auto_trade(df, smart_api, symbol_to_token: dict, total_capital: float, already_bought: set, max_positions: int = 3) -> list:
    results = []
    slots_left = max_positions - len(already_bought)
    if slots_left <= 0: return results

    capital_per_trade = total_capital / 4
    triggers = get_2pct_trigger_stocks(df, already_bought)

    for trigger in triggers[:slots_left]:
        symbol = trigger["symbol"]
        token = symbol_to_token.get(symbol)
        
        if not token:
            logger.warning(f"Skipping {symbol}: Token missing in map")
            continue

        qty = math.floor(capital_per_trade / trigger["ltp"])
        if qty < 1: qty = 1 

        # Place Order
        order_res = place_buy_order(smart_api, symbol, token, qty)
        
        result = {
            "symbol": symbol, 
            "success": order_res["success"],
            "order_id": order_res["order_id"],
            "error": order_res["error"],
            "qty": qty,
            "ltp": trigger["ltp"],
            "time": datetime.now(IST).strftime("%H:%M:%S")
        }
        results.append(result)
        
        if order_res["success"]:
            already_bought.add(symbol)
            logger.info(f"Trade Success: {symbol} ID: {order_res['order_id']}")

    return results
