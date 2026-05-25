import streamlit as st
import streamlit.components.v1 as components

# ══════════════════════════════════════════════════════════════
#  TRADESENTRY — styles.py v3.0 COMPLETE
#  Professional White Theme — 400+ lines
#  Global CSS + Header + All Streamlit Components
# ══════════════════════════════════════════════════════════════

def apply_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* ══════════════════════════════════════════════════════
       ROOT VARIABLES
    ══════════════════════════════════════════════════════ */
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
        --green-dim: #f0faf5;
        --green-bg:  #f0faf5;
        --red:       #e53935;
        --red-dim:   #fff8f8;
        --red-bg:    #fff8f8;
        --amber:     #f59e0b;
        --amber-dim: #fffbf0;
        --blue:      #2563eb;
        --blue-dim:  #f0f6ff;
        --mono:      'JetBrains Mono', monospace;
        --sans:      'Inter', sans-serif;
        --radius:    7px;
        --radius-lg: 10px;
        --shadow:    0 1px 3px rgba(0,0,0,0.06);
        --shadow-md: 0 2px 8px rgba(0,0,0,0.08);
    }

    /* ══════════════════════════════════════════════════════
       KILL STREAMLIT DEFAULTS
    ══════════════════════════════════════════════════════ */
    * { box-sizing: border-box; }
    #root > div:first-child { padding-top: 0 !important; }
    .stApp > header { display: none !important; height: 0 !important; }
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
    }

    .stApp {
        background: #f0f2f5 !important;
        font-family: 'Inter', sans-serif !important;
        color: #0f1117 !important;
    }

    /* ══════════════════════════════════════════════════════
       SIDEBAR STYLING
    ══════════════════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #e0e3e8 !important;
        box-shadow: 2px 0 8px rgba(0,0,0,0.04) !important;
        top: 0 !important;
        padding-top: 0 !important;
    }

    [data-testid="stSidebarHeader"] {
        display: none !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Sidebar nav links */
    [data-testid="stSidebar"] a {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #3d4452 !important;
        border-radius: 7px !important;
        padding: 8px 12px !important;
        transition: all 0.15s !important;
        letter-spacing: 0.01em !important;
    }

    [data-testid="stSidebar"] a:hover {
        color: #00a854 !important;
        background: #f0faf5 !important;
    }

    [data-testid="stSidebar"] [aria-current="page"] {
        color: #00a854 !important;
        background: #f0faf5 !important;
        border-left: 3px solid #00a854 !important;
        font-weight: 600 !important;
        padding-left: 9px !important;
    }

    /* Sidebar toggle button */
    [data-testid="stSidebarCollapseButton"] button {
        background: #f8f9fb !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 7px !important;
        color: #3d4452 !important;
        transition: all 0.15s !important;
        visibility: visible !important;
    }

    [data-testid="stSidebarCollapseButton"] button:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
        background: #f0faf5 !important;
    }

    /* Collapsed control — reopen arrow */
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        top: 12px !important;
        left: 12px !important;
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 7px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important;
        z-index: 999999 !important;
        transition: all 0.15s !important;
    }

    [data-testid="collapsedControl"]:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
    }

    /* ══════════════════════════════════════════════════════
       PAGE CONTENT
    ══════════════════════════════════════════════════════ */
    .ts-page-content {
        padding: 0;
        background: #f0f2f5;
        min-height: calc(100vh - 52px);
        width: 100%;
    }

    /* ══════════════════════════════════════════════════════
       BUTTONS
    ══════════════════════════════════════════════════════ */
    div[data-testid="stButton"] button {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: 7px !important;
        border: 1px solid #e0e3e8 !important;
        background: #ffffff !important;
        color: #3d4452 !important;
        padding: 6px 16px !important;
        transition: all 0.15s !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        cursor: pointer !important;
    }

    div[data-testid="stButton"] button:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
        background: #f0faf5 !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
    }

    div[data-testid="stButton"] button:active {
        transform: scale(0.98) !important;
    }

    /* ══════════════════════════════════════════════════════
       INPUTS / TEXT FIELDS
    ══════════════════════════════════════════════════════ */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] select,
    div[data-testid="stMultiSelect"] input {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 7px !important;
        color: #0f1117 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
        padding: 7px 11px !important;
        transition: border-color 0.15s !important;
    }

    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stNumberInput"] input:focus,
    div[data-testid="stSelectbox"] select:focus {
        border-color: #00a854 !important;
        box-shadow: 0 0 0 3px rgba(0,168,84,0.1) !important;
        outline: none !important;
    }

    input::placeholder {
        color: #7a8394 !important;
    }

    /* ══════════════════════════════════════════════════════
       DATAFRAME / TABLES
    ══════════════════════════════════════════════════════ */
    div[data-testid="stDataFrame"] {
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        background: #ffffff !important;
    }

    /* ══════════════════════════════════════════════════════
       METRICS
    ══════════════════════════════════════════════════════ */
    div[data-testid="stMetric"] {
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        padding: 14px 18px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 10px !important;
        font-weight: 700 !important;
        letter-spacing: 0.1em !important;
        color: #7a8394 !important;
        text-transform: uppercase !important;
        font-family: 'Inter', sans-serif !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 20px !important;
        font-weight: 700 !important;
        color: #0f1117 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ══════════════════════════════════════════════════════
       EXPANDER
    ══════════════════════════════════════════════════════ */
    div[data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        overflow: hidden !important;
    }

    details > summary {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        color: #3d4452 !important;
        padding: 12px 16px !important;
        cursor: pointer !important;
    }

    details > summary:hover {
        background: #f8f9fb !important;
        color: #00a854 !important;
    }

    /* ══════════════════════════════════════════════════════
       ALERTS (INFO / SUCCESS / WARNING / ERROR)
    ══════════════════════════════════════════════════════ */
    div[data-testid="stAlert"] {
        border-radius: 7px !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        padding: 12px 14px !important;
        border: 1px solid transparent !important;
    }

    /* Info alert */
    div[data-testid="stAlert"] > div:first-child {
        background: #f0f6ff !important;
        border-color: #2563eb !important;
        color: #1e40af !important;
    }

    /* Success alert */
    div[data-testid="stAlert"] > div:nth-child(2) {
        background: #f0faf5 !important;
        border-color: #00a854 !important;
        color: #0d6e3a !important;
    }

    /* Warning alert */
    div[data-testid="stAlert"] > div:nth-child(3) {
        background: #fffbf0 !important;
        border-color: #f59e0b !important;
        color: #92400e !important;
    }

    /* Error alert */
    div[data-testid="stAlert"] > div:nth-child(4) {
        background: #fff8f8 !important;
        border-color: #e53935 !important;
        color: #7f1d1a !important;
    }

    /* ══════════════════════════════════════════════════════
       COLUMNS / LAYOUT
    ══════════════════════════════════════════════════════ */
    div[data-testid="column"] {
        padding: 0 !important;
        gap: 12px !important;
    }

    /* ══════════════════════════════════════════════════════
       CHECKBOX / RADIO
    ══════════════════════════════════════════════════════ */
    div[data-testid="stCheckbox"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        color: #3d4452 !important;
        cursor: pointer !important;
    }

    div[data-testid="stRadio"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        color: #3d4452 !important;
        cursor: pointer !important;
    }

    /* ══════════════════════════════════════════════════════
       SELECTBOX / MULTISELECT
    ══════════════════════════════════════════════════════ */
    div[data-testid="stSelectbox"] {
        font-family: 'Inter', sans-serif !important;
    }

    div[data-testid="stMultiSelect"] {
        font-family: 'Inter', sans-serif !important;
    }

    /* ══════════════════════════════════════════════════════
       SPINNER / LOADING
    ══════════════════════════════════════════════════════ */
    div[data-testid="stSpinner"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        color: #7a8394 !important;
    }

    /* ══════════════════════════════════════════════════════
       SCROLLBAR
    ══════════════════════════════════════════════════════ */
    ::-webkit-scrollbar {
        width: 5px;
        height: 5px;
    }

    ::-webkit-scrollbar-track {
        background: #f0f2f5;
    }

    ::-webkit-scrollbar-thumb {
        background: #cdd1d8;
        border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #00a854;
    }

    /* ══════════════════════════════════════════════════════
       REUSABLE UTILITY CLASSES
    ══════════════════════════════════════════════════════ */

    /* Card */
    .ts-card {
        background: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        margin-bottom: 10px;
        transition: all 0.15s;
    }

    .ts-card:hover {
        border-color: #cdd1d8;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }

    /* Badge */
    .ts-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 10px;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 20px;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.05em;
    }

    .ts-badge-green {
        background: #f0faf5;
        color: #00a854;
        border: 1px solid #00a85430;
    }

    .ts-badge-red {
        background: #fff8f8;
        color: #e53935;
        border: 1px solid #e5393530;
    }

    .ts-badge-amber {
        background: #fffbf0;
        color: #f59e0b;
        border: 1px solid #f59e0b30;
    }

    .ts-badge-blue {
        background: #f0f6ff;
        color: #2563eb;
        border: 1px solid #2563eb30;
    }

    /* Section label */
    .ts-section-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #7a8394;
        font-family: 'Inter', sans-serif;
        padding: 0 0 8px 0;
        border-bottom: 1px solid #e0e3e8;
        margin-bottom: 12px;
    }

    /* Divider */
    .ts-divider {
        border: none;
        border-top: 1px solid #e0e3e8;
        margin: 14px 0;
    }

    /* Status dot */
    .ts-dot-green {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #00a854;
        display: inline-block;
    }

    .ts-dot-red {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #e53935;
        display: inline-block;
    }

    .ts-dot-amber {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #f59e0b;
        display: inline-block;
    }

    /* Table row states */
    .ts-row-up {
        border-left: 3px solid #00a854 !important;
        background: #f0faf5 !important;
    }

    .ts-row-down {
        border-left: 3px solid #e53935 !important;
        background: #fff8f8 !important;
    }

    </style>
    """, unsafe_allow_html=True)


def page_header(page_title: str, page_icon: str = "", refresh_key: str = None):
    """
    Renders the full TradeSentry header bar — sticky, tight, professional.
    Logo left | Page title | Refresh button + Live clock right
    
    Usage:
        page_header("Watchlist", "📋", refresh_key="watchlist_refresh")
    """
    st.markdown(f"""
    <style>
    .ts-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 20px;
        height: 52px;
        background: #ffffff;
        border-bottom: 1px solid #e0e3e8;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        position: sticky;
        top: 0;
        z-index: 9999;
    }}
    .ts-header-left {{
        display: flex;
        align-items: center;
        gap: 18px;
    }}
    .ts-logo {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #0f1117;
        white-space: nowrap;
    }}
    .ts-logo span {{ color: #00a854; }}
    .ts-divider-v {{
        width: 1px;
        height: 20px;
        background: #e0e3e8;
    }}
    .ts-page-label {{
        font-family: 'Inter', sans-serif;
        font-size: 13px;
        font-weight: 600;
        color: #3d4452;
        letter-spacing: 0.01em;
        display: flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
    }}
    .ts-header-right {{
        display: flex;
        align-items: center;
        gap: 12px;
    }}
    .ts-nifty-chip {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        color: #7a8394;
        background: #f8f9fb;
        border: 1px solid #e0e3e8;
        border-radius: 20px;
        padding: 4px 10px;
        letter-spacing: 0.04em;
    }}
    </style>
    <div class="ts-header">
        <div class="ts-header-left">
            <div class="ts-logo">TRADE<span>SENTRY</span></div>
            <div class="ts-divider-v"></div>
            <div class="ts-page-label">{page_icon} {page_title}</div>
        </div>
        <div class="ts-header-right">
            <div class="ts-nifty-chip" id="ts-time">--:--:--</div>
        </div>
    </div>
    <script>
    function updateTime() {{
        var now = new Date();
        var h = String(now.getHours()).padStart(2,'0');
        var m = String(now.getMinutes()).padStart(2,'0');
        var s = String(now.getSeconds()).padStart(2,'0');
        document.getElementById('ts-time').textContent = h+':'+m+':'+s;
    }}
    setInterval(updateTime, 1000);
    updateTime();
    </script>
    """, unsafe_allow_html=True)

    # Refresh button — native Streamlit so it works
    if refresh_key:
        col_space, col_refresh = st.columns([20, 1])
        with col_refresh:
            if st.button("⟳", key=refresh_key, help="Refresh data"):
                st.cache_data.clear()
                st.rerun()


def sidebar_brand():
    """Render TradeSentry branding in sidebar."""
    with st.sidebar:
        st.markdown("""
        <div style="padding:14px 10px 12px 10px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:14px;
            font-weight:700;color:#0f1117;letter-spacing:0.08em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
            </div>
            <div style="font-size:9px;color:#7a8394;font-family:'Inter',sans-serif;
            font-weight:600;letter-spacing:0.12em;text-transform:uppercase;
            margin-top:3px;">NSE Professional Screener</div>
        </div>
        <hr style="border:none;border-top:1px solid #e0e3e8;margin:0 0 8px 0;">
        """, unsafe_allow_html=True)


def content_wrap_start():
    """Opens the page content wrapper div."""
    st.markdown('<div class="ts-page-content" style="padding: 14px 20px;">', unsafe_allow_html=True)


def content_wrap_end():
    """Closes the page content wrapper div."""
    st.markdown('</div>', unsafe_allow_html=True)
