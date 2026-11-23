import asyncio
import json
import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.redis import redis_client
from app.managers.message_manager import MessageManager
from app.managers.message_receipt_manager import MessageReceiptManager
from app.managers.presence_manager import PresenceManager
from app.managers.websocket_ticket_manager import WebSocketTicketManager
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.message_receipt import MessageReceiptResponse
from app.websocket.connection_manager import manager
from app.websocket.redis_manager import redis_pubsub_manager

router = APIRouter(tags=["WebSocket"])

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
AUTH_TIMEOUT_SECONDS = 5


async def send_error(
    websocket: WebSocket,
    code: str,
    detail: str,
) -> None:
    await websocket.send_json(
        {
            "type": "error",
            "code": code,
            "detail": detail,
        }
    )


async def is_session_active(
    user_id: UUID,
    session_id: UUID,
) -> bool:
    from app.repositories.user_repository import UserRepository
    from app.repositories.user_session_repository import UserSessionRepository

    async with AsyncSessionLocal() as db:
        user = await UserRepository.get_by_id(db=db, user_id=user_id)
        if user is None or not user.is_active:
            return False
        session = await UserSessionRepository.get_active_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
        )
        return session is not None


async def maintain_presence(
    websocket: WebSocket,
    user_id: UUID,
    session_id: UUID,
    access_expires_at: int,
    connection_id: UUID,
) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            if int(time.time()) >= access_expires_at:
                await websocket.close(code=1008, reason="Access token expired")
                return

            if await redis_client.sismember(
                "auth:revoked_sessions",
                str(session_id),
            ):
                await websocket.close(code=1008, reason="Session revoked")
                return

            is_active = await PresenceManager.heartbeat(
                user_id=user_id,
                connection_id=connection_id,
            )
            if not is_active:
                await websocket.close(code=1013, reason="Presence expired")
                return
        except (RuntimeError, WebSocketDisconnect):
            return
        except RedisError:
            logger.exception("Redis heartbeat failed for user %s", user_id)
            try:
                await websocket.close(
                    code=1013,
                    reason="Authentication or presence service unavailable",
                )
            except (RuntimeError, WebSocketDisconnect):
                pass
            return


async def handle_message_send(
    websocket: WebSocket,
    user_id: UUID,
    event: dict,
) -> None:
    try:
        conversation_id = UUID(event["conversation_id"])
        payload = MessageCreate.model_validate(event.get("data"))

        async with AsyncSessionLocal() as db:
            message = await MessageManager.create_message(
                db=db,
                conversation_id=conversation_id,
                current_user_id=user_id,
                content=payload.content,
            )

            conversation = await ConversationRepository.get_by_id(
                db=db,
                conversation_id=conversation_id,
            )

            member_ids = [
                member.user_id
                for member in conversation.members
                if member.user_id != user_id
            ]

            message_data = MessageResponse.model_validate(message).model_dump(
                mode="json"
            )

        await websocket.send_json(
            {
                "type": "message.sent",
                "data": message_data,
            }
        )

        try:
            for member_id in member_ids:
                await redis_pubsub_manager.publish_to_user(
                    user_id=member_id,
                    message={
                        "type": "message.new",
                        "data": message_data,
                    },
                )

        except RedisError:
            logger.exception(
                "Message %s saved but realtime delivery failed",
                message.id,
            )

            await send_error(
                websocket,
                "realtime_delivery_unavailable",
                "Message saved, but realtime delivery is unavailable. "
                "Refresh the conversation to sync.",
            )

    except (ValueError, ValidationError, KeyError) as exc:
        await send_error(
            websocket,
            "invalid_message",
            str(exc),
        )

    except PermissionError as exc:
        await send_error(
            websocket,
            "permission_denied",
            str(exc),
        )

    except SQLAlchemyError:
        logger.exception("Database error while sending message")

        await send_error(
            websocket,
            "database_error",
            "Unable to send message",
        )


async def handle_message_receipt(
    websocket: WebSocket,
    user_id: UUID,
    event: dict,
    receipt_type: str,
) -> None:
    try:
        message_id = UUID(event["message_id"])

        async with AsyncSessionLocal() as db:
            if receipt_type == "read":
                receipt = await MessageReceiptManager.mark_message_read(
                    db=db,
                    message_id=message_id,
                    current_user_id=user_id,
                )
            else:
                receipt = await MessageReceiptManager.mark_message_delivered(
                    db=db,
                    message_id=message_id,
                    current_user_id=user_id,
                )

            message = await MessageRepository.get_by_id(
                db=db,
                message_id=message_id,
            )

            sender_id = message.sender_id

            receipt_data = MessageReceiptResponse.model_validate(receipt).model_dump(
                mode="json"
            )

        await websocket.send_json(
            {
                "type": f"message.{receipt_type}.ack",
                "data": receipt_data,
            }
        )

        await redis_pubsub_manager.publish_to_user(
            user_id=sender_id,
            message={
                "type": f"message.{receipt_type}",
                "data": receipt_data,
            },
        )

    except (ValueError, ValidationError, KeyError) as exc:
        await send_error(
            websocket,
            "invalid_receipt",
            str(exc),
        )

    except PermissionError as exc:
        await send_error(
            websocket,
            "permission_denied",
            str(exc),
        )

    except SQLAlchemyError:
        logger.exception(
            "Database error while updating %s receipt",
            receipt_type,
        )

        await send_error(
            websocket,
            "database_error",
            "Unable to update message receipt",
        )

    except RedisError:
        logger.exception(
            "Redis delivery failed for %s receipt",
            receipt_type,
        )


