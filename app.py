import streamlit as st
import pandas as pd
import time
from datetime import datetime

# ------------------------------------------------------------------
# 1. CONFIGURE MSTOCK CONNECTION (replace with your credentials)
# ------------------------------------------------------------------
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="  # generate from mStock dashboard

# If you don't have the SDK installed, use mock data for testing.
try:
    from Mconnect import Mconnect
    mconnect_obj = Mconnect()
    mconnect_obj.set_jwt_token(MSTOCK_API_KEY)
    MSTOCK_AVAILABLE = True
except ImportError:
    MSTOCK_AVAILABLE = False
    st.warning("mStock SDK not installed. Using mock data for demonstration.")
except Exception as e:
    MSTOCK_AVAILABLE = False
    st.warning(f"mStock connection failed: {e}. Using mock data.")

# ------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# ------------------------------------------------------------------
def get_margin_data(stock_symbols):
    """
    For each stock, fetch price, margin, leverage, and max quantity.
    Returns a list of dicts and the available capital.
    """
    # Get available capital (if real API, else mock)
    if MSTOCK_AVAILABLE:
        try:
            funds = mconnect_obj.get_fund_summary()
            capital = float(funds['data'][0]['MTF_AVAILABLE_BALANCE'])
        except:
            capital = 10000.0  # fallback
    else:
        capital = 10000.0  # mock

    results = []
    for sym in stock_symbols:
        sym = sym.strip().upper()
        if not sym:
            continue

        try:
            if MSTOCK_AVAILABLE:
                # Real API calls
                quote = mconnect_obj.get_lttp(sym)
                price = float(quote['data']['ltp'])

                margin_data = mconnect_obj.calculate_order_margin(
                    exchange="NSE",
                    trading_symbol=sym,
                    transaction_type="BUY",
                    product_type="MIS",
                    order_type="MARKET",
                    quantity="1",
                    price="0",
                    trigger_price="0"
                )
                margin_per_share = float(margin_data['data']['total'])
            else:
                # Mock data for testing
                import random
                price = round(random.uniform(50, 5000), 2)
                margin_per_share = round(price * random.uniform(0.2, 0.5), 2)

            # Calculate leverage and max quantity
            leverage = price / margin_per_share
            buying_power = capital * leverage
            max_qty = int(buying_power / price)

            results.append({
                'Symbol': sym,
                'Price (₹)': price,
                'Margin/Share (₹)': margin_per_share,
                'Leverage (x)': round(leverage, 1),
                'Buying Power (₹)': round(buying_power, 2),
                'Max Qty': max_qty,
                'Status': '✅ Ready'
            })
        except Exception as e:
            results.append({
                'Symbol': sym,
                'Price (₹)': 'Error',
                'Margin/Share (₹)': '-',
                'Leverage (x)': '-',
                'Buying Power (₹)': '-',
                'Max Qty': '-',
                'Status': f'❌ {str(e)[:30]}'
            })

    return results, capital

# ------------------------------------------------------------------
# 3. STREAMLIT UI
# ------------------------------------------------------------------
st.set_page_config(page_title="Margin Calculator", layout="wide")
st.title("🚀 Live Margin Calculator")
st.markdown("---")

# Sidebar: Input stocks
with st.sidebar:
    st.header("📊 Stock Selection")
    # Default list from your screenshot
    default_stocks = "GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC"
    stock_input = st.text_area(
        "Enter stock symbols (comma or newline separated):",
        value=default_stocks,
        height=150
    )
    fetch_btn = st.button("🔄 Fetch Margins", type="primary")
    st.markdown("---")
    st.caption("Powered by mStock API")

# Main area
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📈 Margin & Leverage")
with col2:
    capital_placeholder = st.empty()

if fetch_btn:
    # Parse stock symbols
    symbols = [s.strip().upper() for s in stock_input.replace(',', ' ').split() if s.strip()]
    if not symbols:
        st.warning("Please enter at least one stock symbol.")
        st.stop()

    with st.spinner("Fetching margin data..."):
        # Call the function
        data, capital = get_margin_data(symbols)

    # Display capital
    capital_placeholder.metric("💰 Available Capital", f"₹{capital:,.2f}")

    # Create DataFrame
    df = pd.DataFrame(data)

    # Style and display
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

    # Simple Buy button (simulated) for each row
    st.markdown("---")
    st.subheader("📦 Place Order (Simulation)")
    for idx, row in df.iterrows():
        if row['Status'] == '✅ Ready':
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                st.write(f"**{row['Symbol']}**")
            with col2:
                qty = st.number_input(f"Qty", min_value=1, max_value=row['Max Qty'], value=row['Max Qty'], key=f"qty_{idx}")
            with col3:
                if st.button(f"Buy {row['Symbol']}", key=f"buy_{idx}"):
                    st.success(f"✅ Order placed: {row['Symbol']} {qty} shares at ₹{row['Price (₹)']:.2f} (Simulation)")

else:
    st.info("👈 Enter stock symbols in the sidebar and click **Fetch Margins**.")
    # Show a sample table (empty)
    st.dataframe(pd.DataFrame(columns=['Symbol', 'Price (₹)', 'Margin/Share (₹)', 'Leverage (x)', 'Buying Power (₹)', 'Max Qty', 'Status']))

# ------------------------------------------------------------------
# 4. FOOTER
# ------------------------------------------------------------------
st.markdown("---")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
