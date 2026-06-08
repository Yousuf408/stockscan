# ══════════════════════════════════════════════════════════════════════════════
#  TRADESENTRY — dhan_fetch.py
#  Replaces AngelOne getCandleData for scanner
#  Uses Dhan API — 5 req/sec limit (vs AngelOne 3/sec)
#  Auto-generates access token using PIN + TOTP
# ══════════════════════════════════════════════════════════════════════════════

import os
import time
import pyotp
import requests
import pytz
from datetime import datetime, timedelta

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: AUTH — Auto-generate Dhan access token
# ─────────────────────────────────────────────────────────────────────────────

_dhan_token_cache = {"token": None, "expires_at": 0}

def get_dhan_access_token() -> str:
    """
    Auto-generates Dhan access token using PIN + TOTP.
    Caches token for 23 hours (token valid 24 hours).
    """
    now = time.time()

    # Return cached token if still valid
    if _dhan_token_cache["token"] and now < _dhan_token_cache["expires_at"]:
        return _dhan_token_cache["token"]

    client_id   = os.environ.get("DHAN_CLIENT_ID", "")
    api_key     = os.environ.get("DHAN_API_KEY", "")
    pin         = os.environ.get("DHAN_PIN", "")
    totp_secret = os.environ.get("DHAN_TOTP_SECRET", "")

    if not all([client_id, api_key, pin, totp_secret]):
        raise Exception("Dhan credentials missing in environment variables")

    totp = pyotp.TOTP(totp_secret).now()

    try:
        from dhanhq import DhanLogin
        dhan_login  = DhanLogin(client_id)
        token_data  = dhan_login.generate_token(pin, totp)

        print(f"[Dhan Auth] token_data = {token_data}")

        # Extract access token from response
        if isinstance(token_data, dict):
            access_token = (
                token_data.get("access_token") or
                token_data.get("accessToken") or
                token_data.get("data", {}).get("access_token") or
                token_data.get("data", {}).get("accessToken")
            )
        else:
            access_token = str(token_data)

        if not access_token:
            raise Exception(f"Could not extract access token from response: {token_data}")

        # Cache for 23 hours
        _dhan_token_cache["token"]      = access_token
        _dhan_token_cache["expires_at"] = now + (23 * 3600)

        print(f"[Dhan Auth] ✅ Access token generated successfully")
        return access_token

    except Exception as e:
        print(f"[Dhan Auth] ❌ Failed: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: CANDLE FETCH — Replaces fetch_candles_5min
# ─────────────────────────────────────────────────────────────────────────────

def get_ist_now():
    return datetime.now(pytz.utc).astimezone(IST)

def is_market_open():
    now  = get_ist_now()
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30) and now.weekday() < 5

def fetch_candles_5min_dhan(security_id: str, symbol: str, _log: list = None) -> list:
    """
    Fetches 5-min OHLCV candles from Dhan API.
    Returns same format as AngelOne: [[timestamp, open, high, low, close, volume], ...]
    Drop-in replacement for fetch_candles_5min() in scanner.py
    """
    log = _log if _log is not None else []

    if not security_id or str(security_id).strip() == "":
        log.append(f"❌ [{symbol}] Failed — Missing security ID")
        return None

    try:
        access_token = get_dhan_access_token()
    except Exception as e:
        log.append(f"❌ [{symbol}] Dhan auth failed — {e}")
        return None

    now        = get_ist_now()
    end_date   = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    # For intraday endpoint — need datetime format
    from_date  = f"{start_date} 09:15:00"
    to_date    = f"{end_date} 15:30:00" if not is_market_open() else f"{end_date} {now.strftime('%H:%M:%S')}"

    url     = "https://api.dhan.co/v2/charts/intraday"
    headers = {
        "access-token": access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "securityId":      str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument":      "EQUITY",
        "interval":        "5",
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code == 429:
            log.append(f"⚠️ [{symbol}] Dhan rate limit hit — will retry")
            return None

        if resp.status_code != 200:
            log.append(f"❌ [{symbol}] Dhan API error — status {resp.status_code}: {resp.text[:100]}")
            return None

        data = resp.json()

        # Dhan returns separate arrays for each field
        timestamps = data.get("timestamp", [])
        opens      = data.get("open",      [])
        highs      = data.get("high",      [])
        lows       = data.get("low",       [])
        closes     = data.get("close",     [])
        volumes    = data.get("volume",    [])

        if not timestamps:
            log.append(f"⚠️ [{symbol}] No candle data returned from Dhan")
            return None

        # Convert to same format as AngelOne: [timestamp, open, high, low, close, volume]
        rows = []
        for i in range(len(timestamps)):
            try:
                # Dhan timestamp is Unix epoch
                ts  = datetime.fromtimestamp(timestamps[i], tz=IST)
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                rows.append([
                    ts_str,
                    float(opens[i]),
                    float(highs[i]),
                    float(lows[i]),
                    float(closes[i]),
                    float(volumes[i]) if i < len(volumes) else 0.0,
                ])
            except Exception:
                continue

        if not rows:
            log.append(f"⚠️ [{symbol}] 0 valid candles parsed")
            return None

        log.append(f"✅ [{symbol}] {len(rows)} candles fetched via Dhan")
        return rows

    except requests.exceptions.Timeout:
        log.append(f"❌ [{symbol}] Dhan request timeout")
        return None
    except Exception as e:
        log.append(f"❌ [{symbol}] Dhan exception: {e}")
        return None
