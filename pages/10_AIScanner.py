"""
10_AIScanner.py
TradeSentry AI Pattern Scanner — Streamlit Dashboard
Visualizes AI spike predictions, pattern insights, accuracy log, and retraining.
"""

import sys
import os
import sqlite3
import json
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

# Resolve paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import AI Engine components dynamically
import ai_pattern_engine

# ─────────────────────────────────────────────────────────────
# STREAMLIT PAGE SETUP
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Pattern Scanner",
    page_icon="🤖",
    layout="wide"
)

# Custom premium styling
st.markdown("""
    <style>
    header {visibility: hidden;}
    .block-container {padding-top: 1rem !important;}
    
    /* Modern Glassmorphic Cards */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(226, 232, 240, 0.1);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
    }
    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #10b981;
        margin-bottom: 4px;
    }
    .metric-label {
        font-size: 13px;
        color: #64748b;
        font-weight: 500;
    }
    
    /* AI Table Styling */
    .ai-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        font-family: 'Inter', sans-serif;
    }
    .ai-table th {
        background: #0f172a;
        color: #f8fafc;
        font-weight: 600;
        padding: 12px 10px;
        text-align: left;
        border-bottom: 2px solid #334155;
    }
    .ai-table td {
        padding: 10px;
        border-bottom: 1px solid #e2e8f0;
    }
    .ai-table tr:hover {
        background: rgba(241, 245, 249, 0.6) !important;
    }
    
    /* Stage Badges */
    .badge {
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 11px;
        display: inline-block;
    }
    .badge-prime { background: #dcfce7; color: #15803d; }
    .badge-watch { background: #fef9c3; color: #a16207; }
    .badge-build { background: #dbeafe; color: #1d4ed8; }
    .badge-early { background: #f1f5f9; color: #475569; }
    
    .copy-btn {
        cursor: pointer;
        font-weight: 700;
        color: #0f172a;
        background: #e2e8f0;
        border: none;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        transition: all 0.2s;
    }
    .copy-btn:hover { background: #10b981; color: white; }
    
    .toast {
        position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
        background: #0f172a; color: white; padding: 8px 20px;
        border-radius: 8px; font-size: 12px; z-index: 9999;
        opacity: 0; transition: opacity 0.3s; pointer-events: none;
    }
    .toast.show { opacity: 1; }
    </style>
    <div id="toast" class="toast">✅ Symbol Copied to Clipboard!</div>
    <script>
    function copySymbol(btn, symbol) {
        navigator.clipboard.writeText(symbol);
        btn.innerText = '✓ ' + symbol;
        btn.style.background = '#10b981';
        btn.style.color = 'white';
        var toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(function() {
            btn.innerText = symbol;
            btn.style.background = '#e2e8f0';
            btn.style.color = '#0f172a';
            toast.classList.remove('show');
        }, 1200);
    }
    </script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# DB UTILITIES
# ─────────────────────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(ai_pattern_engine.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_latest_predictions():
    conn = get_db_connection()
    # Find latest date
    latest_date_row = conn.execute("SELECT MAX(date) as max_date FROM predictions").fetchone()
    if not latest_date_row or not latest_date_row["max_date"]:
        conn.close()
        return pd.DataFrame(), None
        
    latest_date = latest_date_row["max_date"]
    
    # Fetch rows
    rows = conn.execute("""
        SELECT symbol, probability, stage, features, actual_max_return, outcome 
        FROM predictions 
        WHERE date = ? 
        ORDER BY probability DESC
    """, (latest_date,)).fetchall()
    
    conn.close()
    
    df = pd.DataFrame([dict(r) for r in rows])
    return df, latest_date

def load_metrics():
    conn = get_db_connection()
    metrics = conn.execute("""
        SELECT date, accuracy, precision, recall, total_samples 
        FROM model_metrics 
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    
    # Calculate overall resolved track record
    resolved = conn.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END) as hits,
               SUM(CASE WHEN outcome = 0 THEN 1 ELSE 0 END) as misses
        FROM predictions 
        WHERE outcome IS NOT NULL
    """).fetchone()
    
    conn.close()
    return dict(metrics) if metrics else None, dict(resolved) if resolved else None

def load_feature_importances():
    conn = get_db_connection()
    rows = conn.execute("SELECT feature_name, importance FROM feature_importances ORDER BY importance DESC").fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])

# ─────────────────────────────────────────────────────────────
# RENDER HTML TABLE FOR PREDICTIONS
# ─────────────────────────────────────────────────────────────
def render_predictions_table(df):
    if df.empty:
        return "<p style='text-align:center; color:#64748b;'>No predictions available yet.</p>"
        
    html = """
    <table class="ai-table">
    <thead>
        <tr>
            <th>Symbol</th>
            <th>AI Probability</th>
            <th>Stage</th>
            <th>20 EMA Dist</th>
            <th>Vol vs 5d Avg</th>
            <th>1d Vol Ratio</th>
            <th>1d Px Chg</th>
            <th>Body Ratio</th>
        </tr>
    </thead>
    <tbody>
    """
    
    for _, row in df.iterrows():
        prob = row["probability"]
        stage = row["stage"]
        symbol = row["symbol"]
        
        # Parse features from JSON
        features = {}
        try:
            features = json.loads(row["features"])
        except Exception:
            pass
            
        dist_ema20 = features.get("dist_to_ema20", 0.0)
        vol_5d = features.get("vol_vs_5d_avg", 1.0)
        vol_1d = features.get("vol_ratio_1d", 1.0)
        px_chg = features.get("price_change_1d", 0.0)
        body = features.get("body_ratio", 0.5)
        
        # Class styling for badge
        badge_class = "badge-early"
        if stage == "🚀 PRIME_AI":
            badge_class = "badge-prime"
        elif stage == "🔴 WATCH_AI":
            badge_class = "badge-watch"
        elif stage == "📈 BUILD_AI":
            badge_class = "badge-build"
            
        # Color mapping for price change
        px_color = "#ef4444" if px_chg < 0 else ("#10b981" if px_chg > 0 else "#64748b")
        
        html += f"""
        <tr>
            <td><button class="copy-btn" onclick="copySymbol(this, '{symbol}')">{symbol}</button></td>
            <td><strong>{prob:.1f}%</strong></td>
            <td><span class="badge {badge_class}">{stage}</span></td>
            <td>{dist_ema20:+.2f}%</td>
            <td>{vol_5d:.2f}x</td>
            <td>{vol_1d:.2f}x</td>
            <td style="color:{px_color}; font-weight:600;">{px_chg:+.2f}%</td>
            <td>{body:.2f}</td>
        </tr>
        """
        
    html += "</tbody></table>"
    return html

# ─────────────────────────────────────────────────────────────
# STREAMLIT UI LAYOUT
# ─────────────────────────────────────────────────────────────
st.title("🤖 AI Pattern Scanner")
st.caption("Self-Learning Machine Learning Engine — Predicts breakouts and spikes >= 5% using 20 EMA and Volume DNA")

# Load initial data
df_preds, latest_date = load_latest_predictions()
metrics, track_record = load_metrics()

# Top Navigation / Stats bar
if metrics:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['accuracy']:.1%}</div>
                <div class="metric-label">Model Accuracy (Test Set)</div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        hit_rate = 0.0
        if track_record and track_record['total'] > 0:
            hit_rate = track_record['hits'] / track_record['total']
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{hit_rate:.1%}</div>
                <div class="metric-label">Live Hit Rate (Spike >= 5%)</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{latest_date if latest_date else 'N/A'}</div>
                <div class="metric-label">Latest Data Date</div>
            </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['total_samples']}</div>
                <div class="metric-label">Trained Patterns Count</div>
            </div>
        """, unsafe_allow_html=True)

