from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        user: User,
    ) -> User:
        db.add(user)
        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        user_id: UUID,
    ) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(
        db: AsyncSession,
        email: str,
    ) -> User | None:
        result = await db.execute(select(User).where(User.email == email))

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        db: AsyncSession,
        username: str,
    ) -> User | None:
        result = await db.execute(select(User).where(User.username == username))

        return result.scalar_one_or_none()

    @staticmethod
    async def search_users(
        db: AsyncSession,
        query: str,
        exclude_user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[User]:
        search_term = f"%{query.strip()}%"
        result = await db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                User.id != exclude_user_id,
                User.username.ilike(search_term),
            )
            .order_by(User.username.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_all(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 20,
    ) -> list[User]:
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )

        return list(result.scalars().all())
