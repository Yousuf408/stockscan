# ══════════════════════════════════════════
#  TRADESENTRY — styles.py v4.0
#  Professional White Theme + Top Navbar
#  Mobile Responsive
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
        --mono:      'JetBrains Mono', monospace;
        --sans:      'Inter', sans-serif;
        --radius:    8px;
        --radius-lg: 12px;
        --shadow:    0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
    }

    /* ══════════════════════════════════════
       KILL STREAMLIT DEFAULTS + SIDEBAR
    ══════════════════════════════════════ */
    * { box-sizing: border-box; }
    #MainMenu, footer { visibility: hidden; }
    
    /* Hide sidebar completely */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarHeader"] { display: none !important; }
    [data-testid="stSidebarCollapseButton"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }

    /* ══════════════════════════════════════
       APP BACKGROUND
    ══════════════════════════════════════ */
    .stApp {
        background: var(--bg3) !important;
        font-family: var(--sans) !important;
        color: var(--text) !important;
    }
    
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
    }

    /* ══════════════════════════════════════
       TOP NAVBAR
    ══════════════════════════════════════ */
    .ts-navbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: var(--bg);
        border-bottom: 1px solid var(--border);
        box-shadow: var(--shadow);
        padding: 0 20px;
        height: 52px;
        position: sticky;
        top: 0;
        z-index: 999;
        gap: 20px;
    }

    .ts-navbar-left {
        display: flex;
        align-items: center;
        gap: 20px;
    }

    .ts-navbar-logo {
        font-family: var(--mono);
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: var(--text);
        white-space: nowrap;
    }

    .ts-navbar-logo span {
        color: var(--green);
    }

    .ts-navbar-divider {
        width: 1px;
        height: 20px;
        background: var(--border);
    }

    .ts-navbar-links {
        display: flex;
        gap: 24px;
        align-items: center;
        flex-wrap: wrap;
    }

    .ts-navbar-link {
        font-family: var(--sans);
        font-size: 13px;
        font-weight: 600;
        color: var(--text2);
        text-decoration: none;
        transition: all 0.15s;
        padding-bottom: 2px;
        border-bottom: 2px solid transparent;
        letter-spacing: 0.01em;
        white-space: nowrap;
    }

    .ts-navbar-link:hover {
        color: var(--green);
    }

    .ts-navbar-link.active {
        color: var(--green);
        border-bottom-color: var(--green);
    }

    .ts-navbar-right {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .ts-navbar-time {
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 600;
        color: var(--text3);
        background: var(--bg2);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 4px 10px;
        letter-spacing: 0.04em;
    }

    /* ══════════════════════════════════════
       PAGE CONTENT
    ══════════════════════════════════════ */
    .ts-page-content {
        padding: 20px;
        background: var(--bg3);
        min-height: calc(100vh - 52px);
        width: 100%;
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
       STREAMLIT INPUTS
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
       SCROLLBAR
    ══════════════════════════════════════ */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg3); }
    ::-webkit-scrollbar-thumb {
        background: var(--border2);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover { background: var(--green); }

    /* ══════════════════════════════════════
       MOBILE RESPONSIVE
    ══════════════════════════════════════ */
    @media (max-width: 768px) {
        .ts-navbar {
            padding: 0 12px;
            height: 48px;
            gap: 12px;
        }

        .ts-navbar-logo {
            font-size: 12px;
        }

        .ts-navbar-divider {
            display: none;
        }

        .ts-navbar-links {
            gap: 12px;
            overflow-x: auto;
            flex-wrap: nowrap;
            padding-bottom: 4px;
        }

        .ts-navbar-link {
            font-size: 11px;
            white-space: nowrap;
            flex-shrink: 0;
        }

        .ts-navbar-time {
            display: none;
        }

        .ts-page-content {
            padding: 12px;
        }
    }

    @media (max-width: 480px) {
        .ts-navbar-left {
            gap: 10px;
        }

        .ts-navbar-links {
            gap: 8px;
        }

        .ts-navbar-link {
            font-size: 10px;
            padding-bottom: 1px;
        }
    }

    </style>
    """, unsafe_allow_html=True)


def render_navbar(current_page: str, pages: list):
    """
    Render top navbar with page links.
    
    Usage:
        pages = [
            ("Sectors", "2_Sectors"),
            ("Watchlist", "3_Watchlist"),
            ("Scan", "4_Scan")
        ]
        render_navbar(st.session_state.page or "Sectors", pages)
    """
    st.markdown(f"""
    <div class="ts-navbar">
        <div class="ts-navbar-left">
            <div class="ts-navbar-logo">TRADE<span>SENTRY</span></div>
            <div class="ts-navbar-divider"></div>
            <div class="ts-navbar-links">
    """, unsafe_allow_html=True)

    for page_name, page_key in pages:
        is_active = current_page == page_name
        active_class = "active" if is_active else ""
        st.markdown(f"""
                <a href="#{page_key}" class="ts-navbar-link {active_class}" 
                   onclick="window.location.hash='{page_key}'">{page_name}</a>
        """, unsafe_allow_html=True)

    st.markdown("""
            </div>
        </div>
        <div class="ts-navbar-right">
            <div class="ts-navbar-time" id="ts-time">--:--:--</div>
        </div>
    </div>
    <script>
    function updateTime() {
        var now = new Date();
        var h = String(now.getHours()).padStart(2,'0');
        var m = String(now.getMinutes()).padStart(2,'0');
        var s = String(now.getSeconds()).padStart(2,'0');
        var el = document.getElementById('ts-time');
        if(el) el.textContent = h+':'+m+':'+s;
    }
    setInterval(updateTime, 1000);
    updateTime();
    </script>
    """, unsafe_allow_html=True)


def page_content(title: str = ""):
    """Wrap page content in proper styling."""
    st.markdown(f'<div class="ts-page-content">', unsafe_allow_html=True)
    if title:
        st.markdown(f"""
        <div style="padding:0 0 16px 0;border-bottom:1px solid var(--border);margin-bottom:16px;">
            <div style="font-family:var(--mono);font-size:16px;font-weight:700;
            color:var(--text);letter-spacing:0.06em;">{title}</div>
        </div>
        """, unsafe_allow_html=True)
