# ══════════════════════════════════════════
#  TRADESENTRY — styles.py
#  Global CSS for entire app
#  Theme: Professional White / Light
#  Usage: from styles import apply_styles
#         apply_styles()  ← call on every page
# ══════════════════════════════════════════

import streamlit as st

def apply_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* ══════════════════════════════════════
       ROOT VARIABLES
    ══════════════════════════════════════ */
    :root {
        --bg:        #ffffff;
        --bg2:       #f8f9fb;
        --bg3:       #f0f2f5;
        --bg4:       #e8eaed;
        --border:    #e0e3e8;
        --border2:   #cdd1d8;
        --text:      #0f1117;
        --text2:     #3d4452;
        --text3:     #7a8394;
        --green:     #00a854;
        --green-dim: #00a85412;
        --green-bg:  #f0faf5;
        --red:       #e53935;
        --red-dim:   #e5393512;
        --red-bg:    #fff5f5;
        --amber:     #f59e0b;
        --amber-dim: #f59e0b12;
        --blue:      #2563eb;
        --blue-dim:  #2563eb10;
        --purple:    #7c3aed;
        --mono:      'JetBrains Mono', monospace;
        --sans:      'Inter', sans-serif;
        --radius:    8px;
        --radius-lg: 12px;
        --shadow:    0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
    }

    /* ══════════════════════════════════════
       GLOBAL RESET
    ══════════════════════════════════════ */
    * { box-sizing: border-box; }
    #MainMenu, footer { visibility: hidden; }

    /* ══════════════════════════════════════
       APP BACKGROUND
    ══════════════════════════════════════ */
    .stApp {
        background: var(--bg3) !important;
        font-family: var(--sans) !important;
        color: var(--text) !important;
    }
    .block-container {
        padding: 0rem 2rem 2rem 2rem !important;
        margin-top: 0rem !important;
        max-width: 100% !important;
    }

    /* ══════════════════════════════════════
       SIDEBAR
    ══════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: var(--bg) !important;
        border-right: 1px solid var(--border) !important;
        box-shadow: 2px 0 8px rgba(0,0,0,0.04) !important;
    }
    [data-testid="stSidebarHeader"] {
        background: var(--bg) !important;
        padding: 16px 16px 0 16px !important;
        border-bottom: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] a {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: var(--text2) !important;
        border-radius: var(--radius) !important;
        padding: 8px 12px !important;
        transition: all 0.15s !important;
        letter-spacing: 0.01em !important;
    }
    [data-testid="stSidebar"] a:hover {
        color: var(--green) !important;
        background: var(--green-dim) !important;
    }
    [data-testid="stSidebar"] [aria-current="page"] {
        color: var(--green) !important;
        background: var(--green-bg) !important;
        border-left: 3px solid var(--green) !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        background: var(--bg3) !important;
        border: 1px solid var(--border2) !important;
        border-radius: var(--radius) !important;
        color: var(--text2) !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover {
        border-color: var(--green) !important;
        color: var(--green) !important;
        background: var(--green-dim) !important;
    }
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background: var(--bg) !important;
        border: 1px solid var(--border2) !important;
        border-radius: var(--radius) !important;
        box-shadow: var(--shadow) !important;
    }
    [data-testid="collapsedControl"]:hover {
        border-color: var(--green) !important;
        color: var(--green) !important;
    }

    /* ══════════════════════════════════════
       STREAMLIT BUTTONS
    ══════════════════════════════════════ */
    div[data-testid="stButton"] button {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: var(--radius) !important;
        border: 1px solid var(--border2) !important;
        background: var(--bg) !important;
        color: var(--text) !important;
        padding: 6px 16px !important;
        transition: all 0.15s !important;
        box-shadow: var(--shadow) !important;
        letter-spacing: 0.01em !important;
    }
    div[data-testid="stButton"] button:hover {
        border-color: var(--green) !important;
        color: var(--green) !important;
        background: var(--green-dim) !important;
        box-shadow: none !important;
    }
    div[data-testid="stButton"] button:active {
        transform: scale(0.98) !important;
    }

    /* ══════════════════════════════════════
       STREAMLIT INPUTS / SELECTBOX
    ══════════════════════════════════════ */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] select {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        background: var(--bg) !important;
        border: 1px solid var(--border2) !important;
        border-radius: var(--radius) !important;
        color: var(--text) !important;
        box-shadow: none !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: var(--green) !important;
        box-shadow: 0 0 0 3px var(--green-dim) !important;
    }

    /* ══════════════════════════════════════
       DATAFRAME / TABLES
    ══════════════════════════════════════ */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-lg) !important;
        overflow: hidden !important;
        box-shadow: var(--shadow) !important;
        background: var(--bg) !important;
    }

    /* ══════════════════════════════════════
       METRICS
    ══════════════════════════════════════ */
    div[data-testid="stMetric"] {
        background: var(--bg) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-lg) !important;
        padding: 16px 20px !important;
        box-shadow: var(--shadow) !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        color: var(--text3) !important;
        text-transform: uppercase !important;
        font-family: var(--sans) !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 22px !important;
        font-weight: 700 !important;
        color: var(--text) !important;
        font-family: var(--mono) !important;
    }

    /* ══════════════════════════════════════
       EXPANDER
    ══════════════════════════════════════ */
    div[data-testid="stExpander"] {
        background: var(--bg) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-lg) !important;
        box-shadow: var(--shadow) !important;
    }

    /* ══════════════════════════════════════
       ALERTS
    ══════════════════════════════════════ */
    div[data-testid="stAlert"] {
        border-radius: var(--radius) !important;
        font-family: var(--sans) !important;
        font-size: 13px !important;
    }

    /* ══════════════════════════════════════
       SPINNER
    ══════════════════════════════════════ */
    div[data-testid="stSpinner"] {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        color: var(--text3) !important;
    }

    /* ══════════════════════════════════════
       SCROLLBAR
    ══════════════════════════════════════ */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg3); }
    ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--green); }

    /* ══════════════════════════════════════
       REUSABLE COMPONENT CLASSES
    ══════════════════════════════════════ */

    /* Page header */
    .ts-page-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 0 20px 0;
        border-bottom: 1px solid var(--border);
        margin-bottom: 20px;
    }
    .ts-logo {
        font-family: var(--mono);
        font-size: 18px;
        font-weight: 700;
        color: var(--text);
        letter-spacing: 0.06em;
    }
    .ts-logo span { color: var(--green); }
    .ts-page-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--text3);
        letter-spacing: 0.08em;
        font-family: var(--sans);
    }

    /* Card */
    .ts-card {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 16px 20px;
        box-shadow: var(--shadow);
        margin-bottom: 12px;
    }
    .ts-card:hover {
        border-color: var(--border2);
        box-shadow: var(--shadow-md);
        transition: all 0.15s;
    }

    /* Metric card */
    .ts-metric {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 14px 18px;
        box-shadow: var(--shadow);
    }
    .ts-metric-label {
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.1em;
        color: var(--text3);
        text-transform: uppercase;
        font-family: var(--sans);
        margin-bottom: 6px;
    }
    .ts-metric-value {
        font-size: 20px;
        font-weight: 700;
        color: var(--text);
        font-family: var(--mono);
    }

    /* Badges */
    .ts-badge-green {
        display: inline-flex; align-items: center; gap: 4px;
        background: var(--green-bg); color: var(--green);
        border: 1px solid #00a85430;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        font-family: var(--mono);
    }
    .ts-badge-red {
        display: inline-flex; align-items: center; gap: 4px;
        background: var(--red-bg); color: var(--red);
        border: 1px solid #e5393530;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        font-family: var(--mono);
    }
    .ts-badge-amber {
        display: inline-flex; align-items: center; gap: 4px;
        background: #fffbf0; color: var(--amber);
        border: 1px solid #f59e0b30;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        font-family: var(--mono);
    }
    .ts-badge-blue {
        display: inline-flex; align-items: center; gap: 4px;
        background: var(--blue-dim); color: var(--blue);
        border: 1px solid #2563eb30;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        font-family: var(--mono);
    }
    .ts-badge-purple {
        display: inline-flex; align-items: center; gap: 4px;
        background: #f5f3ff; color: var(--purple);
        border: 1px solid #7c3aed30;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        font-family: var(--mono);
    }

    /* Table row states */
    .ts-row-up   { border-left: 3px solid var(--green) !important; background: var(--green-bg) !important; }
    .ts-row-down { border-left: 3px solid var(--red) !important;   background: var(--red-bg) !important; }

    /* Section label */
    .ts-section-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--text3);
        font-family: var(--sans);
        padding: 0 0 8px 0;
        border-bottom: 1px solid var(--border);
        margin-bottom: 12px;
    }

    /* Divider */
    .ts-divider {
        border: none;
        border-top: 1px solid var(--border);
        margin: 16px 0;
    }

    /* Status dot */
    .ts-dot-green { width:7px; height:7px; border-radius:50%; background:var(--green); display:inline-block; }
    .ts-dot-red   { width:7px; height:7px; border-radius:50%; background:var(--red);   display:inline-block; }
    .ts-dot-amber { width:7px; height:7px; border-radius:50%; background:var(--amber); display:inline-block; }

    /* ══════════════════════════════════════
       WATCHLIST PAGE CLASSES
       Horizontal card design
    ══════════════════════════════════════ */

    /* Horizontal stock card */
    .wl-card {
        background: var(--bg);
        border: 1px solid var(--border);
        border-left: 4px solid var(--border2);
        border-radius: var(--radius-lg);
        padding: 12px 16px;
        margin-bottom: 8px;
        box-shadow: var(--shadow);
        transition: all 0.15s;
    }
    .wl-card:hover { box-shadow: var(--shadow-md); border-color: var(--border2); }

    .wl-watching  { border-left-color: var(--border2); }
    .wl-near      { border-left-color: var(--amber); }
    .wl-triggered { border-left-color: var(--green); background: var(--green-bg); }
    .wl-sl_hit    { border-left-color: var(--red);   background: var(--red-bg); }
    .wl-target1   { border-left-color: var(--blue); }
    .wl-target2   { border-left-color: var(--purple); }

    /* Symbol */
    .wl-symbol {
        font-family: var(--mono);
        font-size: 18px;
        font-weight: 700;
        color: var(--text);
        letter-spacing: 0.04em;
    }

    /* Pill badges */
    .wl-pill-buy {
        font-size: 10px; font-weight: 700;
        background: var(--green-bg); color: var(--green);
        border: 1px solid #00a85430;
        padding: 2px 8px; border-radius: 12px;
        font-family: var(--mono); display: inline-block;
    }
    .wl-pill-sell {
        font-size: 10px; font-weight: 700;
        background: var(--red-bg); color: var(--red);
        border: 1px solid #e5393530;
        padding: 2px 8px; border-radius: 12px;
        font-family: var(--mono); display: inline-block;
    }

    /* LTP */
    .wl-ltp {
        font-family: var(--mono);
        font-size: 18px;
        font-weight: 700;
        color: var(--text);
    }

    /* Percentage color */
    .wl-pct-pos { font-size:12px; color:var(--green); font-family:var(--mono); font-weight:600; }
    .wl-pct-neg { font-size:12px; color:var(--red);   font-family:var(--mono); font-weight:600; }

    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    sub_html = f'<div class="ts-page-title">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="ts-page-header">
        <div class="ts-logo">TRADE<span>SENTRY</span></div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def sidebar_brand():
    with st.sidebar:
        st.markdown("""
        <div style="padding:12px 8px 14px 8px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:15px;
            font-weight:700;color:#0f1117;letter-spacing:0.08em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
            </div>
            <div style="font-size:9px;color:#7a8394;font-family:'Inter',sans-serif;
            font-weight:600;letter-spacing:0.12em;text-transform:uppercase;
            margin-top:3px;">NSE Professional Screener</div>
        </div>
        <hr style="border:none;border-top:1px solid #e0e3e8;margin:0 0 8px 0;">
        """, unsafe_allow_html=True)
