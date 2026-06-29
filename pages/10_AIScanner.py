"""
10_AIScanner.py — TradeSentry AI Pattern Scanner
Professional UI · Supabase-backed · Streamlit Cloud safe
"""

import sys, os, json
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ai_pattern_engine

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Pattern Scanner", page_icon="🤖", layout="wide")

# ── STYLES & SIDEBAR ──
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
header { visibility: hidden; }
.block-container { padding: 1rem 2rem 1rem 2rem !important; max-width: 100% !important; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e2e8f0; }
.stTabs [data-baseweb="tab"] {
    padding: 8px 18px; font-size: 13px; font-weight: 500;
    color: #64748b; border-radius: 6px 6px 0 0;
}
.stTabs [aria-selected="true"] { color: #0f172a !important; font-weight: 600; }

/* ── Page Header ── */
.page-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px; border-radius: 12px;
    background: #ffffff; border: 1px solid #e2e8f0;
    border-left: 4px solid #10b981; margin-bottom: 14px;
}
.page-header-left { display: flex; align-items: center; gap: 12px; }
.page-header-title { font-size: 18px; font-weight: 700; color: #0f172a; letter-spacing: -0.3px; }
.page-header-sub   { font-size: 12px; color: #64748b; margin-top: 2px; }
.page-header-stats { display: flex; gap: 8px; }
.hstat {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 8px 16px; text-align: center; min-width: 90px;
}
.hstat-val  { font-size: 17px; font-weight: 700; color: #10b981; line-height: 1.2; }
.hstat-lbl  { font-size: 10px; color: #94a3b8; margin-top: 2px; letter-spacing: 0.3px; text-transform: uppercase; }

/* ── Section title ── */
.sec-title {
    font-size: 13px; font-weight: 600; color: #475569;
    text-transform: uppercase; letter-spacing: 0.8px;
    margin: 0 0 10px 0; padding-bottom: 6px;
    border-bottom: 1px solid #e2e8f0;
}

/* ── Stat row (retrain tab) ── */
.stat-row {
    display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px;
}
.stat-box {
    flex: 1; min-width: 100px;
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 12px 16px;
}
.stat-box-val { font-size: 20px; font-weight: 700; color: #0f172a; line-height: 1.2; }
.stat-box-lbl { font-size: 11px; color: #64748b; margin-top: 3px; }
.stat-box.green .stat-box-val { color: #10b981; }
.stat-box.red   .stat-box-val { color: #ef4444; }
.stat-box.blue  .stat-box-val { color: #3b82f6; }

/* ── AI Table ── */
.ai-table-wrap { border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }
.ai-table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-family: 'Inter', sans-serif; }
.ai-table thead tr { background: #f8fafc; }
.ai-table th {
    color: #64748b; font-weight: 600; font-size: 10.5px;
    padding: 10px 14px; text-align: left;
    border-bottom: 2px solid #e2e8f0;
    text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap;
}
.ai-table th:first-child { border-radius: 0; }
.ai-table td {
    padding: 10px 14px; border-bottom: 1px solid #f1f5f9;
    color: #334155; vertical-align: middle; white-space: nowrap;
}
.ai-table tbody tr:last-child td { border-bottom: none; }
.ai-table tbody tr:hover td { background: #f0fdf4; }
.ai-table .col-sym  { width: 110px; }
.ai-table .col-prob { width: 150px; }
.ai-table .col-stage{ width: 90px; }
.ai-table .col-num  { width: 100px; text-align: right; }

/* ── Badges ── */
.badge { padding: 3px 8px; border-radius: 5px; font-weight: 600; font-size: 10.5px; display: inline-block; letter-spacing: 0.3px; }
.badge-prime { background: #dcfce7; color: #15803d; }
.badge-watch { background: #fef9c3; color: #a16207; }
.badge-build { background: #dbeafe; color: #1d4ed8; }
.badge-early { background: #f1f5f9; color: #64748b; }

/* ── Copy button ── */
.copy-btn {
    cursor: pointer; font-weight: 600; color: #0f172a; font-size: 12px;
    background: transparent; border: 1px solid #e2e8f0;
    padding: 3px 10px; border-radius: 5px; transition: all 0.15s;
    font-family: 'Inter', monospace;
}
.copy-btn:hover { background: #0f172a; color: #10b981; border-color: #0f172a; }

/* ── Prob bar ── */
.prob-wrap { display: flex; align-items: center; gap: 8px; }
.prob-bar-bg { flex: 1; height: 5px; background: #e2e8f0; border-radius: 3px; }
.prob-bar-fill { height: 5px; border-radius: 3px; }

/* ── Action card (retrain buttons) ── */
.action-card {
    border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 14px 16px; background: #fafafa; margin-bottom: 4px;
}
.action-card-title { font-size: 13px; font-weight: 600; color: #0f172a; margin-bottom: 3px; }
.action-card-desc  { font-size: 11.5px; color: #64748b; line-height: 1.5; margin-bottom: 10px; }
.action-tag {
    display: inline-block; font-size: 10px; font-weight: 600;
    padding: 2px 8px; border-radius: 4px; margin-bottom: 8px;
}
.tag-daily  { background: #dbeafe; color: #1e40af; }
.tag-weekly { background: #d1fae5; color: #065f46; }
.tag-anytime{ background: #f3e8ff; color: #6b21a8; }

/* ── Guide box ── */
.guide-box {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-left: 3px solid #10b981; border-radius: 8px;
    padding: 12px 16px; font-size: 12.5px; color: #334155; line-height: 1.7;
    margin-bottom: 8px;
}
.guide-box.blue  { border-left-color: #3b82f6; }
.guide-box.purple{ border-left-color: #8b5cf6; }
.guide-box b { color: #0f172a; }
.guide-box .result-hit  { color: #10b981; font-weight: 700; }
.guide-box .result-miss { color: #ef4444; font-weight: 700; }

/* ── Toast ── */
.toast {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: #0f172a; color: #f8fafc; padding: 8px 18px;
    border-radius: 8px; font-size: 12px; z-index: 9999;
    opacity: 0; transition: opacity 0.25s; pointer-events: none; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.toast.show { opacity: 1; }
</style>

<div id="toast" class="toast">✅ Copied to clipboard</div>
<script>
function copySymbol(btn, sym) {
    navigator.clipboard.writeText(sym);
    var prev = btn.innerText;
    btn.innerText = '✓ Copied';
    btn.style.background = '#0f172a';
    btn.style.color = '#10b981';
    var t = document.getElementById('toast');
    t.classList.add('show');
    setTimeout(function(){ btn.innerText = prev; btn.style.background=''; btn.style.color=''; t.classList.remove('show'); }, 1400);
}
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SUPABASE + CONFIG
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return ai_pattern_engine.get_supabase_client(
        st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    )

supabase = get_supabase()

try:
    from config import STOCKS_WATCHLIST
    STOCKS = [item[0] for item in STOCKS_WATCHLIST if item[2] == "stock"]
except Exception:
    STOCKS = []

# ─────────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────────
def load_predictions():
    try:    return ai_pattern_engine.fetch_today_predictions(supabase)
    except: return pd.DataFrame()

def load_metrics():
    try:    return ai_pattern_engine.fetch_model_metrics(supabase)
    except: return {}

def load_feature_importances():
    try:    return ai_pattern_engine.fetch_feature_importances(supabase)
    except: return pd.DataFrame()

def load_history():
    try:    return ai_pattern_engine.fetch_prediction_history(supabase, limit=300)
    except: return pd.DataFrame()

# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────
df_preds  = load_predictions()
metrics   = load_metrics()
df_hist   = load_history()
today_str = datetime.now().strftime("%Y-%m-%d")

acc       = metrics.get("accuracy", 0.0)        if metrics else 0.0
trained   = metrics.get("trained_at", "—")[:10] if metrics else "—"
samples   = metrics.get("total_samples", 0)      if metrics else 0
hits_total= len(df_hist)
hits_count= int(df_hist["outcome"].sum()) if not df_hist.empty else 0
live_rate = hits_count / hits_total if hits_total > 0 else 0.0

# ─────────────────────────────────────────────────────────────
# PAGE HEADER
# ─────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="page-header">
  <div class="page-header-left">
    <span style="font-size:28px;">🤖</span>
    <div>
      <div class="page-header-title">AI Pattern Scanner</div>
      <div class="page-header-sub">RandomForest · 821 NSE Stocks · Predicts ≥5% Spike · 20 EMA + Volume DNA</div>
    </div>
  </div>
  <div class="page-header-stats">
    <div class="hstat"><div class="hstat-val">{acc:.1%}</div><div class="hstat-lbl">Accuracy</div></div>
    <div class="hstat"><div class="hstat-val">{live_rate:.1%}</div><div class="hstat-lbl">Live Hit Rate</div></div>
    <div class="hstat"><div class="hstat-val">{samples:,}</div><div class="hstat-lbl">Patterns</div></div>
    <div class="hstat"><div class="hstat-val">{trained}</div><div class="hstat-lbl">Last Trained</div></div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯  Today's Predictions",
    "📊  What AI Learned",
    "📈  Track Record",
    "⚙️  Model & Controls"
])

# ══════════════════════════════════════════════════════════════
# TAB 1 — TODAY'S PREDICTIONS
# ══════════════════════════════════════════════════════════════
with tab1:

    def render_table(df):
        if df.empty:
            return "<div style='text-align:center;padding:48px;color:#94a3b8;font-size:13px;border:1px solid #e2e8f0;border-radius:10px;'>No predictions for today. Run predictions from the Model &amp; Controls tab.</div>"

        rows = ""
        for i, (_, row) in enumerate(df.iterrows()):
            prob   = row.get("probability", 0.0)
            stage  = row.get("stage", "")
            symbol = row.get("symbol", "")
            feat   = row.get("features") or {}
            if isinstance(feat, str):
                try: feat = json.loads(feat)
                except: feat = {}

            dist  = feat.get("dist_to_ema20", 0.0)
            v5    = feat.get("vol_vs_5d_avg", 1.0)
            v1    = feat.get("vol_ratio_1d", 1.0)
            px    = feat.get("price_change_1d", 0.0)
            body  = feat.get("body_ratio", 0.5)

            bcls  = "badge-early"
            if "PRIME_AI" in stage: bcls = "badge-prime"
            elif "WATCH_AI" in stage: bcls = "badge-watch"
            elif "BUILD_AI" in stage: bcls = "badge-build"

            stage_label = stage.split()[-1] if stage else "—"
            pxcol     = "#ef4444" if px < 0 else ("#10b981" if px > 0 else "#64748b")
            bar_color = "#10b981" if prob >= 60 else ("#f59e0b" if prob >= 40 else "#94a3b8")
            dist_col  = "#10b981" if abs(dist) <= 2 else "#334155"
            dist_wt   = "600"     if abs(dist) <= 2 else "400"
            v5_col    = "#10b981" if v5 < 0.8 else ("#f59e0b" if v5 < 1.2 else "#334155")
            row_bg    = "#ffffff" if i % 2 == 0 else "#fafafa"
            rank_col  = "#10b981" if i < 3 else "#94a3b8"

            rows += f"""
            <tr style="background:{row_bg};">
              <td class="col-sym">
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-size:10px;font-weight:700;color:{rank_col};min-width:16px;">#{i+1}</span>
                  <button class="copy-btn" onclick="copySymbol(this,'{symbol}')">{symbol}</button>
                </div>
              </td>
              <td class="col-prob">
                <div class="prob-wrap">
                  <span style="font-size:13px;font-weight:700;color:#0f172a;min-width:42px;">{prob:.1f}%</span>
                  <div class="prob-bar-bg" style="min-width:60px;">
                    <div class="prob-bar-fill" style="width:{min(prob,100):.0f}%;background:{bar_color};"></div>
                  </div>
                </div>
              </td>
              <td class="col-stage"><span class="badge {bcls}">{stage_label}</span></td>
              <td class="col-num" style="color:{dist_col};font-weight:{dist_wt};">{dist:+.2f}%</td>
              <td class="col-num" style="color:{v5_col};">{v5:.2f}x</td>
              <td class="col-num" style="color:#475569;">{v1:.2f}x</td>
              <td class="col-num" style="color:{pxcol};font-weight:600;">{px:+.2f}%</td>
              <td class="col-num" style="color:#94a3b8;">{body:.2f}</td>
            </tr>"""

        return f"""
        <div class="ai-table-wrap">
        <table class="ai-table">
          <colgroup>
            <col class="col-sym"><col class="col-prob"><col class="col-stage">
            <col class="col-num"><col class="col-num"><col class="col-num">
            <col class="col-num"><col class="col-num">
          </colgroup>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>AI Probability</th>
              <th>Stage</th>
              <th style="text-align:right;">EMA20 Dist</th>
              <th style="text-align:right;">Vol/5d Avg</th>
              <th style="text-align:right;">Vol 1d</th>
              <th style="text-align:right;">Price Chg</th>
              <th style="text-align:right;">Body</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        </div>"""

    # ── Filters row ──
    f1, f2, f3 = st.columns([3, 2, 1])
    with f1:
        stage_filter = st.multiselect(
            "Stage Filter",
            ["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI", "📍 EARLY_AI"],
            default=["🚀 PRIME_AI", "🔴 WATCH_AI", "📈 BUILD_AI"],
            label_visibility="collapsed"
        )
    with f2:
        min_prob = st.slider("Min Probability", 0.0, 100.0, 40.0, 5.0, label_visibility="collapsed")
    with f3:
        st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#64748b;'>{today_str}</div>", unsafe_allow_html=True)

    if not df_preds.empty:
        df_filtered = df_preds[
            df_preds["stage"].isin(stage_filter) &
            (df_preds["probability"] >= min_prob)
        ]
        # Summary chips
        prime = len(df_filtered[df_filtered["stage"].str.contains("PRIME", na=False)])
        watch = len(df_filtered[df_filtered["stage"].str.contains("WATCH", na=False)])
        build = len(df_filtered[df_filtered["stage"].str.contains("BUILD", na=False)])
        st.markdown(f"""
        <div style="display:flex;gap:8px;margin:6px 0 10px 0;">
          <span class="badge badge-prime">🚀 PRIME: {prime}</span>
          <span class="badge badge-watch">🔴 WATCH: {watch}</span>
          <span class="badge badge-build">📈 BUILD: {build}</span>
          <span style="font-size:12px;color:#64748b;margin-left:4px;padding-top:3px;">
            {len(df_filtered)} stocks shown
          </span>
        </div>
        """, unsafe_allow_html=True)

        st.components.v1.html(
            render_table(df_filtered),
            height=min(600, 55 + len(df_filtered) * 40),
            scrolling=True
        )

        # ── Deep Dive ──
        if not df_filtered.empty:
            st.markdown('<div class="sec-title" style="margin-top:18px;">Deep Dive — Pattern Analysis</div>', unsafe_allow_html=True)
            sel = st.selectbox("Select stock", df_filtered["symbol"].tolist(), label_visibility="collapsed")
            if sel:
                srow = df_filtered[df_filtered["symbol"] == sel].iloc[0]
                feat = srow.get("features") or {}
                if isinstance(feat, str):
                    try: feat = json.loads(feat)
                    except: feat = {}

                d1, d2 = st.columns([1, 1])
                with d1:
                    prob_val = srow["probability"]
                    color = "#10b981" if prob_val >= 60 else ("#f59e0b" if prob_val >= 40 else "#94a3b8")
                    st.markdown(f"""
                    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;">
                      <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">AI Spike Confidence</div>
                      <div style="font-size:32px;font-weight:700;color:{color};margin:4px 0;">{prob_val:.1f}%</div>
                      <div style="font-size:12px;color:#64748b;">Probability of ≥5% spike within 2 days</div>
                    </div>
                    """, unsafe_allow_html=True)

                    dist20 = feat.get("dist_to_ema20", 0.0)
                    vol5   = feat.get("vol_vs_5d_avg", 1.0)
                    st.markdown("<div style='margin-top:12px;font-size:12px;font-weight:600;color:#475569;'>Signal Checklist</div>", unsafe_allow_html=True)

                    def chk(ok, txt):
                        icon = "✅" if ok else "⚠️"
                        col  = "#15803d" if ok else "#a16207"
                        return f"<div style='font-size:12.5px;color:{col};padding:3px 0;'>{icon} {txt}</div>"

                    st.markdown(
                        chk(abs(dist20) <= 2, f"EMA20 distance {dist20:+.2f}% — {'tight pullback setup' if abs(dist20)<=2 else 'away from EMA'}") +
                        chk(vol5 < 0.85, f"Vol/5d avg {vol5:.2f}x — {'dry-up confirmed ✓' if vol5<0.85 else 'volume not compressed'}") +
                        chk(feat.get("ema_5_vs_20", 0) == 1, "EMA5 above EMA20 — bullish alignment") +
                        chk(feat.get("vol_dry_up_3d", 0) == 1, "3-day volume dry-up pattern detected"),
                        unsafe_allow_html=True
                    )

                with d2:
                    feat_df = pd.DataFrame([
                        {"Feature": k, "Value": f"{v:+.4f}" if isinstance(v, float) else str(v)}
                        for k, v in feat.items()
                    ])
                    st.markdown("<div style='font-size:12px;font-weight:600;color:#475569;margin-bottom:6px;'>All Feature Values</div>", unsafe_allow_html=True)
                    st.dataframe(feat_df, use_container_width=True, hide_index=True, height=220)
    else:
        st.markdown(render_table(pd.DataFrame()), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TAB 2 — WHAT AI LEARNED
# ══════════════════════════════════════════════════════════════
with tab2:
    df_imp = load_feature_importances()
    if df_imp.empty:
        st.info("No feature importances yet. Train the model first.")
    else:
        st.markdown('<div class="sec-title">Feature Importance — What the Model Weights Most</div>', unsafe_allow_html=True)

        fig = go.Figure(go.Bar(
            x=df_imp["importance"],
            y=df_imp["feature_name"],
            orientation="h",
            marker=dict(
                color=df_imp["importance"],
                colorscale=[[0,"#e2e8f0"],[0.5,"#3b82f6"],[1,"#10b981"]],
                showscale=False
            ),
            text=[f"{v:.3f}" for v in df_imp["importance"]],
            textposition="outside",
            textfont=dict(size=11, color="#475569")
        ))
        fig.update_layout(
            height=380,
            margin=dict(l=0, r=60, t=10, b=10),
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False,
                       tickfont=dict(size=10, color="#94a3b8")),
            yaxis=dict(categoryorder="total ascending",
                       tickfont=dict(size=11, color="#334155")),
        )
        st.plotly_chart(fig, use_container_width=True)

        top = df_imp.iloc[-1]["feature_name"]
        st.markdown(f"""
        <div class="guide-box">
          <b>Key Insight:</b> The most important signal is <b>{top}</b>.<br>
          When <b>EMA20 distance is tight</b> + <b>volume drops below 5-day average (dry-up)</b>,
          the model flags these as highest-probability pre-spike setups —
          consistent with the volume-first trading philosophy.
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TAB 3 — TRACK RECORD
# ══════════════════════════════════════════════════════════════
with tab3:
    if df_hist.empty:
        st.info("No resolved predictions yet. Come back after 2 trading days.")
    else:
        total  = len(df_hist)
        hits   = int(df_hist["outcome"].sum())
        misses = total - hits
        rate   = hits / total if total > 0 else 0.0

        st.markdown('<div class="sec-title">Live Performance</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="stat-row">
          <div class="stat-box"><div class="stat-box-val">{total}</div><div class="stat-box-lbl">Total Resolved</div></div>
          <div class="stat-box green"><div class="stat-box-val">{hits}</div><div class="stat-box-lbl">Hits ≥5%</div></div>
          <div class="stat-box red"><div class="stat-box-val">{misses}</div><div class="stat-box-lbl">Misses</div></div>
          <div class="stat-box blue"><div class="stat-box-val">{rate:.1%}</div><div class="stat-box-lbl">Hit Rate</div></div>
        </div>
        """, unsafe_allow_html=True)

        stage_grp = (df_hist.groupby("stage")
                     .agg(total=("outcome","count"), hits=("outcome","sum"))
                     .reset_index())
        stage_grp["hit_pct"] = (stage_grp["hits"] / stage_grp["total"] * 100).round(1)

        fig2 = go.Figure(go.Bar(
            x=stage_grp["stage"].str.split().str[-1],
            y=stage_grp["hit_pct"],
            marker_color=["#10b981","#f59e0b","#3b82f6","#94a3b8"][:len(stage_grp)],
            text=[f"{v:.1f}%" for v in stage_grp["hit_pct"]],
            textposition="outside",
            textfont=dict(size=11)
        ))
        fig2.update_layout(
            height=280, margin=dict(l=0,r=0,t=20,b=0),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(title="Hit Rate %", showgrid=True, gridcolor="#f1f5f9"),
            xaxis=dict(tickfont=dict(size=12, color="#334155"))
        )
        st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<div class="sec-title" style="margin-top:8px;">Full Outcomes Log</div>', unsafe_allow_html=True)
        disp = df_hist.copy()
        disp["outcome"] = disp["outcome"].map({1: "✅ Hit", 0: "❌ Miss"})
        disp["actual_max_return"] = disp["actual_max_return"].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "—")
        disp["probability"] = disp["probability"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(disp, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# TAB 4 — MODEL & CONTROLS
# ══════════════════════════════════════════════════════════════
with tab4:

    # ── Model status row ──
    prec = metrics.get("precision_score", 0.0) if metrics else 0.0
    rec  = metrics.get("recall_score", 0.0)    if metrics else 0.0
    st.markdown('<div class="sec-title">Current Model Status</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="stat-row">
      <div class="stat-box green"><div class="stat-box-val">{acc:.1%}</div><div class="stat-box-lbl">Accuracy</div></div>
      <div class="stat-box blue"><div class="stat-box-val">{prec:.1%}</div><div class="stat-box-lbl">Precision</div></div>
      <div class="stat-box"><div class="stat-box-val">{rec:.1%}</div><div class="stat-box-lbl">Recall</div></div>
      <div class="stat-box"><div class="stat-box-val">{trained}</div><div class="stat-box-lbl">Last Trained</div></div>
      <div class="stat-box"><div class="stat-box-val">{len(STOCKS)}</div><div class="stat-box-lbl">Stocks in Config</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Action cards + buttons ──
    st.markdown('<div class="sec-title" style="margin-top:4px;">Actions</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("""
        <div class="action-card">
          <span class="action-tag tag-weekly">🔁 Weekly</span>
          <div class="action-card-title">🧠 Train Model</div>
          <div class="action-card-desc">Fetches 60d OHLCV for all stocks, computes 13 features, trains RandomForest. Model saved to Supabase — survives restarts.</div>
        </div>""", unsafe_allow_html=True)
        libs_ok = ai_pattern_engine.ML_AVAILABLE and ai_pattern_engine.YF_AVAILABLE
        if st.button("Train Model", type="primary", use_container_width=True, disabled=(not libs_ok or not STOCKS)):
            progress = st.progress(0, text="Fetching data...")
            def prog_cb(done, total):
                progress.progress(int(done/total*60) if total else 0, text=f"Fetching {done}/{total} stocks...")
            result = ai_pattern_engine.train_ai_model(supabase, STOCKS, progress_callback=prog_cb)
            progress.progress(100, text="Done!")
            if result["success"]:
                st.success(f"✅ Trained — Acc: {result['accuracy']:.1%} | Prec: {result['precision']:.1%} | Rec: {result['recall']:.1%} | {result['total_samples']:,} patterns")
                st.rerun()
            else:
                st.error(f"❌ {result['error']}")

    with c2:
        st.markdown("""
        <div class="action-card">
          <span class="action-tag tag-daily">📅 Daily after 3:30 PM</span>
          <div class="action-card-title">🎯 Run Predictions</div>
          <div class="action-card-desc">Scores all 821 stocks using the trained model. Saves today's AI probability + stage to Supabase with outcome = NULL.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("Run Predictions", type="secondary", use_container_width=True, disabled=(not ai_pattern_engine.ML_AVAILABLE or not STOCKS)):
            with st.spinner("Scoring stocks..."):
                preds = ai_pattern_engine.run_predictions(supabase, STOCKS)
            if preds:
                st.success(f"✅ {len(preds)} predictions saved for {today_str}")
                st.rerun()
            else:
                st.error("❌ No predictions. Train the model first.")

    with c3:
        st.markdown("""
        <div class="action-card">
          <span class="action-tag tag-daily">📅 Daily after 3:30 PM</span>
          <div class="action-card-title">🔍 Resolve Outcomes</div>
          <div class="action-card-desc">Checks 2-day-old predictions against actual prices. Marks each Hit ✅ (≥5%) or Miss ❌. Updates Live Hit Rate on dashboard.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("Resolve Outcomes", type="secondary", use_container_width=True):
            with st.spinner("Resolving outcomes..."):
                resolved = ai_pattern_engine.update_past_outcomes(supabase)
            st.success(f"✅ Resolved {resolved} predictions")
            st.rerun()

    # ── How it works guide ──
    with st.expander("📋 How This Works — Quick Guide", expanded=False):
        st.markdown("""
        <div class="guide-box" style="margin-bottom:8px;">
          <b>📅 Daily Routine — Market close ke baad (3:30 PM)</b><br><br>
          <b>① Run Predictions</b> — Aaj ke sabhi 821 stocks score hote hain. Supabase mein save hota hai with outcome = NULL.<br>
          <b>② Resolve Outcomes</b> — 2 din purani predictions check hoti hain. Agar stock 5%+ utha → Hit ✅, nahi utha → Miss ❌.
        </div>
        <div class="guide-box blue" style="margin-bottom:8px;">
          <b>🔍 Resolve Example</b><br><br>
          RELIANCE close on prediction day = ₹1,450 &nbsp;→&nbsp; 2 din baad max = ₹1,530<br>
          Return = (1530 − 1450) / 1450 × 100 = <b>5.5%</b> → <span class="result-hit">✅ HIT — outcome = 1</span><br><br>
          TATASTEEL close = ₹150 &nbsp;→&nbsp; 2 din baad max = ₹153<br>
          Return = 2.0% → <span class="result-miss">❌ MISS — outcome = 0</span>
        </div>
        <div class="guide-box purple">
          <b>🧠 Weekly — Train Model</b><br><br>
          Naye 60 din ka data lekar RandomForest dobara train hota hai.
          Model Supabase mein save hota hai — Streamlit Cloud restart pe kuch nahi jaata.
          Accuracy, Precision, Recall upar status row mein update ho jaate hain.
        </div>
        """, unsafe_allow_html=True)

    # ── System status ──
    st.markdown(f"""
    <div style="display:flex;gap:16px;margin-top:14px;font-size:11.5px;color:#94a3b8;">
      <span>{'✅' if ai_pattern_engine.ML_AVAILABLE else '❌'} scikit-learn</span>
      <span>{'✅' if ai_pattern_engine.YF_AVAILABLE else '❌'} yfinance</span>
      <span>{'✅' if ai_pattern_engine.SUPABASE_AVAILABLE else '❌'} supabase-py</span>
    </div>
    """, unsafe_allow_html=True)
