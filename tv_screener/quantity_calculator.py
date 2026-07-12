# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — QUANTITY CALCULATOR MODULE
#
# Calculates how many shares of each stock can be bought given the user's
# total capital, split into N parts (default 4), using DhanHQ's live
# Margin Calculator API (real intraday margin per stock, not a hardcoded
# 5x assumption — some stocks have different leverage e.g. 2x).
#
# Flow:
#   1. Load NSE-equity symbol -> securityId map (from Dhan's public
#      instrument master CSV, cached for 24h)
#   2. For each stock in the table, call Margin Calculator API with
#      quantity=1, productType=INTRADAY to get margin required per share
#   3. max_quantity = floor(capital_per_part / margin_per_share)
#
# DEBUG: every failure reason is tracked in st.session_state['qty_calc_debug']
# so issues (bad token, symbol not found, API error) are visible, not silent.
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import requests
import io
import math
import pyotp
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DHAN CREDENTIALS
#
# DHAN_ACCESS_TOKEN is NO LONGER used directly — access tokens are now
# auto-generated daily via TOTP (see get_access_token() below), since Dhan
# access tokens expire every 24 hours and manual regeneration is impractical.
# ─────────────────────────────────────────────────────────────────────────────

DHAN_CLIENT_ID = "1102302753"
DHAN_PIN = "YOUR_DHAN_PIN"                  # 4/6-digit trading PIN
DHAN_TOTP_SECRET = "THWBRO5KI5N7ACJUNY7W3JUDKL4M2LML"  # From Profile > DhanHQ Trading APIs > Set-up TOTP

DHAN_MARGIN_CALCULATOR_URL = "https://api.dhan.co/v2/margincalculator"
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
DHAN_TOKEN_GENERATE_URL = "https://auth.dhan.co/app/generateAccessToken"
DHAN_FUND_LIMIT_URL = "https://api.dhan.co/v2/fundlimit"

# Token generation MUST come from the same whitelisted static IP used for
# order placement — Dhan's own guidance: "if IPs has been added post
# [token generation], regenerate access token" — so route this call
# through the same proxy as dhan_orders.py to keep the source IP consistent.
DHAN_PROXY_HOST = "151.242.178.149"
DHAN_PROXY_PORT = "50100"
DHAN_PROXY_USERNAME = "yousufshaikh420"
DHAN_PROXY_PASSWORD = "cVTbJi6VVA"
DHAN_PROXY_URL = f"http://{DHAN_PROXY_USERNAME}:{DHAN_PROXY_PASSWORD}@{DHAN_PROXY_HOST}:{DHAN_PROXY_PORT}"
DHAN_PROXIES = {"http": DHAN_PROXY_URL, "https": DHAN_PROXY_URL}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: AUTO ACCESS TOKEN GENERATION (via TOTP — no manual daily login)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_totp_code():
    """Generate the current 6-digit TOTP code from the stored secret."""
    return pyotp.TOTP(DHAN_TOTP_SECRET).now()


