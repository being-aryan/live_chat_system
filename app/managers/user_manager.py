import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserManager:
    DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))

    @staticmethod
    async def create_user(
        db: AsyncSession,
        username: str,
        email: str,
        password: str,
    ) -> User:

        email = email.strip().lower()
        username = username.strip()
        existing_email = await UserRepository.get_by_email(
            db,
            email,
        )
        existing_username = await UserRepository.get_by_username(
            db,
            username,
        )

        if existing_email or existing_username:
            raise ValueError("Email or username is already registered")

        hashed_password = hash_password(password)

        user = User(
            username=username,
            email=email,
            password_hash=hashed_password,
        )

        try:
            created_user = await UserRepository.create(
                db,
                user,
            )

            await db.commit()

            return created_user

        except IntegrityError:
            await db.rollback()
            raise ValueError("Email or username is already registered")

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User | None:

        email = email.strip().lower()
        user = await UserRepository.get_by_email(
            db,
            email,
        )

        if user is None:
            verify_password(password, UserManager.DUMMY_PASSWORD_HASH)
            return None

        if not verify_password(
            password,
            user.password_hash,
        ):
            return None

        if not user.is_active:
            return None

        return user
