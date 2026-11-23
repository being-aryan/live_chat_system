from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.dependencies import get_db
from app.managers.message_receipt_manager import (
    MessageReceiptManager,
)
from app.models.user import User
from app.schemas.message_receipt import (
    MessageReceiptListResponse,
    MessageReceiptResponse,
)


class BulkReadRequest(BaseModel):
    last_read_message_id: UUID


router = APIRouter(
    prefix="/messages",
    tags=["Message Receipts"],
)

conversation_router = APIRouter(
    prefix="/conversations",
    tags=["Message Receipts"],
)


@router.patch(
    "/{message_id}/delivered",
    response_model=MessageReceiptResponse,
)
async def mark_message_delivered(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await MessageReceiptManager.mark_message_delivered(
            db,
            message_id,
            current_user.id,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc)
            in {
                "Message not found",
                "Message receipt not found",
            }
            else status.HTTP_400_BAD_REQUEST
        )

        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{message_id}/read",
    response_model=MessageReceiptResponse,
)
async def mark_message_read(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await MessageReceiptManager.mark_message_read(
            db,
            message_id,
            current_user.id,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc)
            in {
                "Message not found",
                "Message receipt not found",
            }
            else status.HTTP_400_BAD_REQUEST
        )

        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc


@router.get(
    "/{message_id}/receipts",
    response_model=MessageReceiptListResponse,
)
async def get_message_receipts(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        receipts = await MessageReceiptManager.get_message_receipts(
            db,
            message_id,
            current_user.id,
        )

        return MessageReceiptListResponse(
            receipts=receipts,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "Message not found"
            else status.HTTP_400_BAD_REQUEST
        )

        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc


@conversation_router.post(
    "/{conversation_id}/read",
    status_code=status.HTTP_200_OK,
)
async def mark_conversation_read(
    conversation_id: UUID,
    payload: BulkReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        updated_count = await MessageReceiptManager.mark_conversation_read(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user.id,
            last_read_message_id=payload.last_read_message_id,
        )
        return {"updated_receipts": updated_count}
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
