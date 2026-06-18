# ╔════════════════════════════════════════════════════════════╗
# ║         SUPABASE HANDLER - BACKEND CONFIGURATION            ║
# ║      All database operations for stock prices storage       ║
# ╚════════════════════════════════════════════════════════════╝

# ── SECTION 1: IMPORTS ────────────────────────────────────────
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import json


# ── SECTION 2: SUPABASE CREDENTIALS & CLIENT INITIALIZATION ───
# ⚠️ These credentials are your Anon Key (safe for frontend)
# Do NOT expose Service Role Key in frontend code

SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── SECTION 3: DATA EXTRACTION FUNCTION ───────────────────────
# Extract stock data from Streamlit session state (angel_ws.latest_ticks)

def extract_stock_data_from_websocket(ticks_dict, watchlist):
    """
    Convert WebSocket ticks dictionary to a list of dictionaries
    ready for Supabase insertion.
    
    Args:
        ticks_dict: Dictionary of ticks from angel_ws.latest_ticks
        watchlist: List of tuples (name, token, kind) from config.py
    
    Returns:
        List of dictionaries with stock data
    """
    rows = []
    
    for name, token, kind in watchlist:
        tick = ticks_dict.get(token, {})
        
        # Extract values with defaults if no data
        ltp = tick.get('ltp', 0)
        open_p = tick.get('open', 0)
        high_p = tick.get('high', 0)
        low_p = tick.get('low', 0)
        change = tick.get('change', 0)
        change_pct = tick.get('change_pct', 0)
        volume = tick.get('volume', 0)
        timestamp = tick.get('timestamp', '-')
        
        # Only include if we have LTP data
        if ltp > 0:
            rows.append({
                "stock": name,
                "type": "Index" if kind == "index" else "Stock",
                "ltp": float(ltp),
                "open": float(open_p),
                "high": float(high_p),
                "low": float(low_p),
                "change": float(change),
                "change_percent": float(change_pct),
                "volume": int(volume) if volume else 0,
                "time": str(timestamp)
            })
    
    return rows


# ── SECTION 4: DATA UPLOAD FUNCTION ───────────────────────────
# Insert/Update data to Supabase table

def upload_stocks_to_supabase(stock_data):
    """
    Upload stock data to Supabase 'websocket_stock_values' table.
    Uses UPSERT to avoid duplicate entries for the same stock on same day.
    
    Args:
        stock_data: List of dictionaries containing stock information
    
    Returns:
        Tuple: (success: bool, message: str, count: int)
    """
    
    if not stock_data:
        return False, "❌ No stock data to upload!", 0
    
    try:
        # Insert data into Supabase table
        response = supabase.table("websocket_stock_values").insert(stock_data).execute()
        
        # Check if insertion was successful
        if response.data:
            count = len(response.data)
            message = f"✅ Successfully uploaded {count} stocks to Supabase!"
            return True, message, count
        else:
            return False, "⚠️ Data inserted but no response received", len(stock_data)
    
    except Exception as error:
        # Catch and return specific error messages
        error_msg = str(error)
        
        if "duplicate key" in error_msg.lower():
            message = "⚠️ Some stocks already exist for today. Try again tomorrow or delete old entries."
        elif "connection" in error_msg.lower():
            message = "❌ Connection error! Check your internet or Supabase status."
        else:
            message = f"❌ Error: {error_msg}"
        
        return False, message, 0


# ── SECTION 5: DATA VERIFICATION FUNCTION ─────────────────────
# Check what's already in Supabase

def get_latest_stocks_from_supabase(limit=10):
    """
    Fetch latest stock records from Supabase for verification.
    
    Args:
        limit: Number of records to fetch (default: 10)
    
    Returns:
        List of dictionaries with stock data from database
    """
    
    try:
        response = supabase.table("websocket_stock_values") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        
        return response.data if response.data else []
    
    except Exception as error:
        st.error(f"Could not fetch data: {error}")
        return []


# ── SECTION 6: DATA DELETION FUNCTION (Optional - for testing) ─
# Delete records if needed for testing

def delete_stock_records(limit_hours=24):
    """
    Delete old stock records (useful for testing).
    
    Args:
        limit_hours: Delete records older than X hours
    
    Returns:
        Tuple: (success: bool, message: str)
    """
    
    try:
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(hours=limit_hours)
        
        response = supabase.table("websocket_stock_values") \
            .delete() \
            .lt("created_at", cutoff_time.isoformat()) \
            .execute()
        
        return True, f"✅ Deleted records older than {limit_hours} hours"
    
    except Exception as error:
        return False, f"❌ Delete error: {error}"


# ── END OF SUPABASE HANDLER ───────────────────────────────────
