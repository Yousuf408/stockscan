"""
ai_pattern_engine.py
ML Pattern Recognition Engine — studies volume and price setups preceding spikes >= 5%
Uses 20 EMA, range compression, and volume dry-ups.
Supabase-backed: predictions, model metrics, feature importances, and model binary all stored in Supabase.
NO SQLite. NO local joblib. Streamlit Cloud safe.
"""

import os
import io
import sys
import json
import base64
import logging
import pickle
from datetime import datetime
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── ML imports ──
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# ── yfinance ──
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# ── Supabase ──
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

FEATURE_COLS = [
    "dist_to_ema20", "above_ema20", "ema_5_vs_20", "ema_9_vs_20",
    "vol_ratio_1d", "vol_ratio_2d", "vol_vs_5d_avg", "vol_dry_up_3d",
    "price_change_1d", "price_change_3d", "range_compression",
    "range_compress_3d_avg", "body_ratio"
]

# ─────────────────────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────────────────────

def get_supabase_client(url: str, key: str):
    if not SUPABASE_AVAILABLE:
        raise RuntimeError("supabase-py not installed")
    return create_client(url, key)


def ensure_tables_exist(supabase):
    """
    Creates required Supabase tables via SQL if they don't exist.
    Requires you to run this SQL once in Supabase SQL Editor:

    CREATE TABLE IF NOT EXISTS ai_predictions (
        id BIGSERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        probability REAL,
        stage TEXT,
        features JSONB,
        actual_max_return REAL,
        outcome INTEGER,
        UNIQUE(date, symbol)
    );

    CREATE TABLE IF NOT EXISTS ai_model_metrics (
        date TEXT PRIMARY KEY,
        accuracy REAL,
        precision_score REAL,
        recall_score REAL,
        total_samples INTEGER,
        trained_at TEXT
    );

    CREATE TABLE IF NOT EXISTS ai_feature_importances (
        feature_name TEXT PRIMARY KEY,
        importance REAL
    );

    CREATE TABLE IF NOT EXISTS ai_model_store (
        id TEXT PRIMARY KEY,
        model_blob TEXT,
        saved_at TEXT
    );
    """
    pass  # Tables must be created manually in Supabase SQL Editor (see docstring above)


# ─────────────────────────────────────────────────────────────
# MODEL PERSISTENCE — Supabase (base64 pickle)
# ─────────────────────────────────────────────────────────────

def save_model_to_supabase(model, supabase):
    """Serialize model to base64 string and upsert into ai_model_store."""
    buf = io.BytesIO()
    pickle.dump(model, buf)
    model_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    supabase.table("ai_model_store").upsert({
        "id": "main_model",
        "model_blob": model_b64,
        "saved_at": datetime.now().isoformat()
    }).execute()
    logging.info("Model saved to Supabase ai_model_store.")


