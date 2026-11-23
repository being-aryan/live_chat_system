import hashlib

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.config import settings
from app.database.redis import redis_client

RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def enforce_rate_limit(
    request: Request,
    scope: str,
    identity: str | None = None,
    limit: int | None = None,
) -> None:
    client_host = request.client.host if request.client else "unknown"
    subject = identity or client_host
    digest = hashlib.sha256(subject.lower().encode("utf-8")).hexdigest()
    key = f"rate-limit:{scope}:{digest}"
    maximum = limit or settings.RATE_LIMIT_LOGIN
    window = settings.RATE_LIMIT_WINDOW_SECONDS

    try:
        count = await redis_client.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            window,
        )
        if count > maximum:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(window)},
            )
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting service unavailable",
        ) from None
