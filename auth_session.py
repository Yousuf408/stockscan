# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth_session.py  v2.0
#  Session persistence using Supabase sessions table + st.query_params
#  Works 100% on Streamlit Cloud — no cookies, no extra libraries needed.
#
#  HOW IT WORKS:
#    Login → saves refresh_token to Supabase sessions table
#          → puts session ID in URL as ?sid=xxxx
#    Page load → reads ?sid from URL → fetches token from Supabase
#              → calls Supabase refresh endpoint → restores session_state
#    Logout → deletes session row from Supabase → clears URL param
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL: Supabase config
# ─────────────────────────────────────────────────────────────────────────────

def _get_config():
    try:
        url         = st.secrets["SUPABASE_URL"].rstrip("/")
        key         = st.secrets["SUPABASE_KEY"]
        service_key = st.secrets["SUPABASE_SERVICE_KEY"]
    except Exception:
        url         = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key         = os.environ.get("SUPABASE_KEY", "")
        service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    return url, key, service_key


def _service_headers():
    _, _, service_key = _get_config()
    return {
        "apikey":        service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: save session to Supabase after login
# ─────────────────────────────────────────────────────────────────────────────

def save_refresh_token(refresh_token: str):
    """
    Call after successful login.
    Saves refresh_token to Supabase sessions table.
    Puts session ID in URL as ?sid=xxxx
    """
    if not refresh_token:
        return

    user_id    = st.session_state.get("user_id", "")
    user_email = st.session_state.get("user_email", "")

    try:
        url, _, _ = _get_config()
        res = requests.post(
            f"{url}/rest/v1/sessions",
            headers=_service_headers(),
            json={
                "user_id":       user_id,
                "user_email":    user_email,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        data = res.json()
        if isinstance(data, list) and len(data) > 0:
            session_id = data[0].get("id", "")
            if session_id:
                st.query_params["sid"] = session_id
                st.session_state["session_id"] = session_id
    except Exception as e:
        print(f"[auth_session] save_refresh_token failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: delete session on logout
# ─────────────────────────────────────────────────────────────────────────────

def delete_refresh_token():
    """
    Call during logout.
    Deletes session row from Supabase and clears URL param.
    """
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        session_id = st.query_params.get("sid", "")

    if session_id:
        try:
            url, _, _ = _get_config()
            requests.delete(
                f"{url}/rest/v1/sessions?id=eq.{session_id}",
                headers=_service_headers(),
                timeout=10,
            )
        except Exception as e:
            print(f"[auth_session] delete_refresh_token failed: {e}")

    # Clear URL param and session state
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.session_state.pop("session_id", None)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: restore session on every page load
# ─────────────────────────────────────────────────────────────────────────────

def restore_session() -> bool:
    """
    Call this BEFORE the auth guard on every protected page.

    Flow:
      1. Already logged in → skip
      2. Read ?sid from URL
      3. Fetch refresh_token from Supabase sessions table
      4. Call Supabase refresh endpoint → get fresh access_token
      5. Repopulate st.session_state
    """

    # Already logged in
    if st.session_state.get("user_id"):
        return True

    # Read session ID from URL
    session_id = st.query_params.get("sid", "")
    if not session_id:
        return False

    try:
        url, key, service_key = _get_config()

        # Fetch session row from Supabase
        res = requests.get(
            f"{url}/rest/v1/sessions?id=eq.{session_id}&select=*",
            headers=_service_headers(),
            timeout=10,
        )
        rows = res.json()

        if not isinstance(rows, list) or len(rows) == 0:
            st.query_params.clear()
            return False

        refresh_token = rows[0].get("refresh_token", "")
        if not refresh_token:
            st.query_params.clear()
            return False

        # Call Supabase refresh endpoint
        refresh_res = requests.post(
            f"{url}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        data = refresh_res.json()

        if not data.get("access_token"):
            # Token expired — delete session row
            requests.delete(
                f"{url}/rest/v1/sessions?id=eq.{session_id}",
                headers=_service_headers(),
                timeout=10,
            )
            st.query_params.clear()
            return False

        # Restore session state
        user = data.get("user") or {}
        st.session_state["user_id"]      = user.get("id", "")
        st.session_state["user_email"]   = user.get("email", "")
        st.session_state["access_token"] = data.get("access_token", "")
        st.session_state["session_id"]   = session_id

        # Update refresh token in Supabase (token rotation)
        new_refresh_token = data.get("refresh_token", "")
        if new_refresh_token:
            requests.patch(
                f"{url}/rest/v1/sessions?id=eq.{session_id}",
                headers=_service_headers(),
                json={"refresh_token": new_refresh_token},
                timeout=10,
            )

        print(f"[auth_session] Session restored for {user.get('email', '?')}")
        return True

    except Exception as e:
        print(f"[auth_session] restore_session failed: {e}")
        return False
