import math
from logzero import logger
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# 1. Yeh function aapki main file dhoond rahi hai
def build_symbol_to_token(stocks_watchlist):
    return {name: token for name, token, kind in stocks_watchlist}

# 2. Yeh function bhi aapki main file dhoond rahi hai
def place_buy_order(smart_api, symbol, token, qty):
    params = {
        "variety": "NORMAL", "tradingsymbol": f"{symbol}-EQ",
        "symboltoken": str(token), "exchange": "NSE",
        "transactiontype": "BUY", "ordertype": "MARKET",
        "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
    }
    try:
        res = smart_api.placeOrder(params)
        if isinstance(res, str): return {"success": True, "order_id": res, "error": None}
        if isinstance(res, dict) and res.get("status") == True:
            return {"success": True, "order_id": res.get("data", {}).get("orderid"), "error": None}
        return {"success": False, "order_id": None, "error": "API returned empty or invalid response"}
    except Exception as e:
        return {"success": False, "order_id": None, "error": str(e)}

# 3. Yeh main function hai
def run_auto_trade(df, smart_api, symbol_to_token, total_capital, already_bought, max_positions=3):
    results = []
    capital_per_trade = total_capital / 4
    
    for _, row in df.iterrows():
        if len(already_bought) >= max_positions: break
        
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought: continue
        
        try:
            ltp = float(row["LTP"])
            prev_close = float(row["Prev Close"])
            move_pct = ((ltp - prev_close) / prev_close) * 100
            
            # Logic: 5% trigger
            if move_pct >= 5.0:
                token = symbol_to_token.get(symbol)
                if not token: continue
                
                qty = max(math.floor(capital_per_trade / ltp), 1)
                
                order = place_buy_order(smart_api, symbol, token, qty)
                
                if order["success"]:
                    already_bought.add(symbol)
                    results.append({"symbol": symbol, "success": True, "order_id": order["order_id"], "ltp": ltp})
                else:
                    logger.error(f"Failed {symbol}: {order['error']}")
        except Exception as e:
            logger.error(f"Error in {symbol}: {e}")
            
    return results
