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
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import requests
import io
import math

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DHAN CREDENTIALS (fill in your own client_id + access_token)
# ─────────────────────────────────────────────────────────────────────────────

DHAN_CLIENT_ID = "YOUR_DHAN_CLIENT_ID"
DHAN_ACCESS_TOKEN = "YOUR_DHAN_ACCESS_TOKEN"

DHAN_MARGIN_CALCULATOR_URL = "https://api.dhan.co/v2/margincalculator"
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

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
    """
    try:
        response = requests.get(DHAN_SCRIP_MASTER_URL, timeout=30)
        if response.status_code != 200:
            return {}

        df = pd.read_csv(io.StringIO(response.text), low_memory=False)

        # Column names can vary slightly across Dhan CSV versions — find them
        # defensively by substring match instead of hardcoding exact names.
        symbol_col = next((c for c in df.columns if "TRADING_SYMBOL" in c.upper()), None)
        security_id_col = next((c for c in df.columns if "SECURITY_ID" in c.upper()), None)
        exch_col = next((c for c in df.columns if c.upper() in ("SEM_EXM_EXCH_ID", "EXCH_ID")), None)
        segment_col = next((c for c in df.columns if "SEGMENT" in c.upper() and "EXPIRY" not in c.upper()), None)
        instrument_col = next((c for c in df.columns if "INSTRUMENT" in c.upper() and "EXCH" not in c.upper()), None)

        if not symbol_col or not security_id_col:
            return {}

        # Filter to NSE Equity only (avoid F&O/currency/commodity duplicates
        # of the same symbol name)
        filtered = df
        if exch_col:
            filtered = filtered[filtered[exch_col].astype(str).str.upper() == "NSE"]
        if instrument_col:
            filtered = filtered[filtered[instrument_col].astype(str).str.upper().isin(["EQUITY", "ES"])]

        security_map = {}
        for _, row in filtered.iterrows():
            sym = str(row[symbol_col]).strip().upper()
            sec_id = str(row[security_id_col]).strip()
            if sym and sec_id and sym not in security_map:
                security_map[sym] = sec_id

        return security_map
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MARGIN CALCULATOR API CALL (per stock)
# ─────────────────────────────────────────────────────────────────────────────

def get_margin_per_share(security_id, price, product_type="INTRADAY"):
    """
    Call DhanHQ's live Margin Calculator API to get the real margin
    required to buy 1 share of a stock (accounts for actual leverage —
    most stocks are 5x, some are 2x or other custom ratios).

    Args:
        security_id (str): Dhan's internal security ID for the symbol
        price (float): Current market price of the stock
        product_type (str): "INTRADAY" for MIS margin (leveraged),
                            "CNC" for full delivery margin (no leverage)

    Returns:
        float: Margin required per share, or None if call failed
    """
    try:
        payload = {
            "dhanClientId": DHAN_CLIENT_ID,
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
            "access-token": DHAN_ACCESS_TOKEN,
        }
        response = requests.post(DHAN_MARGIN_CALCULATOR_URL, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        return float(data.get("totalMargin")) if data.get("totalMargin") is not None else None
    except Exception:
        return None

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
    """
    if total_capital is None or total_capital <= 0 or df.empty:
        return pd.Series([0] * len(df), index=df.index)

    part_capital = total_capital / num_parts
    security_map = get_security_id_map()

    max_qty_list = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        price = row.get("Price", 0)

        security_id = security_map.get(symbol)
        if not security_id or not price or price <= 0:
            max_qty_list.append(0)
            continue

        margin_per_share = get_margin_per_share(security_id, price)
        if margin_per_share is None or margin_per_share <= 0:
            max_qty_list.append(0)
            continue

        max_qty = math.floor(part_capital / margin_per_share)
        max_qty_list.append(max(max_qty, 0))

    return pd.Series(max_qty_list, index=df.index)
