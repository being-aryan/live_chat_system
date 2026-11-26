import hashlib
import hmac
import secrets
from uuid import UUID

from redis.exceptions import RedisError, WatchError

from app.config import settings
from app.database.redis import redis_client


class OTPError(Exception):
    """Base exception for OTP workflow errors."""


class OTPResendCooldown(OTPError):
    """Raised when an OTP was requested too recently."""


class OTPVerificationBusy(OTPError):
    """Raised when concurrent OTP updates prevent verification."""


class OTPManager:
    PURPOSE = "email_verification"
    KEY_PREFIX = "auth:otp:email-verification"
    COOLDOWN_PREFIX = "auth:otp:email-verification:cooldown"

    @staticmethod
    def _validate_secret() -> bytes:
        secret = settings.OTP_SECRET_KEY
        if len(secret) < 32:
            raise RuntimeError("OTP_SECRET_KEY must contain at least 32 characters")
        return secret.encode("utf-8")

    @classmethod
    def _otp_key(cls, user_id: UUID | str) -> str:
        return f"{cls.KEY_PREFIX}:{user_id}"

    @classmethod
    def _cooldown_key(cls, user_id: UUID | str) -> str:
        return f"{cls.COOLDOWN_PREFIX}:{user_id}"

    @classmethod
    def generate_otp(cls) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def hash_otp(cls, otp: str, user_id: UUID | str) -> str:
        message = f"{cls.PURPOSE}:{user_id}:{otp}".encode("utf-8")
        return hmac.new(
            cls._validate_secret(),
            message,
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    async def issue_otp(cls, user_id: UUID | str) -> str:
        cls._validate_secret()
        cooldown_key = cls._cooldown_key(user_id)
        otp_key = cls._otp_key(user_id)

        try:
            acquired = await redis_client.set(
                cooldown_key,
                "1",
                ex=settings.OTP_RESEND_COOLDOWN_SECONDS,
                nx=True,
            )
            if not acquired:
                raise OTPResendCooldown

            otp = cls.generate_otp()
            otp_hash = cls.hash_otp(otp, user_id)

            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.hset(
                    otp_key,
                    mapping={"otp_hash": otp_hash, "attempts": "0"},
                )
                pipe.expire(otp_key, settings.OTP_TTL_SECONDS)
                await pipe.execute()

            return otp

        except OTPResendCooldown:
            raise
        except RedisError:
            try:
                await redis_client.delete(cooldown_key)
            except RedisError:
                pass
            raise
        except Exception:
            try:
                await redis_client.delete(cooldown_key)
            except RedisError:
                pass
            raise

    @classmethod
    async def cancel_issued_otp(cls, user_id: UUID | str) -> None:
        await redis_client.delete(
            cls._otp_key(user_id),
            cls._cooldown_key(user_id),
        )

    @classmethod
    async def verify_otp(
        cls,
        user_id: UUID | str,
        submitted_otp: str,
    ) -> bool:
        expected_hash = cls.hash_otp(submitted_otp, user_id)
        key = cls._otp_key(user_id)

        for _ in range(5):
            try:
                async with redis_client.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    record = await pipe.hgetall(key)

                    if not record:
                        await pipe.unwatch()
                        return False

                    attempts = int(record.get("attempts", "0"))
                    stored_hash = record.get("otp_hash", "")

                    if attempts >= settings.OTP_MAX_ATTEMPTS:
                        pipe.multi()
                        pipe.delete(key)
                        await pipe.execute()
                        return False

                    if not hmac.compare_digest(expected_hash, stored_hash):
                        pipe.multi()
                        pipe.hincrby(key, "attempts", 1)
                        if attempts + 1 >= settings.OTP_MAX_ATTEMPTS:
                            pipe.delete(key)
                        await pipe.execute()
                        return False

                    pipe.multi()
                    pipe.delete(key)
                    await pipe.execute()
                    return True

            except WatchError:
                continue
            except RedisError:
                raise

        raise OTPVerificationBusy("OTP verification was busy; retry the request")
