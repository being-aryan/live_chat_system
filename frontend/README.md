# Live Chat System — Streamlit Frontend

This frontend connects to the FastAPI backend in the parent project.

## Features

- Registration, login, access-token refresh and logout
- Conversation inbox with unread counts
- Direct conversations and group creation
- Group rename, add-member and leave-group actions
- Message history, send, edit and soft-delete
- Delivery/read receipt updates
- WebSocket ticket authentication and event listener with reconnect attempts
- Message history refresh through the API as a fallback

## Setup

From the project root:

```bash
poetry run pip install -r frontend/requirements.txt
```

Set the backend URL in the root `.env` file, or export it in your shell:

```env
BACKEND_API_URL=http://127.0.0.1:8000
FRONTEND_ORIGIN=http://localhost:8501
```

The backend's `ALLOWED_ORIGINS` must include the exact frontend origin, normally:

```env
ALLOWED_ORIGINS=["http://localhost:8501","http://127.0.0.1:8501"]
```

Run the backend in one terminal:

```bash
poetry run python -m uvicorn app.main:app --reload
```

Run Streamlit in another terminal from the project root:

```bash
poetry run streamlit run frontend/app.py
```

Open `http://localhost:8501`.

## Notes

- The frontend uses the backend's existing JSON request schemas and `/api/v1` routes.
- WebSocket connections use `POST /api/v1/ws/ticket`, then send the first frame as `{"type":"auth","ticket":"..."}` to `/api/v1/ws/connect`.
- WebSocket Origin validation is strict. Keep `FRONTEND_ORIGIN` and backend `ALLOWED_ORIGINS` aligned. If you open Streamlit using `127.0.0.1`, set `FRONTEND_ORIGIN=http://127.0.0.1:8501` and add that origin to the backend allowlist.
- Streamlit session state is not a persistent token vault. Logging out clears the frontend's in-session credentials.
- The inbox response exposes member UUIDs but not usernames. Direct conversation entries therefore use a generic title until a conversation is renamed/otherwise identified by the backend.
