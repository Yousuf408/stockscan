"""
mStock Trading Module
All mStock functions - Auth, Orders, Margin, Symbols
Use: from tv_screener.mstock import *
"""
import requests
import json
import csv
import io
import pyotp
from typing import Tuple, Dict, Any

# ============================================================================
# CREDENTIALS (FOR TESTING ONLY - Remove before production!)
# ============================================================================
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_CLIENT_CODE = "MA1764118"
MSTOCK_PASSWORD = "P@ssw0rd"
MSTOCK_TOTP_SECRET = "CRIJTB7OAMTK7L5UB27PILGM6RHHS6FV"

# ============================================================================
# CONSTANTS
# ============================================================================
MSTOCK_API_BASE = "https://api.mstock.trade/openapi/typeb"
INSTRUMENT_MASTER_URL = f"{MSTOCK_API_BASE}/instruments/OpenAPIScripMaster"

# ============================================================================
# HEADERS & UTILITIES
# ============================================================================
def get_headers(api_key: str = None, jwt_token: str = None) -> Dict[str, str]:
    """Returns mStock API headers with optional authentication"""
    headers = {
        "X-Mirae-Version": "1",
        "Content-Type": "application/json"
    }
    if api_key and jwt_token:
        headers["X-PrivateKey"] = api_key
        headers["Authorization"] = f"Bearer {jwt_token}"
    return headers

# ============================================================================
# AUTO-LOGIN (For Testing - uses hardcoded credentials)
# ============================================================================
def auto_login() -> Tuple[bool, str, str]:
    """
    Auto-login using hardcoded credentials
    
    Returns: (success, api_key, jwt_token)
    WARNING: Only for testing! Remove before production!
    """
    if not all([MSTOCK_API_KEY, MSTOCK_CLIENT_CODE, MSTOCK_PASSWORD, MSTOCK_TOTP_SECRET]):
        return False, "", "Credentials not set in mstock.py"
    
    success, jwt = login_with_totp(MSTOCK_CLIENT_CODE, MSTOCK_PASSWORD, MSTOCK_TOTP_SECRET)
    
    if success:
        return True, MSTOCK_API_KEY, jwt
    else:
        return False, "", jwt  # jwt contains error message

# ============================================================================
# AUTHENTICATION
# ============================================================================
def login_with_totp(client_code: str, password: str, totp_secret: str) -> Tuple[bool, Any]:
    """
    Two-step TOTP login:
    1. Login with clientcode/password → get refreshToken
    2. Verify TOTP → get jwtToken
    
    Returns: (success, jwt_token_or_error_msg)
    """
    try:
        # Step 1: Initial login
        login_payload = {
            "clientcode": client_code,
            "password": password,
            "totp": "",
            "state": ""
        }
        login_response = requests.post(
            f"{MSTOCK_API_BASE}/connect/login",
            json=login_payload,
            headers=get_headers(),
            timeout=10
        )
        login_data = login_response.json()
        
        if login_data.get("status") != "true":
            return False, login_data.get("message", "Login failed")
        
        refresh_token = login_data.get("data", {}).get("refreshToken")
        if not refresh_token:
            return False, "No refreshToken received"
        
        # Step 2: Generate TOTP and verify
        totp = pyotp.TOTP(totp_secret)
        current_totp = totp.now()
        
        totp_payload = {
            "refreshToken": refresh_token,
            "totp": current_totp
        }
        totp_response = requests.post(
            f"{MSTOCK_API_BASE}/session/verifytotp",
            json=totp_payload,
            headers=get_headers(),
            timeout=10
        )
        totp_data = totp_response.json()
        
        if totp_data.get("status") != "true":
            return False, totp_data.get("message", "TOTP verification failed")
        
        jwt_token = totp_data.get("data", {}).get("jwtToken")
        return True, jwt_token
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# SYMBOL MASTER (Instrument List)
# ============================================================================
def fetch_instrument_master(api_key: str, jwt_token: str) -> Tuple[bool, Any]:
    """
    Fetch instrument master CSV from mStock
    Returns symbol→token mapping
    
    Returns: (success, {symbol: token} dict or error_msg)
    """
    try:
        response = requests.get(
            INSTRUMENT_MASTER_URL,
            headers=get_headers(api_key, jwt_token),
            timeout=30
        )
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        
        # Parse CSV
        csv_data = response.text
        symbol_map = {}
        
        reader = csv.DictReader(io.StringIO(csv_data))
        for row in reader:
            token = row.get("ExchangeTokens", "").strip()
            symbol = row.get("TradingSymbol", "").strip()
            if token and symbol:
                symbol_map[symbol] = token
        
        if not symbol_map:
            return False, "No symbols parsed from master"
        
        return True, symbol_map
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# FUND SUMMARY (Account Balance & Leverage)
# ============================================================================
def fetch_fund_summary(api_key: str, jwt_token: str) -> Tuple[bool, Any]:
    """
    Fetch fund summary with available balance, margins, leverage
    
    Returns: (success, funds_dict or error_msg)
    """
    try:
        response = requests.put(
            f"{MSTOCK_API_BASE}/user/fundsummary",
            headers=get_headers(api_key, jwt_token),
            timeout=10
        )
        data = response.json()
        
        if data.get("status") != True:
            return False, data.get("message", "Fund summary failed")
        
        funds = data.get("data", [{}])[0]
        return True, funds
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# MARGIN CALCULATION
# ============================================================================
def calculate_order_margin(
    api_key: str,
    jwt_token: str,
    symbol_token: str,
    qty: int,
    price: float,
    side: str = "BUY"
) -> Tuple[bool, Any]:
    """
    Calculate required margin for an order
    
    Args:
        api_key: mStock API key
        jwt_token: JWT token from login
        symbol_token: Token from instrument master
        qty: Order quantity
        price: Order price (0 for market)
        side: BUY or SELL
    
    Returns: (success, margin_amount or error_msg)
    """
    try:
        payload = {
            "exchange": "NSE",
            "symboltoken": str(symbol_token),
            "producttype": "INTRADAY",
            "transactiontype": side,
            "ordertype": "MARKET",
            "quantity": str(qty),
            "price": str(price)
        }
        
        response = requests.post(
            f"{MSTOCK_API_BASE}/orders/calculatemargin",
            json=payload,
            headers=get_headers(api_key, jwt_token),
            timeout=10
        )
        data = response.json()
        
        if data.get("status") == "true":
            margin = float(data.get("data", {}).get("margin", 0))
            return True, margin
        else:
            return False, data.get("message", "Margin calc failed")
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# MAXIMUM QUANTITY CALCULATOR
# ============================================================================
def calculate_max_qty(
    api_key: str,
    jwt_token: str,
    symbol_token: str,
    price: float,
    available_balance: float,
    side: str = "BUY"
) -> int:
    """
    Calculate max quantity that fits within available balance (binary search)
    
    Args:
        api_key: mStock API key
        jwt_token: JWT token
        symbol_token: Token from master
        price: Current stock price
        available_balance: Available margin balance
        side: BUY or SELL
    
    Returns: Max viable quantity
    """
    try:
        if price <= 0:
            return 1
        
        low, high = 1, int(available_balance / price)
        max_viable_qty = 1
        
        while low <= high:
            mid = (low + high) // 2
            success, margin = calculate_order_margin(
                api_key, jwt_token, symbol_token, mid, price, side
            )
            
            if success and margin <= available_balance:
                max_viable_qty = mid
                low = mid + 1
            else:
                high = mid - 1
        
        return max_viable_qty
    
    except Exception:
        return 1

