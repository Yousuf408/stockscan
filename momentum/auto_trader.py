import math
from logzero import logger
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def build_symbol_to_token(stocks_watchlist):
    return {name: token for name, token, kind in stocks_watchlist}

def run_auto_trade(df, smart_api, symbol_to_token, total_capital, already_bought, max_positions=3):
    results = []
    capital_per_trade = total_capital / 4
    
    # 1. Scanner Logic
    for _, row in df.iterrows():
        if len(already_bought) >= max_positions: break
        
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought: continue
        
        try:
            ltp = float(row["LTP"])
            prev_close = float(row["Prev Close"])
            move_pct = ((ltp - prev_close) / prev_close) * 100
            
            if move_pct >= 5.0: # Testing 5%
                token = symbol_to_token.get(symbol)
                if not token: continue
                
                qty = max(math.floor(capital_per_trade / ltp), 1)
                
                # 2. Direct Execution (Same as your working app.py)
                params = {
                    "variety": "NORMAL", "tradingsymbol": f"{symbol}-EQ",
                    "symboltoken": str(token), "exchange": "NSE",
                    "transactiontype": "BUY", "ordertype": "MARKET",
                    "producttype": "INTRADAY", "duration": "DAY", "quantity": str(qty)
                }
                
                res = smart_api.placeOrder(params)
                
                # 3. Simple ID validation
                order_id = None
                if isinstance(res, str): order_id = res
                elif isinstance(res, dict) and res.get("status") == True:
                    order_id = res.get("data", {}).get("orderid")
                
                if order_id:
                    already_bought.add(symbol)
                    results.append({"symbol": symbol, "success": True, "order_id": order_id, "ltp": ltp})
                else:
                    logger.error(f"Failed to place order for {symbol}")
        except Exception as e:
            logger.error(f"Error in {symbol}: {e}")
            
    return results
