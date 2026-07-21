# ─── DEFAULT NIFTY 50 SYMBOLS ───
NIFTY50_SYMBOLS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
    'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT',
    'AXISBANK', 'HINDUNILVR', 'BAJFINANCE', 'MARUTI', 'SUNPHARMA',
    'TITAN', 'WIPRO', 'HCLTECH', 'ASIANPAINT', 'NESTLEIND',
    'ULTRACEMCO', 'POWERGRID', 'NTPC', 'M&M', 'BAJAJFINSV',
    'TECHM', 'ONGC', 'COALINDIA', 'ADANIPORTS', 'GRASIM',
    'JSWSTEEL', 'TATASTEEL', 'DRREDDY', 'CIPLA', 'APOLLOHOSP',
    'EICHERMOT', 'HDFCLIFE', 'SBILIFE', 'DIVISLAB', 'BRITANNIA',
    'HEROMOTOCO', 'BAJAJ-AUTO', 'INDUSINDBK', 'TATAMOTORS', 'BPCL',
    'HINDALCO', 'SHREECEM', 'ADANIENT', 'BEL', 'TRENT'
]


def render_backtest_page():
    st.markdown("""
    <div style="padding:1rem 0;">
        <h2 style="color:#1a1a2e;">📊 Strategy Backtest</h2>
        <p style="color:#888;">Inside 9:15 Strategy - Historical Performance</p>
    </div>
    """, unsafe_allow_html=True)

    # Strategy Summary
    with st.expander("📋 Strategy Rules", expanded=False):
        st.markdown("""
        | Rule | Value |
        |------|-------|
        | Entry | Price > 9:15 High + 0.15% |
        | Stop Loss | 9:20 Low |
        | Target | 1:1.5 Risk-Reward |
        | Max Hold | EOD (3:15 PM) |
        | 200 EMA Filter | Price must be above 200 EMA |
        """)

    # Symbol Selection
    st.markdown("### Select Stocks")
    col1, col2 = st.columns([3, 1])
    with col1:
        symbols_input = st.text_area(
            "Enter NSE symbols (comma separated)",
            value=", ".join(NIFTY50_SYMBOLS),
            height=80
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)

    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

    if run_btn:
        if not symbols:
            st.warning("Please enter at least one symbol")
        else:
            all_trades = []
            errors = []
            progress = st.progress(0)
            status = st.empty()

            for i, symbol in enumerate(symbols):
                status.text(f"Testing {symbol} ({i+1}/{len(symbols)})...")
                trades = backtest_single_stock(symbol)
                if trades:
                    all_trades.extend(trades)
                else:
                    errors.append(symbol)
                progress.progress((i + 1) / len(symbols))

            status.empty()

            if not all_trades:
                st.warning("No trades found")
            else:
                trades_df = pd.DataFrame(all_trades)

                # Summary
                st.markdown("---")
                st.markdown("### 📊 Results Summary")
                total = len(trades_df)
                winners = trades_df[trades_df['P&L'] > 0]
                losers = trades_df[trades_df['P&L'] <= 0]
                win_rate = (len(winners) / total * 100) if total > 0 else 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Trades", total)
                c2.metric("Win Rate", f"{win_rate:.1f}%")
                c3.metric("Total P&L", f"₹{trades_df['P&L'].sum():,.2f}")
                c4.metric("Avg P&L", f"₹{trades_df['P&L'].mean():,.2f}")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Winners", len(winners))
                c2.metric("Losers", len(losers))
                c3.metric("Target Hits", len(trades_df[trades_df['Result']=='TARGET']))
                c4.metric("SL Hits", len(trades_df[trades_df['Result']=='SL']))

                # Trade table
                st.markdown("### 📋 All Trades")
                def color_pnl(val):
                    return 'color:green' if (isinstance(val,(int,float)) and val>0) else 'color:red'
                st.dataframe(trades_df.style.applymap(color_pnl, subset=['P&L','P&L%']))

                csv = trades_df.to_csv(index=False)
                st.download_button("📥 Download CSV", csv, "backtest_results.csv")

                if errors:
                    st.caption(f"⚠️ No trades: {', '.join(errors)}")
