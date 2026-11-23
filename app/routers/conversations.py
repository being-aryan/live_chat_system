from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.dependencies import get_db
from app.managers.conversation_manager import ConversationManager
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationInboxResponse,
    ConversationResponse,
    DirectConversationCreate,
    GroupConversationCreate,
    GroupMemberAdd,
    GroupNameUpdate,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.post(
    "/direct",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_direct_conversation(
    payload: DirectConversationCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        conversation, created = await ConversationManager.create_direct_conversation(
            db=db,
            current_user_id=current_user.id,
            other_user_id=payload.other_user_id,
        )

        if not created:
            response.status_code = status.HTTP_200_OK

        return conversation

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/groups",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_conversation(
    payload: GroupConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ConversationManager.create_group(
            db=db,
            creator_id=current_user.id,
            name=payload.name,
            member_ids=payload.member_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{conversation_id}/group-name",
    response_model=ConversationDetailResponse,
)
async def rename_group(
    conversation_id: UUID,
    payload: GroupNameUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ConversationManager.rename_group(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/{conversation_id}/members",
    response_model=ConversationDetailResponse,
)
async def add_group_member(
    conversation_id: UUID,
    payload: GroupMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ConversationManager.add_group_member(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            new_user_id=payload.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.delete("/{conversation_id}/members/{member_user_id}")
async def remove_group_member(
    conversation_id: UUID,
    member_user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await ConversationManager.remove_group_member(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            member_user_id=member_user_id,
        )
        return {"message": "Group member removed"}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post("/{conversation_id}/leave")
async def leave_group(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await ConversationManager.leave_group(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
        )
        return {"message": "You left the group"}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/inbox",
    response_model=ConversationInboxResponse,
)
async def get_conversation_inbox(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await ConversationRepository.get_user_inbox(
        db=db,
        user_id=current_user.id,
    )
    return {"conversations": items}


@router.get(
    "",
    response_model=list[ConversationResponse],
)
async def get_my_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ConversationRepository.get_user_conversations(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation_details(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_member = await ConversationRepository.is_member(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation = await ConversationRepository.get_by_id(
        db=db,
        conversation_id=conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return conversation
