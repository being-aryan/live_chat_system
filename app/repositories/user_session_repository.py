from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_session import UserSession


class UserSessionRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        session: UserSession,
    ) -> UserSession:
        db.add(session)

        await db.flush()
        await db.refresh(session)

        return session

    @staticmethod
    async def get_by_token_hash(
        db: AsyncSession,
        token_hash: str,
        lock: bool = False,
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.refresh_token_hash == token_hash)

        if lock:
            query = query.with_for_update()

        result = await db.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        session_id: UUID,
        lock: bool = False,
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.id == session_id)

        if lock:
            query = query.with_for_update()

        result = await db.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_session(
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID,
    ) -> UserSession | None:
        now = datetime.now(UTC)

        statement = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )

        result = await db.execute(statement)

        return result.scalar_one_or_none()

    @staticmethod
    async def link_replacement(
        db: AsyncSession,
        old_session: UserSession,
        new_session: UserSession,
    ) -> None:
        now = datetime.now(UTC)

        old_session.replaced_by_id = new_session.id
        old_session.revoked_at = now
        old_session.last_used_at = now

        await db.flush()

    @staticmethod
    async def revoke(
        db: AsyncSession,
        session: UserSession,
    ) -> None:
        if session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)

        await db.flush()

    @staticmethod
    async def revoke_all_for_user(
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        now = datetime.now(UTC)

        statement = (
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session="fetch")
        )

        result = await db.execute(statement)

        await db.flush()

        return result.rowcount or 0

    @staticmethod
    async def get_active_sessions(
        db: AsyncSession,
        user_id: UUID,
    ) -> list[UserSession]:
        now = datetime.now(UTC)

        statement = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.created_at.desc())
        )

        result = await db.execute(statement)

        return list(result.scalars().all())

    @staticmethod
    async def get_sessions_by_family(
        db: AsyncSession,
        family_id: UUID,
    ) -> list[UserSession]:
        result = await db.execute(
            select(UserSession).where(UserSession.family_id == family_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def revoke_family(
        db: AsyncSession,
        family_id: UUID,
    ) -> int:
        now = datetime.now(UTC)

        statement = (
            update(UserSession)
            .where(
                UserSession.family_id == family_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session="fetch")
        )

        result = await db.execute(statement)

        await db.flush()

        return result.rowcount or 0
