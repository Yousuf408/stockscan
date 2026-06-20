"""
breakout_4h_config.py
Supabase credentials + scanner constants
"""

# ─────────────────────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

# ─────────────────────────────────────────────────────────────
# SCANNER CONSTANTS
# ─────────────────────────────────────────────────────────────

# Check 1: Max consolidation range %
MAX_CONSOLIDATION_PCT   = 12.0

# Check 2: Min breakout above zone high
MIN_BREAKOUT_ABOVE_ZONE = 1.02   # 2% above

# Check 3: Min breakout candle body size %
MIN_BODY_PCT            = 5.0

# Check 4: Min relative volume
MIN_REL_VOL             = 1.5

# Check 5: Min avg daily volume (liquidity)
MIN_AVG_DAILY_VOL       = 500_000

# Check 6: Min market cap
MIN_MARKET_CAP          = 50_000_000

# Check 7: Within % of 20d/50d high
NEAR_HIGH_THRESHOLD     = 0.90   # within 10%

# Lookback: how many prior 4H candles for consolidation
CONSOLIDATION_LOOKBACK  = 10

# yfinance fetch period for 1h data
YFINANCE_1H_PERIOD      = "1mo"

# yfinance fetch period for daily data
YFINANCE_DAILY_PERIOD   = "6mo"

# Parallel workers for scan
PARALLEL_WORKERS        = 20

# Supabase table name
SUPABASE_TABLE          = "websocket_stock_values"
