import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.jwt import create_access_token
from app.core.security import (
    generate_refresh_token,
    hash_refresh_token,
)
from app.database.redis import redis_client
from app.models.user_session import UserSession
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import (
    UserSessionRepository,
)


class SessionManager:
    REVOKED_SESSIONS_KEY = "auth:revoked_sessions"

    @staticmethod
    async def _cache_revoked_sessions(session_ids: list[UUID]) -> None:
        if not session_ids:
            return
        await redis_client.sadd(
            SessionManager.REVOKED_SESSIONS_KEY,
            *(str(session_id) for session_id in session_ids),
        )
        await redis_client.expire(
            SessionManager.REVOKED_SESSIONS_KEY,
            (settings.REFRESH_TOKEN_EXPIRE_DAYS + 1) * 86400,
        )

    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: UUID,
    ) -> tuple[str, str]:
        try:
            refresh_token = generate_refresh_token()
            refresh_token_hash = hash_refresh_token(refresh_token)

            now = datetime.now(UTC)

            session = UserSession(
                user_id=user_id,
                family_id=uuid.uuid4(),
                refresh_token_hash=refresh_token_hash,
                expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )

            await UserSessionRepository.create(
                db=db,
                session=session,
            )

            access_token = create_access_token(
                subject=str(user_id),
                session_id=session.id,
            )

            await db.commit()

            return access_token, refresh_token

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def rotate_refresh_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> tuple[str, str]:
        try:
            token_hash = hash_refresh_token(refresh_token)

            session = await UserSessionRepository.get_by_token_hash(
                db=db,
                token_hash=token_hash,
                lock=True,
            )

            if session is None:
                raise ValueError("Invalid refresh token")

            if session.revoked_at is not None:
                if session.replaced_by_id is not None:
                    family_sessions = (
                        await UserSessionRepository.get_sessions_by_family(
                            db=db,
                            family_id=session.family_id,
                        )
                    )
                    await UserSessionRepository.revoke_family(
                        db=db,
                        family_id=session.family_id,
                    )

                    await db.commit()
                    await SessionManager._cache_revoked_sessions(
                        [item.id for item in family_sessions]
                    )

                    raise ValueError(
                        "Refresh token reuse detected. Session family revoked."
                    )

                raise ValueError("Refresh token has been revoked")

            now = datetime.now(UTC)

            if session.expires_at <= now:
                raise ValueError("Refresh token has expired")

            user = await UserRepository.get_by_id(
                db=db,
                user_id=session.user_id,
            )

            if user is None or not user.is_active:
                family_sessions = await UserSessionRepository.get_sessions_by_family(
                    db=db,
                    family_id=session.family_id,
                )
                await UserSessionRepository.revoke_family(
                    db=db,
                    family_id=session.family_id,
                )

                await db.commit()
                await SessionManager._cache_revoked_sessions(
                    [item.id for item in family_sessions]
                )

                raise ValueError("User account is unavailable")

            new_refresh_token = generate_refresh_token()

            new_session = UserSession(
                user_id=session.user_id,
                family_id=session.family_id,
                refresh_token_hash=hash_refresh_token(new_refresh_token),
                expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )

            await UserSessionRepository.create(
                db=db,
                session=new_session,
            )

            await UserSessionRepository.link_replacement(
                db=db,
                old_session=session,
                new_session=new_session,
            )

            access_token = create_access_token(
                subject=str(user.id),
                session_id=new_session.id,
            )

            await db.commit()
            await SessionManager._cache_revoked_sessions([session.id])

            return access_token, new_refresh_token

        except Exception:
            if db.in_transaction():
                await db.rollback()
            raise

    @staticmethod
    async def logout(
        db: AsyncSession,
        refresh_token: str,
    ) -> None:
        try:
            token_hash = hash_refresh_token(refresh_token)

            session = await UserSessionRepository.get_by_token_hash(
                db=db,
                token_hash=token_hash,
                lock=True,
            )

            if session is None or session.revoked_at is not None:
                await db.rollback()
                return

            await UserSessionRepository.revoke(
                db=db,
                session=session,
            )

            await db.commit()
            await SessionManager._cache_revoked_sessions([session.id])

        except Exception:
            if db.in_transaction():
                await db.rollback()
            raise

    @staticmethod
    async def logout_all(
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        try:
            active_sessions = await UserSessionRepository.get_active_sessions(
                db=db,
                user_id=user_id,
            )
            revoked_count = await UserSessionRepository.revoke_all_for_user(
                db=db,
                user_id=user_id,
            )

            await db.commit()
            await SessionManager._cache_revoked_sessions(
                [session.id for session in active_sessions]
            )

            return revoked_count

        except Exception:
            if db.in_transaction():
                await db.rollback()
            raise

    @staticmethod
    async def get_user_sessions(
        db: AsyncSession,
        user_id: UUID,
    ) -> list[UserSession]:
        return await UserSessionRepository.get_active_sessions(
            db=db,
            user_id=user_id,
        )

    @staticmethod
    async def revoke_user_session(
        db: AsyncSession,
        user_id: UUID,
        session_id: UUID,
    ) -> bool:
        try:
            session = await UserSessionRepository.get_by_id(
                db=db,
                session_id=session_id,
                lock=True,
            )

            if session is None or session.user_id != user_id:
                await db.rollback()
                return False

            if session.revoked_at is not None:
                await db.rollback()
                return False

            family_sessions = await UserSessionRepository.get_sessions_by_family(
                db=db,
                family_id=session.family_id,
            )
            await UserSessionRepository.revoke_family(
                db=db,
                family_id=session.family_id,
            )

            await db.commit()
            await SessionManager._cache_revoked_sessions(
                [item.id for item in family_sessions]
            )

            return True

        except Exception:
            if db.in_transaction():
                await db.rollback()
            raise
