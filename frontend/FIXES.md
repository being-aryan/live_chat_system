# Frontend review fixes

This Streamlit frontend remains a prototype/internal chat UI. The following issues from the supplied review have been addressed:

- Delivery receipts are attempted only for incoming messages that are not already marked delivered and have not been acknowledged in the current Streamlit session.
- Conversation read receipts are sent only when the latest incoming message ID changes.
- WebSocket events are drained inside the 3-second chat fragment, so fragment reruns consume queued events.
- General authenticated HTTP calls can refresh an expired access token once after a 401, then retry the original request once.
- Refreshed access and refresh tokens are written back to Streamlit session state. WebSocket-thread token refreshes are handed back to the UI through its event queue rather than mutating Streamlit session state from the background thread.
- WebSocket service shutdown closes the socket and joins its worker thread; a stop request received during ticket acquisition prevents a new socket from starting.
- The Streamlit entry point adds the project root to `sys.path` before importing the `frontend` package, avoiding the deployment import error when launched as `frontend/app.py`.

The chat view still uses a 3-second fragment refresh as a fallback and still fetches the current message page on each fragment rerun. This is not a fully event-driven production chat client. Streamlit's scroll retention and large-scale real-time limitations described in the review remain.
