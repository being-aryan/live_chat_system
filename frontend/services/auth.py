from typing import Any

from frontend.api.client import APIClient, APIError


class AuthService:
    ACCESS_TOKEN_KEY = "access_token"
    REFRESH_TOKEN_KEY = "refresh_token"
    USER_KEY = "current_user"

    def __init__(self, session_state: Any) -> None:
        self.session_state = session_state

    def store_tokens(self, access_token: str, refresh_token: str) -> None:
        self.session_state[self.ACCESS_TOKEN_KEY] = access_token
        self.session_state[self.REFRESH_TOKEN_KEY] = refresh_token
        websocket_service = self.session_state.get("websocket_service")
        if websocket_service:
            websocket_service.update_tokens(access_token, refresh_token)

    def _client(self) -> APIClient:
        return APIClient(
            access_token=self.session_state.get(self.ACCESS_TOKEN_KEY),
            refresh_token=self.session_state.get(self.REFRESH_TOKEN_KEY),
            on_token_refreshed=self.store_tokens,
        )

    def is_authenticated(self) -> bool:
        return bool(
            self.session_state.get(self.ACCESS_TOKEN_KEY)
            and self.session_state.get(self.REFRESH_TOKEN_KEY)
        )

    def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        return APIClient().register(username, email, password)

    def login(self, email: str, password: str) -> dict[str, Any]:
        tokens = APIClient().login(email, password)
        self.store_tokens(tokens["access_token"], tokens["refresh_token"])
        try:
            user = self._client().get_me()
        except Exception:
            self.clear_session()
            raise
        self.session_state[self.USER_KEY] = user
        return user

    def refresh_access_token(self) -> bool:
        refresh_token = self.session_state.get(self.REFRESH_TOKEN_KEY)
        if not refresh_token:
            self.clear_session()
            return False
        try:
            tokens = APIClient().refresh(refresh_token)
        except APIError:
            self.clear_session()
            return False
        self.store_tokens(tokens["access_token"], tokens["refresh_token"])
        return True

    def get_current_user(self) -> dict[str, Any]:
        try:
            user = self._client().get_me()
        except APIError as exc:
            if exc.status_code != 401:
                raise
            if not self.refresh_access_token():
                raise APIError(401, "Your session has expired. Please log in again.") from exc
            user = self._client().get_me()
        self.session_state[self.USER_KEY] = user
        return user

    def logout(self) -> None:
        refresh_token = self.session_state.get(self.REFRESH_TOKEN_KEY)
        try:
            if refresh_token:
                APIClient().logout(refresh_token)
        finally:
            self.clear_session()

    def logout_all(self) -> dict[str, Any]:
        try:
            return self._client().logout_all()
        finally:
            self.clear_session()

    def clear_session(self) -> None:
        for key in (self.ACCESS_TOKEN_KEY, self.REFRESH_TOKEN_KEY, self.USER_KEY):
            self.session_state.pop(key, None)
