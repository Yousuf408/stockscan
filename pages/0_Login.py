# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — login.py  v1.0
#  Email login / signup using Supabase Auth (plain requests — no supabase client)
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os

st.set_page_config(page_title="Trade Sentry — Login", layout="centered")

# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE AUTH HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def auth_sign_up(email: str, password: str) -> dict:
    url, key = _get_config()
    res = requests.post(
        f"{url}/auth/v1/signup",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    return res.json()


def auth_sign_in(email: str, password: str) -> dict:
    url, key = _get_config()
    res = requests.post(
        f"{url}/auth/v1/token?grant_type=password",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    return res.json()


def auth_sign_out(access_token: str):
    url, key = _get_config()
    requests.post(
        f"{url}/auth/v1/logout",
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        },
        timeout=10,
    )


def auth_reset_password(email: str) -> dict:
    url, key = _get_config()
    res = requests.post(
        f"{url}/auth/v1/recover",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email},
        timeout=10,
    )
    return res.json()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def get_user_id() -> str:
    return st.session_state.get("user_id", "")


def get_user_email() -> str:
    return st.session_state.get("user_email", "")


def get_access_token() -> str:
    return st.session_state.get("access_token", "")


def _set_session(data: dict):
    user  = data.get("user") or {}
    uid   = user.get("id", "")
    email = user.get("email", "")
    token = data.get("access_token", "")
    st.session_state["user_id"]      = uid
    st.session_state["user_email"]   = email
    st.session_state["access_token"] = token
    # Save to cookie for 7-day persistence
    try:
        import sys, os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from auth import save_session_to_cookie
        save_session_to_cookie(token, uid, email)
    except Exception as e:
        print(f"[login] Cookie save failed: {e}")


def logout():
    token = get_access_token()
    if token:
        auth_sign_out(token)
    for k in ["user_id", "user_email", "access_token", "results", "scan_log"]:
        st.session_state.pop(k, None)
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.login-box {
    max-width: 420px; margin: 60px auto 0;
    background: #ffffff; border: 1px solid #e8e8e8;
    border-radius: 14px; padding: 36px 32px;
}
.login-title {
    font-size: 22px; font-weight: 800;
    color: #111111; margin-bottom: 4px;
    font-family: monospace;
}
.login-sub {
    font-size: 13px; color: #888888; margin-bottom: 24px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="login-box">', unsafe_allow_html=True)
st.markdown('<p class="login-title">TRADE SENTRY</p>', unsafe_allow_html=True)
st.markdown('<p class="login-sub">NSE Professional Screener</p>', unsafe_allow_html=True)

tab_login, tab_signup, tab_reset = st.tabs(["Login", "Sign Up", "Forgot Password"])

# ── LOGIN ──
with tab_login:
    with st.form("login_form"):
        email    = st.text_input("Email",    placeholder="you@email.com")
        password = st.text_input("Password", placeholder="••••••••", type="password")
        li_btn   = st.form_submit_button("Login", use_container_width=True)

    if li_btn:
        if not email or not password:
            st.error("Enter email and password.")
        else:
            with st.spinner("Signing in..."):
                data = auth_sign_in(email.strip(), password.strip())
            if data.get("access_token"):
                _set_session(data)
                st.success("Logged in!")
                st.switch_page("app.py")
            else:
                msg = data.get("error_description") or data.get("msg") or "Login failed."
                st.error(msg)

# ── SIGN UP ──
with tab_signup:
    with st.form("signup_form"):
        su_email = st.text_input("Email",            placeholder="you@email.com")
        su_pass  = st.text_input("Password",         placeholder="Min 6 characters", type="password")
        su_pass2 = st.text_input("Confirm Password", placeholder="Repeat password",  type="password")
        su_btn   = st.form_submit_button("Create Account", use_container_width=True)

    if su_btn:
        if not su_email or not su_pass:
            st.error("Fill in all fields.")
        elif su_pass != su_pass2:
            st.error("Passwords do not match.")
        elif len(su_pass) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            with st.spinner("Creating account..."):
                data = auth_sign_up(su_email.strip(), su_pass.strip())
            if data.get("id") or data.get("access_token"):
                st.success("Account created! Please login below.")
            else:
                msg = data.get("error_description") or data.get("msg") or "Signup failed."
                st.error(msg)

# ── FORGOT PASSWORD ──
with tab_reset:
    with st.form("reset_form"):
        rp_email = st.text_input("Email", placeholder="you@email.com")
        rp_btn   = st.form_submit_button("Send Reset Link", use_container_width=True)

    if rp_btn:
        if not rp_email:
            st.error("Enter your email.")
        else:
            with st.spinner("Sending..."):
                auth_reset_password(rp_email.strip())
            st.success("Reset link sent! Check your inbox.")

st.markdown('</div>', unsafe_allow_html=True)
