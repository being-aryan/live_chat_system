import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.dependencies import get_db
from app.managers.message_manager import MessageManager
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageUpdate,
)
from app.websocket.redis_manager import redis_pubsub_manager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/conversations",
    tags=["Messages"],
)


async def publish_message_event(
    db: AsyncSession,
    message,
    event_type: str,
    sender_id: UUID,
) -> None:
    conversation = await ConversationRepository.get_by_id(
        db=db,
        conversation_id=message.conversation_id,
    )
    if conversation is None:
        return

    payload = MessageResponse.model_validate(message).model_dump(mode="json")
    if message.deleted_at is not None:
        payload["content"] = None

    for member in conversation.members:
        if member.user_id != sender_id:
            await redis_pubsub_manager.publish_to_user(
                user_id=member.user_id,
                message={"type": event_type, "data": payload},
            )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    payload: MessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        message = await MessageManager.create_message(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            content=payload.content,
        )
        try:
            await publish_message_event(
                db, message, "message.new", current_user.id
            )
        except Exception:
            logger.exception(
                "Message %s saved but realtime publish failed",
                message.id,
            )
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_username=current_user.username,
            content=message.content,
            created_at=message.created_at,
            updated_at=message.updated_at,
            deleted_at=message.deleted_at,
            is_delivered=False,
            is_read=False,
        )
    except ValueError as exc:
        error_message = str(exc)
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error_message == "Conversation not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=error_status,
            detail=error_message,
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
)
async def get_conversation_messages(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_created_at: datetime | None = None,
    before_id: UUID | None = None,
):
    try:
        messages = await MessageManager.get_conversation_messages(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            limit=limit,
            before_created_at=before_created_at,
            before_id=before_id,
        )
        has_more = len(messages) > limit
        messages = messages[:limit]
        message_responses = [
            MessageResponse.model_validate(message).model_copy(
                update={
                    "content": (
                        None if message.deleted_at is not None else message.content
                    )
                }
            )
            for message in messages
        ]
        return MessageListResponse(
            messages=message_responses,
            limit=limit,
            has_more=has_more,
            next_before_created_at=(
                messages[-1].created_at if has_more and messages else None
            ),
            next_before_id=messages[-1].id if has_more and messages else None,
        )
    except ValueError as exc:
        error_message = str(exc)
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error_message == "Conversation not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=error_status,
            detail=error_message,
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.patch(
    "/messages/{message_id}",
    response_model=MessageResponse,
)
async def update_message(
    message_id: UUID,
    payload: MessageUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        message = await MessageManager.update_message(
            db=db,
            message_id=message_id,
            current_user_id=current_user.id,
            content=payload.content,
        )
        try:
            await publish_message_event(
                db, message, "message.updated", current_user.id
            )
        except Exception:
            logger.exception(
                "Message %s updated but realtime publish failed",
                message.id,
            )
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_username=current_user.username,
            content=message.content,
            created_at=message.created_at,
            updated_at=message.updated_at,
            deleted_at=message.deleted_at,
            is_delivered=False,
            is_read=False,
        )
    except ValueError as exc:
        error_message = str(exc)
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error_message == "Message not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=error_status,
            detail=error_message,
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.delete(
    "/messages/{message_id}",
    response_model=MessageResponse,
)
async def delete_message(
    message_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        message = await MessageManager.delete_message(
            db=db,
            message_id=message_id,
            current_user_id=current_user.id,
        )
        try:
            await publish_message_event(
                db, message, "message.deleted", current_user.id
            )
        except Exception:
            logger.exception(
                "Message %s deleted but realtime publish failed",
                message.id,
            )
        return MessageResponse.model_validate(message).model_copy(
            update={"content": None}
        )
    except ValueError as exc:
        error_message = str(exc)
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error_message == "Message not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=error_status,
            detail=error_message,
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
