import json
import queue
import threading
import time
from typing import Any

import websocket

from frontend.api.client import APIClient
from frontend.config import WEBSOCKET_URL


class WebSocketService:
    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._app: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._lifecycle_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def update_tokens(self, access_token: str, refresh_token: str) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="live-chat-websocket",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ticket_client = APIClient(
                    access_token=self.access_token,
                    refresh_token=self.refresh_token,
                    on_token_refreshed=self._store_refreshed_tokens,
                )
                ticket_data = ticket_client.create_websocket_ticket()
                if self._stop.is_set():
                    break
                ticket = ticket_data["ticket"]

                def on_open(app: websocket.WebSocketApp) -> None:
                    app.send(json.dumps({"type": "auth", "ticket": ticket}))
                    self._connected.set()

                def on_message(app: websocket.WebSocketApp, message: str) -> None:
                    try:
                        event = json.loads(message)
                        if isinstance(event, dict):
                            self.events.put(event)
                    except json.JSONDecodeError:
                        self.events.put({"type": "client.error", "detail": "Invalid server event"})

                def on_error(app: websocket.WebSocketApp, error: Any) -> None:
                    self._connected.clear()
                    if not self._stop.is_set():
                        self.events.put({"type": "connection.error", "detail": str(error)})

                def on_close(app: websocket.WebSocketApp, code: Any, reason: Any) -> None:
                    self._connected.clear()

                self._app = websocket.WebSocketApp(
                    WEBSOCKET_URL,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                self._app.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    origin=self._origin(),
                )
            except Exception as exc:
                self._connected.clear()
                if not self._stop.is_set():
                    self.events.put({"type": "connection.error", "detail": str(exc)})
            finally:
                self._connected.clear()
                self._app = None

            if not self._stop.wait(3):
                continue

    def _store_refreshed_tokens(self, access_token: str, refresh_token: str) -> None:
        self.update_tokens(access_token, refresh_token)
        self.events.put({
            "type": "auth.tokens_refreshed",
            "access_token": access_token,
            "refresh_token": refresh_token,
        })

    @staticmethod
    def _origin() -> str:
        from frontend.config import FRONTEND_ORIGIN
        return FRONTEND_ORIGIN

    def send_event(self, event: dict[str, Any]) -> bool:
        app = self._app
        if not self.connected or app is None or app.sock is None:
            return False
        try:
            app.send(json.dumps(event))
            return True
        except websocket.WebSocketException:
            self._connected.clear()
            return False

    def drain_events(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                return items

    def stop(self) -> None:
        self._stop.set()
        self._connected.clear()
        app = self._app
        if app is not None:
            app.close()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        with self._lifecycle_lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None