st.divider()

# Create Tabs
tab_preds, tab_insights, tab_track, tab_compare, tab_retrain = st.tabs([
    "🎯 Today's AI Predictions",
    "📊 What AI Learned (Insights)",
    "📈 Track Record (Accuracy)",
    "⚖️ Compare AI vs Rules",
    "🔄 Model Retrain & Status"
])

# ─────────────────────────────────────────────────────────────
# TAB 1: TODAY'S PREDICTIONS
# ─────────────────────────────────────────────────────────────
with tab_preds:
    if df_preds.empty:
        st.info("No predictions found in the database. Go to the 'Model Retrain' tab to train and run predictions.")
    else:
        st.subheader(f"Breakout Predictions for {latest_date}")
        
        # Sub filters
        col_filter, col_sort = st.columns([3, 1])
        with col_filter:
            stage_filter = st.multiselect(
                "Filter by AI Confidence Stage:",
                options=["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI", "📍 EARLY_AI"],
                default=["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI"]
            )
        with col_sort:
            prob_threshold = st.slider("Min Probability %:", min_value=0.0, max_value=100.0, value=40.0)
            
        # Apply filters
        df_filtered = df_preds[
            df_preds["stage"].isin(stage_filter) & 
            (df_preds["probability"] >= prob_threshold)
        ]
        
        if df_filtered.empty:
            st.warning("No stocks match the selected confidence filters.")
        else:
            st.markdown(f"Found **{len(df_filtered)} stocks** with active consolidation patterns matching your filter:")
            
            # Render custom HTML table
            st.components.v1.html(
                render_predictions_table(df_filtered),
                height=min(600, 60 + len(df_filtered) * 44),
                scrolling=True
            )
            
            # Interactive details expander
            st.subheader("💡 Deep Dive: Stock Pattern Details")
            selected_stock = st.selectbox("Select stock to inspect why AI predicted it:", df_filtered["symbol"].tolist())
            
            if selected_stock:
                stock_row = df_filtered[df_filtered["symbol"] == selected_stock].iloc[0]
                features_dict = json.loads(stock_row["features"])
                
                col_sub1, col_sub2 = st.columns(2)
                with col_sub1:
                    st.metric("AI Confidence of >= 5% Spike", f"{stock_row['probability']:.1f}%")
                    st.write("**Pattern Analysis Checklist:**")
                    
                    # Distance to 20 EMA interpretation
                    dist_20 = features_dict.get("dist_to_ema20", 0.0)
                    if abs(dist_20) <= 1.5:
                        st.success(f"✅ Price is extremely close to 20 EMA ({dist_20:+.2f}%) — Perfect Pullback Setup!")
                    elif dist_20 > 0:
                        st.info(f"📈 Price is hovering above 20 EMA ({dist_20:+.2f}%) — Standard Bullish Trend.")
                    else:
                        st.warning(f"⚠️ Price is below 20 EMA ({dist_20:+.2f}%) — Downtrend risk.")
                        
                    # Volume relative to 5d Average
                    vol_5d = features_dict.get("vol_vs_5d_avg", 1.0)
                    if vol_5d < 0.8:
                        st.success(f"✅ Volume Dry-up confirmed ({vol_5d:.2f}x of 5d average) — Dry Consolidation!")
                    elif vol_5d > 1.5:
                        st.info(f"⚡ High Volume activity ({vol_5d:.2f}x of 5d average) — Buildup phase.")
                        
                with col_sub2:
                    st.write("**Technical Parameters Read by AI:**")
                    for k, v in features_dict.items():
                        st.write(f"- `{k}`: **{v:+.4f}**" if isinstance(v, float) else f"- `{k}`: **{v}**")

