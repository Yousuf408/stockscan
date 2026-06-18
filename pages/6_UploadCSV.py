# ──────────────────────────────────────────────────────────────────────────────
# pages/6_UploadCSV.py
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import sys
import os

# ── Make sure root folder is in path ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── SUPABASE IMPORTS ──────────────────────────────────────────
from supabase import create_client, Client

st.set_page_config(page_title="Upload CSV Data", page_icon="📤", layout="wide")
st.title("📤 Upload Historical CSV Data")

# ── SUPABASE CONFIGURATION ────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────────────────────────────────────
# FUNCTION: Upload CSV Data
# ──────────────────────────────────────────────────────────────────────────────
def upload_csv_data(csv_file_path, test_mode=True):
    """Upload CSV data to Supabase"""
    
    try:
        # Read CSV
        df = pd.read_csv(csv_file_path)
        st.write(f"📄 CSV has {len(df)} records")
        
        # TEST MODE: Only 2 stocks
        if test_mode:
            df = df[df['symbol'].isin(['NATIONSTD', 'RELIANCE'])]
            st.info(f"🔬 TEST MODE: Uploading {len(df)} records for NATIONSTD & RELIANCE only")
        else:
            st.info(f"📤 FULL MODE: Uploading {len(df)} records for ALL stocks")
        
        if df.empty:
            return False, "❌ No data to upload! Check if symbols exist."
        
        rows = []
        for _, row in df.iterrows():
            # Calculate change from open-close
            if row['close'] > 0 and row['open'] > 0:
                change = row['close'] - row['open']
                change_percent = (change / row['open']) * 100
            else:
                change = 0
                change_percent = 0
            
            rows.append({
                "stock": row['symbol'],
                "type": "Stock",
                "ltp": float(row['close']),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "volume": int(row['volume']),
                "time": pd.to_datetime(row['created_at']).strftime('%H:%M:%S'),
                "date": row['trade_date'],
                "created_at": row['created_at'],
                "vol_ratio": float(row['vol_ratio']),
                "vol_signal": row['vol_signal'],
                "status": row['status']
            })
        
        if not rows:
            return False, "❌ No rows to upload"
        
        # Upload to Supabase
        with st.spinner(f"Uploading {len(rows)} records..."):
            response = supabase.table("websocket_stock_values").insert(rows).execute()
            
        return True, f"✅ Successfully uploaded {len(rows)} records!"
        
    except FileNotFoundError:
        return False, f"❌ CSV file not found: {csv_file_path}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# UI: Main Page
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
### 📂 Upload Historical Data

This page will upload data from `swing_status_history_rows.csv` to Supabase.

**⚠️ Important:**
- CSV file must be in the **root folder** of your project
- File name: `swing_status_history_rows.csv`
- Test mode will upload only **NATIONSTD & RELIANCE** first
- Full mode will upload **ALL 850 stocks**
""")

# ── Check if CSV exists ──────────────────────────────────────
csv_path = "swing_status_history_rows.csv"

if os.path.exists(csv_path):
    st.success(f"✅ CSV found: {csv_path}")
    
    # Show sample data
    df_sample = pd.read_csv(csv_path)
    st.write(f"📊 Total records: {len(df_sample)}")
    st.write(f"📋 Columns: {', '.join(df_sample.columns)}")
    
    with st.expander("🔍 Preview CSV Data (First 5 rows)"):
        st.dataframe(df_sample.head(5))
    
    st.divider()
    
    # ── Upload Buttons ────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🧪 TEST: Upload NATIONSTD & RELIANCE", use_container_width=True, type="primary"):
            success, message = upload_csv_data(csv_path, test_mode=True)
            if success:
                st.success(message)
                st.balloons()
            else:
                st.error(message)
    
    with col2:
        if st.button("📤 FULL: Upload ALL Stocks", use_container_width=True):
            # Confirm before full upload
            if st.checkbox("✅ I confirm I want to upload ALL stocks"):
                success, message = upload_csv_data(csv_path, test_mode=False)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)
            else:
                st.warning("⚠️ Please check the box to confirm full upload.")
    
    with col3:
        if st.button("🗑️ Check Today's Data", use_container_width=True):
            from datetime import date
            today = date.today().isoformat()
            
            response = supabase.table("websocket_stock_values")\
                               .select("stock", "date", "ltp")\
                               .eq("date", today)\
                               .limit(10)\
                               .execute()
            
            if response.data:
                st.success(f"✅ Found {len(response.data)} records for today")
                st.dataframe(pd.DataFrame(response.data))
            else:
                st.warning(f"⚠️ No data found for {today}")
    
else:
    st.error(f"❌ CSV file not found: {csv_path}")
    st.info("""
    **Please ensure:**
    1. CSV file is in the root folder of your project
    2. File name is exactly: `swing_status_history_rows.csv`
    3. File has these columns: symbol, trade_date, close, volume, vol_ratio, vol_signal, status, open, high, low, created_at
    """)
    
    # Show current directory
    st.write(f"📁 Current directory: {os.getcwd()}")
    st.write("📂 Files in current directory:")
    for file in os.listdir():
        if file.endswith('.csv'):
            st.write(f"  - {file}")

st.divider()
st.caption("⚠️ This page is for temporary use. You can remove this page after data upload.")
