"""
momentum/auto_trader.py

Auto-buy logic for MomentumScanner.
- Capital ÷ 4 = per trade budget
- Trigger: stock moves 2% above previous close
- Max 3 simultaneous positions (1 slot buffer)
- Uses same SmartConnect session from angel_auth
- No SL logic (Phase 2 me add karenge)
"""

import math
from datetime import datetime, timezone, timedelta
from logzero import logger

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Stock token map (same as config.py STOCKS_WATCHLIST) ────
# auto_trader ko token chahiye placeOrder ke liye
# renderer/backend se Symbol milta hai — yahan reverse lookup hai
def build_symbol_to_token(stocks_watchlist: list) -> dict:
    """
    STOCKS_WATCHLIST format: [(name, token, kind), ...]
    Returns: {"RELIANCE": "2885", "TCS": "11536", ...}
    """
    return {name: token for name, token, kind in stocks_watchlist}


# ─── CORE: Check which stocks crossed 2% above prev close ────
def get_2pct_trigger_stocks(df, already_bought: set) -> list:
    """
    df: momentum scan result DataFrame (already filtered, has Symbol, LTP, Prev Close)
    already_bought: set of symbols already purchased today
    
    Returns list of dicts: [{symbol, ltp, prev_close, move_pct, qty_hint}, ...]
    """
    triggers = []

    for _, row in df.iterrows():
        symbol = row["Symbol"]

        # Skip already bought
        if symbol in already_bought:
            continue

        ltp        = float(row["LTP"])
        prev_close = float(row["Prev Close"])

        if prev_close <= 0:
            continue

        move_pct = ((ltp - prev_close) / prev_close) * 100

        if move_pct >= 2.0:
            triggers.append({
                "symbol"    : symbol,
                "ltp"       : ltp,
                "prev_close": prev_close,
                "move_pct"  : round(move_pct, 2),
            })

    return triggers


# ─── CORE: Calculate quantity from capital ────────────────────
def calculate_qty(capital_per_trade: float, ltp: float) -> int:
    """
    capital_per_trade = total_capital / 4
    qty = floor(capital_per_trade / ltp)
    Minimum 1 share.
    """
    if ltp <= 0:
        return 0
    qty = math.floor(capital_per_trade / ltp)
    return max(qty, 1)


# ─── CORE: Place market buy order ────────────────────────────
def place_buy_order(smart_api, symbol: str, token: str, qty: int) -> dict:
    """
    Places MARKET INTRADAY BUY order via Angel One SmartAPI.
    Returns: {"success": True/False, "order_id": ..., "error": ...}
    """
    try:
        params = {
            "variety"        : "NORMAL",
            "tradingsymbol"  : f"{symbol}-EQ",
            "symboltoken"    : str(token),
            "exchange"       : "NSE",
            "transactiontype": "BUY",
            "ordertype"      : "MARKET",
            "producttype"    : "INTRADAY",
            "duration"       : "DAY",
            "quantity"       : str(qty),
        }
        order_res = smart_api.placeOrder(params)

        # placeOrder returns order_id string directly (working code confirmed)
        # Handle both string and dict response just in case
        if isinstance(order_res, dict):
            order_id = order_res.get("data", {}).get("orderid") or order_res.get("orderid")
            success  = bool(order_res.get("status")) and bool(order_id)
        else:
            order_id = order_res  # direct string ID like "0708face4beaAO"
            success  = bool(order_id)

        if success:
            logger.info(f"Order placed: {symbol} x{qty} | ID: {order_id}")
            return {"success": True, "order_id": order_id, "error": None}
        else:
            err = f"No order ID returned: {order_res}"
            logger.error(err)
            return {"success": False, "order_id": None, "error": err}

    except Exception as e:
        logger.error(f"Order failed for {symbol}: {e}")
        return {"success": False, "order_id": None, "error": str(e)}


# ─── MAIN: Run auto-trade for triggered stocks ────────────────
def run_auto_trade(
    df,
    smart_api,
    symbol_to_token : dict,
    total_capital   : float,
    already_bought  : set,        # pass by reference — will be mutated
    max_positions   : int = 3,
) -> list:
    """
    Full auto-trade pipeline:
    1. Check 2% triggers
    2. Check position limit (max 3)
    3. Calculate qty (capital ÷ 4)
    4. Place order
    5. Update already_bought set
    
    Returns list of order results for UI display.
    """
    results = []

    # How many more positions can we take?
    slots_left = max_positions - len(already_bought)
    if slots_left <= 0:
        logger.info("Max positions reached. No new orders.")
        return results

    capital_per_trade = total_capital / 4

    # Get stocks that crossed 2%
    triggers = get_2pct_trigger_stocks(df, already_bought)

    if not triggers:
        return results

    # Only take as many as slots allow
    for trigger in triggers[:slots_left]:
        symbol = trigger["symbol"]
        ltp    = trigger["ltp"]

        token = symbol_to_token.get(symbol)
        if not token:
            logger.warning(f"Token not found for {symbol} — skipping")
            results.append({
                "symbol"  : symbol,
                "success" : False,
                "error"   : "Token not found",
                "qty"     : 0,
                "ltp"     : ltp,
                "move_pct": trigger["move_pct"],
            })
            continue

        qty = calculate_qty(capital_per_trade, ltp)
        if qty == 0:
            results.append({
                "symbol"  : symbol,
                "success" : False,
                "error"   : "Qty came to 0 — LTP too high for capital",
                "qty"     : 0,
                "ltp"     : ltp,
                "move_pct": trigger["move_pct"],
            })
            continue

        order_result = place_buy_order(smart_api, symbol, token, qty)

        result = {
            "symbol"   : symbol,
            "success"  : order_result["success"],
            "order_id" : order_result["order_id"],
            "error"    : order_result["error"],
            "qty"      : qty,
            "ltp"      : ltp,
            "move_pct" : trigger["move_pct"],
            "capital_used": round(qty * ltp, 2),
            "time"     : datetime.now(IST).strftime("%H:%M:%S"),
        }
        results.append(result)

        # Mark as bought if order succeeded
        if order_result["success"]:
            already_bought.add(symbol)

    return results
