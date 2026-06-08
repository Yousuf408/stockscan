# ══════════════════════════════════════════════════════════════════════════════
#  TRADESENTRY — yfinance_fetch.py v2.0
#  FAST parallel fetch using ThreadPoolExecutor
#  No rate limits — fetch all stocks simultaneously
# ══════════════════════════════════════════════════════════════════════════════

import pytz
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

IST = pytz.timezone("Asia/Kolkata")


def fetch_candles_5min_yfinance(symbol: str, _log: list = None) -> list:
    """Single stock fetch — called by parallel fetcher"""
    log = _log if _log is not None else []

    try:
        import yfinance as yf
    except ImportError:
        log.append(f"❌ [{symbol}] yfinance not installed")
        return None

    yf_symbol = f"{symbol}.NS"

    try:
        ticker = yf.Ticker(yf_symbol)
        data   = ticker.history(period="25d", interval="5m")

        if data is None or data.empty:
            log.append(f"⚠️ [{symbol}] No data from yfinance")
            return None

        rows = []
        for ts, row in data.iterrows():
            try:
                if ts.tzinfo is None:
                    ts_ist = pytz.utc.localize(ts).astimezone(IST)
                else:
                    ts_ist = ts.astimezone(IST)

                rows.append([
                    ts_ist.strftime("%Y-%m-%d %H:%M:%S"),
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])
            except Exception:
                continue

        if not rows:
            log.append(f"⚠️ [{symbol}] 0 candles parsed")
            return None

        return rows

    except Exception as e:
        log.append(f"❌ [{symbol}] yfinance error: {e}")
        return None


def fetch_all_candles_parallel(watchlist_stocks: list, _log: list = None,
                                progress_callback=None) -> dict:
    """
    Fetch all stocks in parallel — no rate limit so max workers
    Returns dict: { "SYMBOL": candles_list }
    """
    log         = _log if _log is not None else []
    candles_map = {}
    total       = len(watchlist_stocks)
    completed   = [0]

    def fetch_one(stock):
        symbol  = stock["symbol"]
        candles = fetch_candles_5min_yfinance(symbol, _log=log)
        return symbol, candles

    # Max 20 parallel workers — yfinance has no server-side limit
    # 20 workers = ~5-10x faster than sequential
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_one, s): s for s in watchlist_stocks}

        for future in as_completed(futures):
            symbol, candles = future.result()
            candles_map[symbol] = candles
            completed[0] += 1

            if progress_callback:
                progress_callback(completed[0], total, symbol)

    return candles_map
