import math
from datetime import datetime, timezone, timedelta
from logzero import logger

IST = timezone(timedelta(hours=5, minutes=30))

def build_symbol_to_token(stocks_watchlist: list) -> dict:
    return {name: token for name, token, kind in stocks_watchlist}

def get_2pct_trigger_stocks(df, already_bought: set) -> list:
    triggers = []
    for _, row in df.iterrows():
        symbol = row["Symbol"]
        if symbol in already_bought: continue
        ltp = float(row["LTP"])
        prev_close = float(row["Prev Close"])
        if prev_close <= 0: continue
        move_pct = ((ltp - prev_close) / prev_close) * 100
        if move_pct >= 2.0:
            triggers.append({
                "symbol": symbol, "ltp": ltp, "prev_close": prev_close,
                "move_pct": round(move_pct, 2),
            })
    return triggers

def calculate_qty(capital_per_trade: float, ltp: float) -> int:
    if ltp <= 0: return 0
    qty = math.floor(capital_per_trade / ltp)
    return max(qty, 1)

def place_buy_order(smart_api, symbol: str, token: str, qty: int) -> dict:
    """
    Robust Order Placement with API response validation.
    """
    try:
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
        
        # Call API
        res = smart_api.placeOrder(params)
        
        # Validation Logic
        order_id = None
        if isinstance(res, str):
            order_id = res
        elif isinstance(res, dict):
            # Check if API returned success=True
            if res.get("status") == True:
                order_id = res.get("data", {}).get("orderid")
            else:
                err_msg = res.get("message", "Unknown API error")
                return {"success": False, "order_id": None, "error": err_msg}
        
        if order_id:
            logger.info(f"Order Success: {symbol} | ID: {order_id}")
            return {"success": True, "order_id": order_id, "error": None}
        else:
            return {"success": False, "order_id": None, "error": f"API returned: {res}"}

    except Exception as e:
        logger.error(f"Order failed for {symbol}: {e}")
        return {"success": False, "order_id": None, "error": str(e)}

def run_auto_trade(df, smart_api, symbol_to_token: dict, total_capital: float, already_bought: set, max_positions: int = 3) -> list:
    results = []
    slots_left = max_positions - len(already_bought)
    if slots_left <= 0: return results

    capital_per_trade = total_capital / 4
    triggers = get_2pct_trigger_stocks(df, already_bought)

    for trigger in triggers[:slots_left]:
        symbol = trigger["symbol"]
        token = symbol_to_token.get(symbol)
        if not token: continue

        qty = calculate_qty(capital_per_trade, trigger["ltp"])
        if qty == 0: continue

        order_res = place_buy_order(smart_api, symbol, token, qty)
        
        result = {
            "symbol": symbol, "success": order_res["success"],
            "order_id": order_res["order_id"], "error": order_res["error"],
            "qty": qty, "ltp": trigger["ltp"], "move_pct": trigger["move_pct"],
            "time": datetime.now(IST).strftime("%H:%M:%S")
        }
        results.append(result)
        if order_res["success"]:
            already_bought.add(symbol)

    return results