# ============================================================================
# ORDER PLACEMENT
# ============================================================================
def place_order(
    api_key: str,
    jwt_token: str,
    symbol: str,
    symbol_token: str,
    qty: int,
    price: float,
    side: str,
    order_type: str = "MARKET"
) -> Tuple[bool, str]:
    """
    Place order on mStock
    
    Args:
        api_key: mStock API key
        jwt_token: JWT token
        symbol: Trading symbol (e.g., "ACC-EQ")
        symbol_token: Token from master
        qty: Order quantity
        price: Order price (0 for market)
        side: BUY or SELL
        order_type: MARKET or LIMIT (auto-detected if price=0)
    
    Returns: (success, order_id_or_error_msg)
    """
    try:
        # Auto-detect order type based on price
        if price == 0:
            order_type = "MARKET"
        else:
            order_type = "LIMIT"
        
        payload = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": str(symbol_token),
            "exchange": "NSE",
            "transactiontype": side,
            "ordertype": order_type,
            "quantity": str(qty),
            "producttype": "INTRADAY",
            "price": str(price) if order_type == "LIMIT" else "0",
            "triggerprice": "0",
            "squareoff": "0",
            "stoploss": "0",
            "trailingStopLoss": "",
            "disclosedquantity": "",
            "duration": "DAY",
            "ordertag": ""
        }
        
        response = requests.post(
            f"{MSTOCK_API_BASE}/orders/regular",
            json=payload,
            headers=get_headers(api_key, jwt_token),
            timeout=10
        )
        data = response.json()
        
        if data.get("status") == "true":
            order_id = data.get("data", {}).get("orderid", "N/A")
            return True, f"Order placed! ID: {order_id}"
        else:
            return False, data.get("message", "Order failed")
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# QUICK ORDER (All-in-one)
# ============================================================================
def quick_order(
    api_key: str,
    jwt_token: str,
    symbol: str,
    qty: int,
    price: float,
    side: str,
    symbol_token_map: Dict[str, str]
) -> Tuple[bool, str]:
    """
    One-function order placement with auto token lookup
    
    Args:
        api_key: mStock API key
        jwt_token: JWT token
        symbol: Trading symbol (e.g., "ACC-EQ")
        qty: Quantity
        price: Price (0 for market)
        side: BUY or SELL
        symbol_token_map: {symbol: token} dict from fetch_instrument_master
    
    Returns: (success, message)
    """
    try:
        symbol_token = symbol_token_map.get(symbol)
        if not symbol_token:
            return False, f"Symbol '{symbol}' not found in master"
        
        return place_order(api_key, jwt_token, symbol, symbol_token, qty, price, side)
    
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================================
# BATCH ORDER PLACEMENT (for multiple signals)
# ============================================================================
def place_batch_orders(
    api_key: str,
    jwt_token: str,
    orders_list: list,
    symbol_token_map: Dict[str, str]
) -> Dict[str, Any]:
    """
    Place multiple orders in sequence
    
    Args:
        orders_list: [
            {"symbol": "ACC-EQ", "qty": 5, "price": 0, "side": "BUY"},
            {"symbol": "TCS-EQ", "qty": 3, "price": 0, "side": "BUY"},
        ]
        symbol_token_map: {symbol: token} dict
    
    Returns: {
        "successful": [order_ids],
        "failed": [(symbol, error_msg)],
        "total": count
    }
    """
    results = {
        "successful": [],
        "failed": [],
        "total": len(orders_list)
    }
    
    for order in orders_list:
        symbol = order.get("symbol")
        qty = order.get("qty", 1)
        price = order.get("price", 0)
        side = order.get("side", "BUY")
        
        success, msg = quick_order(
            api_key, jwt_token, symbol, qty, price, side, symbol_token_map
        )
        
        if success:
            results["successful"].append(symbol)
        else:
            results["failed"].append((symbol, msg))
    
    return results
