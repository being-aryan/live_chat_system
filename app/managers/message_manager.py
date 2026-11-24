from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.managers.presence_manager import PresenceManager
from app.models.message import Message
from app.models.message_receipt import MessageReceipt
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_receipt_repository import (
    MessageReceiptRepository,
)
from app.repositories.message_repository import MessageRepository
from app.repositories.user_repository import UserRepository


class MessageManager:
    @staticmethod
    async def create_message(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        content: str,
    ) -> Message:
        try:
            user = await UserRepository.get_by_id(
                db,
                current_user_id,
            )

            if user is None:
                raise ValueError("User not found")

            if not user.is_active:
                raise PermissionError("User account is inactive")

            conversation = await ConversationRepository.get_by_id(
                db,
                conversation_id,
            )

            if conversation is None:
                raise ValueError("Conversation not found")

            is_member = await ConversationRepository.is_member(
                db,
                conversation_id,
                current_user_id,
            )

            if not is_member:
                raise PermissionError("You are not a member of this conversation")

            message = Message(
                conversation_id=conversation_id,
                sender_id=current_user_id,
                content=content,
            )

            message = await MessageRepository.create(
                db,
                message,
            )

            receipts = [
                MessageReceipt(
                    message_id=message.id,
                    user_id=member.user_id,
                )
                for member in conversation.members
                if member.user_id != current_user_id
            ]

            await MessageReceiptRepository.create_many(
                db,
                receipts,
            )

            await db.commit()
            refreshed = await db.execute(
                select(Message)
                .options(selectinload(Message.sender), selectinload(Message.receipts))
                .where(Message.id == message.id)
            )
            message = refreshed.scalar_one()
            await PresenceManager.record_user_active(current_user_id)

            return message

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_conversation_messages(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        limit: int = 50,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
    ) -> list[Message]:
        try:
            if limit < 1 or limit > 100:
                raise ValueError("Limit must be between 1 and 100")

            conversation = await ConversationRepository.get_by_id(
                db,
                conversation_id,
            )

            if conversation is None:
                raise ValueError("Conversation not found")

            is_member = await ConversationRepository.is_member(
                db,
                conversation_id,
                current_user_id,
            )

            if not is_member:
                raise PermissionError("You are not a member of this conversation")

            # Mark incoming undelivered messages as delivered
            now = datetime.now(UTC)
            undelivered_msg_ids = (
                select(Message.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_id != current_user_id,
                )
            )
            await db.execute(
                update(MessageReceipt)
                .where(
                    MessageReceipt.user_id == current_user_id,
                    MessageReceipt.delivered_at.is_(None),
                    MessageReceipt.message_id.in_(undelivered_msg_ids),
                )
                .values(delivered_at=now)
            )
            await db.commit()
            await PresenceManager.record_user_active(current_user_id)

            return await MessageRepository.get_conversation_messages(
                db,
                conversation_id,
                limit,
                before_created_at,
                before_id,
            )

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def update_message(
        db: AsyncSession,
        message_id: UUID,
        current_user_id: UUID,
        content: str,
    ) -> Message:
        try:
            user = await UserRepository.get_by_id(
                db,
                current_user_id,
            )

            if user is None:
                raise ValueError("User not found")

            if not user.is_active:
                raise PermissionError("User account is inactive")

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

            if message.sender_id != current_user_id:
                raise PermissionError("You can only edit your own messages")

            if message.deleted_at is not None:
                raise ValueError("Cannot update a deleted message")

            message = await MessageRepository.update(
                db,
                message,
                content,
            )

            await db.commit()
            refreshed = await db.execute(
                select(Message)
                .options(selectinload(Message.sender), selectinload(Message.receipts))
                .where(Message.id == message.id)
            )
            message = refreshed.scalar_one()
            await PresenceManager.record_user_active(current_user_id)

            return message

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def delete_message(
        db: AsyncSession,
        message_id: UUID,
        current_user_id: UUID,
    ) -> Message:
        try:
            user = await UserRepository.get_by_id(
                db,
                current_user_id,
            )

            if user is None:
                raise ValueError("User not found")

            if not user.is_active:
                raise PermissionError("User account is inactive")

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

            if message.sender_id != current_user_id:
                raise PermissionError("You can only delete your own messages")

            if message.deleted_at is not None:
                raise ValueError("Message is already deleted")

            message = await MessageRepository.soft_delete(
                db,
                message,
            )

            await db.commit()
            refreshed = await db.execute(
                select(Message)
                .options(selectinload(Message.sender), selectinload(Message.receipts))
                .where(Message.id == message.id)
            )
            message = refreshed.scalar_one()
            await PresenceManager.record_user_active(current_user_id)

            return message

        except Exception:
            await db.rollback()
            raise
