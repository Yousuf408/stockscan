"""
Simple Supabase Authentication.
Handles: Login, Signup, Logout, Get Current User.
"""

import streamlit as st
from tv_screener.database import supabase


def login_user(email, password):
    """
    Login existing user with email and password.
    Returns: (user_object, error_message)
    """
    try:
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return result.user, None
    except Exception as e:
        return None, str(e)


def signup_user(email, password, name):
    """
    Create a new account.
    Returns: (user_object, error_message)
    """
    try:
        result = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "display_name": name
                }
            }
        })
        return result.user, None
    except Exception as e:
        return None, str(e)


def logout_user():
    """Clear user session and sign out from Supabase."""
    st.session_state['user'] = None
    st.session_state['authenticated'] = False
    st.session_state['broker_configured'] = False
    try:
        supabase.auth.sign_out()
    except:
        pass


def get_user():
    """Return currently logged in user, or None if not logged in."""
    return st.session_state.get('user')