# ─────────────────────────────────────────────────────────────
# TAB 2: WHAT AI LEARNED (FEATURE INSIGHTS)
# ─────────────────────────────────────────────────────────────
with tab_insights:
    st.subheader("📊 What features matter most to predict spikes?")
    st.write("This chart shows the exact weight our AI model puts on each technical pattern to predict if a stock will spike >= 5%.")
    
    df_imp = load_feature_importances()
    if df_imp.empty:
        st.info("No feature importances found. Retrain the model to compute insights.")
    else:
        # Plot Plotly chart
        fig = px.bar(
            df_imp,
            x="importance",
            y="feature_name",
            orientation="h",
            labels={"importance": "Importance Score", "feature_name": "Technical Pattern / Feature"},
            color="importance",
            color_continuous_scale="Viridis",
            height=400
        )
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
        
        # Summary Interpretation
        top_feature = df_imp.iloc[0]["feature_name"]
        st.markdown(f"""
        ### 📖 Translation (Plain English Summary)
        - The most critical pattern for predicting breakout spikes is **`{top_feature}`**.
        - When the **20 EMA distance** is close and **Volume drops significantly (dry-up)** compared to the 5-day average, the ML model clusters these as the highest-probability entries.
        """)

# ─────────────────────────────────────────────────────────────
# TAB 3: TRACK RECORD & ACCURACY LOG
# ─────────────────────────────────────────────────────────────
with tab_track:
    st.subheader("🎯 Real-World Track Record")
    st.write("The AI Scanner saves its predictions daily, and once the 2-day forward window passes, it calculates if the stock actually rose by 5% or more.")
    
    conn = get_db_connection()
    df_resolved = pd.read_sql_query("""
        SELECT date, symbol, probability, stage, actual_max_return, outcome 
        FROM predictions 
        WHERE outcome IS NOT NULL
        ORDER BY date DESC
    """, conn)
    conn.close()
    
    if df_resolved.empty:
        st.info("No resolved predictions found yet. Check back in 2 days once outcomes resolve!")
    else:
        # Metrics cards
        total_p = len(df_resolved)
        hits = df_resolved["outcome"].sum()
        misses = total_p - hits
        actual_acc = hits / total_p
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Resolved Calls", total_p)
        c1.metric("Actual Hits (>=5% spikes)", hits)
        c2.metric("Misses", misses)
        c2.metric("Hit Rate Percentage", f"{actual_acc:.1%}")
        
        st.subheader("📋 Historical Outcomes Log")
        st.dataframe(df_resolved, use_container_width=True)

