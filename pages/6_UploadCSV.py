# ──────────────────────────────────────────────────────────────────────────────
# pages/6_UploadCSV.py (Modified with File Uploader)
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import sys
import os
from datetime import date

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
def upload_csv_data(df, test_mode=True):
    """Upload CSV data to Supabase"""
    
    try:
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
            # Upload in batches of 100
            batch_size = 100
            total = len(rows)
            
            for i in range(0, total, batch_size):
                batch = rows[i:i+batch_size]
                supabase.table("websocket_stock_values").insert(batch).execute()
                st.progress((i + batch_size) / total if i + batch_size < total else 1.0)
            
        return True, f"✅ Successfully uploaded {len(rows)} records!"
        
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# UI: Main Page
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
### 📂 Upload Historical Data

Upload your `swing_status_history_rows.csv` file and store data in Supabase.

**⚠️ Important:**
- Test mode will upload only **NATIONSTD & RELIANCE** first
- Full mode will upload **ALL stocks** in the CSV
- File must have these columns: `symbol, trade_date, close, volume, vol_ratio, vol_signal, status, open, high, low, created_at`
""")

# ── File Uploader ─────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "📁 Choose CSV file",
    type=['csv'],
    help="Upload your swing_status_history_rows.csv file"
)

if uploaded_file is not None:
    try:
        # Read CSV
        df = pd.read_csv(uploaded_file)
        st.success(f"✅ CSV loaded successfully!")
        
        # Show file info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Records", len(df))
        with col2:
            st.metric("Unique Stocks", df['symbol'].nunique())
        with col3:
            st.metric("Columns", len(df.columns))
        
        # Show sample data
        with st.expander("🔍 Preview CSV Data (First 5 rows)"):
            st.dataframe(df.head(5))
        
        # Check required columns
        required_cols = ['symbol', 'trade_date', 'close', 'volume', 'vol_ratio', 
                        'vol_signal', 'status', 'open', 'high', 'low', 'created_at']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"❌ Missing columns: {', '.join(missing_cols)}")
            st.stop()
        else:
            st.success("✅ All required columns present!")
        
        st.divider()
        
        # ── Upload Buttons ────────────────────────────────────────
        st.subheader("📤 Upload Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🧪 TEST: Upload NATIONSTD & RELIANCE", use_container_width=True, type="primary"):
                success, message = upload_csv_data(df, test_mode=True)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)
        
        with col2:
            confirm = st.checkbox("✅ I confirm I want to upload ALL stocks")
            if st.button("📤 FULL: Upload ALL Stocks", use_container_width=True, disabled=not confirm):
                success, message = upload_csv_data(df, test_mode=False)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)
        
        st.divider()
        
        # ── Check Today's Data ──────────────────────────────────
        with st.expander("📊 Check Today's Data in Supabase"):
            if st.button("🔄 Refresh Today's Data"):
                today = date.today().isoformat()
                
                response = supabase.table("websocket_stock_values")\
                                   .select("stock", "date", "ltp", "vol_signal", "status")\
                                   .eq("date", today)\
                                   .limit(20)\
                                   .execute()
                
                if response.data:
                    st.success(f"✅ Found {len(response.data)} records for {today}")
                    st.dataframe(pd.DataFrame(response.data))
                else:
                    st.warning(f"⚠️ No data found for {today}")
        
    except Exception as e:
        st.error(f"❌ Error reading CSV: {str(e)}")

else:
    st.info("👆 Upload your CSV file using the file uploader above.")
    
    # Show required columns format
    with st.expander("📋 Required CSV Format"):
        st.code("""
        symbol, trade_date, close, volume, vol_ratio, vol_signal, status, open, high, low, created_at
        NATIONSTD, 2026-06-17, 1250.0, 20, 1.0, 🔴 Weak, WATCH, 1202.3, 1250.0, 1202.3, 2026-06-18 03:03:23.271934+00
        RELIANCE, 2026-06-17, 1332.7, 10029170, 0.76, 🔴 Weak, WATCH, 1333.0, 1334.0, 1317.0, 2026-06-18 03:03:24.84838+00
        """)

st.divider()
st.caption("⚠️ This page is for temporary use. Remove this page after data upload.")
