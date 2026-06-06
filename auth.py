# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth.py  v2.0
#  Persistent login via browser cookies (7 days)
#  Uses streamlit-cookies-manager
#  Add to requirements.txt: streamlit-cookies-manager
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os

# ─────────────────────────────────────────────────────────────────────────────
# COOKIE MANAGER — singleton per session
# ─────────────────────────────────────────────────────────────────────────────

def _get_cookie_manager():
    """Get or create cookie manager — singleton."""
    if "cookie_manager" not in st.session_state:
        try:
            from streamlit_cookies_manager import EncryptedCookieManager
            cm = EncryptedCookieManager(
                prefix="tradesentry_",
                password=_get_cookie_secret(),
            )
            st.session_state["cookie_manager"] = cm
        except Exception as e:
            print(f"[auth] Cookie manager init failed: {e}")
            st.session_state["cookie_manager"] = None
    return st.session_state["cookie_manager"]


def _get_cookie_secret() -> str:
    try:
        return st.secrets.get("COOKIE_SECRET", "tradesentry_secret_key_2024")
    except Exception:
        return os.environ.get("COOKIE_SECRET", "tradesentry_secret_key_2024")


def _get_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def _verify_token(access_token: str) -> dict:
    """Verify token with Supabase and return user info."""
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


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def restore_session() -> bool:
    """
    Call at top of every page BEFORE auth guard.
    1. If session_state has user_id → already logged in ✅
    2. Else → read token from cookie → verify → restore session
    Returns True if logged in, False if not.
    """
    # Already logged in
    if st.session_state.get("user_id"):
        return True

    cm = _get_cookie_manager()
    if cm is None:
        return False

    # Cookie manager must be ready — if not ready yet, return False
    # It will be ready on next rerun
    if not cm.ready():
        return False

    token = cm.get("access_token", "")
    uid   = cm.get("user_id", "")
    email = cm.get("user_email", "")

    if not token or not uid:
        return False

    # Verify token is still valid
    user = _verify_token(token)
    if user.get("id"):
        st.session_state["user_id"]      = user.get("id", uid)
        st.session_state["user_email"]   = user.get("email", email)
        st.session_state["access_token"] = token
        return True
    else:
        # Token expired — clear cookies
        save_session_to_cookie("", "", "")
        return False


def save_session_to_cookie(access_token: str, user_id: str, user_email: str):
    """Save session to cookie after login."""
    cm = _get_cookie_manager()
    if cm is None:
        return
    if not cm.ready():
        return
    cm["access_token"] = access_token
    cm["user_id"]      = user_id
    cm["user_email"]   = user_email
    cm.save()


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def logout():
    """Clear session and cookies."""
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

    # Clear cookies
    save_session_to_cookie("", "", "")

    # Clear session state
    for k in ["user_id", "user_email", "access_token", "results",
              "scan_log", "wl_names", "db_results_loaded", "cookie_manager"]:
        st.session_state.pop(k, None)

    st.rerun()
