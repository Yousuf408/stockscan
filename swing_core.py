# swing_core.py v2.1
# v2.1: period 20d→7d for faster fetch, update_swing_stock restored, full error handling
import os, requests, yfinance as yf, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed

def _get_config():
    try:
        import streamlit as st
        return st.secrets["SUPABASE_URL"].rstrip("/"), st.secrets["SUPABASE_KEY"]
    except Exception:
        return os.environ.get("SUPABASE_URL","").rstrip("/"), os.environ.get("SUPABASE_KEY","")

def _get_user_id():
    try:
        import streamlit as st
        return st.session_state.get("user_id","")
    except: return ""

def _get_access_token():
    try:
        import streamlit as st
        return st.session_state.get("access_token","")
    except: return ""

def _headers():
    _, key = _get_config()
    token = _get_access_token()
    return {"apikey": key, "Authorization": f"Bearer {token or key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

def _table_url():
    url, _ = _get_config()
    return f"{url}/rest/v1/swing_watchlist"

def load_swing_stocks():
    try:
        uid = _get_user_id()
        if not uid: return []
        r = requests.get(_table_url(), headers=_headers(),
                         params={"select":"*","user_id":f"eq.{uid}","order":"symbol.asc"}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[swing_core] load error: {e}")
        return []

def add_swing_stock(symbol, screener_url="", breakout_date=None, notes=""):
    uid = _get_user_id()
    if not uid: raise RuntimeError("Not logged in")
    symbol = symbol.upper().strip()
    if any(s["symbol"]==symbol for s in load_swing_stocks()):
        raise ValueError(f"{symbol} already in swing list")
    row = {"user_id": uid, "symbol": symbol,
           "screener_url": screener_url.strip() or f"https://www.screener.in/company/{symbol}/",
           "notes": notes.strip()}
    if breakout_date: row["breakout_date"] = str(breakout_date)
    r = requests.post(_table_url(), headers=_headers(), json=row, timeout=10)
    r.raise_for_status()
    d = r.json()
    return d[0] if isinstance(d, list) else d

def delete_swing_stock(db_id):
    r = requests.delete(f"{_table_url()}?id=eq.{db_id}", headers=_headers(), timeout=10)
    r.raise_for_status()

def update_swing_stock(db_id: int, updates: dict):
    """Update breakout_date, screener_url, or notes for a swing stock."""
    allowed = {"screener_url", "breakout_date", "notes", "symbol"}
    clean   = {k: v for k, v in updates.items() if k in allowed}
    if not clean:
        return
    r = requests.patch(
        f"{_table_url()}?id=eq.{db_id}",
        headers=_headers(),
        json=clean,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def bulk_add_swing_stocks(symbols):
    uid = _get_user_id()
    existing = {s["symbol"] for s in load_swing_stocks()}
    added, skipped, errors = [], [], []
    rows = []
    for sym in symbols:
        sym = sym.upper().strip()
        if not sym: continue
        if sym in existing: skipped.append(sym); continue
        rows.append({"user_id": uid, "symbol": sym,
                     "screener_url": f"https://www.screener.in/company/{sym}/", "notes": ""})
        added.append(sym)
    if rows:
        try:
            r = requests.post(_table_url(), headers=_headers(), json=rows, timeout=15)
            r.raise_for_status()
        except Exception:
            errors = added.copy(); added = []
    return {"added": added, "skipped": skipped, "errors": errors}

def fmt_vol(v):
    if v is None: return "—"
    v = int(v)
    if v >= 10_000_000: return f"{v/10_000_000:.2f}Cr"
    if v >= 100_000:    return f"{v/100_000:.2f}L"
    if v >= 1_000:      return f"{v/1_000:.1f}K"
    return str(v)

def _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio):
    max_hist_vol = max(hist_volumes) if hist_volumes else 0
    if current_price > max_close and current_vol > max_hist_vol and vol_ratio >= 2.0:
        return "BLASTING"
    if current_price >= max_close * 0.995 and vol_ratio >= 1.5:
        return "READY"
    if current_price >= max_close * 0.92:
        return "WATCH"
    return ""

def _vol_signal(ratio):
    if ratio > 2.0: return f"🔥 Explosive ({ratio})"
    if ratio > 1.5: return f"🟢 Strong ({ratio})"
    if ratio > 1.0: return f"🟡 Build ({ratio})"
    return f"🔴 Weak ({ratio})"

def _fetch_single(symbol):
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="7d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 6:
            return {"symbol": symbol, "error": "Not enough data"}
        df = df.dropna(subset=["Close","Volume"])
        if len(df) < 6:
            return {"symbol": symbol, "error": "Not enough clean data"}

        hist      = df.iloc[-6:-1]   # 5 historical days
        cur       = df.iloc[-1]      # current/today

        hist_closes  = hist["Close"].tolist()
        hist_volumes = hist["Volume"].tolist()
        hist_opens   = hist["Open"].tolist()
        hist_highs   = hist["High"].tolist()
        hist_lows    = hist["Low"].tolist()
        hist_dates   = hist.index.strftime("%d %b").tolist()

        current_price = round(float(cur["Close"]), 2)
        current_open  = round(float(cur["Open"]),  2)
        current_high  = round(float(cur["High"]),  2)
        current_low   = round(float(cur["Low"]),   2)
        current_vol   = int(cur["Volume"])
        current_date  = df.index[-1].strftime("%d %b")

        max_close       = max(hist_closes)
        clean_vols      = [v for v in hist_volumes if v > 0]
        median_vol      = statistics.median(clean_vols) if clean_vols else 1
        vol_ratio       = round(current_vol / median_vol, 2) if median_vol > 0 else 0
        status          = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
        vol_signal      = _vol_signal(vol_ratio)
        pct_vs_high     = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

        return {
            "symbol": symbol, "error": None,
            "hist_dates": hist_dates,
            "hist_opens":  [round(v,2) for v in hist_opens],
            "hist_highs":  [round(v,2) for v in hist_highs],
            "hist_lows":   [round(v,2) for v in hist_lows],
            "hist_closes": [round(v,2) for v in hist_closes],
            "hist_volumes":[int(v)     for v in hist_volumes],
            "current_date": current_date,
            "current_price": current_price, "current_open": current_open,
            "current_high": current_high,   "current_low": current_low,
            "current_vol": current_vol,
            "max_close": round(max_close, 2), "median_vol": int(median_vol),
            "vol_ratio": vol_ratio, "vol_signal": vol_signal,
            "pct_vs_high": pct_vs_high, "status": status,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

def run_swing_scan(stocks, batch_size=10, pause=0.5):
    meta    = {s["symbol"]: s for s in stocks}
    results, errors = [], []
    symbols = [s["symbol"] for s in stocks]
    batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    for idx, batch in enumerate(batches):
        with ThreadPoolExecutor(max_workers=batch_size) as ex:
            futures = {ex.submit(_fetch_single, s): s for s in batch}
            for f in as_completed(futures):
                d = f.result()
                if not d.get("error"):
                    m = meta.get(d["symbol"], {})
                    d["screener_url"]  = m.get("screener_url", f"https://www.screener.in/company/{d['symbol']}/")
                    d["breakout_date"] = m.get("breakout_date", "")
                    d["notes"]         = m.get("notes", "")
                    d["db_id"]         = m.get("id")
                    results.append(d)
                else:
                    errors.append({"symbol": d["symbol"], "error": d["error"]})
        if idx < len(batches)-1: time.sleep(pause)
    priority = {"BLASTING":0,"READY":1,"WATCH":2,"":3}
    results.sort(key=lambda x: priority.get(x.get("status",""),3))
    return results, errors