@router.websocket("/ws/connect")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin not in settings.ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()

    try:
        raw_auth = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=AUTH_TIMEOUT_SECONDS,
        )
        auth_event = json.loads(raw_auth)
        if (
            not isinstance(auth_event, dict)
            or auth_event.get("type") != "auth"
            or not isinstance(auth_event.get("ticket"), str)
        ):
            await websocket.close(code=1008, reason="Authentication required")
            return
        ticket_data = await WebSocketTicketManager.consume_ticket(auth_event["ticket"])
    except TimeoutError:
        await websocket.close(code=1008, reason="Authentication timeout")
        return
    except (json.JSONDecodeError, RedisError):
        await websocket.close(
            code=1013,
            reason="Authentication service unavailable",
        )
        return
    except WebSocketDisconnect:
        return

    if ticket_data is None:
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return

    user_id, session_id, access_expires_at = ticket_data

    try:
        if int(time.time()) >= access_expires_at:
            await websocket.close(code=1008, reason="Access token expired")
            return
        if await redis_client.sismember(
            "auth:revoked_sessions",
            str(session_id),
        ):
            await websocket.close(code=1008, reason="Session revoked")
            return
        if not await is_session_active(user_id, session_id):
            await websocket.close(
                code=1008,
                reason="Session expired or revoked",
            )
            return
    except (RedisError, SQLAlchemyError):
        logger.exception("WebSocket authentication failed for user %s", user_id)
        await websocket.close(
            code=1013,
            reason="Authentication service unavailable",
        )
        return

    connection_id = uuid4()
    try:
        became_online = await PresenceManager.connect(
            user_id=user_id,
            connection_id=connection_id,
        )
    except RedisError:
        await websocket.close(code=1013, reason="Presence service unavailable")
        return

    await manager.connect(user_id, websocket)

    if became_online:
        try:
            await PresenceManager.broadcast_presence(
                user_id=user_id,
                is_online=True,
            )
        except RedisError:
            logger.exception(
                "Failed to broadcast online presence for user %s",
                user_id,
            )

    heartbeat_task = asyncio.create_task(
        maintain_presence(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
            access_expires_at=access_expires_at,
            connection_id=connection_id,
        )
    )

    try:
        while True:
            raw_message = await websocket.receive_text()

            rate_key = f"ws-rate:{user_id}:{int(time.time())}"
            message_count = await redis_client.incr(rate_key)
            if message_count == 1:
                await redis_client.expire(rate_key, 2)
            if message_count > settings.WEBSOCKET_MAX_MESSAGES_PER_SECOND:
                await send_error(
                    websocket,
                    "rate_limit_exceeded",
                    "Message rate limit exceeded",
                )
                await websocket.close(code=1008, reason="Message rate limit exceeded")
                break

            if raw_message == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                event = json.loads(raw_message)
            except json.JSONDecodeError:
                await send_error(websocket, "invalid_json", "Invalid JSON message")
                continue

            if not isinstance(event, dict):
                await send_error(
                    websocket,
                    "invalid_event",
                    "Event must be a JSON object",
                )
                continue

            event_type = event.get("type")
            if event_type == "message.send":
                await handle_message_send(websocket, user_id, event)
            elif event_type == "message.delivered":
                await handle_message_receipt(
                    websocket,
                    user_id,
                    event,
                    "delivered",
                )
            elif event_type == "message.read":
                await handle_message_receipt(
                    websocket,
                    user_id,
                    event,
                    "read",
                )
            else:
                await send_error(
                    websocket,
                    "unsupported_event",
                    "Unsupported WebSocket event",
                )
    except WebSocketDisconnect:
        pass
    except RedisError:
        logger.exception("WebSocket rate limiter failed for user %s", user_id)
        try:
            await websocket.close(
                code=1013,
                reason="Rate limiting service unavailable",
            )
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Heartbeat task failed for user %s", user_id)

        manager.disconnect(user_id, websocket)
        try:
            await PresenceManager.disconnect(
                user_id=user_id,
                connection_id=connection_id,
            )
        except RedisError:
            logger.exception(
                "Failed to remove presence connection for user %s",
                user_id,
            )
