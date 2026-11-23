from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        message: Message,
    ) -> Message:
        db.add(message)

        await db.flush()
        await db.refresh(message)

        return message

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        message_id: UUID,
    ) -> Message | None:
        result = await db.execute(
            select(Message).where(
                Message.id == message_id,
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_conversation_messages(
        db: AsyncSession,
        conversation_id: UUID,
        limit: int = 50,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
    ) -> list[Message]:
        statement = select(Message).where(
            Message.conversation_id == conversation_id,
        )

        if (before_created_at is None) != (before_id is None):
            raise ValueError("Both before_created_at and before_id are required")

        if before_created_at is not None and before_id is not None:
            statement = statement.where(
                or_(
                    Message.created_at < before_created_at,
                    and_(
                        Message.created_at == before_created_at,
                        Message.id < before_id,
                    ),
                )
            )

        result = await db.execute(
            statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(
                limit + 1
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(
        db: AsyncSession,
        message: Message,
        content: str,
    ) -> Message:
        message.content = content

        await db.flush()
        await db.refresh(message)

        return message

    @staticmethod
    async def soft_delete(db: AsyncSession, message: Message) -> Message:
        message.deleted_at = datetime.now(UTC)

        await db.flush()
        await db.refresh(message)

        return message
