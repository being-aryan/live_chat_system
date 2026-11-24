from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.dependencies import get_db
from app.managers.presence_manager import PresenceManager
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.presence import PresenceResponse

router = APIRouter(
    prefix="/users",
    tags=["Presence"],
)


@router.post(
    "/heartbeat",
    status_code=status.HTTP_200_OK,
)
async def user_heartbeat(
    current_user: Annotated[User, Depends(get_current_user)],
):
    await PresenceManager.record_user_active(current_user.id)
    return {"status": "ok"}


@router.get(
    "/{user_id}/presence",
    response_model=PresenceResponse,
)
async def get_user_presence(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    await PresenceManager.record_user_active(current_user.id)
    if user_id != current_user.id:
        has_common_conversation = (
            await ConversationRepository.have_common_conversation(
                db=db,
                first_user_id=current_user.id,
                second_user_id=user_id,
            )
        )
        if not has_common_conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    user = await UserRepository.get_by_id(
        db=db,
        user_id=user_id,
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        is_online = await PresenceManager.is_user_online(user.id)

    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Presence service temporarily unavailable",
        ) from None

    return PresenceResponse(
        user_id=user.id,
        is_online=is_online,
        last_seen=user.last_seen,
    )