import os

from dotenv import load_dotenv

load_dotenv()

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_V1_URL = f"{BACKEND_API_URL}/api/v1"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8501").rstrip("/")

if BACKEND_API_URL.startswith("https://"):
    WEBSOCKET_BASE_URL = BACKEND_API_URL.replace("https://", "wss://", 1)
else:
    WEBSOCKET_BASE_URL = BACKEND_API_URL.replace("http://", "ws://", 1)

WEBSOCKET_URL = f"{WEBSOCKET_BASE_URL}/api/v1/ws/connect"
APP_TITLE = "Live Chat System"
APP_ICON = "💬"