# ─────────────────────────────────────────────────────────────
# TAB 4: COMPARE AI vs RULES
# ─────────────────────────────────────────────────────────────
with tab_compare:
    st.subheader("⚖️ Rule-Based (9_SetupTracker) vs AI Engine")
    st.write("Compare the static consolidation tracker stages (Rule-based) with the Dynamic AI confidence percentages.")
    
    # Try importing 9_SetupTracker functions to get real-time rules stages
    try:
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import importlib
        setup_tracker = importlib.import_module("9_SetupTracker")
        
        if st.button("⚖️ Generate Comparison Table", type="secondary"):
            with st.spinner("Analyzing rules & merging with AI..."):
                hist = setup_tracker.fetch_setup_data()
                if hist:
                    df_rules = setup_tracker.analyze_setups(hist)
                    if not df_rules.empty and not df_preds.empty:
                        # Merge on symbol
                        df_compare = pd.merge(
                            df_rules[["Symbol", "Setup_Stage", "Readiness_%"]],
                            df_preds[["symbol", "probability", "stage"]],
                            left_on="Symbol", right_on="symbol", how="inner"
                        )
                        
                        # Find disagreements
                        st.success("Analysis Complete!")
                        st.dataframe(
                            df_compare.rename(columns={
                                "Setup_Stage": "Rule-Based Stage",
                                "Readiness_%": "Rule-Based Readiness",
                                "probability": "AI Probability %",
                                "stage": "AI Stage"
                            }).drop(columns=["symbol"]),
                            use_container_width=True
                        )
                    else:
                        st.warning("No overlapping stocks or empty data.")
                else:
                    st.error("Failed to load historical data for rules scanner.")
    except Exception as e:
        st.warning(f"Unable to run automatic comparison side-by-side: {str(e)}")

# ─────────────────────────────────────────────────────────────
# TAB 5: RETRAIN MODEL
# ─────────────────────────────────────────────────────────────
with tab_retrain:
    st.subheader("🔄 Train and Predict AI Model")
    st.write("Retrain the ML brain with the latest market data to adjust for fresh volume spikes and trend changes.")
    
    # Check library availability
    if not ai_pattern_engine.ML_AVAILABLE:
        st.error("❌ `scikit-learn` or `joblib` is not installed. Run `pip install scikit-learn joblib` on your machine.")
    if not ai_pattern_engine.YF_AVAILABLE:
        st.error("❌ `yfinance` is not installed. Run `pip install yfinance` on your machine.")
        
    st.write(f"**Current model file:** `{ai_pattern_engine.MODEL_PATH}`")
    
    if st.button("🔄 Retrain AI Model Now", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("1. Fetching historical daily candles for 840+ watchlist stocks (takes ~1-2 mins)...")
            progress_bar.progress(20)
            
            # Execute backend training
            success = ai_pattern_engine.train_ai_model()
            
            if success:
                status_text.text("2. Model training completed successfully! Running today's predictions...")
                progress_bar.progress(70)
                
                # Predict
                ai_pattern_engine.run_predictions()
                
                # Resolve outcomes
                ai_pattern_engine.update_past_outcomes()
                
                status_text.text("3. AI Scan execution complete! Updating dashboard...")
                progress_bar.progress(100)
                
                st.success("✅ AI Scanner successfully retrained and predicted. Refreshing page...")
                st.rerun()
            else:
                st.error("❌ Training failed. See terminal/logs for details.")
        except Exception as ex:
            st.error(f"Error during training cycle: {str(ex)}")
