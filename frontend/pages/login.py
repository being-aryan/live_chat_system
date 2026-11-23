import streamlit as st

from frontend.api.client import APIError
from frontend.services.auth import AuthService


def render_login(auth_service: AuthService) -> None:
    st.title("Welcome back")
    st.caption("Log in to continue to Live Chat System.")
    with st.form("login_form"):
        email = st.text_input("Email address", placeholder="you@example.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")
    if submitted:
        if not email.strip() or not password:
            st.error("Please enter your email and password.")
        else:
            try:
                auth_service.login(email.strip(), password)
                st.session_state["page"] = "dashboard"
                st.rerun()
            except APIError as exc:
                st.error(str(exc.detail))
    st.divider()
    if st.button("Don't have an account? Register"):
        st.session_state["page"] = "register"
        st.rerun()
