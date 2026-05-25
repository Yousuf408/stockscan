# ══════════════════════════════════════════
#  TRADESENTRY — styles.py
#  Professional White Theme
#  Simple Sidebar Navigation
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
        --border:    #e0e3e8;
        --border2:   #cdd1d8;
        --text:      #0f1117;
        --text2:     #3d4452;
        --text3:     #7a8394;
        --green:     #00a854;
        --green-dim: #f0faf5;
        --red:       #e53935;
        --red-bg:    #fff5f5;
        --mono:      'JetBrains Mono', monospace;
        --sans:      'Inter', sans-serif;
        --radius:    8px;
        --radius-lg: 12px;
        --shadow:    0 1px 3px rgba(0,0,0,0.08);
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
        padding: 1.5rem 2rem 2rem 2rem !important;
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

    /* Sidebar nav links */
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
        background: var(--green-dim) !important;
        border-left: 3px solid var(--green) !important;
        font-weight: 600 !important;
    }

    /* Sidebar toggle */
    [data-testid="stSidebarCollapseButton"] button {
        background: var(--bg2) !important;
        border: 1px solid var(--border2) !important;
        border-radius: var(--radius) !important;
        color: var(--text2) !important;
        visibility: visible !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover {
        border-color: var(--green) !important;
        color: var(--green) !important;
        background: var(--green-dim) !important;
    }
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
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
       BUTTONS
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
    }
    div[data-testid="stButton"] button:hover {
        border-color: var(--green) !important;
        color: var(--green) !important;
        background: var(--green-dim) !important;
    }
    div[data-testid="stButton"] button:active {
        transform: scale(0.98) !important;
    }

    /* ══════════════════════════════════════
       INPUTS
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
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: var(--green) !important;
        box-shadow: 0 0 0 3px var(--green-dim) !important;
    }

    /* ══════════════════════════════════════
       DATAFRAME
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
       SCROLLBAR
    ══════════════════════════════════════ */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg3); }
    ::-webkit-scrollbar-thumb {
        background: var(--border2);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover { background: var(--green); }

    </style>
    """, unsafe_allow_html=True)


def sidebar_brand():
    """Render TradeSentry branding in sidebar"""
    with st.sidebar:
        st.markdown("""
        <div style="padding:8px 4px 12px 4px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:14px;
            font-weight:700;color:#0f1117;letter-spacing:0.08em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
            </div>
            <div style="font-size:9px;color:#7a8394;font-family:'Inter',sans-serif;
            font-weight:600;letter-spacing:0.12em;text-transform:uppercase;
            margin-top:2px;">NSE SCREENER</div>
        </div>
        <hr style="border:none;border-top:1px solid #e0e3e8;margin-bottom:8px;">
        """, unsafe_allow_html=True)


def page_header(title: str = ""):
    """Render page header with title"""
    if title:
        st.markdown(f"""
        <div style="padding:0 0 16px 0;border-bottom:1px solid #e0e3e8;margin-bottom:16px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:16px;font-weight:700;
            color:#0f1117;letter-spacing:0.06em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
                <span style="font-size:13px;color:#7a8394;margin-left:12px;font-weight:400;
                font-family:'Inter',sans-serif;">{title}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
