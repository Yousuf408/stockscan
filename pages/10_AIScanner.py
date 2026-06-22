"""
ai_pattern_engine.py
ML Pattern Recognition Engine — studies volume and price setups preceding spikes >= 5%
Uses 20 EMA, range compression, and volume dry-ups.
"""

import os
import sys
import sqlite3
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try imports for ML
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Resolve paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import STOCKS_WATCHLIST
except ImportError:
    STOCKS_WATCHLIST = []

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_memory.db")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_pattern_model.joblib")

# ─────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────
def init_db():
    """Initialize SQLite database for storing model memory and predictions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Predictions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symbol TEXT,
            probability REAL,
            stage TEXT,
            features TEXT,
            actual_max_return REAL,
            outcome INTEGER, -- 1 = hit (>=5% spike), 0 = miss, NULL = pending
            UNIQUE(date, symbol)
        )
    """)
    
    # Model Metrics Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_metrics (
            date TEXT PRIMARY KEY,
            accuracy REAL,
            precision REAL,
            recall REAL,
            total_samples INTEGER,
            trained_at TEXT
        )
    """)
    
    # Feature Importances Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feature_importances (
            feature_name TEXT PRIMARY KEY,
            importance REAL
        )
    """)
    
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA FETCHING (yfinance with ThreadPool)
# ─────────────────────────────────────────────────────────────
def fetch_single_stock_history(symbol, period="60d"):
    """Fetch daily history for a single stock using yfinance."""
    try:
        ticker = f"{symbol}.NS"
        df = yf.download(ticker, period=period, interval="1d", progress=False, group_by="ticker")
        if df.empty:
            return symbol, None
        
        # Handle multi-index column if returned by yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(1)
            
        df = df.reset_index()
        # Standardize columns to lowercase
        df.columns = [col.lower() for col in df.columns]
        df = df.rename(columns={"date": "datetime"})
        df["symbol"] = symbol
        return symbol, df
    except Exception as e:
        logging.error(f"Error fetching {symbol}: {str(e)}")
        return symbol, None

def fetch_all_history(symbols, period="60d"):
    """Fetch history for all stocks concurrently."""
    stock_dfs = {}
    logging.info(f"Fetching history for {len(symbols)} stocks using ThreadPool...")
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_single_stock_history, sym, period): sym for sym in symbols}
        for idx, future in enumerate(as_completed(futures)):
            sym, df = future.result()
            if df is not None and len(df) >= 25: # Need at least 25 trading days for 20 EMA + features
                stock_dfs[sym] = df
            if idx % 100 == 0 and idx > 0:
                logging.info(f"Fetched {idx}/{len(symbols)} stocks...")
                
    logging.info(f"Successfully fetched data for {len(stock_dfs)} stocks.")
    return stock_dfs

# ─────────────────────────────────────────────────────────────
# FEATURE ENGINEERING & STUDY MODULE
# ─────────────────────────────────────────────────────────────
def calculate_stock_features(df):
    """
    Calculate high-quality technical features.
    Studies relation to 20 EMA, range compression, and volume dry-ups.
    """
    df = df.sort_values("datetime").reset_index(drop=True)
    
    # Prices and Volume
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_px = df["open"].astype(float)
    volume = df["volume"].astype(float)
    
    # ── 1. EMA Calculations ──
    df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    df["ema_5"] = close.ewm(span=5, adjust=False).mean()
    df["ema_9"] = close.ewm(span=9, adjust=False).mean()
    
    # Distance to 20 EMA & status
    df["dist_to_ema20"] = (close - df["ema_20"]) / df["ema_20"] * 100
    df["above_ema20"] = (close > df["ema_20"]).astype(int)
    
    # EMA Crossovers
    df["ema_5_vs_20"] = (df["ema_5"] > df["ema_20"]).astype(int)
    df["ema_9_vs_20"] = (df["ema_9"] > df["ema_20"]).astype(int)
    
    # ── 2. Volume DNA Features ──
    df["vol_ratio_1d"] = volume / volume.shift(1).replace(0, np.nan)
    df["vol_ratio_2d"] = volume.shift(1) / volume.shift(2).replace(0, np.nan)
    
    # Volume relative to recent 5-day average
    rolling_vol_5 = volume.rolling(window=5).mean()
    df["vol_vs_5d_avg"] = volume / rolling_vol_5.replace(0, np.nan)
    
    # Volume Dry-up indicator (e.g. volume drop while price consolidates)
    df["vol_dry_up_3d"] = ((df["vol_ratio_1d"] < 0.9) & (df["vol_ratio_2d"] < 1.0)).astype(int)
    
    # ── 3. Price Actions & Range Compression ──
    df["price_change_1d"] = close.pct_change(1) * 100
    df["price_change_3d"] = close.pct_change(3) * 100
    
    # Range Compression = (High - Low) / Close
    df["range_compression"] = (high - low) / close * 100
    df["range_compress_3d_avg"] = df["range_compression"].rolling(window=3).mean()
    
    # Candle Body Ratio = abs(Close - Open) / (High - Low)
    candle_range = (high - low).replace(0, np.nan)
    df["body_ratio"] = abs(close - open_px) / candle_range
    
    # ── 4. Target Labeling (For Training) ──
    # Check if max price in next 1 to 2 days goes up >= 5% from current close
    future_close_1 = close.shift(-1)
    future_close_2 = close.shift(-2)
    max_future_close = pd.concat([future_close_1, future_close_2], axis=1).max(axis=1)
    
    df["forward_max_return"] = (max_future_close - close) / close * 100
    # Label is 1 if spike >= 5%, else 0
    df["spike_label"] = (df["forward_max_return"] >= 5.0).astype(int)
    
    # Drop rows without labels (the latest 2 rows in history cannot be labeled)
    return df

