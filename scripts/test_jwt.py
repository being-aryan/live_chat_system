
from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings
from app.core.jwt import (
    create_access_token,
    decode_access_token,
)


def test_valid_token():
    token = create_access_token("test-user-123")

    payload = decode_access_token(token)

    assert payload["sub"] == "test-user-123"
    assert payload["type"] == "access"

    print("PASS: Valid token")


def test_modified_token():
    token = create_access_token("test-user-123")

    modified_token = token[:-1] + (
        "A" if token[-1] != "A" else "B"
    )

    try:
        decode_access_token(modified_token)
    except InvalidTokenError:
        print("PASS: Modified token rejected")
    else:
        raise AssertionError("Modified token was accepted")


def test_wrong_secret():
    create_access_token("test-user-123")

    wrong_secret_token = jwt.encode(
        {"sub": "test-user-123", "type": "access"},
        "incorrect-secret",
        algorithm=settings.JWT_ALGORITHM,
    )

    try:
        decode_access_token(wrong_secret_token)
    except InvalidTokenError:
        print("PASS: Wrong secret rejected")
    else:
        raise AssertionError("Wrong secret was accepted")


def test_expired_token():
    now = datetime.now(UTC)

    expired_token = jwt.encode(
        {
            "sub": "test-user-123",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
            "type": "access",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    try:
        decode_access_token(expired_token)
    except InvalidTokenError:
        print("PASS: Expired token rejected")
    else:
        raise AssertionError("Expired token was accepted")


def test_wrong_token_type():
    now = datetime.now(UTC)

    refresh_like_token = jwt.encode(
        {
            "sub": "test-user-123",
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "type": "refresh",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    try:
        decode_access_token(refresh_like_token)
    except InvalidTokenError:
        print("PASS: Wrong token type rejected")
    else:
        raise AssertionError("Wrong token type was accepted")


if __name__ == "__main__":
    test_valid_token()
    test_modified_token()
    test_wrong_secret()
    test_expired_token()
    test_wrong_token_type()

    print("\nAll JWT security checks passed.")
