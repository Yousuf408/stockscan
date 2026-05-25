import streamlit as st
import streamlit.components.v1 as components

# ══════════════════════════════════════════
#  TRADESENTRY — styles.py v2.0
#  Professional White Theme
#  Global CSS + Header component
# ══════════════════════════════════════════

def apply_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* ── KILL ALL STREAMLIT DEFAULT SPACING ── */
    #root > div:first-child { padding-top: 0 !important; }
    .stApp > header { display: none !important; height: 0 !important; }
    header[data-testid="stHeader"] { display: none !important; height: 0 !important; }
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
    }

    /* ── SIDEBAR ── */
    [data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #e0e3e8 !important;
        box-shadow: 2px 0 8px rgba(0,0,0,0.04) !important;
        top: 0 !important;
    }
    [data-testid="stSidebarHeader"] {
        display: none !important;
        height: 0 !important;
        padding: 0 !important;
    }
    [data-testid="stSidebar"] a {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #3d4452 !important;
        border-radius: 7px !important;
        padding: 8px 12px !important;
        transition: all 0.15s !important;
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
    }

    /* ── SIDEBAR TOGGLE — always visible ── */
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        top: 12px !important;
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 7px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important;
        z-index: 999999 !important;
    }
    [data-testid="collapsedControl"]:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        background: #f8f9fb !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 7px !important;
        color: #3d4452 !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
        background: #f0faf5 !important;
    }

    /* ── PAGE CONTENT WRAPPER ── */
    .ts-page-content {
        padding: 16px 24px;
        background: #f0f2f5;
        min-height: calc(100vh - 52px);
    }

    /* ── BUTTONS ── */
    div[data-testid="stButton"] button {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: 7px !important;
        border: 1px solid #e0e3e8 !important;
        background: #ffffff !important;
        color: #3d4452 !important;
        padding: 5px 14px !important;
        transition: all 0.15s !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }
    div[data-testid="stButton"] button:hover {
        border-color: #00a854 !important;
        color: #00a854 !important;
        background: #f0faf5 !important;
    }

    /* ── DATAFRAME ── */
    div[data-testid="stDataFrame"] {
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }

    /* ── EXPANDER ── */
    div[data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid #e0e3e8 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        margin-top: 12px !important;
    }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #f0f2f5; }
    ::-webkit-scrollbar-thumb { background: #cdd1d8; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #00a854; }
    </style>
    """, unsafe_allow_html=True)


def page_header(page_title: str, page_icon: str = "", refresh_key: str = None):
    """
    Renders the full TradeSentry header bar.
    Logo left | Page title center-left | Refresh button right
    Returns True if refresh was clicked.
    """
    # Inject header CSS + HTML
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
        margin-bottom: 0;
    }}
    .ts-header-left {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    .ts-logo {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #0f1117;
        text-decoration: none;
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
    }}
    .ts-header-right {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .ts-nifty-chip {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        color: #7a8394;
        background: #f0f2f5;
        border: 1px solid #e0e3e8;
        border-radius: 20px;
        padding: 3px 10px;
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
        var el = document.getElementById('ts-time');
        if(el) el.textContent = h+':'+m+':'+s;
    }}
    setInterval(updateTime, 1000);
    updateTime();
    </script>
    """, unsafe_allow_html=True)

    # Refresh button — Streamlit native (so it works)
    if refresh_key:
        col_spacer, col_btn = st.columns([20, 1])
        with col_btn:
            if st.button("⟳", key=refresh_key, help="Refresh data"):
                st.cache_data.clear()
                st.rerun()


def sidebar_brand():
    """TradeSentry branding in sidebar."""
    with st.sidebar:
        st.markdown("""
        <div style="padding:16px 12px 14px 12px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:14px;
            font-weight:700;color:#0f1117;letter-spacing:0.08em;">
                TRADE<span style="color:#00a854;">SENTRY</span>
            </div>
            <div style="font-size:9px;color:#7a8394;font-family:'Inter',sans-serif;
            font-weight:600;letter-spacing:0.12em;text-transform:uppercase;
            margin-top:3px;">NSE Professional Screener</div>
        </div>
        <hr style="border:none;border-top:1px solid #e0e3e8;margin:0 0 6px 0;">
        """, unsafe_allow_html=True)


def content_wrap_start():
    """Opens the page content wrapper div."""
    st.markdown('<div class="ts-page-content">', unsafe_allow_html=True)


def content_wrap_end():
    """Closes the page content wrapper div."""
    st.markdown('</div>', unsafe_allow_html=True)
