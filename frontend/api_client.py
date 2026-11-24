import os
from typing import Any, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BACKEND_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_V1_PREFIX = f"{DEFAULT_BACKEND_URL}/api/v1"


class APIError(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class ChatAPIClient:
    def __init__(
        self,
        base_url: str = API_V1_PREFIX,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_tokens_refreshed: Optional[Any] = None,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.on_tokens_refreshed = on_tokens_refreshed
        self.timeout = timeout

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        headers.update(kwargs.pop("headers", {}))

        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.ConnectError:
            raise APIError(503, "Backend server is offline or unreachable.")
        except httpx.TimeoutException:
            raise APIError(408, "Request timed out connecting to backend.")
        except Exception as exc:
            raise APIError(500, f"Network error: {str(exc)}")

        # Handle automatic token refresh on 401 Unauthorized
        if response.status_code == 401 and self.refresh_token and not kwargs.get("_is_retry"):
            if self._attempt_token_refresh():
                headers["Authorization"] = f"Bearer {self.access_token}"
                return self._request(method, endpoint, headers=headers, _is_retry=True, **kwargs)

        try:
            data = response.json()
        except ValueError:
            data = response.text

        if not response.is_success:
            detail = data.get("detail", data) if isinstance(data, dict) else str(data)
            raise APIError(response.status_code, detail)

        return data

    def _attempt_token_refresh(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            res = httpx.post(
                f"{self.base_url}/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=5.0,
            )
            if res.is_success:
                tokens = res.json()
                self.access_token = tokens["access_token"]
                self.refresh_token = tokens["refresh_token"]
                if self.on_tokens_refreshed:
                    self.on_tokens_refreshed(self.access_token, self.refresh_token)
                return True
        except Exception:
            pass
        return False

    # ---------------- Auth Endpoints ----------------
    def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
        )

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/auth/me")

    def logout(self, refresh_token: str) -> None:
        try:
            self._request("POST", "/auth/logout", json={"refresh_token": refresh_token})
        except Exception:
            pass

    # ---------------- User Endpoints & Presence ----------------
    def search_users(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/users/search",
            params={"q": query, "limit": limit},
        )

    def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/users/{user_id}")

    def get_presence(self, user_id: str) -> dict[str, Any]:
        try:
            return self._request("GET", f"/users/{user_id}/presence")
        except Exception:
            return {"user_id": user_id, "is_online": False, "last_seen": None}

    def heartbeat(self) -> None:
        try:
            self._request("POST", "/users/heartbeat")
        except Exception:
            pass

    # ---------------- Conversation Endpoints ----------------
    def get_inbox(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/conversations/inbox")
        return data.get("conversations", []) if isinstance(data, dict) else []

    def get_conversation_details(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/conversations/{conversation_id}")

    def create_direct_conversation(self, other_user_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/conversations/direct",
            json={"other_user_id": other_user_id},
        )

    def create_group_conversation(self, name: str, member_ids: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/conversations/groups",
            json={"name": name, "member_ids": member_ids},
        )

    def rename_group(self, conversation_id: str, new_name: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/conversations/{conversation_id}/group-name",
            json={"name": new_name},
        )

    def add_group_member(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/members",
            json={"user_id": user_id},
        )

    def leave_group(self, conversation_id: str) -> dict[str, Any]:
        return self._request("POST", f"/conversations/{conversation_id}/leave")

    # ---------------- Message Endpoints ----------------
    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before_created_at: Optional[str] = None,
        before_id: Optional[str] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before_created_at and before_id:
            params["before_created_at"] = before_created_at
            params["before_id"] = before_id
        return self._request("GET", f"/conversations/{conversation_id}/messages", params=params)

    def send_message(self, conversation_id: str, content: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            json={"content": content},
        )

    def mark_conversation_read(self, conversation_id: str, last_read_message_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/conversations/{conversation_id}/read",
                json={"last_read_message_id": last_read_message_id},
            )
        except Exception:
            try:
                self._request("PATCH", f"/messages/{last_read_message_id}/read")
            except Exception:
                pass

    def mark_message_delivered(self, message_id: str) -> None:
        try:
            self._request("PATCH", f"/messages/{message_id}/delivered")
        except Exception:
            pass

    # ---------------- Typing Indicators ----------------
    def set_typing(self, conversation_id: str, is_typing: bool = True) -> None:
        try:
            self._request(
                "POST",
                f"/conversations/{conversation_id}/typing",
                json={"is_typing": is_typing},
            )
        except Exception:
            pass

    def get_typing(self, conversation_id: str) -> list[str]:
        try:
            data = self._request("GET", f"/conversations/{conversation_id}/typing")
            return data.get("typing_users", []) if isinstance(data, dict) else []
        except Exception:
            return []
