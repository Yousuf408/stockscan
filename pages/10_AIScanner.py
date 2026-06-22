"""
10_AIScanner.py
TradeSentry AI Pattern Scanner — Streamlit Dashboard
Supabase-backed. No SQLite. No local joblib. Streamlit Cloud safe.
"""

import sys
import os
import json
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.express as px

# ── Path fix so ai_pattern_engine can be found ──
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ai_pattern_engine

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Pattern Scanner",
    page_icon="🤖",
    layout="wide"
)

st.markdown("""
<style>
header {visibility: hidden;}
.block-container {padding-top: 1rem !important;}

.metric-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(226,232,240,0.1);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.metric-value { font-size: 30px; font-weight: 700; color: #10b981; margin-bottom: 4px; }
.metric-label { font-size: 13px; color: #64748b; font-weight: 500; }

.ai-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ai-table th {
    background: #0f172a; color: #f8fafc; font-weight: 600;
    padding: 12px 10px; text-align: left; border-bottom: 2px solid #334155;
}
.ai-table td { padding: 10px; border-bottom: 1px solid #e2e8f0; }
.ai-table tr:hover { background: rgba(241,245,249,0.6) !important; }

.badge { padding: 4px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; display: inline-block; }
.badge-prime { background: #dcfce7; color: #15803d; }
.badge-watch { background: #fef9c3; color: #a16207; }
.badge-build { background: #dbeafe; color: #1d4ed8; }
.badge-early { background: #f1f5f9; color: #475569; }

.copy-btn {
    cursor: pointer; font-weight: 700; color: #0f172a;
    background: #e2e8f0; border: none; padding: 4px 8px;
    border-radius: 4px; font-size: 11px;
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
<div id="toast" class="toast">✅ Symbol Copied!</div>
<script>
function copySymbol(btn, symbol) {
    navigator.clipboard.writeText(symbol);
    btn.innerText = '✓ ' + symbol;
    btn.style.background = '#10b981';
    btn.style.color = 'white';
    var t = document.getElementById('toast');
    t.classList.add('show');
    setTimeout(function() {
        btn.innerText = symbol;
        btn.style.background = '#e2e8f0';
        btn.style.color = '#0f172a';
        t.classList.remove('show');
    }, 1200);
}
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT — cached
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return ai_pattern_engine.get_supabase_client(url, key)

supabase = get_supabase()

# ─────────────────────────────────────────────────────────────
# STOCKS LIST from config
# ─────────────────────────────────────────────────────────────
try:
    from config import STOCKS_WATCHLIST
    STOCKS = [item[0] for item in STOCKS_WATCHLIST if item[2] == "stock"]
except Exception:
    STOCKS = []

# ─────────────────────────────────────────────────────────────
# HTML TABLE RENDERER
# ─────────────────────────────────────────────────────────────
def render_predictions_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p style='text-align:center;color:#64748b;'>No predictions available.</p>"

    html = """
    <table class="ai-table">
    <thead><tr>
        <th>Symbol</th><th>AI Probability</th><th>Stage</th>
        <th>20 EMA Dist</th><th>Vol vs 5d Avg</th>
        <th>1d Vol Ratio</th><th>1d Px Chg</th><th>Body Ratio</th>
    </tr></thead><tbody>
    """

    for _, row in df.iterrows():
        prob   = row.get("probability", 0.0)
        stage  = row.get("stage", "")
        symbol = row.get("symbol", "")

        # features stored as dict (already parsed by fetch_today_predictions)
        feat = row.get("features") or {}
        if isinstance(feat, str):
            try:
                feat = json.loads(feat)
            except Exception:
                feat = {}

        dist_ema = feat.get("dist_to_ema20", 0.0)
        vol_5d   = feat.get("vol_vs_5d_avg", 1.0)
        vol_1d   = feat.get("vol_ratio_1d", 1.0)
        px_chg   = feat.get("price_change_1d", 0.0)
        body     = feat.get("body_ratio", 0.5)

        badge_cls = "badge-early"
        if "PRIME_AI"  in stage: badge_cls = "badge-prime"
        elif "WATCH_AI" in stage: badge_cls = "badge-watch"
        elif "BUILD_AI" in stage: badge_cls = "badge-build"

        px_color = "#ef4444" if px_chg < 0 else ("#10b981" if px_chg > 0 else "#64748b")

        html += f"""
        <tr>
            <td><button class="copy-btn" onclick="copySymbol(this,'{symbol}')">{symbol}</button></td>
            <td><strong>{prob:.1f}%</strong></td>
            <td><span class="badge {badge_cls}">{stage}</span></td>
            <td>{dist_ema:+.2f}%</td>
            <td>{vol_5d:.2f}x</td>
            <td>{vol_1d:.2f}x</td>
            <td style="color:{px_color};font-weight:600;">{px_chg:+.2f}%</td>
            <td>{body:.2f}</td>
        </tr>
        """

    html += "</tbody></table>"
    return html

# ─────────────────────────────────────────────────────────────
# LOAD DATA — no @st.cache_data (supabase client not serializable)
# Wrap each call in try/except so missing tables show a clean warning
# ─────────────────────────────────────────────────────────────
def load_predictions() -> pd.DataFrame:
    try:
        return ai_pattern_engine.fetch_today_predictions(supabase)
    except Exception as e:
        if "relation" in str(e).lower() or "does not exist" in str(e).lower() or "APIError" in type(e).__name__:
            return pd.DataFrame()          # table missing — handled below
        st.error(f"load_predictions error: {e}")
        return pd.DataFrame()

def load_metrics() -> dict:
    try:
        return ai_pattern_engine.fetch_model_metrics(supabase)
    except Exception:
        return {}

def load_feature_importances() -> pd.DataFrame:
    try:
        return ai_pattern_engine.fetch_feature_importances(supabase)
    except Exception:
        return pd.DataFrame()

def load_history() -> pd.DataFrame:
    try:
        return ai_pattern_engine.fetch_prediction_history(supabase, limit=300)
    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
st.title("🤖 AI Pattern Scanner")
st.caption("Self-Learning ML Engine — Predicts breakout spikes ≥ 5% using 20 EMA + Volume DNA")

df_preds = load_predictions()
metrics  = load_metrics()
df_hist  = load_history()

today_str = datetime.now().strftime("%Y-%m-%d")

# ── Top Stats Bar ──
if metrics:
    acc      = metrics.get("accuracy", 0.0)
    trained  = metrics.get("trained_at", "N/A")[:10]
    samples  = metrics.get("total_samples", 0)

    hits_total  = len(df_hist)
    hits_count  = int(df_hist["outcome"].sum()) if not df_hist.empty else 0
    live_rate   = hits_count / hits_total if hits_total > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="metric-card"><div class="metric-value">{acc:.1%}</div><div class="metric-label">Model Accuracy (Test Set)</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><div class="metric-value">{live_rate:.1%}</div><div class="metric-label">Live Hit Rate (≥5% Spike)</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><div class="metric-value">{trained}</div><div class="metric-label">Last Trained</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card"><div class="metric-value">{samples:,}</div><div class="metric-label">Patterns Trained On</div></div>', unsafe_allow_html=True)
else:
    st.info("⚠️ Model not trained yet. Go to **Model Retrain** tab to train.")

st.divider()

# ─────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────
tab_preds, tab_insights, tab_track, tab_retrain = st.tabs([
    "🎯 Today's AI Predictions",
    "📊 What AI Learned",
    "📈 Track Record",
    "🔄 Model Retrain & Status"
])

# ══════════════════════════════════════════════════════════════
# TAB 1 — TODAY'S PREDICTIONS
# ══════════════════════════════════════════════════════════════
with tab_preds:
    if df_preds.empty:
        st.info("No predictions for today. Go to **Model Retrain** tab and click **Run Predictions**.")
    else:
        st.subheader(f"Breakout Predictions — {today_str}")

        col_f, col_s = st.columns([3, 1])
        with col_f:
            stage_filter = st.multiselect(
                "Filter by Stage:",
                options=["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI", "📍 EARLY_AI"],
                default=["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI"]
            )
        with col_s:
            min_prob = st.slider("Min Probability %", 0.0, 100.0, 40.0, step=5.0)

        df_filtered = df_preds[
            df_preds["stage"].isin(stage_filter) &
            (df_preds["probability"] >= min_prob)
        ].copy()

        if df_filtered.empty:
            st.warning("No stocks match the selected filters.")
        else:
            st.markdown(f"**{len(df_filtered)} stocks** match your filter:")
            st.components.v1.html(
                render_predictions_table(df_filtered),
                height=min(650, 70 + len(df_filtered) * 44),
                scrolling=True
            )

            st.subheader("💡 Deep Dive — Stock Pattern Details")
            selected = st.selectbox("Select stock to inspect:", df_filtered["symbol"].tolist())

            if selected:
                row  = df_filtered[df_filtered["symbol"] == selected].iloc[0]
                feat = row.get("features") or {}
                if isinstance(feat, str):
                    try:
                        feat = json.loads(feat)
                    except Exception:
                        feat = {}

                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("AI Spike Confidence", f"{row['probability']:.1f}%")
                    st.write("**Pattern Analysis:**")

                    dist_20 = feat.get("dist_to_ema20", 0.0)
                    if abs(dist_20) <= 1.5:
                        st.success(f"✅ Price is very close to 20 EMA ({dist_20:+.2f}%) — Perfect Pullback Setup!")
                    elif dist_20 > 0:
                        st.info(f"📈 Price above 20 EMA ({dist_20:+.2f}%) — Bullish trend.")
                    else:
                        st.warning(f"⚠️ Price below 20 EMA ({dist_20:+.2f}%) — Downtrend risk.")

                    vol_5d = feat.get("vol_vs_5d_avg", 1.0)
                    if vol_5d < 0.8:
                        st.success(f"✅ Volume Dry-up confirmed ({vol_5d:.2f}x of 5d avg) — Consolidation!")
                    elif vol_5d > 1.5:
                        st.info(f"⚡ High volume ({vol_5d:.2f}x of 5d avg) — Buildup phase.")

                with col_b:
                    st.write("**All Feature Values:**")
                    feat_df = pd.DataFrame(
                        [{"Feature": k, "Value": f"{v:+.4f}" if isinstance(v, float) else str(v)}
                         for k, v in feat.items()]
                    )
                    st.dataframe(feat_df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# TAB 2 — WHAT AI LEARNED
# ══════════════════════════════════════════════════════════════
with tab_insights:
    st.subheader("📊 Feature Importances — What the AI weights most")
    st.write("Higher score = AI depends more on that technical feature to call a spike.")

    df_imp = load_feature_importances()
    if df_imp.empty:
        st.info("No feature importances found. Retrain the model first.")
    else:
        fig = px.bar(
            df_imp,
            x="importance", y="feature_name",
            orientation="h",
            labels={"importance": "Importance Score", "feature_name": "Feature"},
            color="importance",
            color_continuous_scale="Viridis",
            height=420
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        top = df_imp.iloc[0]["feature_name"]
        st.markdown(f"""
        **Key Insight:** The most important feature is **`{top}`**.

        When **20 EMA distance is small** + **volume drops below 5-day average** (dry-up),
        the model clusters these as the highest-probability pre-spike setups —
        which matches the volume-first philosophy of the entire scanner.
        """)

# ══════════════════════════════════════════════════════════════
# TAB 3 — TRACK RECORD
# ══════════════════════════════════════════════════════════════
with tab_track:
    st.subheader("🎯 Real-World Track Record")
    st.write("After each prediction, outcomes are resolved 2 days later — did the stock actually spike ≥5%?")

    if df_hist.empty:
        st.info("No resolved predictions yet. Come back after 2 trading days once outcomes are computed.")
    else:
        total  = len(df_hist)
        hits   = int(df_hist["outcome"].sum())
        misses = total - hits
        rate   = hits / total if total > 0 else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Resolved Calls", total)
        c2.metric("Hits (≥5% spike)", hits)
        c3.metric("Misses", misses)
        c4.metric("Live Hit Rate", f"{rate:.1%}")

        # By stage breakdown
        st.subheader("Hit Rate by AI Stage")
        stage_grp = (df_hist.groupby("stage")
                     .agg(total=("outcome", "count"), hits=("outcome", "sum"))
                     .reset_index())
        stage_grp["hit_rate"] = stage_grp["hits"] / stage_grp["total"]
        stage_grp["hit_rate_pct"] = (stage_grp["hit_rate"] * 100).round(1)

        fig2 = px.bar(
            stage_grp, x="stage", y="hit_rate_pct",
            text="hit_rate_pct",
            labels={"hit_rate_pct": "Hit Rate %", "stage": "AI Stage"},
            color="hit_rate_pct",
            color_continuous_scale="RdYlGn",
            height=350
        )
        fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig2.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("📋 Full Outcomes Log")
        display_df = df_hist.copy()
        display_df["outcome"] = display_df["outcome"].map({1: "✅ Hit", 0: "❌ Miss"})
        display_df["actual_max_return"] = display_df["actual_max_return"].apply(
            lambda x: f"{x:+.2f}%" if pd.notna(x) else "—"
        )
        display_df["probability"] = display_df["probability"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# TAB 4 — RETRAIN & STATUS
# ══════════════════════════════════════════════════════════════
with tab_retrain:
    st.subheader("🔄 Train / Predict / Resolve")

    # ── Check if Supabase tables exist ──
    tables_ok = True
    try:
        supabase.table("ai_predictions").select("id").limit(1).execute()
        supabase.table("ai_model_metrics").select("date").limit(1).execute()
        supabase.table("ai_feature_importances").select("feature_name").limit(1).execute()
        supabase.table("ai_model_store").select("id").limit(1).execute()
    except Exception:
        tables_ok = False

    if not tables_ok:
        st.error(
            "❌ **Supabase tables are missing!** "
            "Expand the **Supabase Tables Setup** section below, copy the SQL, "
            "paste it in your **Supabase → SQL Editor**, and run it. "
            "Then refresh this page."
        )

    # Library status
    col_lib1, col_lib2, col_lib3 = st.columns(3)
    col_lib1.metric("scikit-learn", "✅ Ready" if ai_pattern_engine.ML_AVAILABLE else "❌ Missing")
    col_lib2.metric("yfinance",     "✅ Ready" if ai_pattern_engine.YF_AVAILABLE else "❌ Missing")
    col_lib3.metric("supabase-py",  "✅ Ready" if ai_pattern_engine.SUPABASE_AVAILABLE else "❌ Missing")

    if not STOCKS:
        st.error("❌ No stocks found in config.py STOCKS_WATCHLIST. Fix config first.")
    else:
        st.info(f"**{len(STOCKS)} stocks** loaded from config.")

    st.divider()

    # ── Action buttons ──
    col_btn1, col_btn2, col_btn3 = st.columns(3)

    # TRAIN
    with col_btn1:
        if st.button("🧠 Train Model", type="primary", use_container_width=True,
                     disabled=(not ai_pattern_engine.ML_AVAILABLE or not STOCKS)):
            with st.spinner("Fetching 60d history + training RandomForest... (1–3 min)"):
                progress = st.progress(0, text="Fetching data...")

                def prog_cb(done, total):
                    pct = int(done / total * 60) if total else 0
                    progress.progress(pct, text=f"Fetching... {done}/{total}")

                result = ai_pattern_engine.train_ai_model(supabase, STOCKS, progress_callback=prog_cb)
                progress.progress(100, text="Done!")

            if result["success"]:
                st.success(
                    f"✅ Model trained! "
                    f"Accuracy: **{result['accuracy']:.1%}** | "
                    f"Precision: **{result['precision']:.1%}** | "
                    f"Recall: **{result['recall']:.1%}** | "
                    f"Samples: **{result['total_samples']:,}**"
                )

                st.rerun()
            else:
                st.error(f"❌ Training failed: {result['error']}")

    # PREDICT
    with col_btn2:
        if st.button("🎯 Run Predictions", type="secondary", use_container_width=True,
                     disabled=(not ai_pattern_engine.ML_AVAILABLE or not STOCKS)):
            with st.spinner("Fetching 30d history + running predictions..."):
                preds = ai_pattern_engine.run_predictions(supabase, STOCKS)
            if preds:
                st.success(f"✅ {len(preds)} predictions saved for today ({today_str}).")

                st.rerun()
            else:
                st.error("❌ Predictions failed or model not found. Train first.")

    # RESOLVE OUTCOMES
    with col_btn3:
        if st.button("🔍 Resolve Outcomes", type="secondary", use_container_width=True):
            with st.spinner("Checking past predictions vs actual prices..."):
                resolved = ai_pattern_engine.update_past_outcomes(supabase)
            st.success(f"✅ Resolved **{resolved}** past predictions.")
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── Current model metrics ──
    st.subheader("📊 Current Model Status")
    if metrics:
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Accuracy",   f"{metrics.get('accuracy', 0):.1%}")
        m_col2.metric("Precision",  f"{metrics.get('precision_score', 0):.1%}")
        m_col3.metric("Recall",     f"{metrics.get('recall_score', 0):.1%}")
        m_col4.metric("Trained On", metrics.get("trained_at", "N/A")[:10])
    else:
        st.warning("Model hasn't been trained yet.")

    # ── Supabase tables setup instructions ──
    with st.expander("📋 Supabase Tables Setup (run once in SQL Editor)", expanded=not tables_ok):
        st.code("""
-- Run these 4 CREATE TABLE statements once in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS ai_predictions (
    id BIGSERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    probability REAL,
    stage TEXT,
    features JSONB,
    actual_max_return REAL,
    outcome INTEGER,
    UNIQUE(date, symbol)
);

CREATE TABLE IF NOT EXISTS ai_model_metrics (
    date TEXT PRIMARY KEY,
    accuracy REAL,
    precision_score REAL,
    recall_score REAL,
    total_samples INTEGER,
    trained_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_feature_importances (
    feature_name TEXT PRIMARY KEY,
    importance REAL
);

CREATE TABLE IF NOT EXISTS ai_model_store (
    id TEXT PRIMARY KEY,
    model_blob TEXT,
    saved_at TEXT
);
        """, language="sql")
        st.info("After creating tables, click **Train Model** above to begin.")
