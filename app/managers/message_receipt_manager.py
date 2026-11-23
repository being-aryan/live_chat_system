from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.message_receipt import MessageReceipt
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_receipt_repository import (
    MessageReceiptRepository,
)
from app.repositories.message_repository import MessageRepository


class MessageReceiptManager:
    @staticmethod
    async def mark_conversation_read(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        last_read_message_id: UUID,
    ) -> int:
        try:
            if not await ConversationRepository.is_member(
                db,
                conversation_id,
                current_user_id,
            ):
                raise PermissionError("You are not a member of this conversation")

            anchor_result = await db.execute(
                select(Message.created_at).where(
                    Message.id == last_read_message_id,
                    Message.conversation_id == conversation_id,
                )
            )
            anchor_created_at = anchor_result.scalar_one_or_none()
            if anchor_created_at is None:
                raise ValueError("Last read message not found")

            message_ids = select(Message.id).where(
                Message.conversation_id == conversation_id,
                Message.sender_id != current_user_id,
                or_(
                    Message.created_at < anchor_created_at,
                    and_(
                        Message.created_at == anchor_created_at,
                        Message.id <= last_read_message_id,
                    ),
                ),
            )
            now = datetime.now(UTC)
            result = await db.execute(
                update(MessageReceipt)
                .where(
                    MessageReceipt.user_id == current_user_id,
                    MessageReceipt.message_id.in_(message_ids),
                    MessageReceipt.read_at.is_(None),
                )
                .values(
                    delivered_at=func.coalesce(
                        MessageReceipt.delivered_at,
                        now,
                    ),
                    read_at=now,
                )
            )
            await db.commit()
            return result.rowcount or 0
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def mark_message_delivered(
        db: AsyncSession,
        message_id: UUID,
        current_user_id: UUID,
    ) -> MessageReceipt:
        try:
            message = await MessageRepository.get_by_id(
                db,
                message_id,
            )

            if message is None:
                raise ValueError("Message not found")

            is_member = await ConversationRepository.is_member(
                db,
                message.conversation_id,
                current_user_id,
            )

            if not is_member:
                raise PermissionError("You are not a member of this conversation")

            if message.sender_id == current_user_id:
                raise ValueError("Sender cannot mark their own message as delivered")

            receipt = await MessageReceiptRepository.get_by_message_and_user(
                db,
                message_id,
                current_user_id,
            )

            if receipt is None:
                raise ValueError("Message receipt not found")

            receipt = await MessageReceiptRepository.mark_delivered(
                db,
                receipt,
            )

            await db.commit()
            await db.refresh(receipt)

            return receipt

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def mark_message_read(
        db: AsyncSession,
        message_id: UUID,
        current_user_id: UUID,
    ) -> MessageReceipt:
        try:
            message = await MessageRepository.get_by_id(
                db,
                message_id,
            )

            if message is None:
                raise ValueError("Message not found")

            is_member = await ConversationRepository.is_member(
                db,
                message.conversation_id,
                current_user_id,
            )

            if not is_member:
                raise PermissionError("You are not a member of this conversation")

            if message.sender_id == current_user_id:
                raise ValueError("Sender cannot mark their own message as read")

            receipt = await MessageReceiptRepository.get_by_message_and_user(
                db,
                message_id,
                current_user_id,
            )

            if receipt is None:
                raise ValueError("Message receipt not found")

            receipt = await MessageReceiptRepository.mark_read(
                db,
                receipt,
            )

            await db.commit()
            await db.refresh(receipt)

            return receipt

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_message_receipts(
        db: AsyncSession,
        message_id: UUID,
        current_user_id: UUID,
    ) -> list[MessageReceipt]:
        try:
            message = await MessageRepository.get_by_id(
                db,
                message_id,
            )

            if message is None:
                raise ValueError("Message not found")

            if message.sender_id != current_user_id:
                raise PermissionError("Only the message sender can view receipts")

            receipts = await MessageReceiptRepository.get_by_message(
                db,
                message_id,
            )

            return receipts

        except Exception:
            await db.rollback()
            raise
