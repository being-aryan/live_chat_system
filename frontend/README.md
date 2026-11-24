# 💬 Streamlit Live Chat Frontend

A clean, modern, native Streamlit frontend tailored specifically to the FastAPI chat backend.

## ✨ Features
- **Native Chat UI**: Uses Streamlit's official `st.chat_message()` and `st.chat_input()` pinned input bar.
- **Auto Token Refresh**: Automatically detects expired 15-minute access tokens and refreshes them in the background via `/auth/refresh`.
- **Direct & Group Chats**: Search for users to initiate 1-on-1 chats, or create group chats with custom names and member selection.
- **Group Management**: Group admins can rename groups, add new members, and members can leave groups with automatic admin succession.
- **Unread Badges & Read Receipts**: Displays real-time unread count badges (`🔴 2`) and marks conversations as read in a single batch call without server spam.
- **Lightweight & Fast**: Eliminates fragile multi-threaded WebSocket background daemons in favor of Streamlit's native `@st.fragment(run_every="4s")` smooth polling.

## 🚀 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Backend URL (Optional)
If your backend is running on a port or host other than `http://127.0.0.1:8000`:
```bash
cp .env.example .env
# Edit .env to set your BACKEND_API_URL
```

### 3. Run the Streamlit Application
```bash
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`.