# ─────────────────────────────────────────────────────────────
# MODEL TRAINING & VALIDATION
# ─────────────────────────────────────────────────────────────
def train_ai_model():
    """Trains the RandomForestClassifier on historical stock patterns."""
    if not ML_AVAILABLE or not YF_AVAILABLE:
        logging.error("Required libraries (scikit-learn/yfinance) not installed.")
        return False
        
    init_db()
    
    # Fetch watchlist symbols (stocks only)
    stocks = [item[0] for item in STOCKS_WATCHLIST if item[2] == "stock"]
    if not stocks:
        logging.warning("No stocks found in STOCKS_WATCHLIST.")
        return False
        
    # Fetch historical data
    histories = fetch_all_history(stocks, period="60d")
    if not histories:
        logging.error("Failed to fetch historical data for training.")
        return False
        
    # Process features for all stocks and concatenate
    all_processed_dfs = []
    for symbol, df in histories.items():
        processed_df = calculate_stock_features(df)
        all_processed_dfs.append(processed_df)
        
    full_df = pd.concat(all_processed_dfs, ignore_index=True)
    
    # Drop rows with NaN in features
    feature_cols = [
        "dist_to_ema20", "above_ema20", "ema_5_vs_20", "ema_9_vs_20",
        "vol_ratio_1d", "vol_ratio_2d", "vol_vs_5d_avg", "vol_dry_up_3d",
        "price_change_1d", "price_change_3d", "range_compression", 
        "range_compress_3d_avg", "body_ratio"
    ]
    
    # Clean data for training (remove rows where label or features are NaN)
    train_data = full_df.dropna(subset=feature_cols + ["spike_label"])
    
    if len(train_data) < 100:
        logging.error(f"Not enough clean training samples. Found {len(train_data)} rows.")
        return False
        
    X = train_data[feature_cols]
    y = train_data["spike_label"]
    
    logging.info(f"Training ML Model on {len(train_data)} patterns...")
    
    # Chronological Split: Train on 80% oldest, validate on 20% newest to prevent data leakage
    # We will sort by datetime
    train_data_sorted = train_data.sort_values("datetime").reset_index(drop=True)
    split_idx = int(len(train_data_sorted) * 0.8)
    
    X_train = train_data_sorted.loc[:split_idx, feature_cols]
    y_train = train_data_sorted.loc[:split_idx, "spike_label"]
    X_test = train_data_sorted.loc[split_idx:, feature_cols]
    y_test = train_data_sorted.loc[split_idx:, "spike_label"]
    
    # Train Random Forest Classifier
    # Class weight balanced to handle minority class (spikes are relatively rare)
    model = RandomForestClassifier(n_estimators=150, max_depth=8, class_weight="balanced", random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    
    accuracy = accuracy_score(y_test, preds)
    precision = precision_score(y_test, preds, zero_division=0)
    recall = recall_score(y_test, preds, zero_division=0)
    
    logging.info(f"Model Evaluation -> Accuracy: {accuracy:.2%}, Precision: {precision:.2%}, Recall: {recall:.2%}")
    
    # Save Model
    joblib.dump(model, MODEL_PATH)
    logging.info(f"Saved trained model to {MODEL_PATH}")
    
    # Save Feature Importances to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM feature_importances")
    for feat, imp in zip(feature_cols, model.feature_importances_):
        cursor.execute("INSERT INTO feature_importances (feature_name, importance) VALUES (?, ?)", (feat, float(imp)))
    
    # Save Model Metrics to DB
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        INSERT OR REPLACE INTO model_metrics (date, accuracy, precision, recall, total_samples, trained_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (today_str, float(accuracy), float(precision), float(recall), len(train_data), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return True

# ─────────────────────────────────────────────────────────────
# INFERENCE & REAL-TIME PREDICTION
# ─────────────────────────────────────────────────────────────
def run_predictions():
    """Runs predictions on the latest market state for all stocks."""
    if not os.path.exists(MODEL_PATH):
        logging.warning("Model file not found. Running training first...")
        success = train_ai_model()
        if not success:
            return []
            
    model = joblib.load(MODEL_PATH)
    stocks = [item[0] for item in STOCKS_WATCHLIST if item[2] == "stock"]
    
    # Fetch last 30 days history to generate features for today
    histories = fetch_all_history(stocks, period="30d")
    if not histories:
        logging.error("Failed to fetch historical data for predictions.")
        return []
        
    predictions_to_save = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    feature_cols = [
        "dist_to_ema20", "above_ema20", "ema_5_vs_20", "ema_9_vs_20",
        "vol_ratio_1d", "vol_ratio_2d", "vol_vs_5d_avg", "vol_dry_up_3d",
        "price_change_1d", "price_change_3d", "range_compression", 
        "range_compress_3d_avg", "body_ratio"
    ]
    
    for symbol, df in histories.items():
        processed_df = calculate_stock_features(df)
        
        # Take the absolute last row (today's market state)
        latest_row = processed_df.iloc[-1]
        
        # Skip if features have NaNs
        if latest_row[feature_cols].isna().any():
            continue
            
        # Reshape for single prediction
        features_df = pd.DataFrame([latest_row[feature_cols]])
        prob = model.predict_proba(features_df)[0][1] * 100 # Convert to percentage
        
        # Classify Setup Stage based on Probability
        if prob >= 80.0:
            stage = "🚀 PRIME_AI"
        elif prob >= 60.0:
            stage = "🔴 WATCH_AI"
        elif prob >= 40.0:
            stage = "📈 BUILD_AI"
        else:
            stage = "📍 EARLY_AI"
            
        features_dict = latest_row[feature_cols].to_dict()
        
        predictions_to_save.append((
            today_str,
            symbol,
            float(prob),
            stage,
            json.dumps(features_dict)
        ))
        
    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert or update today's predictions
    cursor.executemany("""
        INSERT OR REPLACE INTO predictions (date, symbol, probability, stage, features)
        VALUES (?, ?, ?, ?, ?)
    """, predictions_to_save)
    
    conn.commit()
    conn.close()
    
    logging.info(f"Saved {len(predictions_to_save)} AI predictions for date {today_str}.")
    return predictions_to_save

# ─────────────────────────────────────────────────────────────
# OUTCOME UPDATE ENGINE (Resolves past predictions accuracy)
# ─────────────────────────────────────────────────────────────
def update_past_outcomes():
    """
    Check historical data for past pending predictions.
    Computes if predictions actually spiked >= 5% in the following 2 days.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Select predictions that have no outcomes resolved yet
    # Exclude today's predictions (which need 2 future days to resolve)
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT id, date, symbol FROM predictions 
        WHERE outcome IS NULL AND date != ?
    """, (today_str,))
    
    pending = cursor.fetchall()
    if not pending:
        conn.close()
        return
        
    logging.info(f"Resolving outcomes for {len(pending)} historical predictions...")
    
    # Group by stock to minimize yfinance downloads
    stocks_to_check = list(set([row[2] for row in pending]))
    histories = fetch_all_history(stocks_to_check, period="30d")
    
    resolved_count = 0
    for db_id, pred_date_str, symbol in pending:
        if symbol not in histories:
            continue
            
        df = histories[symbol].sort_values("datetime").reset_index(drop=True)
        # Parse prediction date
        try:
            pred_date = datetime.strptime(pred_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
            
        # Find index of prediction date in stock history
        df["date_only"] = df["datetime"].dt.date
        matching_rows = df[df["date_only"] == pred_date]
        
        if matching_rows.empty:
            continue
            
        idx = matching_rows.index[0]
        
        # Check if we have at least 2 future rows to resolve
        if idx + 2 >= len(df):
            continue # Not enough future data yet
            
        close_today = float(df.loc[idx, "close"])
        future_prices = df.loc[idx+1 : idx+2, "close"].astype(float).tolist()
        
        max_future_close = max(future_prices)
        max_return = (max_future_close - close_today) / close_today * 100
        
        outcome = 1 if max_return >= 5.0 else 0
        
        cursor.execute("""
            UPDATE predictions 
            SET actual_max_return = ?, outcome = ?
            WHERE id = ?
        """, (float(max_return), outcome, db_id))
        resolved_count += 1
        
    conn.commit()
    conn.close()
    logging.info(f"Successfully resolved {resolved_count} predictions outcomes.")

# ─────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["train", "predict", "update", "run-all"], default="run-all")
    args = parser.parse_args()
    
    init_db()
    
    if args.action == "train":
        train_ai_model()
    elif args.action == "predict":
        run_predictions()
    elif args.action == "update":
        update_past_outcomes()
    elif args.action == "run-all":
        logging.info("Starting complete AI cycle...")
        update_past_outcomes()
        train_success = train_ai_model()
        if train_success:
            run_predictions()
        logging.info("Completed AI cycle.")
