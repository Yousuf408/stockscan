# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER DATABASE MODULE
# Supabase integration — persistent cache for POC, EMA, Vol5D, Crossover signals
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
from supabase import create_client
from datetime import datetime
import pytz

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SUPABASE CLIENT INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

@st.cache_resource
def get_supabase():
    """
    Cached Supabase client — ek baar connect hone ke baad reuse hota hai
    pura session mein (jab tak app reload na ho).
    """
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CACHE READ FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def supabase_get_cached_row(symbol, calc_date):
    """
    Supabase se ek specific row fetch karo (symbol + calc_date basis par).
    
    Args:
        symbol (str): Stock symbol (e.g., "RELIANCE")
        calc_date (datetime.date): Calculation date
    
    Returns:
        dict: {poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status}
              ya None agar nahi mila
    """
    try:
        result = (supabase.table("tv_screener_cache")
                  .select("poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                  .eq("symbol", symbol)
                  .eq("calc_date", calc_date.isoformat())
                  .limit(1)
                  .execute())
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        # Log silently, fallback to yfinance
        return None


def supabase_get_all_for_date(calc_date):
    """
    Saare stocks ka data ek saath fetch karo ek specific calc_date ke liye.
    Market-band read-only mode mein use hota hai (poori table ek Supabase call mein).
    
    Args:
        calc_date (datetime.date): Calculation date
    
    Returns:
        dict: {symbol: {poc_value, prev_high_val, ema_coil_pct, vol5d_median, 
                        crossover_status}, ...}
              ya empty dict agar kuch nahi mila
    """
    try:
        result = (supabase.table("tv_screener_cache")
                  .select("symbol, poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                  .eq("calc_date", calc_date.isoformat())
                  .execute())
        if result.data:
            return {row['symbol']: row for row in result.data}
        return {}
    except Exception as e:
        # Log silently, fallback to empty cache
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CACHE WRITE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def supabase_save_row(symbol, signal_date, calc_date, poc_value=None, prev_high_val=None,
                       ema_coil_pct=None, vol5d_median=None, crossover_status=None):
    """
    (symbol, calc_date) ke liye row upsert karo — agar already hai toh update, 
    warna naya insert karo. Partial save bhi support karta hai (sirf jo values diye 
    gaye hain woh update honge, baaki unchanged rahenge).
    
    IMPORTANT: Supabase ka upsert() poori row REPLACE karta hai un columns ke liye 
    jo payload mein missing hain (merge nahi karta apne-aap) — isliye pehle 
    EXISTING row fetch karke merge karte hain, taaki partial-save se dusre fields 
    accidentally NULL na ho jayein.
    
    Args:
        symbol (str): Stock symbol
        signal_date (datetime.date): Signal detection date (usually today)
        calc_date (datetime.date): Calculation reference date (usually yesterday)
        poc_value (float, optional): Point of Control price
        prev_high_val (float, optional): Previous day's high
        ema_coil_pct (float, optional): EMA coil percentage
        vol5d_median (float, optional): 5-day median volume
        crossover_status (str, optional): "09:15" / "09:20" / ""
    """
    try:
        # Step 1: Pehle existing row fetch karo (agar hai) — taaki merge kar sakein
        existing = None
        try:
            result = (supabase.table("tv_screener_cache")
                      .select("poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                      .eq("symbol", symbol)
                      .eq("calc_date", calc_date.isoformat())
                      .limit(1)
                      .execute())
            if result.data and len(result.data) > 0:
                existing = result.data[0]
        except:
            existing = None

        # Step 2: Merge logic — naya value diya gaya hai toh woh use karo, 
        # warna existing (agar hai) rakho, nahi toh None
        def merged(new_val, key):
            if new_val is not None:
                return new_val
            if existing is not None:
                return existing.get(key)
            return None

        # Step 3: Build final payload with merged values
        payload = {
            "symbol"          : symbol,
            "signal_date"     : signal_date.isoformat(),
            "calc_date"       : calc_date.isoformat(),
            "poc_value"       : merged(poc_value, "poc_value"),
            "prev_high_val"   : merged(prev_high_val, "prev_high_val"),
            "ema_coil_pct"    : merged(ema_coil_pct, "ema_coil_pct"),
            "vol5d_median"    : merged(vol5d_median, "vol5d_median"),
            "crossover_status": merged(crossover_status, "crossover_status"),
        }

        # Step 4: Upsert karo
        supabase.table("tv_screener_cache").upsert(payload, on_conflict="symbol,calc_date").execute()
        
        # Step 5: Track success in session_state (for diagnostics)
        if 'supabase_save_success_count' not in st.session_state:
            st.session_state['supabase_save_success_count'] = 0
        st.session_state['supabase_save_success_count'] += 1
        
    except Exception as e:
        # Step 5: Track error in session_state (fallback to session cache, app chalti rahe)
        if 'supabase_save_errors' not in st.session_state:
            st.session_state['supabase_save_errors'] = []
        st.session_state['supabase_save_errors'].append(f"{symbol}: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SESSION STATE CACHE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def init_session_caches():
    """
    Session-state caches initialize karo — fast in-memory storage jab app run ho.
    Supabase persistent cache ka supplement hai (faster access, session-specific).
    """
    if 'poc_cache' not in st.session_state:
        st.session_state['poc_cache'] = {}
    if 'crossover_cache' not in st.session_state:
        st.session_state['crossover_cache'] = {}
    if 'ema_cache' not in st.session_state:
        st.session_state['ema_cache'] = {}
    if 'vol5d_cache' not in st.session_state:
        st.session_state['vol5d_cache'] = {}
    if 'prevhigh_cache' not in st.session_state:
        st.session_state['prevhigh_cache'] = {}
    if 'candle_cache' not in st.session_state:
        st.session_state['candle_cache'] = {}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DIAGNOSTIC HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_supabase_stats():
    """
    Session ke liye Supabase save stats return karo — diagnostics ke liye.
    
    Returns:
        tuple: (success_count, errors_list)
    """
    success_count = st.session_state.get('supabase_save_success_count', 0)
    errors = st.session_state.get('supabase_save_errors', [])
    return success_count, errors

def reset_supabase_stats():
    """Session ke Supabase stats reset karo."""
    st.session_state['supabase_save_success_count'] = 0
    st.session_state['supabase_save_errors'] = []
