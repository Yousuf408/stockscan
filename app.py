"""
TradeOS — Main Entry Point
Simple routing: Login → Broker Setup → Screener
"""

import streamlit as st

# ── Page Config ──
st.set_page_config(
    page_title="TradeOS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Session State Init ──
if 'user' not in st.session_state:
    st.session_state['user'] = None

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if 'broker_configured' not in st.session_state:
    st.session_state['broker_configured'] = False

if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'login'

# ── Import modules ──
from tv_screener.auth import login_user, signup_user, logout_user, get_user
from tv_screener.pages.broker_setup import render_broker_setup

# ═══════════════════════════════════════════════════════════
# CHECK LOGIN
# ═══════════════════════════════════════════════════════════

user = get_user()

if user is None:
    # ═══════════════════════════════════════════════════════
    # LOGIN PAGE
    # ═══════════════════════════════════════════════════════
    
    st.markdown("""
    <div style="text-align:center; padding:3rem 0 1rem 0;">
        <h1 style="color:#1a1a2e; font-size:2.5rem; margin:0;">📊 TradeOS</h1>
        <p style="color:#888; font-size:1rem;">Semi-Automated Trading Workstation</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    
    with col2:
        tab1, tab2 = st.tabs(["🔐 Login", "✨ Create Account"])
        
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login", type="primary", use_container_width=True):
                if not email or not password:
                    st.error("Please fill all fields")
                else:
                    with st.spinner("Logging in..."):
                        user_obj, error = login_user(email, password)
                        if error:
                            st.error(f"Login failed: {error}")
                        else:
                            st.session_state['user'] = user_obj
                            st.session_state['authenticated'] = True
                            st.success("✅ Login successful!")
                            st.rerun()
        
        with tab2:
            name = st.text_input("Full Name", key="signup_name")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            
            if st.button("Create Account", type="primary", use_container_width=True):
                if not name or not email or not password:
                    st.error("Please fill all fields")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    with st.spinner("Creating account..."):
                        user_obj, error = signup_user(email, password, name)
                        if error:
                            st.error(f"Signup failed: {error}")
                        else:
                            st.success("✅ Account created! Check your email to verify, then login.")
    
    # Stop here — don't show anything else
    st.stop()

# ═══════════════════════════════════════════════════════════
# USER IS LOGGED IN
# ═══════════════════════════════════════════════════════════

# ── Sidebar ──
with st.sidebar:
    st.markdown(f"### 👤 {user.email}")
    st.markdown("---")
    
    # Navigation
    if st.button("🔍 Screener", use_container_width=True):
        st.session_state['current_page'] = 'screener'
        st.rerun()
    
    if st.button("⚙️ Broker Setup", use_container_width=True):
        st.session_state['current_page'] = 'setup'
        st.rerun()
    
    st.markdown("---")
    
    if st.button("🚪 Logout", use_container_width=True):
        logout_user()
        st.rerun()

# ── Page Router ──
current_page = st.session_state.get('current_page', 'setup')

if current_page == 'setup':
    render_broker_setup()
    
elif current_page == 'screener':
    # Check if broker is configured
    if not st.session_state.get('broker_configured', False):
        st.warning("⚠️ Please configure your broker first")
        if st.button("Go to Broker Setup"):
            st.session_state['current_page'] = 'setup'
            st.rerun()
    else:
        # Run your existing screener code
        # Import and execute observation.py logic
        import observation  # or exec(open("observation.py").read())
