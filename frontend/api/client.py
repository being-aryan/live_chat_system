from typing import Any

import httpx

from frontend.config import API_V1_URL


class APIError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class APIClient:
    def __init__(
        self,
        base_url: str = API_V1_URL,
        access_token: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        headers.update(kwargs.pop("headers", {}))
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise APIError(408, "The server took too long to respond.") from exc
        except httpx.RequestError as exc:
            raise APIError(503, "Unable to connect to the backend server.") from exc

        try:
            data = response.json()
        except ValueError:
            data = response.text
        if not response.is_success:
            detail = data.get("detail", data) if isinstance(data, dict) else data
            raise APIError(response.status_code, detail)
        return data

    def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST", "/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST", "/auth/login", json={"email": email, "password": password}
        )

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/auth/me")

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._request("POST", "/auth/refresh", json={"refresh_token": refresh_token})

    def logout(self, refresh_token: str) -> dict[str, Any]:
        return self._request("POST", "/auth/logout", json={"refresh_token": refresh_token})

    def logout_all(self) -> dict[str, Any]:
        return self._request("POST", "/auth/logout-all")

    def get_sessions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/auth/sessions")

    def revoke_session(self, session_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/auth/sessions/{session_id}")

    def get_conversation_inbox(self) -> dict[str, Any]:
        return self._request("GET", "/conversations/inbox")

    def get_conversations(self) -> list[dict[str, Any]]:
        return self._request("GET", "/conversations")

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/conversations/{conversation_id}")

    def create_direct_conversation(self, other_user_id: str) -> dict[str, Any]:
        return self._request("POST", "/conversations/direct", json={"other_user_id": other_user_id})

    def create_group_conversation(self, name: str, member_ids: list[str]) -> dict[str, Any]:
        return self._request(
            "POST", "/conversations/groups",
            json={"name": name, "member_ids": member_ids},
        )

    def rename_group(self, conversation_id: str, name: str) -> dict[str, Any]:
        return self._request(
            "PATCH", f"/conversations/{conversation_id}/group-name", json={"name": name}
        )

    def add_group_member(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/conversations/{conversation_id}/members", json={"user_id": user_id}
        )

    def remove_group_member(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/conversations/{conversation_id}/members/{user_id}")

    def leave_group(self, conversation_id: str) -> dict[str, Any]:
        return self._request("POST", f"/conversations/{conversation_id}/leave")

    def search_users(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/users/search", params={"q": query, "limit": limit, "offset": offset}
        )

    def get_presence(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/users/{user_id}/presence")

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before_created_at: str | None = None,
        before_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before_created_at:
            params["before_created_at"] = before_created_at
        if before_id:
            params["before_id"] = before_id
        return self._request("GET", f"/conversations/{conversation_id}/messages", params=params)

    def send_message(self, conversation_id: str, content: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/conversations/{conversation_id}/messages", json={"content": content}
        )

    def update_message(self, message_id: str, content: str) -> dict[str, Any]:
        return self._request("PATCH", f"/conversations/messages/{message_id}", json={"content": content})

    def delete_message(self, message_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/conversations/messages/{message_id}")

    def mark_message_delivered(self, message_id: str) -> dict[str, Any]:
        return self._request("PATCH", f"/messages/{message_id}/delivered")

    def mark_message_read(self, message_id: str) -> dict[str, Any]:
        return self._request("PATCH", f"/messages/{message_id}/read")

    def mark_conversation_read(self, conversation_id: str, message_id: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/conversations/{conversation_id}/read",
            json={"last_read_message_id": message_id},
        )

    def get_message_receipts(self, message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/messages/{message_id}/receipts")

    def create_websocket_ticket(self) -> dict[str, Any]:
        return self._request("POST", "/ws/ticket")
