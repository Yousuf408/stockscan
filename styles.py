# ══════════════════════════════════════════
#  TRADESENTRY — styles.py
#  Theme: Glass Gradient + Option A Sidebar
#  Usage: from styles import apply_styles, sidebar_brand, page_header
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
        --bg3:       #f0f4ff;
        --bg4:       #eef6f2;
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
    #MainMenu, footer, header,
    [data-testid="stToolbar"] { visibility: hidden; }

    /* ══════════════════════════════════════
       APP BACKGROUND — Glass Gradient
    ══════════════════════════════════════ */
    .stApp {
        background: linear-gradient(135deg, #f0f4ff 0%, #f8faff 55%, #eef6f2 100%) !important;
        background-attachment: fixed !important;
        font-family: var(--sans) !important;
        color: var(--text) !important;
    }
    .block-container {
        padding: 1.5rem 2rem 2rem 2rem !important;
        max-width: 100% !important;
    }

    /* ══════════════════════════════════════
       SIDEBAR — Option A: Icon + Label
    ══════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid var(--border) !important;
        box-shadow: 2px 0 12px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stSidebarHeader"] {
        background: #ffffff !important;
        padding: 0 !important;
        border-bottom: none !important;
    }

    /* Hide default Streamlit page nav links */
    [data-testid="stSidebarNav"] {
        display: none !important;
    }

    /* Sidebar collapse button */
    [data-testid="stSidebarCollapseButton"] button {
        background: var(--bg2) !important;
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

    /* ══════════════════════════════════════
       STREAMLIT BUTTONS
    ══════════════════════════════════════ */
    div[data-testid="stButton"] button {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: var(--radius) !important;
        border: 1px solid var(--border2) !important;
        background: rgba(255,255,255,0.85) !important;
        color: var(--text) !important;
        padding: 6px 16px !important;
        transition: all 0.15s !important;
        box-shadow: var(--shadow) !important;
        backdrop-filter: blur(4px) !important;
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
       INPUTS / SELECTBOX
    ══════════════════════════════════════ */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] select {
        font-family: var(--sans) !important;
        font-size: 13px !important;
        background: rgba(255,255,255,0.85) !important;
        border: 1px solid var(--border2) !important;
        border-radius: var(--radius) !important;
        color: var(--text) !important;
        box-shadow: none !important;
        backdrop-filter: blur(4px) !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: var(--green) !important;
        box-shadow: 0 0 0 3px var(--green-dim) !important;
    }

    /* ══════════════════════════════════════
       DATAFRAME / TABLES — Glass style
    ══════════════════════════════════════ */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(255,255,255,0.9) !important;
        border-radius: var(--radius-lg) !important;
        overflow: hidden !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04) !important;
        background: rgba(255,255,255,0.6) !important;
        backdrop-filter: blur(8px) !important;
    }

    /* ══════════════════════════════════════
       METRICS — Glass card
    ══════════════════════════════════════ */
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.75) !important;
        border: 1px solid rgba(255,255,255,0.9) !important;
        border-radius: var(--radius-lg) !important;
        padding: 16px 20px !important;
        box-shadow: var(--shadow) !important;
        backdrop-filter: blur(6px) !important;
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
       EXPANDER — Glass
    ══════════════════════════════════════ */
    div[data-testid="stExpander"] {
        background: rgba(255,255,255,0.7) !important;
        border: 1px solid rgba(255,255,255,0.9) !important;
        border-radius: var(--radius-lg) !important;
        box-shadow: var(--shadow) !important;
        backdrop-filter: blur(6px) !important;
    }

    /* ══════════════════════════════════════
       ALERTS
    ══════════════════════════════════════ */
    div[data-testid="stAlert"] {
        border-radius: var(--radius) !important;
        font-family: var(--sans) !important;
        font-size: 13px !important;
        background: rgba(255,255,255,0.75) !important;
        backdrop-filter: blur(4px) !important;
    }

    /* ══════════════════════════════════════
       SCROLLBAR
    ══════════════════════════════════════ */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
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
        border-bottom: 1px solid rgba(224,227,232,0.6);
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

    /* Glass Card */
    .ts-card {
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(255,255,255,0.9);
        border-radius: var(--radius-lg);
        padding: 16px 20px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(6px);
        margin-bottom: 12px;
        transition: all 0.15s;
    }
    .ts-card:hover {
        box-shadow: var(--shadow-md);
        background: rgba(255,255,255,0.88);
    }

    /* Metric card */
    .ts-metric {
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(255,255,255,0.9);
        border-radius: var(--radius-lg);
        padding: 14px 18px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(6px);
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

    /* Status dot */
    .ts-dot-green { width:7px; height:7px; border-radius:50%; background:var(--green); display:inline-block; }
    .ts-dot-red   { width:7px; height:7px; border-radius:50%; background:var(--red);   display:inline-block; }
    .ts-dot-amber { width:7px; height:7px; border-radius:50%; background:var(--amber); display:inline-block; }

    /* ══════════════════════════════════════
       WATCHLIST PAGE CLASSES
    ══════════════════════════════════════ */
    .wl-card {
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(255,255,255,0.9);
        border-left: 4px solid var(--border2);
        border-radius: var(--radius-lg);
        padding: 12px 16px;
        margin-bottom: 8px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(6px);
        transition: all 0.15s;
    }
    .wl-card:hover { box-shadow: var(--shadow-md); }
    .wl-watching  { border-left-color: var(--border2); }
    .wl-near      { border-left-color: var(--amber); }
    .wl-triggered { border-left-color: var(--green); background: rgba(240,250,245,0.8); }
    .wl-sl_hit    { border-left-color: var(--red);   background: rgba(255,245,245,0.8); }
    .wl-target1   { border-left-color: var(--blue); }
    .wl-target2   { border-left-color: var(--purple); }

    .wl-symbol {
        font-family: var(--mono);
        font-size: 18px; font-weight: 700;
        color: var(--text); letter-spacing: 0.04em;
    }
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
    .wl-ltp {
        font-family: var(--mono);
        font-size: 18px; font-weight: 700; color: var(--text);
    }
    .wl-pct-pos { font-size:12px; color:var(--green); font-family:var(--mono); font-weight:600; }
    .wl-pct-neg { font-size:12px; color:var(--red);   font-family:var(--mono); font-weight:600; }

    /* ══════════════════════════════════════
       CUSTOM SIDEBAR NAV STYLES
    ══════════════════════════════════════ */
    .ts-nav-section {
        font-size: 8px;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #c0c7d4;
        padding: 10px 12px 4px 12px;
        font-family: var(--sans);
    }
    .ts-nav-item {
        display: flex;
        align-items: center;
        gap: 9px;
        padding: 7px 12px;
        border-radius: 7px;
        font-size: 12px;
        font-weight: 500;
        color: #4a5568;
        margin: 1px 6px;
        cursor: pointer;
        text-decoration: none;
        transition: all 0.15s;
    }
    .ts-nav-item:hover {
        background: #f7f9fc;
        color: #0f1117;
    }
    .ts-nav-item.active {
        background: #f0faf5;
        color: #00a854;
        font-weight: 600;
        border-left: 3px solid #00a854;
        padding-left: 9px;
    }
    .ts-nav-item i {
        font-size: 15px;
        width: 16px;
        text-align: center;
        opacity: 0.7;
    }
    .ts-nav-item.active i { opacity: 1; }
    .ts-nav-divider {
        height: 1px;
        background: #f0f2f5;
        margin: 6px 12px;
    }

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
    # Tabler icons CDN
    st.markdown("""
    <link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
    """, unsafe_allow_html=True)

    with st.sidebar:
        # Brand header
        st.markdown("""
        <div style="padding: 18px 14px 12px 14px; border-bottom: 1px solid #f0f2f5;">
            <div style="font-family:'JetBrains Mono',monospace; font-size:15px;
                font-weight:800; color:#0f1117; letter-spacing:0.08em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
            </div>
            <div style="font-size:9px; color:#9aa3b2; font-family:'Inter',sans-serif;
                font-weight:600; letter-spacing:0.12em; text-transform:uppercase;
                margin-top:3px;">NSE Professional Screener</div>
        </div>
        """, unsafe_allow_html=True)

        # Get current page for active state
        try:
            current = st.context.page_script_hash
        except:
            current = ""

        # Navigation HTML
        st.markdown("""
        <div style="padding: 8px 0 12px 0;">

            <div class="ts-nav-section">Market</div>

            <a class="ts-nav-item" href="/app" target="_self">
                <i class="ti ti-layout-dashboard"></i> Dashboard
            </a>
            <a class="ts-nav-item" href="/LiveFeed" target="_self">
                <i class="ti ti-radio"></i> Live Feed
            </a>

            <div class="ts-nav-divider"></div>
            <div class="ts-nav-section">Scanners</div>

            <a class="ts-nav-item" href="/MomentumScanner" target="_self">
                <i class="ti ti-rocket"></i> Momentum Scanner
            </a>
            <a class="ts-nav-item" href="/ORBScanner" target="_self">
                <i class="ti ti-circle-dot"></i> ORB Scanner
            </a>
            <a class="ts-nav-item" href="/BreakoutScanner" target="_self">
                <i class="ti ti-chart-bar"></i> Breakout Scanner
            </a>
            <a class="ts-nav-item" href="/AIScanner" target="_self">
                <i class="ti ti-brain"></i> AI Scanner
            </a>

            <div class="ts-nav-divider"></div>
            <div class="ts-nav-section">Tools</div>

            <a class="ts-nav-item" href="/Watchlist" target="_self">
                <i class="ti ti-list-check"></i> Watchlist
            </a>
            <a class="ts-nav-item" href="/Observation" target="_self">
                <i class="ti ti-eye"></i> Observation
            </a>
            <a class="ts-nav-item" href="/SetupTracker" target="_self">
                <i class="ti ti-shield-check"></i> Setup Tracker
            </a>
            <a class="ts-nav-item" href="/Sectors" target="_self">
                <i class="ti ti-chart-pie"></i> Sectors
            </a>

        </div>
        """, unsafe_allow_html=True)
