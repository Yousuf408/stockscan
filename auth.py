# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth.py
#  Persistent login via browser localStorage
#  Import and call restore_session() at top of every page
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import streamlit.components.v1 as components
import requests
import os


def _get_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def _verify_token(access_token: str) -> dict:
    """Verify token with Supabase and get user info."""
    try:
        url, key = _get_config()
        res = requests.get(
            f"{url}/auth/v1/user",
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
        if res.status_code == 200:
            return res.json()
        return {}
    except Exception:
        return {}


def save_session_to_browser(access_token: str, user_id: str, user_email: str):
    """Save session to browser localStorage — persists across refreshes."""
    components.html(f"""
    <script>
        localStorage.setItem('ts_access_token', '{access_token}');
        localStorage.setItem('ts_user_id',      '{user_id}');
        localStorage.setItem('ts_user_email',   '{user_email}');
        localStorage.setItem('ts_saved_at',     Date.now().toString());
    </script>
    """, height=0)


def clear_session_from_browser():
    """Clear session from browser localStorage."""
    components.html("""
    <script>
        localStorage.removeItem('ts_access_token');
        localStorage.removeItem('ts_user_id');
        localStorage.removeItem('ts_user_email');
        localStorage.removeItem('ts_saved_at');
    </script>
    """, height=0)


def restore_session():
    """
    Call at the top of every page.
    If session_state has user_id → already logged in, skip.
    If not → inject JS to read localStorage and post back via query params.
    """
    # Already logged in in this session
    if st.session_state.get("user_id"):
        return True

    # Check query params — JS posts token back via URL
    params = st.query_params
    token  = params.get("ts_token", "")
    uid    = params.get("ts_uid", "")
    email  = params.get("ts_email", "")

    if token and uid:
        # Verify token is still valid with Supabase
        user = _verify_token(token)
        if user.get("id"):
            st.session_state["user_id"]      = user.get("id", uid)
            st.session_state["user_email"]   = user.get("email", email)
            st.session_state["access_token"] = token
            # Clear query params
            st.query_params.clear()
            return True
        else:
            # Token expired — clear browser storage
            clear_session_from_browser()
            st.query_params.clear()
            return False

    # Inject JS to read localStorage and redirect with token in params
    components.html("""
    <script>
        const token = localStorage.getItem('ts_access_token');
        const uid   = localStorage.getItem('ts_user_id');
        const email = localStorage.getItem('ts_user_email');
        const saved = parseInt(localStorage.getItem('ts_saved_at') || '0');
        const WEEK  = 7 * 24 * 60 * 60 * 1000;

        if (token && uid && (Date.now() - saved) < WEEK) {
            // Token exists and within 7 days — restore session
            const url = new URL(window.location.href);
            url.searchParams.set('ts_token', token);
            url.searchParams.set('ts_uid',   uid);
            url.searchParams.set('ts_email', email || '');
            window.location.href = url.toString();
        }
    </script>
    """, height=0)

    return False


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def logout():
    """Clear session state and browser storage."""
    try:
        token = st.session_state.get("access_token", "")
        if token:
            url, key = _get_config()
            requests.post(
                f"{url}/auth/v1/logout",
                headers={"apikey": key, "Authorization": f"Bearer {token}"},
                timeout=5,
            )
    except Exception:
        pass

    for k in ["user_id", "user_email", "access_token", "results",
              "scan_log", "wl_names", "db_results_loaded"]:
        st.session_state.pop(k, None)

    clear_session_from_browser()
    st.rerun()
