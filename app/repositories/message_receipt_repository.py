from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message_receipt import MessageReceipt


class MessageReceiptRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        receipt: MessageReceipt,
    ) -> MessageReceipt:
        db.add(receipt)
        await db.flush()
        await db.refresh(receipt)

        return receipt

    @staticmethod
    async def create_many(
        db: AsyncSession,
        receipts: list[MessageReceipt],
    ) -> list[MessageReceipt]:
        if not receipts:
            return []

        db.add_all(receipts)
        await db.flush()

        return receipts

    @staticmethod
    async def get_by_message_and_user(
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID,
    ) -> MessageReceipt | None:
        result = await db.execute(
            select(MessageReceipt).where(
                MessageReceipt.message_id == message_id,
                MessageReceipt.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_message(
        db: AsyncSession,
        message_id: UUID,
    ) -> list[MessageReceipt]:
        result = await db.execute(
            select(MessageReceipt)
            .where(MessageReceipt.message_id == message_id)
            .order_by(MessageReceipt.created_at.asc())
        )

        return list(result.scalars().all())

    @staticmethod
    async def mark_delivered(
        db: AsyncSession,
        receipt: MessageReceipt,
    ) -> MessageReceipt:
        if receipt.delivered_at is None:
            receipt.delivered_at = datetime.now(UTC)

        await db.flush()
        await db.refresh(receipt)

        return receipt

    @staticmethod
    async def mark_read(
        db: AsyncSession,
        receipt: MessageReceipt,
    ) -> MessageReceipt:
        now = datetime.now(UTC)

        if receipt.delivered_at is None:
            receipt.delivered_at = now

        if receipt.read_at is None:
            receipt.read_at = now

        await db.flush()
        await db.refresh(receipt)

        return receipt
