import streamlit as st

from frontend.api.client import APIError
from frontend.services.auth import AuthService


def render_register(auth_service: AuthService) -> None:
    st.title("Create your account")
    st.caption("Join Live Chat System and start connecting.")
    with st.form("registration_form"):
        username = st.text_input("Username", placeholder="3–50 characters; letters, numbers and _")
        email = st.text_input("Email address", placeholder="you@example.com")
        password = st.text_input("Password", type="password", placeholder="At least 8 characters")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True, type="primary")
    if submitted:
        username, email = username.strip(), email.strip()
        if not username or not email or not password:
            st.error("Please fill in all required fields.")
        elif len(username) < 3 or len(username) > 50:
            st.error("Username must contain between 3 and 50 characters.")
        elif not all(char.isalnum() or char == "_" for char in username):
            st.error("Username can contain only letters, numbers and underscores.")
        elif len(password) < 8:
            st.error("Password must contain at least 8 characters.")
        elif password != confirm_password:
            st.error("Passwords do not match.")
        else:
            try:
                auth_service.register(username, email, password)
                st.success("Account created successfully. Please log in.")
                st.session_state["page"] = "login"
                st.rerun()
            except APIError as exc:
                st.error(str(exc.detail))
    st.divider()
    if st.button("Already have an account? Login"):
        st.session_state["page"] = "login"
        st.rerun()
