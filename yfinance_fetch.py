# ══════════════════════════════════════════════════════════════════════════════
#  TRADESENTRY — yfinance_fetch.py
#  Fetches 5-min OHLCV candles using yfinance
#  Drop-in replacement for AngelOne getCandleData
#  No rate limits, no auth, completely free
#  Note: Uses closed candles only — 15min delay on LTP doesn't affect signals
# ══════════════════════════════════════════════════════════════════════════════

import pytz
from datetime import datetime, timedelta

IST = pytz.timezone("Asia/Kolkata")


def get_ist_now():
    return datetime.now(pytz.utc).astimezone(IST)


def fetch_candles_5min_yfinance(symbol: str, _log: list = None) -> list:
    """
    Fetches 5-min OHLCV candles from yfinance for Indian NSE stocks.
    Returns same format as AngelOne: [[timestamp, open, high, low, close, volume], ...]
    Drop-in replacement for fetch_candles_5min() in scanner.py
    """
    log = _log if _log is not None else []

    try:
        import yfinance as yf
    except ImportError:
        log.append(f"❌ [{symbol}] yfinance not installed — add to requirements.txt")
        return None

    # Add .NS suffix for NSE stocks
    yf_symbol = f"{symbol}.NS"

    try:
        ticker = yf.Ticker(yf_symbol)

        # Fetch last 25 days of 5min data (need 20 trading days = 800+ candles)
        data = ticker.history(period="25d", interval="5m")

        if data is None or data.empty:
            log.append(f"⚠️ [{symbol}] No data from yfinance — symbol may be delisted")
            return None

        # Convert to same format as AngelOne
        # AngelOne format: [timestamp_str, open, high, low, close, volume]
        rows = []
        for ts, row in data.iterrows():
            try:
                # Convert to IST
                if ts.tzinfo is None:
                    ts_ist = pytz.utc.localize(ts).astimezone(IST)
                else:
                    ts_ist = ts.astimezone(IST)

                ts_str = ts_ist.strftime("%Y-%m-%d %H:%M:%S")

                rows.append([
                    ts_str,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])
            except Exception:
                continue

        if not rows:
            log.append(f"⚠️ [{symbol}] 0 valid candles parsed from yfinance")
            return None

        log.append(f"✅ [{symbol}] {len(rows)} candles fetched via yfinance")
        return rows

    except Exception as e:
        log.append(f"❌ [{symbol}] yfinance exception: {e}")
        return None
