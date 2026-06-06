# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth.py  v3.0
#  Persistent login via cookies using extra-streamlit-components
#  Add to requirements.txt: extra-streamlit-components
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os
from datetime import datetime, timedelta

COOKIE_NAME    = "ts_session"
COOKIE_EXPIRY  = 7  # days


def _get_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def _get_cookie_manager():
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager(key="ts_cookie_mgr")
    except Exception as e:
        print(f"[auth] CookieManager init failed: {e}")
        return None


def _verify_token(access_token: str) -> dict:
    try:
        url, key = _get_config()
        res = requests.get(
            f"{url}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if res.status_code == 200:
            return res.json()
        return {}
    except Exception:
        return {}


def restore_session() -> bool:
    """
    Call at top of EVERY page before auth guard.
    Reads cookie and restores session if token is valid.
    """
    # Already logged in this session
    if st.session_state.get("user_id"):
        return True

    cm = _get_cookie_manager()
    if cm is None:
        return False

    # Read cookie
    token = cm.get(COOKIE_NAME)
    if not token:
        return False

    # Parse stored value: "user_id|user_email|access_token"
    try:
        parts = token.split("|")
        if len(parts) != 3:
            return False
        uid, email, access_token = parts
    except Exception:
        return False

    if not access_token or not uid:
        return False

    # Verify token with Supabase
    user = _verify_token(access_token)
    if user.get("id"):
        st.session_state["user_id"]      = user.get("id", uid)
        st.session_state["user_email"]   = user.get("email", email)
        st.session_state["access_token"] = access_token
        return True
    else:
        # Token expired — delete cookie
        try:
            cm.delete(COOKIE_NAME)
        except Exception:
            pass
        return False


def save_session_to_cookie(access_token: str, user_id: str, user_email: str):
    """Save session cookie after login."""
    try:
        cm = _get_cookie_manager()
        if cm is None:
            return
        value   = f"{user_id}|{user_email}|{access_token}"
        expires = datetime.now() + timedelta(days=COOKIE_EXPIRY)
        cm.set(COOKIE_NAME, value, expires_at=expires)
    except Exception as e:
        print(f"[auth] Cookie save failed: {e}")


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def logout():
    """Clear session and cookie."""
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

    # Delete cookie
    try:
        cm = _get_cookie_manager()
        if cm:
            cm.delete(COOKIE_NAME)
    except Exception:
        pass

    # Clear session state
    for k in ["user_id", "user_email", "access_token", "results",
              "scan_log", "wl_names", "db_results_loaded"]:
        st.session_state.pop(k, None)

    st.rerun()
