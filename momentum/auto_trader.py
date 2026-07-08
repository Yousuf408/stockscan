import math
from logzero import logger

def place_buy_order(smart_api, symbol, token, qty):
    """
    Ekdum minimal aur fast execution.
    """
    params = {
        "variety": "NORMAL", "tradingsymbol": f"{symbol}-EQ",
        "symboltoken": str(token), "exchange": "NSE",
        "transactiontype": "BUY", "ordertype": "MARKET",
        "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
    }

    try:
        # Time-critical call
        res = smart_api.placeOrder(params)
        
        # Immediate check (Faster)
        if res and (isinstance(res, str) or res.get("status") == True):
            order_id = res if isinstance(res, str) else res.get("data", {}).get("orderid")
            return {"success": True, "order_id": order_id}
        
        # Agar failed toh fast error return karo
        return {"success": False, "error": "Rejected or Empty"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def run_auto_trade(df, smart_api, symbol_to_token, total_capital, already_bought, max_positions=3):
    results = []
    # Fast filtering
    capital_per_trade = total_capital / 4
    
    # 2% or 5% logic (Jo aapne set kiya hai)
    for _, row in df.iterrows():
        if len(already_bought) >= max_positions: break
        
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought: continue
        
        ltp = float(row["LTP"])
        prev_close = float(row["Prev Close"])
        
        # Momentum check
        if ((ltp - prev_close) / prev_close) * 100 >= 5.0:
            token = symbol_to_token.get(symbol)
            if not token: continue
            
            qty = max(math.floor(capital_per_trade / ltp), 1)
            
            # Execution
            order = place_buy_order(smart_api, symbol, token, qty)
            if order["success"]:
                already_bought.add(symbol)
                results.append(order)
                
    return results
