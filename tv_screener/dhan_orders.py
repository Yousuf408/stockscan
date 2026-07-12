# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — DHAN ORDERS MODULE
#
# Direct order placement via DhanHQ Order API — bypasses AlgoMojo entirely
# for faster execution (one less network hop: App -> Dhan, not App ->
# AlgoMojo -> Broker).
#
# Reuses auth (TOTP-based access token) and security_id lookup from
# quantity_calculator.py — does NOT duplicate that logic.
#
# IMPORTANT: DhanHQ requires a whitelisted Static IP for Order Placement
# APIs specifically (not required for Margin Calculator / Fund Limit).
# All requests here are routed through the same static-IP proxy already
# used for Angel One (151.242.178.149:50100).
# ═══════════════════════════════════════════════════════════════════════════════

import requests
import uuid

from .quantity_calculator import get_access_token, get_security_id_map, DHAN_CLIENT_ID

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PROXY CONFIGURATION (Static IP requirement for Order APIs)
# ─────────────────────────────────────────────────────────────────────────────

DHAN_PROXY = "http://151.242.178.149:50100"
PROXIES = {
    "http": DHAN_PROXY,
    "https": DHAN_PROXY,
}

DHAN_ORDER_URL = "https://api.dhan.co/v2/orders"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PLACE ORDER (Direct Dhan — no AlgoMojo)
# ─────────────────────────────────────────────────────────────────────────────

def place_dhan_order(symbol, quantity, transaction_type="BUY", product_type="INTRADAY"):
    """
    Place a market order directly via DhanHQ Order API (routed through the
    static-IP proxy, since Dhan requires IP whitelisting for order placement).

    Args:
        symbol (str): Stock symbol (e.g., "RELIANCE") — looked up internally
                      to Dhan's security_id via quantity_calculator's map
        quantity (int): Number of shares to buy
        transaction_type (str): "BUY" or "SELL" (default "BUY")
        product_type (str): "INTRADAY" for MIS (leveraged), "CNC" for delivery

    Returns:
        dict: {
            "success": bool,
            "order_id": str (if success),
            "error": str (if failed),
            "symbol": str
        }
    """
    symbol_upper = str(symbol).strip().upper()

    # Step 1: Resolve symbol -> security_id (reuses quantity_calculator's cached map)
    security_map = get_security_id_map()
    security_id = security_map.get(symbol_upper)
    if not security_id:
        return {"success": False, "error": "Symbol not found in Dhan instrument master", "symbol": symbol}

    if not quantity or quantity <= 0:
        return {"success": False, "error": "Invalid quantity", "symbol": symbol}

    # Step 2: Get valid access token (auto-refreshes via TOTP if expired)
    access_token = get_access_token()
    if not access_token:
        return {"success": False, "error": "Could not obtain access token (check TOTP/PIN)", "symbol": symbol}

    # Step 3: Place the order
    payload = {
        "dhanClientId": str(DHAN_CLIENT_ID),
        "correlationId": str(uuid.uuid4())[:20],
        "transactionType": transaction_type,
        "exchangeSegment": "NSE_EQ",
        "productType": product_type,
        "orderType": "MARKET",
        "validity": "DAY",
        "securityId": str(security_id),
        "quantity": str(int(quantity)),
        "disclosedQuantity": "",
        "price": "0",
        "triggerPrice": "",
        "afterMarketOrder": False,
        "amoTime": "",
        "boProfitValue": "",
        "boStopLossValue": "",
    }
    headers = {
        "Content-Type": "application/json",
        "access-token": access_token,
    }

    try:
        response = requests.post(
            DHAN_ORDER_URL, json=payload, headers=headers, proxies=PROXIES, timeout=10
        )

        if response.status_code == 401:
            # Token expired mid-flight — refresh once and retry
            access_token = get_access_token(force_refresh=True)
            if not access_token:
                return {"success": False, "error": "401 Unauthorized, token refresh also failed", "symbol": symbol}
            headers["access-token"] = access_token
            response = requests.post(
                DHAN_ORDER_URL, json=payload, headers=headers, proxies=PROXIES, timeout=10
            )

        if response.status_code not in (200, 201, 202):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}", "symbol": symbol}

        data = response.json()
        order_id = data.get("orderId")
        if not order_id:
            return {"success": False, "error": f"No orderId in response: {data}", "symbol": symbol}

        return {"success": True, "order_id": order_id, "symbol": symbol}

    except Exception as e:
        return {"success": False, "error": f"Exception: {str(e)}", "symbol": symbol}
