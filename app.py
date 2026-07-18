import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# ================================================================
# 1. SET PAGE CONFIG – MUST BE FIRST
# ================================================================
st.set_page_config(page_title="Margin Calculator", layout="wide")

# ================================================================
# 2. MSTOCK CONFIG (replace with your key)
# ================================================================
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_AVAILABLE = False

try:
    from Mconnect import Mconnect
    mconnect_obj = Mconnect()
    mconnect_obj.set_jwt_token(MSTOCK_API_KEY)
    MSTOCK_AVAILABLE = True
except:
    pass

# ================================================================
# 3. AUTO-DETECT STOCKS FROM YOUR DASHBOARD URL
# ================================================================
def scrape_stock_symbols_from_url(url):
    """
    Fetches the webpage and extracts stock symbols from the first column of a table.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        symbols = []
        
        # Method 1: Look for <td> in first column (your dashboard style)
        rows = soup.select('table tbody tr')
        for row in rows:
            first_cell = row.find('td')
            if first_cell:
                text = first_cell.get_text(strip=True)
                # Match stock symbols: 2-5 uppercase letters
                if re.match(r'^[A-Z]{2,5}$', text):
                    symbols.append(text)
        
        # Method 2: If no table rows found, look for elements with stock-symbol class
        if not symbols:
            for el in soup.select('[data-symbol], .symbol, .stock-symbol'):
                text = el.get_text(strip=True)
                if re.match(r'^[A-Z]{2,5}$', text):
                    symbols.append(text)
        
        return list(dict.fromkeys(symbols))  # remove duplicates
    except Exception as e:
        st.warning(f"Could not auto-fetch from URL: {e}")
        return []

# ================================================================
# 4. MARGIN CALCULATION FUNCTION
# ================================================================
def get_margin_data(stock_symbols):
    """Fetch price, margin, leverage, max quantity for each stock."""
    capital = 10000.0  # default mock
    if MSTOCK_AVAILABLE:
        try:
            funds = mconnect_obj.get_fund_summary()
            capital = float(funds['data'][0]['MTF_AVAILABLE_BALANCE'])
        except:
            pass

    results = []
    for sym in stock_symbols:
        sym = sym.strip().upper()
        if not sym:
            continue
        try:
            if MSTOCK_AVAILABLE:
                quote = mconnect_obj.get_lttp(sym)
                price = float(quote['data']['ltp'])
                margin_data = mconnect_obj.calculate_order_margin(
                    exchange="NSE", trading_symbol=sym, transaction_type="BUY",
                    product_type="MIS", order_type="MARKET", quantity="1",
                    price="0", trigger_price="0"
                )
                margin_per_share = float(margin_data['data']['total'])
            else:
                import random
                price = round(random.uniform(50, 5000), 2)
                margin_per_share = round(price * random.uniform(0.2, 0.5), 2)

            leverage = price / margin_per_share
            buying_power = capital * leverage
            max_qty = int(buying_power / price)

            results.append({
                'Symbol': sym, 'Price (₹)': price, 'Margin/Share (₹)': margin_per_share,
                'Leverage (x)': round(leverage, 1), 'Buying Power (₹)': round(buying_power, 2),
                'Max Qty': max_qty, 'Status': '✅ Ready'
            })
        except Exception as e:
            results.append({
                'Symbol': sym, 'Price (₹)': 'Error', 'Margin/Share (₹)': '-',
                'Leverage (x)': '-', 'Buying Power (₹)': '-', 'Max Qty': '-',
                'Status': f'❌ {str(e)[:30]}'
            })
    return results, capital

# ================================================================
# 5. STREAMLIT UI
# ================================================================
st.title("🚀 Live Margin Calculator")

# --- Sidebar: Auto-Fetch or Manual Entry ---
with st.sidebar:
    st.header("📊 Stock Sources")
    
    # Option 1: Auto-fetch from URL
    st.subheader("🌐 Auto-Fetch from Dashboard")
    dashboard_url = st.text_input("Enter your dashboard URL:", placeholder="https://your-trading-dashboard.com")
    if st.button("🔍 Auto-Detect Stocks", type="primary"):
        if dashboard_url:
            with st.spinner("Scraping stock symbols..."):
                scraped = scrape_stock_symbols_from_url(dashboard_url)
                if scraped:
                    st.success(f"✅ Found {len(scraped)} stocks!")
                    st.session_state['stock_list'] = scraped
                    st.session_state['auto_detected'] = True
                else:
                    st.warning("No symbols found. Enter manually below.")
        else:
            st.warning("Please enter a URL.")
    
    st.markdown("---")
    
    # Option 2: Manual Entry (fallback)
    st.subheader("✏️ Manual Entry")
    default_stocks = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    
    # If auto-detected, use that list, else default
    if 'stock_list' in st.session_state and st.session_state.get('auto_detected'):
        default_val = ", ".join(st.session_state['stock_list'])
    else:
        default_val = default_stocks
    
    stock_input = st.text_area(
        "Stock symbols (comma or newline):",
        value=default_val,
        height=150,
        key="stock_input_area"
    )
    
    fetch_btn = st.button("🔄 Fetch Margins", type="primary")
    st.caption("Powered by mStock API")
    
    if not MSTOCK_AVAILABLE:
        st.warning("⚠️ mStock SDK not installed – using mock data.")

# --- Main Area ---
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📈 Margin & Leverage")
with col2:
    capital_placeholder = st.empty()

if fetch_btn:
    # Parse symbols from the text area
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    
    if not symbols:
        st.warning("No stocks to fetch. Enter symbols or auto-detect.")
        st.stop()
    
    with st.spinner("Calculating margins..."):
        data, capital = get_margin_data(symbols)
    
    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")
    df = pd.DataFrame(data)
    
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", width="small"),
            "Price (₹)": st.column_config.NumberColumn("Price", format="₹%.2f"),
            "Margin/Share (₹)": st.column_config.NumberColumn("Margin/Share", format="₹%.2f"),
            "Leverage (x)": st.column_config.NumberColumn("Leverage", format="%.1fx"),
            "Buying Power (₹)": st.column_config.NumberColumn("Buying Power", format="₹%.2f"),
            "Max Qty": st.column_config.NumberColumn("Max Qty", format="%d"),
            "Status": st.column_config.TextColumn("Status"),
        },
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("📦 Place Order (Simulation)")
    for idx, row in df.iterrows():
        if row['Status'] == '✅ Ready':
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                st.write(f"**{row['Symbol']}**")
            with c2:
                qty = st.number_input("Qty", min_value=1, max_value=row['Max Qty'], value=row['Max Qty'], key=f"qty_{idx}")
            with c3:
                if st.button(f"Buy {row['Symbol']}", key=f"buy_{idx}"):
                    st.success(f"✅ Order placed: {row['Symbol']} {qty} shares (Simulation)")
else:
    st.info("👈 Enter symbols or auto-fetch from your dashboard URL, then click **Fetch Margins**.")
    st.dataframe(pd.DataFrame(columns=['Symbol', 'Price (₹)', 'Margin/Share (₹)', 'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status']))

st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
