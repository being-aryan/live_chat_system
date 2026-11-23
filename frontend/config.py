
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_backend_url() -> str:
    default_url = "http://127.0.0.1:8000"

    try:
        backend_url = st.secrets.get(
            "BACKEND_API_URL",
            os.getenv("BACKEND_API_URL", default_url),
        )
    except Exception:
        backend_url = os.getenv("BACKEND_API_URL", default_url)

    return backend_url.strip().rstrip("/")


BACKEND_API_URL = get_backend_url()

API_V1_URL = f"{BACKEND_API_URL}/api/v1"

if BACKEND_API_URL.startswith("https://"):
    WEBSOCKET_BASE_URL = BACKEND_API_URL.replace(
        "https://", "wss://", 1
    )
elif BACKEND_API_URL.startswith("http://"):
    WEBSOCKET_BASE_URL = BACKEND_API_URL.replace(
        "http://", "ws://", 1
    )
else:
    raise ValueError("BACKEND_API_URL must start with http:// or https://")

WEBSOCKET_URL = f"{WEBSOCKET_BASE_URL}/api/v1/ws/connect"

WEBSOCKET_TICKET_URL = f"{API_V1_URL}/ws/ticket"

APP_TITLE = "Live Chat System"
APP_ICON = "💬"
