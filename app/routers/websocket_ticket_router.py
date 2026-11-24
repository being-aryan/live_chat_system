from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from redis.exceptions import RedisError

from app.config import settings
from app.core.dependencies import bearer_scheme, get_current_user
from app.core.jwt import decode_access_token
from app.core.rate_limit import enforce_rate_limit
from app.managers.websocket_ticket_manager import WebSocketTicketManager
from app.models.user import User
from app.schemas.websocket_ticket import WebSocketTicketResponse

router = APIRouter(
    prefix="/ws",
    tags=["WebSocket Authentication"],
)


@router.post(
    "/ticket",
    response_model=WebSocketTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_websocket_ticket(
    request: Request,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
):
    await enforce_rate_limit(
        request,
        "websocket-ticket",
        identity=str(current_user.id),
        limit=settings.RATE_LIMIT_TICKET,
    )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        session_id = UUID(payload["sid"])

    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    try:
        ticket = await WebSocketTicketManager.create_ticket(
            user_id=current_user.id,
            session_id=session_id,
            access_expires_at=int(payload["exp"]),
        )

        return WebSocketTicketResponse(
            ticket=ticket,
            expires_in=WebSocketTicketManager.TICKET_EXPIRE_SECONDS,
        )

    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WebSocket authentication service unavailable",
        ) from None