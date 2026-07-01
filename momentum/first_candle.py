"""
momentum/first_candle.py
Fetches the first 5-min candle (9:15–9:20 IST) for a list of stocks
and calculates body ratio = |close - open| / (high - low) * 100.

Used purely as a runtime toggle-filter on MomentumScanner — no DB save,
no persistent column. Session-cached by the caller (8_MomentumScanner.py).
"""

import pandas as pd
import yfinance as yf


def fetch_body_ratio_for_stocks(stock_names: list) -> dict:
    """
    Returns: { stock_name: body_ratio (float, 0-100) or None }
    """
    result = {}
    if not stock_names:
        return result

    tickers = [f"{s}.NS" for s in stock_names]
    try:
        raw = yf.download(
            tickers,
            period="1d",
            interval="5m",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception:
        return result

    if raw.empty:
        return result

    for stock in stock_names:
        ticker = f"{stock}.NS"
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                first = raw.xs(ticker, axis=1, level=1).iloc[0]
            else:
                first = raw.iloc[0]

            o = float(first["Open"])
            h = float(first["High"])
            l = float(first["Low"])
            c = float(first["Close"])

            if h - l == 0:
                result[stock] = 0.0
                continue

            body_ratio = round(abs(c - o) / (h - l) * 100, 1)
            result[stock] = body_ratio
        except Exception:
            result[stock] = None

    return result
