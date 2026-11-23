from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember
from app.models.message import Message
from app.models.message_receipt import MessageReceipt


class ConversationRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        conversation: Conversation,
    ) -> Conversation:
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        conversation_id: UUID,
    ) -> Conversation | None:
        result = await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.members))
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_direct_conversation(
        db: AsyncSession,
        user_one_id: UUID,
        user_two_id: UUID,
    ) -> Conversation | None:
        first_user_id, second_user_id = sorted([user_one_id, user_two_id])

        result = await db.execute(
            select(Conversation).where(
                Conversation.conversation_type == "direct",
                Conversation.direct_user_one_id == first_user_id,
                Conversation.direct_user_two_id == second_user_id,
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def add_member(
        db: AsyncSession,
        member: ConversationMember,
    ) -> ConversationMember:
        db.add(member)
        await db.flush()
        return member

    @staticmethod
    async def is_member(
        db: AsyncSession,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:
        result = await db.execute(
            select(ConversationMember.id).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_member(
        db: AsyncSession,
        conversation_id: UUID,
        user_id: UUID,
    ) -> ConversationMember | None:
        result = await db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def remove_member(
        db: AsyncSession,
        member: ConversationMember,
    ) -> None:
        await db.delete(member)
        await db.flush()

    @staticmethod
    async def have_common_conversation(
        db: AsyncSession,
        first_user_id: UUID,
        second_user_id: UUID,
    ) -> bool:
        first_membership = ConversationMember.__table__.alias("first_membership")
        second_membership = ConversationMember.__table__.alias("second_membership")
        result = await db.execute(
            select(first_membership.c.id)
            .select_from(
                first_membership.join(
                    second_membership,
                    first_membership.c.conversation_id
                    == second_membership.c.conversation_id,
                )
            )
            .where(
                first_membership.c.user_id == first_user_id,
                second_membership.c.user_id == second_user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_user_inbox(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 50,
    ) -> list[dict]:
        latest_message_id = (
            select(Message.id)
            .where(
                Message.conversation_id == Conversation.id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_message_content = (
            select(Message.content)
            .where(
                Message.conversation_id == Conversation.id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_message_created_at = (
            select(Message.created_at)
            .where(
                Message.conversation_id == Conversation.id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        unread_count = (
            select(func.count(MessageReceipt.id))
            .join(Message, Message.id == MessageReceipt.message_id)
            .where(
                Message.conversation_id == Conversation.id,
                MessageReceipt.user_id == user_id,
                MessageReceipt.read_at.is_(None),
                Message.sender_id != user_id,
                Message.deleted_at.is_(None),
            )
            .scalar_subquery()
        )

        statement = (
            select(
                Conversation,
                latest_message_id.label("last_message_id"),
                latest_message_content.label("last_message_content"),
                latest_message_created_at.label("last_message_created_at"),
                unread_count.label("unread_count"),
            )
            .join(
                ConversationMember,
                ConversationMember.conversation_id == Conversation.id,
            )
            .where(ConversationMember.user_id == user_id)
            .options(selectinload(Conversation.members))
            .order_by(
                latest_message_created_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
            .limit(limit)
        )
        result = await db.execute(statement)
        return [
            {
                "conversation": row[0],
                "last_message_id": row.last_message_id,
                "last_message_content": row.last_message_content,
                "last_message_created_at": row.last_message_created_at,
                "unread_count": row.unread_count or 0,
            }
            for row in result
        ]

    @staticmethod
    async def get_user_conversations(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:

        result = await db.execute(
            select(Conversation)
            .join(
                ConversationMember,
                ConversationMember.conversation_id == Conversation.id,
            )
            .where(ConversationMember.user_id == user_id)
            .options(
                selectinload(Conversation.members),
            )
            .order_by(
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().unique().all())