def load_model_from_supabase(supabase):
    """Load model from Supabase ai_model_store. Returns None if not found."""
    try:
        result = supabase.table("ai_model_store").select("model_blob").eq("id", "main_model").execute()
        if not result.data:
            return None
        model_b64 = result.data[0]["model_blob"]
        model_bytes = base64.b64decode(model_b64)
        model = pickle.loads(model_bytes)
        logging.info("Model loaded from Supabase.")
        return model
    except Exception as e:
        logging.error(f"Failed to load model from Supabase: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA (yfinance + ThreadPool)
# ─────────────────────────────────────────────────────────────

def fetch_single_stock_history(symbol: str, period: str = "60d"):
    try:
        ticker = f"{symbol}.NS"
        df = yf.download(
            ticker, period=period, interval="1d",
            progress=False, auto_adjust=True, group_by="ticker"
        )
        if df is None or df.empty:
            return symbol, None

        # ── Flatten MultiIndex columns (yfinance >= 0.2.x) ──
        # MultiIndex: level-0 = Price field, level-1 = Ticker
        # Single-ticker download sometimes gives (field, ticker) or (ticker, field)
        if isinstance(df.columns, pd.MultiIndex):
            # Detect which level holds OHLCV names
            lvl0 = [str(c).lower() for c in df.columns.get_level_values(0)]
            lvl1 = [str(c).lower() for c in df.columns.get_level_values(1)]
            ohlcv = {"open", "high", "low", "close", "volume"}
            if ohlcv.issubset(set(lvl0)):
                df.columns = df.columns.get_level_values(0)
            elif ohlcv.issubset(set(lvl1)):
                df.columns = df.columns.get_level_values(1)
            else:
                # Fallback: just take level 0
                df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        # Normalize all column names to lowercase, strip spaces
        df.columns = [str(col).strip().lower() for col in df.columns]

        # yfinance may return "date" or "datetime" or "timestamp"
        for possible in ["date", "datetime", "timestamp", "index"]:
            if possible in df.columns:
                df = df.rename(columns={possible: "datetime"})
                break

        # Must have all required OHLCV columns
        required = {"open", "high", "low", "close", "volume", "datetime"}
        if not required.issubset(set(df.columns)):
            logging.warning(f"{symbol}: missing columns after parse. Got: {list(df.columns)}")
            return symbol, None

        # Drop rows with NaN in critical columns
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        df["symbol"] = symbol
        return symbol, df

    except Exception as e:
        logging.error(f"Error fetching {symbol}: {e}")
        return symbol, None


def fetch_all_history(symbols: list, period: str = "60d", progress_callback=None) -> dict:
    stock_dfs = {}
    total = len(symbols)
    logging.info(f"Fetching history for {total} stocks...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_single_stock_history, sym, period): sym for sym in symbols}
        for idx, future in enumerate(as_completed(futures)):
            sym, df = future.result()
            if df is not None and len(df) >= 25:
                stock_dfs[sym] = df
            if progress_callback and idx % 50 == 0:
                progress_callback(idx, total)
    logging.info(f"Fetched data for {len(stock_dfs)} stocks.")
    return stock_dfs


# ─────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────

def calculate_stock_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("datetime").reset_index(drop=True)

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    open_ = df["open"].astype(float)
    vol   = df["volume"].astype(float)

    # EMAs
    df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    df["ema_5"]  = close.ewm(span=5,  adjust=False).mean()
    df["ema_9"]  = close.ewm(span=9,  adjust=False).mean()

    df["dist_to_ema20"] = (close - df["ema_20"]) / df["ema_20"] * 100
    df["above_ema20"]   = (close > df["ema_20"]).astype(int)
    df["ema_5_vs_20"]   = (df["ema_5"] > df["ema_20"]).astype(int)
    df["ema_9_vs_20"]   = (df["ema_9"] > df["ema_20"]).astype(int)

    # Volume features
    df["vol_ratio_1d"]  = vol / vol.shift(1).replace(0, np.nan)
    df["vol_ratio_2d"]  = vol.shift(1) / vol.shift(2).replace(0, np.nan)
    rolling5            = vol.rolling(window=5).mean()
    df["vol_vs_5d_avg"] = vol / rolling5.replace(0, np.nan)
    df["vol_dry_up_3d"] = ((df["vol_ratio_1d"] < 0.9) & (df["vol_ratio_2d"] < 1.0)).astype(int)

    # Price / range
    df["price_change_1d"]      = close.pct_change(1) * 100
    df["price_change_3d"]      = close.pct_change(3) * 100
    df["range_compression"]    = (high - low) / close * 100
    df["range_compress_3d_avg"]= df["range_compression"].rolling(window=3).mean()
    candle_range               = (high - low).replace(0, np.nan)
    df["body_ratio"]           = abs(close - open_) / candle_range

    # Target label (for training only — NaN for last 2 rows)
    future_close_1  = close.shift(-1)
    future_close_2  = close.shift(-2)
    max_future      = pd.concat([future_close_1, future_close_2], axis=1).max(axis=1)
    df["forward_max_return"] = (max_future - close) / close * 100
    df["spike_label"]        = (df["forward_max_return"] >= 5.0).astype(int)

    return df


# ─────────────────────────────────────────────────────────────
# TRAINING
# ─────────────────────────────────────────────────────────────

def train_ai_model(supabase, stocks: list, progress_callback=None) -> dict:
    """
    Train RandomForest on historical data.
    Returns dict with keys: success, accuracy, precision, recall, total_samples, error
    """
    if not ML_AVAILABLE:
        return {"success": False, "error": "scikit-learn not installed"}
    if not YF_AVAILABLE:
        return {"success": False, "error": "yfinance not installed"}
    if not stocks:
        return {"success": False, "error": "No stocks provided"}

    histories = fetch_all_history(stocks, period="60d", progress_callback=progress_callback)
    if not histories:
        return {"success": False, "error": "Failed to fetch historical data"}

    all_dfs = []
    for sym, df in histories.items():
        all_dfs.append(calculate_stock_features(df))

    full_df    = pd.concat(all_dfs, ignore_index=True)
    train_data = full_df.dropna(subset=FEATURE_COLS + ["spike_label"])

    if len(train_data) < 100:
        return {"success": False, "error": f"Only {len(train_data)} clean samples — need ≥ 100"}

    # Chronological split (no data leakage)
    train_data = train_data.sort_values("datetime").reset_index(drop=True)
    split_idx  = int(len(train_data) * 0.8)

    X_train = train_data.loc[:split_idx,  FEATURE_COLS]
    y_train = train_data.loc[:split_idx,  "spike_label"]
    X_test  = train_data.loc[split_idx:,  FEATURE_COLS]
    y_test  = train_data.loc[split_idx:,  "spike_label"]

    model = RandomForestClassifier(
        n_estimators=150, max_depth=8, class_weight="balanced", random_state=42
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    acc  = float(accuracy_score(y_test, preds))
    prec = float(precision_score(y_test, preds, zero_division=0))
    rec  = float(recall_score(y_test, preds, zero_division=0))

    # Persist model
    save_model_to_supabase(model, supabase)

    # Persist feature importances
    fi_rows = [{"feature_name": f, "importance": float(i)}
               for f, i in zip(FEATURE_COLS, model.feature_importances_)]
    supabase.table("ai_feature_importances").upsert(fi_rows).execute()

    # Persist model metrics
    today = datetime.now().strftime("%Y-%m-%d")
    supabase.table("ai_model_metrics").upsert({
        "date": today,
        "accuracy": acc,
        "precision_score": prec,
        "recall_score": rec,
        "total_samples": len(train_data),
        "trained_at": datetime.now().isoformat()
    }).execute()

    logging.info(f"Training complete — Acc: {acc:.2%}, Prec: {prec:.2%}, Rec: {rec:.2%}")
    return {"success": True, "accuracy": acc, "precision": prec, "recall": rec,
            "total_samples": len(train_data)}


# ─────────────────────────────────────────────────────────────
# PREDICTIONS
# ─────────────────────────────────────────────────────────────

def run_predictions(supabase, stocks: list, progress_callback=None) -> list:
    """
    Run predictions for all stocks using the stored model.
    Returns list of prediction dicts.
    """
    model = load_model_from_supabase(supabase)
    if model is None:
        logging.warning("No model found. Train first.")
        return []

    histories = fetch_all_history(stocks, period="30d", progress_callback=progress_callback)
    if not histories:
        return []

    today_str    = datetime.now().strftime("%Y-%m-%d")
    preds_to_save = []

    for symbol, df in histories.items():
        processed  = calculate_stock_features(df)
        latest_row = processed.iloc[-1]

        if latest_row[FEATURE_COLS].isna().any():
            continue

        feat_df = pd.DataFrame([latest_row[FEATURE_COLS]])
        prob    = float(model.predict_proba(feat_df)[0][1] * 100)

        if prob >= 80.0:
            stage = "🚀 PRIME_AI"
        elif prob >= 60.0:
            stage = "🔴 WATCH_AI"
        elif prob >= 40.0:
            stage = "📈 BUILD_AI"
        else:
            stage = "📍 EARLY_AI"

        preds_to_save.append({
            "date":     today_str,
            "symbol":   symbol,
            "probability": prob,
            "stage":    stage,
            "features": latest_row[FEATURE_COLS].to_dict()
        })

    if preds_to_save:
        # Upsert in batches of 500
        for i in range(0, len(preds_to_save), 500):
            batch = preds_to_save[i:i+500]
            supabase.table("ai_predictions").upsert(batch).execute()

    logging.info(f"Saved {len(preds_to_save)} predictions for {today_str}.")
    return preds_to_save


# ─────────────────────────────────────────────────────────────
# OUTCOME RESOLUTION
# ─────────────────────────────────────────────────────────────

def update_past_outcomes(supabase) -> int:
    """
    Resolve pending predictions (outcome IS NULL, date != today).
    Returns count of resolved predictions.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Paginate through all pending predictions
    pending = []
    offset  = 0
    while True:
        result = (supabase.table("ai_predictions")
                  .select("id, date, symbol")
                  .is_("outcome", "null")
                  .neq("date", today_str)
                  .range(offset, offset + 999)
                  .execute())
        if not result.data:
            break
        pending.extend(result.data)
        if len(result.data) < 1000:
            break
        offset += 1000

    if not pending:
        return 0

    stocks_to_check = list({r["symbol"] for r in pending})
    histories       = fetch_all_history(stocks_to_check, period="30d")

    resolved = 0
    updates  = []

    for row in pending:
        sym      = row["symbol"]
        pred_id  = row["id"]
        pred_date_str = row["date"]

        if sym not in histories:
            continue

        df = histories[sym].sort_values("datetime").reset_index(drop=True)
        try:
            pred_date = datetime.strptime(pred_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        df["date_only"] = pd.to_datetime(df["datetime"]).dt.date
        match = df[df["date_only"] == pred_date]
        if match.empty:
            continue

        idx = match.index[0]
        if idx + 2 >= len(df):
            continue

        close_today     = float(df.loc[idx, "close"])
        future_closes   = df.loc[idx+1:idx+2, "close"].astype(float).tolist()
        max_return      = (max(future_closes) - close_today) / close_today * 100
        outcome         = 1 if max_return >= 5.0 else 0

        updates.append({"id": pred_id, "actual_max_return": float(max_return), "outcome": outcome})
        resolved += 1

    # Upsert resolved outcomes
    for i in range(0, len(updates), 500):
        supabase.table("ai_predictions").upsert(updates[i:i+500]).execute()

    logging.info(f"Resolved {resolved} past prediction outcomes.")
    return resolved


# ─────────────────────────────────────────────────────────────
# FETCH STORED PREDICTIONS FOR DISPLAY
# ─────────────────────────────────────────────────────────────

def fetch_today_predictions(supabase) -> pd.DataFrame:
    today_str = datetime.now().strftime("%Y-%m-%d")
    result    = (supabase.table("ai_predictions")
                 .select("symbol, probability, stage, features")
                 .eq("date", today_str)
                 .order("probability", desc=True)
                 .execute())
    if not result.data:
        return pd.DataFrame()
    return pd.DataFrame(result.data)


def fetch_model_metrics(supabase) -> dict:
    result = (supabase.table("ai_model_metrics")
              .select("*")
              .order("date", desc=True)
              .limit(1)
              .execute())
    if not result.data:
        return {}
    return result.data[0]


def fetch_feature_importances(supabase) -> pd.DataFrame:
    result = (supabase.table("ai_feature_importances")
              .select("*")
              .order("importance", desc=True)
              .execute())
    if not result.data:
        return pd.DataFrame()
    return pd.DataFrame(result.data)


def fetch_prediction_history(supabase, limit: int = 200) -> pd.DataFrame:
    """Fetch past predictions with resolved outcomes for accuracy tracking."""
    result = (supabase.table("ai_predictions")
              .select("date, symbol, probability, stage, actual_max_return, outcome")
              .not_.is_("outcome", "null")
              .order("date", desc=True)
              .limit(limit)
              .execute())
    if not result.data:
        return pd.DataFrame()
    return pd.DataFrame(result.data)
