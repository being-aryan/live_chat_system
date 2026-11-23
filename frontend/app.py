import streamlit as st

from frontend.config import APP_ICON, APP_TITLE
from frontend.pages.dashboard import render_dashboard
from frontend.pages.login import render_login
from frontend.pages.register import render_register
from frontend.api.client import APIError
from frontend.services.auth import AuthService
from frontend.services.websocket import WebSocketService


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_styles() -> None:
    from pathlib import Path

    css_path = Path(__file__).parent / "styles" / "main.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


load_styles()

if "page" not in st.session_state:
    st.session_state["page"] = "dashboard" if st.session_state.get("access_token") else "login"

auth_service = AuthService(st.session_state)

if auth_service.is_authenticated():
    try:
        st.session_state["current_user"] = auth_service.get_current_user()
    except APIError:
        auth_service.clear_session()
        st.session_state["page"] = "login"

if auth_service.is_authenticated():
    if "websocket_service" not in st.session_state:
        websocket_service = WebSocketService(st.session_state["access_token"])
        websocket_service.start()
        st.session_state["websocket_service"] = websocket_service
    elif st.session_state["websocket_service"].access_token != st.session_state["access_token"]:
        st.session_state["websocket_service"].stop()
        websocket_service = WebSocketService(st.session_state["access_token"])
        websocket_service.start()
        st.session_state["websocket_service"] = websocket_service
else:
    old_service = st.session_state.pop("websocket_service", None)
    if old_service:
        old_service.stop()

page = st.session_state.get("page", "login")
if page == "register":
    render_register(auth_service)
elif page == "dashboard" and auth_service.is_authenticated():
    render_dashboard(auth_service)
else:
    st.session_state["page"] = "login"
    render_login(auth_service)