def get_access_token(force_refresh=False):
    """
    Return a valid DhanHQ access token, auto-generating a fresh one via
    TOTP if the cached token is missing or expired.

    Cached in session_state so it's reused across reruns/fragment refreshes
    within the day — not regenerated on every single call (avoids hitting
    Dhan's token-generation rate limits).

    Args:
        force_refresh (bool): If True, ignore cache and generate a new token

    Returns:
        str: Valid access token, or None if generation failed
             (check get_qty_calc_debug()['token_error'] for the reason)
    """
    now = datetime.now()
    cached = st.session_state.get('dhan_access_token_data')

    if not force_refresh and cached and cached.get('expiry') and cached['expiry'] > now:
        return cached['token']

    try:
        totp_code = _generate_totp_code()
        params = {
            "dhanClientId": DHAN_CLIENT_ID,
            "pin": DHAN_PIN,
            "totp": totp_code,
        }
        response = requests.post(DHAN_TOKEN_GENERATE_URL, params=params, proxies=DHAN_PROXIES, timeout=10)

        if response.status_code != 200:
            _log_debug('token_error', f"HTTP {response.status_code}: {response.text[:200]}")
            return None

        data = response.json()
        token = data.get("accessToken")
        if not token:
            _log_debug('token_error', f"No accessToken in response: {data}")
            return None

        expiry_str = data.get("expiryTime")
        try:
            expiry = datetime.fromisoformat(expiry_str) if expiry_str else now + timedelta(hours=23)
        except Exception:
            expiry = now + timedelta(hours=23)

        # Keep a 5-minute safety buffer before actual expiry
        st.session_state['dhan_access_token_data'] = {
            "token": token,
            "expiry": expiry - timedelta(minutes=5),
        }
        _log_debug('token_error', None)
        _log_debug('token_last_generated', now.strftime("%Y-%m-%d %H:%M:%S"))
        return token
    except Exception as e:
        _log_debug('token_error', f"Exception: {str(e)}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DEBUG TRACKING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _init_debug():
    if 'qty_calc_debug' not in st.session_state:
        st.session_state['qty_calc_debug'] = {
            'security_map_size': 0,
            'security_map_columns_found': None,
            'security_map_error': None,
            'token_error': None,
            'token_last_generated': None,
            'per_symbol': {},  # symbol -> {"security_id": ..., "margin_error": ...}
        }

def _log_debug(key, value):
    _init_debug()
    st.session_state['qty_calc_debug'][key] = value

def _log_symbol_debug(symbol, **kwargs):
    _init_debug()
    if symbol not in st.session_state['qty_calc_debug']['per_symbol']:
        st.session_state['qty_calc_debug']['per_symbol'][symbol] = {}
    st.session_state['qty_calc_debug']['per_symbol'][symbol].update(kwargs)

def get_qty_calc_debug():
    """Return the debug info dict for display in a UI expander."""
    _init_debug()
    return st.session_state['qty_calc_debug']

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FETCH AVAILABLE BALANCE DIRECTLY FROM BROKER (Fund Limit API)
# ─────────────────────────────────────────────────────────────────────────────

def get_available_balance():
    """
    Fetch current available trading balance directly from DhanHQ account
    (Fund Limit API) — so the user doesn't have to manually type capital.

    Returns:
        tuple: (balance: float or None, error_message: str or None)
    """
    access_token = get_access_token()
    if not access_token:
        return None, "Could not obtain access token (check TOTP/PIN/client_id)"

    try:
        headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
        }
        response = requests.get(DHAN_FUND_LIMIT_URL, headers=headers, timeout=10)

        if response.status_code == 401:
            access_token = get_access_token(force_refresh=True)
            if not access_token:
                return None, "401 Unauthorized, and token refresh also failed"
            headers["access-token"] = access_token
            response = requests.get(DHAN_FUND_LIMIT_URL, headers=headers, timeout=10)

        if response.status_code != 200:
            return None, f"HTTP {response.status_code}: {response.text[:200]}"

        data = response.json()
        # Note: Dhan's API has a typo in this field name — "availabelBalance"
        balance = data.get("availabelBalance", data.get("availableBalance"))
        if balance is None:
            return None, f"No balance field in response: {data}"
        return float(balance), None
    except Exception as e:
        return None, f"Exception: {str(e)}"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SYMBOL -> SECURITY ID MAP (Dhan's public instrument master)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_security_id_map():
    """
    Download Dhan's public instrument master CSV and build a
    {trading_symbol: security_id} map for NSE Equity instruments.

    Cached for 24 hours — the instrument master rarely changes intraday,
    so no need to re-download on every rerun.

    Returns:
        dict: {symbol: security_id_str}, or {} if download/parse failed
              (check get_qty_calc_debug() for the failure reason)
    """
    try:
        response = requests.get(DHAN_SCRIP_MASTER_URL, timeout=30)
        if response.status_code != 200:
            _log_debug('security_map_error', f"CSV download failed: HTTP {response.status_code}")
            return {}

        df = pd.read_csv(io.StringIO(response.text), low_memory=False)

        # Column names can vary slightly across Dhan CSV versions — find them
        # defensively. Dhan's actual columns are SYMBOL_NAME (equity trading
        # symbol), DISPLAY_NAME (full name), UNDERLYING_SYMBOL (for F&O).
        # Priority: SYMBOL_NAME first (matches TV screener symbols directly).
        symbol_col = next(
            (c for c in df.columns if c.upper() in ("SYMBOL_NAME", "TRADING_SYMBOL", "UNDERLYING_SYMBOL")),
            None
        )
        security_id_col = next((c for c in df.columns if "SECURITY_ID" in c.upper()), None)
        exch_col = next((c for c in df.columns if c.upper() in ("SEM_EXM_EXCH_ID", "EXCH_ID")), None)
        segment_col = next((c for c in df.columns if c.upper() == "SEGMENT"), None)
        instrument_col = next((c for c in df.columns if "INSTRUMENT" in c.upper() and "EXCH" not in c.upper() and "UNDERLYING" not in c.upper()), None)

        _log_debug('security_map_columns_found', {
            'all_columns': list(df.columns),
            'symbol_col': symbol_col,
            'security_id_col': security_id_col,
            'exch_col': exch_col,
            'segment_col': segment_col,
            'instrument_col': instrument_col,
        })

        if not symbol_col or not security_id_col:
            _log_debug('security_map_error', "Could not find symbol/security_id columns in CSV")
            return {}

        # Filter to NSE Equity only (avoid F&O/currency/commodity duplicates
        # of the same symbol name). Equity cash rows have SEGMENT == "E".
        filtered = df
        if exch_col:
            filtered = filtered[filtered[exch_col].astype(str).str.upper() == "NSE"]
        if segment_col:
            filtered = filtered[filtered[segment_col].astype(str).str.upper() == "E"]
        elif instrument_col:
            filtered = filtered[filtered[instrument_col].astype(str).str.upper().isin(["EQUITY", "ES"])]

        security_map = {}
        for _, row in filtered.iterrows():
            sym = str(row[symbol_col]).strip().upper()
            sec_id = str(row[security_id_col]).strip()
            if sym and sec_id and sym not in security_map:
                security_map[sym] = sec_id

        _log_debug('security_map_size', len(security_map))
        if len(security_map) == 0:
            _log_debug('security_map_error', "Filtered result was empty — check exch/instrument filter values")

        return security_map
    except Exception as e:
        _log_debug('security_map_error', f"Exception: {str(e)}")
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MARGIN CALCULATOR API CALL (per stock)
# ─────────────────────────────────────────────────────────────────────────────

def get_margin_per_share(security_id, price, product_type="INTRADAY"):
    """
    Call DhanHQ's live Margin Calculator API to get the real margin
    required to buy 1 share of a stock (accounts for actual leverage —
    most stocks are 5x, some are 2x or other custom ratios).

    Uses get_access_token() internally — token is auto-generated/refreshed
    via TOTP, no manual daily login needed.

    Args:
        security_id (str): Dhan's internal security ID for the symbol
        price (float): Current market price of the stock
        product_type (str): "INTRADAY" for MIS margin (leveraged),
                            "CNC" for full delivery margin (no leverage)

    Returns:
        tuple: (margin_per_share: float or None, error_message: str or None)
    """
    access_token = get_access_token()
    if not access_token:
        return None, "Could not obtain access token (check TOTP/PIN/client_id)"

    try:
        payload = {
            "dhanClientId": str(DHAN_CLIENT_ID),
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "quantity": 1,
            "productType": product_type,
            "securityId": str(security_id),
            "price": float(price),
            "triggerPrice": 0,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "access-token": access_token,
        }
        response = requests.post(DHAN_MARGIN_CALCULATOR_URL, json=payload, headers=headers, timeout=10)

        if response.status_code == 401:
            # Token might have just expired — force a one-time refresh and retry
            access_token = get_access_token(force_refresh=True)
            if not access_token:
                return None, "401 Unauthorized, and token refresh also failed"
            headers["access-token"] = access_token
            response = requests.post(DHAN_MARGIN_CALCULATOR_URL, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            return None, f"HTTP {response.status_code}: {response.text[:200]}"

        data = response.json()
        margin = data.get("totalMargin")
        if margin is None:
            return None, f"No totalMargin in response: {data}"
        return float(margin), None
    except Exception as e:
        return None, f"Exception: {str(e)}"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MAX QUANTITY CALCULATION (main entry point)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_max_quantity_column(df, total_capital, num_parts=4):
    """
    For each stock in df, calculate the max quantity purchasable using
    (total_capital / num_parts) as the budget for that single stock,
    accounting for real intraday margin/leverage via DhanHQ.

    Args:
        df (pd.DataFrame): Must have 'Symbol' and 'Price' columns
        total_capital (float): User's total trading capital
        num_parts (int): Number of equal parts to split capital into (default 4)

    Returns:
        pd.Series: Max quantity per row (int), aligned with df's index.
                   0 if margin couldn't be determined for that symbol.
                   Check get_qty_calc_debug() to see why, per symbol.
    """
    _init_debug()

    if total_capital is None or total_capital <= 0 or df.empty:
        return pd.Series([0] * len(df), index=df.index)

    part_capital = total_capital / num_parts
    security_map = get_security_id_map()

    max_qty_list = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        price = row.get("Price", 0)

        security_id = security_map.get(symbol)
        if not security_id:
            _log_symbol_debug(symbol, security_id=None, margin_error="Symbol not found in Dhan instrument master")
            max_qty_list.append(0)
            continue

        if not price or price <= 0:
            _log_symbol_debug(symbol, security_id=security_id, margin_error="Invalid price")
            max_qty_list.append(0)
            continue

        margin_per_share, error = get_margin_per_share(security_id, price)
        _log_symbol_debug(symbol, security_id=security_id, margin_error=error, margin_value=margin_per_share)

        if margin_per_share is None or margin_per_share <= 0:
            max_qty_list.append(0)
            continue

        max_qty = math.floor(part_capital / margin_per_share)
        max_qty_list.append(max(max_qty, 0))

    return pd.Series(max_qty_list, index=df.index)
