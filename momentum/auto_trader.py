import math
from datetime import datetime, timezone, timedelta
from logzero import logger

IST = timezone(timedelta(hours=5, minutes=30))

# ─── 1. Build Token Map ────────────────────────────────────
def build_symbol_to_token(stocks_watchlist: list) -> dict:
    return {name: token for name, token, kind in stocks_watchlist}

# ─── 2. Trigger Logic (2% Momentum Strategy) ──────────────
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
            
            # Logic: Only trigger if >= 2.0%
            if move_pct >= 2.0:
                triggers.append({
                    "symbol": symbol, 
                    "ltp": ltp, 
                    "move_pct": round(move_pct, 2)
                })
        except Exception as e:
            logger.error(f"Error parsing row for {row.get('Symbol', 'Unknown')}: {e}")
            continue
    return triggers

# ─── 3. Quantity Logic ────────────────────────────────────
def calculate_qty(capital_per_trade: float, ltp: float) -> int:
    if ltp <= 0: return 0
    return max(math.floor(capital_per_trade / ltp), 1)

# ─── 4. Robust Order Execution ────────────────────────────
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
        logger.info(f"Attempting to buy {symbol} | Token: {token} | Qty: {qty}")
        res = smart_api.placeOrder(params)
        
        # Diagnostic Check for Empty Response
        if res is None:
            logger.error(f"CRITICAL: API returned None (Empty Response) for {symbol}. Network/Proxy Issue.")
            return {"success": False, "order_id": None, "error": "API returned empty response"}
        
        # Parse Response
        if isinstance(res, str):
            return {"success": True, "order_id": res, "error": None}
        elif isinstance(res, dict):
            if res.get("status") == True:
                return {"success": True, "order_id": res.get("data", {}).get("orderid"), "error": None}
            else:
                err = res.get("message", "Unknown API error")
                logger.error(f"API Rejected {symbol}: {err}")
                return {"success": False, "order_id": None, "error": err}
        
        return {"success": False, "order_id": None, "error": f"Unexpected Response: {res}"}

    except Exception as e:
        logger.error(f"System Exception for {symbol}: {str(e)}")
        return {"success": False, "order_id": None, "error": str(e)}

# ─── 5. Main Auto-Trade Loop ──────────────────────────────
def run_auto_trade(df, smart_api, symbol_to_token: dict, total_capital: float, already_bought: set, max_positions: int = 3) -> list:
    results = []
    
    # Check slots available
    if len(already_bought) >= max_positions:
        return results

    capital_per_trade = total_capital / 4
    triggers = get_2pct_trigger_stocks(df, already_bought)
    
    logger.info(f"Scan found {len(triggers)} potential momentum stocks.")

    for trigger in triggers:
        # Stop if max positions reached
        if len(already_bought) >= max_positions: break
        
        symbol = trigger["symbol"]
        token = symbol_to_token.get(symbol)
        
        if not token:
            logger.warning(f"Skipping {symbol}: Token mapping missing.")
            continue

        qty = calculate_qty(capital_per_trade, trigger["ltp"])
        
        # Execution
        order_res = place_buy_order(smart_api, symbol, token, qty)
        
        results.append({
            "symbol": symbol,
            "success": order_res["success"],
            "order_id": order_res["order_id"],
            "error": order_res["error"],
            "ltp": trigger["ltp"],
            "move_pct": trigger["move_pct"]
        })
        
        if order_res["success"]:
            already_bought.add(symbol)
            logger.info(f"Order Success: {symbol} at {trigger['ltp']}")
        else:
            logger.error(f"Order Failed: {symbol} -> {order_res['error']}")

    return results
