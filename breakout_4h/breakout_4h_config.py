"""
breakout_4h_config.py
Scanner constants
"""

# ─────────────────────────────────────────────────────────────
# SUPABASE — kept for future use
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
SUPABASE_TABLE = "websocket_stock_values"

# ─────────────────────────────────────────────────────────────
# 4 CHECKS CONFIG
# ─────────────────────────────────────────────────────────────

# Check 1: Max consolidation range %
MAX_CONSOLIDATION_PCT  = 12.0

# Check 2: Breakout — just close > conHigh (no multiplier)
# (handled directly in logic)

# Check 3: Rel. Volume
MIN_REL_VOL            = 1.2   # 1H vol ≥ 1.2x median
VOL_MEDIAN_WINDOW      = 5     # last 5 1H candles

# Check 4: Trend
# SMA20 & SMA50 (handled in logic)

# Consolidation lookback
CONSOLIDATION_LOOKBACK = 10    # last 10 completed 4H candles

# yfinance periods
YFINANCE_1H_PERIOD     = "1mo"
YFINANCE_DAILY_PERIOD  = "6mo"

# Parallel workers
PARALLEL_WORKERS       = 20
