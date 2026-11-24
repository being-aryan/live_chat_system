
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings


def create_access_token(
    subject: str,
    session_id: UUID,
) -> str:
    issued_at = datetime.now(UTC)

    expires_at = issued_at + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": subject,
        "sid": str(session_id),
        "iat": issued_at,
        "exp": expires_at,
        "type": "access",
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={
            "require": ["sub", "sid", "iat", "exp", "type"],
        },
    )

    if payload.get("type") != "access":
        raise InvalidTokenError("Invalid token type")

    try:
        UUID(payload["sid"])
    except (ValueError, TypeError, AttributeError):
        raise InvalidTokenError("Invalid session ID") from None

    return payload
