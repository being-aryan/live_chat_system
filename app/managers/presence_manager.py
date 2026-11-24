import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import AsyncSessionLocal
from app.database.redis import redis_client
from app.repositories.user_repository import UserRepository
from app.websocket.redis_manager import redis_pubsub_manager

logger = logging.getLogger(__name__)


class PresenceManager:
    CONNECTION_TTL_SECONDS = 45
    CONNECTION_KEY_PREFIX = "presence:user:"
    CONNECTION_KEY_SUFFIX = ":connections"
    GLOBAL_PRESENCE_KEY = "presence:active_users"
    PENDING_OFFLINE_KEY = "presence:pending_offline"
    GENERATION_KEY_PREFIX = "presence:user:"
    GENERATION_KEY_SUFFIX = ":generation"
    CLEANUP_CHANNEL = redis_pubsub_manager.CHANNEL
    HTTP_PRESENCE_KEY_PREFIX = "presence:http:"
    HTTP_TTL_SECONDS = 45

    CONNECT_SCRIPT = """
    local connection_key = KEYS[1]
    local global_key = KEYS[2]
    local pending_key = KEYS[3]
    local generation_key = KEYS[4]

    local user_id = ARGV[1]
    local connection_id = ARGV[2]
    local now = tonumber(ARGV[3])
    local expires_at = tonumber(ARGV[4])
    local key_ttl = tonumber(ARGV[5])

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    local previous_count = redis.call("ZCARD", connection_key)

    redis.call("INCR", generation_key)
    redis.call("ZREM", pending_key, user_id)

    redis.call("ZADD", connection_key, expires_at, connection_id)
    redis.call("EXPIRE", connection_key, key_ttl)

    redis.call("ZADD", global_key, expires_at, user_id)

    return previous_count
    """

    HEARTBEAT_SCRIPT = """
    local connection_key = KEYS[1]
    local global_key = KEYS[2]

    local user_id = ARGV[1]
    local connection_id = ARGV[2]
    local now = tonumber(ARGV[3])
    local expires_at = tonumber(ARGV[4])
    local key_ttl = tonumber(ARGV[5])

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    if redis.call("ZSCORE", connection_key, connection_id) then
        redis.call("ZADD", connection_key, expires_at, connection_id)
        redis.call("EXPIRE", connection_key, key_ttl)
        redis.call("ZADD", global_key, expires_at, user_id)

        return 1
    end

    return 0
    """

    DISCONNECT_SCRIPT = """
    local connection_key = KEYS[1]
    local global_key = KEYS[2]
    local pending_key = KEYS[3]
    local generation_key = KEYS[4]

    local user_id = ARGV[1]
    local connection_id = ARGV[2]
    local now = tonumber(ARGV[3])

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    local removed_count = redis.call(
        "ZREM",
        connection_key,
        connection_id
    )

    if removed_count == 0 then
        return 0
    end

    local remaining_count = redis.call("ZCARD", connection_key)

    if remaining_count > 0 then
        local latest_expiry = redis.call(
            "ZREVRANGE",
            connection_key,
            0,
            0,
            "WITHSCORES"
        )

        redis.call("ZADD", global_key, latest_expiry[2], user_id)

        return 0
    end

    redis.call("DEL", connection_key)
    redis.call("ZREM", global_key, user_id)

    redis.call("INCR", generation_key)

    local generation = redis.call(
        "GET",
        generation_key
    )

    redis.call(
        "ZADD",
        pending_key,
        generation,
        user_id
    )

    return 1
    """

    CLEANUP_SCRIPT = """
    local connection_key = KEYS[1]
    local global_key = KEYS[2]
    local pending_key = KEYS[3]
    local generation_key = KEYS[4]

    local user_id = ARGV[1]
    local now = tonumber(ARGV[2])

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    local remaining_count = redis.call("ZCARD", connection_key)

    if remaining_count > 0 then
        local latest_expiry = redis.call(
            "ZREVRANGE",
            connection_key,
            0,
            0,
            "WITHSCORES"
        )

        redis.call("ZADD", global_key, latest_expiry[2], user_id)

        return 0
    end

    redis.call("DEL", connection_key)
    redis.call("ZREM", global_key, user_id)

    local generation = redis.call(
        "GET",
        generation_key
    ) or "0"

    redis.call(
        "ZADD",
        pending_key,
        generation,
        user_id
    )

    return 1
    """

    STATUS_SCRIPT = """
    local connection_key = KEYS[1]
    local now = tonumber(ARGV[1])

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    return redis.call("ZCARD", connection_key)
    """

    FINALIZE_OFFLINE_SCRIPT = """
    local connection_key = KEYS[1]
    local global_key = KEYS[2]
    local pending_key = KEYS[3]
    local generation_key = KEYS[4]

    local user_id = ARGV[1]
    local expected_generation = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local channel = ARGV[4]
    local payload = ARGV[5]

    local current_generation = tonumber(
        redis.call("GET", generation_key) or "0"
    )

    local pending_generation = redis.call(
        "ZSCORE",
        pending_key,
        user_id
    )

    if current_generation ~= expected_generation
        or not pending_generation
        or tonumber(pending_generation) ~= expected_generation then
        return -1
    end

    redis.call("ZREMRANGEBYSCORE", connection_key, "-inf", now)

    local remaining_count = redis.call("ZCARD", connection_key)

    if remaining_count > 0 then
        local latest_expiry = redis.call(
            "ZREVRANGE",
            connection_key,
            0,
            0,
            "WITHSCORES"
        )

        redis.call("ZADD", global_key, latest_expiry[2], user_id)
        redis.call("ZREM", pending_key, user_id)

        return 0
    end

    redis.call("PUBLISH", channel, payload)
    redis.call("ZREM", pending_key, user_id)
    redis.call("ZREM", global_key, user_id)

    return 1
    """

    @classmethod
    def _get_connection_key(cls, user_id: UUID) -> str:
        return f"{cls.CONNECTION_KEY_PREFIX}{user_id}{cls.CONNECTION_KEY_SUFFIX}"

    @classmethod
    def _get_generation_key(cls, user_id: UUID) -> str:
        return f"{cls.GENERATION_KEY_PREFIX}{user_id}{cls.GENERATION_KEY_SUFFIX}"

    @classmethod
    async def connect(
        cls,
        user_id: UUID,
        connection_id: UUID,
    ) -> bool:
        now = int(time.time() * 1000)
        expires_at = now + cls.CONNECTION_TTL_SECONDS * 1000

        previous_count = await redis_client.eval(
            cls.CONNECT_SCRIPT,
            4,
            cls._get_connection_key(user_id),
            cls.GLOBAL_PRESENCE_KEY,
            cls.PENDING_OFFLINE_KEY,
            cls._get_generation_key(user_id),
            str(user_id),
            str(connection_id),
            now,
            expires_at,
            cls.CONNECTION_TTL_SECONDS * 2,
        )

        return previous_count == 0

    @classmethod
    async def heartbeat(
        cls,
        user_id: UUID,
        connection_id: UUID,
    ) -> bool:
        now = int(time.time() * 1000)
        expires_at = now + cls.CONNECTION_TTL_SECONDS * 1000

        result = await redis_client.eval(
            cls.HEARTBEAT_SCRIPT,
            2,
            cls._get_connection_key(user_id),
            cls.GLOBAL_PRESENCE_KEY,
            str(user_id),
            str(connection_id),
            now,
            expires_at,
            cls.CONNECTION_TTL_SECONDS * 2,
        )

        return bool(result)

    @classmethod
    async def disconnect(
        cls,
        user_id: UUID,
        connection_id: UUID,
    ) -> bool:
        now = int(time.time() * 1000)

        result = await redis_client.eval(
            cls.DISCONNECT_SCRIPT,
            4,
            cls._get_connection_key(user_id),
            cls.GLOBAL_PRESENCE_KEY,
            cls.PENDING_OFFLINE_KEY,
            cls._get_generation_key(user_id),
            str(user_id),
            str(connection_id),
            now,
        )

        return bool(result)

    @classmethod
    async def record_user_active(cls, user_id: UUID) -> None:
        try:
            key = f"{cls.HTTP_PRESENCE_KEY_PREFIX}{user_id}"
            now = int(time.time() * 1000)
            expires_at = now + (cls.HTTP_TTL_SECONDS * 1000)
            pipe = redis_client.pipeline()
            pipe.set(key, "1", ex=cls.HTTP_TTL_SECONDS)
            pipe.zadd(cls.GLOBAL_PRESENCE_KEY, {str(user_id): expires_at})
            await pipe.execute()
        except Exception:
            logger.exception("Failed to record active presence for user %s", user_id)

    @classmethod
    async def record_user_offline(cls, user_id: UUID) -> None:
        try:
            key = f"{cls.HTTP_PRESENCE_KEY_PREFIX}{user_id}"
            conn_key = cls._get_connection_key(user_id)
            pipe = redis_client.pipeline()
            pipe.delete(key)
            pipe.delete(conn_key)
            pipe.zrem(cls.GLOBAL_PRESENCE_KEY, str(user_id))
            pipe.zrem(cls.PENDING_OFFLINE_KEY, str(user_id))
            await pipe.execute()
            await cls.mark_user_offline(user_id, datetime.now(UTC))
        except Exception:
            logger.exception("Failed to record offline presence for user %s", user_id)

    @classmethod
    async def is_user_online(cls, user_id: UUID) -> bool:
        now = int(time.time() * 1000)

        connection_count = await redis_client.eval(
            cls.STATUS_SCRIPT,
            1,
            cls._get_connection_key(user_id),
            now,
        )

        if connection_count > 0:
            return True

        http_active = await redis_client.exists(f"{cls.HTTP_PRESENCE_KEY_PREFIX}{user_id}")
        return bool(http_active)

    @classmethod
    async def cleanup_expired_users(
        cls,
        batch_size: int = 100,
    ) -> list[UUID]:
        now = int(time.time() * 1000)

        expired_users = await redis_client.zrangebyscore(
            cls.GLOBAL_PRESENCE_KEY,
            min="-inf",
            max=now,
            start=0,
            num=batch_size,
        )

        queued_users = []

        for user_id_value in expired_users:
            try:
                user_id = UUID(user_id_value)

                queued = await redis_client.eval(
                    cls.CLEANUP_SCRIPT,
                    4,
                    cls._get_connection_key(user_id),
                    cls.GLOBAL_PRESENCE_KEY,
                    cls.PENDING_OFFLINE_KEY,
                    cls._get_generation_key(user_id),
                    str(user_id),
                    now,
                )

                if queued:
                    queued_users.append(user_id)

            except ValueError:
                await redis_client.zrem(
                    cls.GLOBAL_PRESENCE_KEY,
                    user_id_value,
                )

        return queued_users

    @classmethod
    async def process_pending_offline_users(
        cls,
        batch_size: int = 100,
    ) -> list[UUID]:
        pending_users = await redis_client.zrange(
            cls.PENDING_OFFLINE_KEY,
            0,
            batch_size - 1,
            withscores=True,
        )

        processed_users = []

        for user_id_value, generation_value in pending_users:
            try:
                user_id = UUID(user_id_value)
                generation = int(generation_value)

                last_seen = datetime.now(UTC)

                message = {
                    "type": "presence.update",
                    "data": {
                        "user_id": str(user_id),
                        "is_online": False,
                        "last_seen": (last_seen.isoformat() if last_seen else None),
                    },
                }

                event = {
                    "target": "broadcast",
                    "message": message,
                }

                result = await redis_client.eval(
                    cls.FINALIZE_OFFLINE_SCRIPT,
                    4,
                    cls._get_connection_key(user_id),
                    cls.GLOBAL_PRESENCE_KEY,
                    cls.PENDING_OFFLINE_KEY,
                    cls._get_generation_key(user_id),
                    str(user_id),
                    generation,
                    int(time.time() * 1000),
                    cls.CLEANUP_CHANNEL,
                    json.dumps(event),
                )

                if result == 1:
                    await cls.mark_user_offline(user_id, last_seen)
                    processed_users.append(user_id)

            except (ValueError, SQLAlchemyError):
                logger.exception(
                    "Failed to process pending offline event for user %s",
                    user_id_value,
                )

        return processed_users

    @staticmethod
    async def mark_user_offline(
        user_id: UUID,
        last_seen: datetime | None = None,
    ) -> datetime | None:
        async with AsyncSessionLocal() as db:
            user = await UserRepository.get_by_id(
                db=db,
                user_id=user_id,
            )

            if user is None:
                return None

            user.last_seen = last_seen or datetime.now(UTC)

            await db.commit()
            await db.refresh(user)

            return user.last_seen

    @staticmethod
    async def broadcast_presence(
        user_id: UUID,
        is_online: bool,
        last_seen: datetime | None = None,
    ) -> None:
        await redis_pubsub_manager.publish_broadcast(
            {
                "type": "presence.update",
                "data": {
                    "user_id": str(user_id),
                    "is_online": is_online,
                    "last_seen": (last_seen.isoformat() if last_seen else None),
                },
            }
        )
