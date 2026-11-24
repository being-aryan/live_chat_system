import hashlib
import json
import secrets
from uuid import UUID

from redis.exceptions import RedisError

from app.database.redis import redis_client


class WebSocketTicketManager:
    TICKET_PREFIX = "websocket:ticket:"
    TICKET_EXPIRE_SECONDS = 30

    @staticmethod
    def _get_ticket_key(ticket: str) -> str:
        ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()

        return f"{WebSocketTicketManager.TICKET_PREFIX}{ticket_hash}"

    @staticmethod
    async def create_ticket(
        user_id: UUID,
        session_id: UUID,
        access_expires_at: int,
    ) -> str:
        payload = {
            "user_id": str(user_id),
            "session_id": str(session_id),
            "access_expires_at": access_expires_at,
        }

        for _ in range(3):
            ticket = secrets.token_urlsafe(32)
            ticket_key = WebSocketTicketManager._get_ticket_key(ticket)
            stored = await redis_client.set(
                name=ticket_key,
                value=json.dumps(payload),
                ex=WebSocketTicketManager.TICKET_EXPIRE_SECONDS,
                nx=True,
            )
            if stored:
                return ticket

        raise RedisError("Unable to create a unique WebSocket ticket")

    @staticmethod
    async def consume_ticket(
        ticket: str,
    ) -> tuple[UUID, UUID, int] | None:
        if not ticket:
            return None

        ticket_key = WebSocketTicketManager._get_ticket_key(ticket)

        payload = await redis_client.getdel(ticket_key)

        if payload is None:
            return None

        try:
            ticket_data = json.loads(payload)

            user_id = UUID(ticket_data["user_id"])
            session_id = UUID(ticket_data["session_id"])
            access_expires_at = int(ticket_data["access_expires_at"])

            return user_id, session_id, access_expires_at

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None