# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth_session.py  v1.0
#  Handles refresh-token persistence via browser cookie.
#  Uses Supabase's existing /auth/v1/token?grant_type=refresh_token endpoint.
#  NO new DB tables needed — Supabase manages refresh tokens internally.
#
#  PUBLIC API (import these in other files):
#    save_refresh_token(refresh_token)  — call after successful login
#    restore_session()                  — call at top of every protected page
#    delete_refresh_token()             — call on logout
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os

COOKIE_NAME    = "ts_refresh_token"   # cookie key stored in browser
COOKIE_EXPIRY  = 30                   # days before cookie expires


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL: cookie manager (singleton — initialised once per session)
# ─────────────────────────────────────────────────────────────────────────────

def _get_cookie_manager():
    """
    Returns the CookieManager instance.
    Cached in session_state so we don't re-initialise on every rerun.
    """
    if "cookie_manager" not in st.session_state:
        try:
            import extra_streamlit_components as stx
            st.session_state["cookie_manager"] = stx.CookieManager(key="ts_cookie_mgr")
        except ImportError:
            st.session_state["cookie_manager"] = None
            print("[auth_session] WARNING: extra-streamlit-components not installed. "
                  "Run: pip install extra-streamlit-components")
    return st.session_state["cookie_manager"]


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL: Supabase config
# ─────────────────────────────────────────────────────────────────────────────

def _get_supabase_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: save refresh token to browser cookie
# ─────────────────────────────────────────────────────────────────────────────

def save_refresh_token(refresh_token: str):
    """
    Call this right after a successful Supabase login.
    Stores the refresh_token in a browser cookie for 30 days.
    """
    if not refresh_token:
        return
    mgr = _get_cookie_manager()
    if mgr is None:
        return
    try:
        from datetime import datetime, timedelta
        expiry = datetime.now() + timedelta(days=COOKIE_EXPIRY)
        mgr.set(COOKIE_NAME, refresh_token, expires_at=expiry, key="save_rt")
    except Exception as e:
        print(f"[auth_session] save_refresh_token failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: delete cookie on logout
# ─────────────────────────────────────────────────────────────────────────────

def delete_refresh_token():
    """
    Call this during logout — removes the cookie from the browser.
    """
    mgr = _get_cookie_manager()
    if mgr is None:
        return
    try:
        mgr.delete(COOKIE_NAME, key="del_rt")
    except Exception as e:
        print(f"[auth_session] delete_refresh_token failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: restore session from cookie (call at top of every protected page)
# ─────────────────────────────────────────────────────────────────────────────

def restore_session() -> bool:
    """
    Call this BEFORE the auth guard check on every protected page.

    Flow:
      1. If st.session_state already has user_id → already logged in, skip.
      2. Read refresh_token from browser cookie.
      3. POST to Supabase /auth/v1/token?grant_type=refresh_token
      4. If successful → populate st.session_state + rotate the cookie.
      5. Returns True if session was restored, False otherwise.
    """

    # Already logged in (normal navigation within same session)
    if st.session_state.get("user_id"):
        return True

    # Try to read cookie
    mgr = _get_cookie_manager()
    if mgr is None:
        return False

    try:
        refresh_token = mgr.get(COOKIE_NAME)
    except Exception:
        return False

    if not refresh_token:
        return False

    # Call Supabase refresh endpoint
    try:
        url, key = _get_supabase_config()
        res = requests.post(
            f"{url}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        data = res.json()
    except Exception as e:
        print(f"[auth_session] refresh request failed: {e}")
        return False

    if not data.get("access_token"):
        # Refresh token expired or revoked — clean up cookie
        delete_refresh_token()
        return False

  # Repopulate session state
    user = data.get("user") or {}
    st.session_state["user_id"]      = user.get("id", "")
    st.session_state["user_email"]   = user.get("email", "")
    st.session_state["access_token"] = data.get("access_token", "")

    # Rotate cookie with the NEW refresh_token Supabase issued
    new_refresh_token = data.get("refresh_token", "")
    if new_refresh_token:
        save_refresh_token(new_refresh_token)

    print(f"[auth_session] Session restored for {user.get('email', '?')}")
    st.rerun()   # ← ADD THIS LINE
    return True
