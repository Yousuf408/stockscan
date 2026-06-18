# ──────────────────────────────────────────────────────────────────────────────
# pages/6_UploadCSV.py - Complete Fixed Code with Date Conversion
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import sys
import os
from datetime import date, datetime, timedelta

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
def upload_csv_data(df, test_mode=True, specific_date=None):
    """Upload CSV data - Delete old, insert new with NaN handling"""
    
    try:
        # ── STEP 1: Filter data ──────────────────────────────────
        if specific_date:
            df = df[df['trade_date'] == specific_date]
            st.info(f"📅 Uploading data for {specific_date}")
            
            # Delete existing data for this date
            with st.spinner(f"🗑️ Deleting existing {specific_date} data..."):
                supabase.table("websocket_stock_values")\
                         .delete()\
                         .eq("date", specific_date)\
                         .execute()
            st.success(f"✅ {specific_date} data deleted!")
        else:
            st.info("📅 Uploading ALL data from CSV")
        
        if test_mode:
            df = df[df['symbol'].isin(['NATIONSTD', 'RELIANCE'])]
            st.info(f"🔬 TEST MODE: {len(df)} records")
        else:
            st.info(f"📤 FULL MODE: {len(df)} records")
        
        if df.empty:
            return False, "❌ No data to upload! Check if symbols exist."
        
        # ── STEP 2: Prepare rows with NaN handling ──────────────
        rows = []
        for _, row in df.iterrows():
            # Handle NaN values for all columns
            close_val = float(row['close']) if pd.notna(row['close']) else 0
            open_val = float(row['open']) if pd.notna(row['open']) else 0
            high_val = float(row['high']) if pd.notna(row['high']) else 0
            low_val = float(row['low']) if pd.notna(row['low']) else 0
            volume_val = int(row['volume']) if pd.notna(row['volume']) else 0
            vol_ratio_val = float(row['vol_ratio']) if pd.notna(row['vol_ratio']) else 0
            
            # Calculate change
            if close_val > 0 and open_val > 0:
                change = close_val - open_val
                change_percent = (change / open_val) * 100
            else:
                change = 0
                change_percent = 0
            
            # Handle time
            if pd.notna(row['created_at']):
                time_str = pd.to_datetime(row['created_at']).strftime('%H:%M:%S')
            else:
                time_str = "00:00:00"
            
            rows.append({
                "stock": row['symbol'],
                "type": "Stock",
                "ltp": close_val,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "volume": volume_val,
                "time": time_str,
                "date": row['trade_date'],  # Already in YYYY-MM-DD format
                "created_at": row['created_at'] if pd.notna(row['created_at']) else datetime.now().isoformat(),
                "vol_ratio": vol_ratio_val,
                "vol_signal": row['vol_signal'] if pd.notna(row['vol_signal']) else "🔴 Weak",
                "status": row['status'] if pd.notna(row['status']) else "WATCH"
            })
        
        if not rows:
            return False, "❌ No rows to upload"
        
        # ── STEP 3: Upload in batches ──────────────────────────
        with st.spinner(f"Uploading {len(rows)} records..."):
            batch_size = 100
            total = len(rows)
            progress_bar = st.progress(0)
            
            for i in range(0, total, batch_size):
                batch = rows[i:i+batch_size]
                supabase.table("websocket_stock_values").insert(batch).execute()
                progress_bar.progress(min((i + batch_size) / total, 1.0))
        
        date_str = specific_date if specific_date else "ALL dates"
        return True, f"✅ Successfully uploaded {len(rows)} records for {date_str}!"
        
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# UI: Main Page
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
### 📂 Upload Historical Data

Upload your CSV file and store data in Supabase.

