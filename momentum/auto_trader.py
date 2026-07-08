import math
from concurrent.futures import ThreadPoolExecutor
from logzero import logger

def place_buy_order(smart_api, symbol, token, qty):
    """
    Using the Official SDK structure for order placement.
    """
    try:
        # Standard parameters required by the SDK
        order_params = {
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
        
        # Calling the SDK method directly
        response = smart_api.placeOrder(order_params)
        
        # Validating as per SDK response schema
        if response and 'data' in response and 'orderid' in response['data']:
            return {"symbol": symbol, "success": True, "id": response['data']['orderid']}
        
        return {"symbol": symbol, "success": False, "error": str(response)}
    except Exception as e:
        return {"symbol": symbol, "success": False, "error": str(e)}

def run_auto_trade(df, smart_api, symbol_to_token, total_capital, already_bought, max_positions=3):
    capital_per_trade = total_capital / 4
    tasks = []
    
    # 1. Filter candidates (Fast)
    for _, row in df.iterrows():
        symbol = str(row["Symbol"]).strip()
        if symbol in already_bought or len(already_bought) + len(tasks) >= max_positions: continue
        
        try:
            ltp, prev_close = float(row["LTP"]), float(row["Prev Close"])
            if ((ltp - prev_close) / prev_close) * 100 >= 5.0:
                token = symbol_to_token.get(symbol)
                if token:
                    qty = max(math.floor(capital_per_trade / ltp), 1)
                    tasks.append((symbol, token, qty))
        except: continue

    # 2. Parallel Execution (Using ThreadPool for Speed)
    results = []
    if tasks:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(place_buy_order, smart_api, s, t, q) for s, t, q in tasks]
            for f in futures:
                res = f.result()
                if res["success"]:
                    already_bought.add(res["symbol"])
                    results.append(res)
                else:
                    logger.error(f"Order failed for {res['symbol']}: {res['error']}")
    return results
