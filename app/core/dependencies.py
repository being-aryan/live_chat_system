from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import decode_access_token
from app.database.dependencies import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import (
    UserSessionRepository,
)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)

        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])

    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise unauthorized from None

    user = await UserRepository.get_by_id(
        db=db,
        user_id=user_id,
    )

    if user is None or not user.is_active:
        raise unauthorized

    session = await UserSessionRepository.get_active_session(
        db=db,
        session_id=session_id,
        user_id=user_id,
    )

    if session is None:
        raise unauthorized

    return user