**⚠️ Important:**
- Test mode will upload only **NATIONSTD & RELIANCE**
- Full mode will upload **ALL stocks**
- File must have columns: `symbol, trade_date, close, volume, vol_ratio, vol_signal, status, open, high, low, created_at`
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
        
        # 🔥 FIX 1: Convert trade_date to proper format
        # Try different date formats
        try:
            # Try DD-MM-YYYY format first (e.g., 15-06-2026)
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%d-%m-%Y').dt.strftime('%Y-%m-%d')
            st.info("✅ Date format detected: DD-MM-YYYY")
        except:
            try:
                # Try YYYY-MM-DD format (e.g., 2026-06-15)
                df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
                st.info("✅ Date format detected: YYYY-MM-DD")
            except:
                try:
                    # Try DD/MM/YYYY format (e.g., 15/06/2026)
                    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%d/%m/%Y').dt.strftime('%Y-%m-%d')
                    st.info("✅ Date format detected: DD/MM/YYYY")
                except:
                    # Fallback: convert to string and clean
                    df['trade_date'] = df['trade_date'].astype(str).str.replace('.0', '').str.strip()
                    st.info("✅ Date format detected: String format")
        
        st.success(f"✅ CSV loaded successfully!")
        
        # Show file info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Records", len(df))
        with col2:
            st.metric("Unique Stocks", df['symbol'].nunique())
        with col3:
            st.metric("Unique Dates", df['trade_date'].nunique())
        
        # Show available dates
        available_dates = sorted(df['trade_date'].unique())
        st.write(f"📅 Dates available: {', '.join(available_dates[:5])}{'...' if len(available_dates) > 5 else ''}")
        
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
        
        # Data quality check
        with st.expander("📊 Data Quality Check"):
            null_volume = df['volume'].isna().sum()
            null_close = df['close'].isna().sum()
            null_open = df['open'].isna().sum()
            
            st.write(f"📊 Records with null volume: {null_volume}")
            st.write(f"📊 Records with null close: {null_close}")
            st.write(f"📊 Records with null open: {null_open}")
            
            if null_volume > 0:
                st.warning(f"⚠️ {null_volume} records have missing volume. Will be set to 0.")
        
        st.divider()
        
        # ── Upload Options ──────────────────────────────────────
        st.subheader("📤 Upload Options")
        
        # Select date to upload
        selected_date = st.selectbox(
            "📅 Select date to upload (or 'ALL' for all dates)",
            ['ALL'] + available_dates
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🧪 TEST: Upload 2 Stocks", use_container_width=True, type="primary"):
                date_filter = None if selected_date == 'ALL' else selected_date
                success, message = upload_csv_data(df, test_mode=True, specific_date=date_filter)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)
        
        with col2:
            confirm = st.checkbox("✅ I confirm: Delete existing data and upload fresh")
            if st.button("📤 FULL: Upload ALL Stocks", use_container_width=True, disabled=not confirm):
                date_filter = None if selected_date == 'ALL' else selected_date
                success, message = upload_csv_data(df, test_mode=False, specific_date=date_filter)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)
        
        st.divider()
        
        # ── Check Today's Data ──────────────────────────────────
        with st.expander("📊 Check Data in Supabase"):
            date_to_check = st.date_input("Select date to check", value=date.today())
            date_str = date_to_check.isoformat()
            
            if st.button("🔄 Refresh Data"):
                response = supabase.table("websocket_stock_values")\
                                   .select("stock", "date", "ltp", "vol_signal", "status")\
                                   .eq("date", date_str)\
                                   .limit(20)\
                                   .execute()
                
                if response.data:
                    st.success(f"✅ Found {len(response.data)} records for {date_str}")
                    st.dataframe(pd.DataFrame(response.data))
                    
                    # Show count
                    count_res = supabase.table("websocket_stock_values")\
                                       .select("stock", count="exact")\
                                       .eq("date", date_str)\
                                       .execute()
                    st.metric("Total records for this date", count_res.count)
                else:
                    st.warning(f"⚠️ No data found for {date_str}")
        
    except Exception as e:
        st.error(f"❌ Error reading CSV: {str(e)}")
        st.info("💡 Make sure date column has proper format (YYYY-MM-DD or DD-MM-YYYY)")

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
