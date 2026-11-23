import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from starlette.websockets import WebSocketState

from app.config import settings
from app.core.jwt import create_access_token, decode_access_token
from app.schemas.auth import RefreshRequest, TokenResponse
from app.schemas.message import MessageCreate, MessageUpdate
from app.websocket.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, should_fail: bool = False) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.should_fail = should_fail
        self.sent_messages: list[dict] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        if self.should_fail:
            raise RuntimeError("Connection is closed")
        self.sent_messages.append(message)


class JWTTests(unittest.TestCase):
    def test_access_token_contains_subject_and_session_id(self) -> None:
        user_id = uuid4()
        session_id = uuid4()

        token = create_access_token(str(user_id), session_id)
        payload = decode_access_token(token)

        self.assertEqual(payload["sub"], str(user_id))
        self.assertEqual(payload["sid"], str(session_id))
        self.assertEqual(payload["type"], "access")

    def test_access_token_rejects_invalid_session_id(self) -> None:
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(uuid4()),
                "sid": "not-a-uuid",
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "type": "access",
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        with self.assertRaises(InvalidTokenError):
            decode_access_token(token)

    def test_access_token_rejects_wrong_token_type(self) -> None:
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(uuid4()),
                "sid": str(uuid4()),
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "type": "refresh",
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        with self.assertRaises(InvalidTokenError):
            decode_access_token(token)


class SchemaTests(unittest.TestCase):
    def test_message_content_is_trimmed(self) -> None:
        message = MessageCreate(content="  hello  ")
        self.assertEqual(message.content, "hello")

    def test_message_update_content_is_trimmed(self) -> None:
        message = MessageUpdate(content="  updated  ")
        self.assertEqual(message.content, "updated")

    def test_message_rejects_whitespace_only_content(self) -> None:
        with self.assertRaises(ValueError):
            MessageCreate(content="   ")

    def test_message_rejects_content_over_limit(self) -> None:
        with self.assertRaises(ValueError):
            MessageCreate(content="x" * 5001)

    def test_refresh_request_rejects_short_token(self) -> None:
        with self.assertRaises(ValueError):
            RefreshRequest(refresh_token="short")

    def test_token_response_defaults_to_bearer(self) -> None:
        response = TokenResponse(
            access_token="access",
            refresh_token="refresh",
        )
        self.assertEqual(response.token_type, "bearer")


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_and_disconnect_track_user_connections(self) -> None:
        manager = ConnectionManager()
        user_id = uuid4()
        websocket = FakeWebSocket()

        await manager.connect(user_id, websocket)

        self.assertTrue(manager.is_user_online(user_id))
        self.assertEqual(manager.get_connection_count(user_id), 1)
        self.assertEqual(manager.get_total_connections(), 1)

        manager.disconnect(user_id, websocket)

        self.assertFalse(manager.is_user_online(user_id))
        self.assertEqual(manager.get_total_connections(), 0)

    async def test_connect_does_not_accept_already_connected_socket(self) -> None:
        manager = ConnectionManager()
        websocket = FakeWebSocket()

        await manager.connect(uuid4(), websocket)

        self.assertFalse(websocket.accepted)

    async def test_send_personal_message_returns_success(self) -> None:
        manager = ConnectionManager()
        websocket = FakeWebSocket()
        message = {"type": "test"}

        result = await manager.send_personal_message(message, websocket)

        self.assertTrue(result)
        self.assertEqual(websocket.sent_messages, [message])

    async def test_send_personal_message_handles_closed_socket(self) -> None:
        manager = ConnectionManager()
        websocket = FakeWebSocket(should_fail=True)

        result = await manager.send_personal_message({"type": "test"}, websocket)

        self.assertFalse(result)

    async def test_send_to_user_removes_failed_connections(self) -> None:
        manager = ConnectionManager()
        user_id = uuid4()
        working_socket = FakeWebSocket()
        closed_socket = FakeWebSocket(should_fail=True)

        await manager.connect(user_id, working_socket)
        await manager.connect(user_id, closed_socket)

        delivered = await manager.send_to_user(user_id, {"type": "message.new"})

        self.assertEqual(delivered, 1)
        self.assertEqual(manager.get_connection_count(user_id), 1)
        self.assertEqual(len(working_socket.sent_messages), 1)

    async def test_broadcast_delivers_to_all_connected_users(self) -> None:
        manager = ConnectionManager()
        first_socket = FakeWebSocket()
        second_socket = FakeWebSocket()

        await manager.connect(uuid4(), first_socket)
        await manager.connect(uuid4(), second_socket)

        delivered = await manager.broadcast({"type": "announcement"})

        self.assertEqual(delivered, 2)
        self.assertEqual(len(first_socket.sent_messages), 1)
        self.assertEqual(len(second_socket.sent_messages), 1)


if __name__ == "__main__":
    unittest.main()
