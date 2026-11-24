from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.user_repository import UserRepository


class ConversationManager:
    @staticmethod
    async def create_direct_conversation(
        db: AsyncSession,
        current_user_id: UUID,
        other_user_id: UUID,
    ) -> tuple[Conversation, bool]:

        if current_user_id == other_user_id:
            raise ValueError("You cannot create a conversation with yourself")

        try:
            current_user = await UserRepository.get_by_id(db, current_user_id)

            other_user = await UserRepository.get_by_id(db, other_user_id)

            if current_user is None or not current_user.is_active:
                raise ValueError("Current user is unavailable")

            if other_user is None or not other_user.is_active:
                raise ValueError("The requested user is unavailable")

            existing_conversation = (
                await ConversationRepository.get_direct_conversation(
                    db,
                    current_user_id,
                    other_user_id,
                )
            )

            if existing_conversation is not None:
                return existing_conversation, False

            first_user_id, second_user_id = sorted([current_user_id, other_user_id])

            conversation = Conversation(
                conversation_type="direct",
                created_by=current_user_id,
                direct_user_one_id=first_user_id,
                direct_user_two_id=second_user_id,
            )

            await ConversationRepository.create(db, conversation)

            first_member = ConversationMember(
                conversation_id=conversation.id,
                user_id=first_user_id,
            )

            second_member = ConversationMember(
                conversation_id=conversation.id,
                user_id=second_user_id,
            )

            await ConversationRepository.add_member(db, first_member)
            await ConversationRepository.add_member(db, second_member)

            await db.commit()
            await db.refresh(conversation)

            return conversation, True

        except IntegrityError:
            await db.rollback()

            existing_conversation = (
                await ConversationRepository.get_direct_conversation(
                    db,
                    current_user_id,
                    other_user_id,
                )
            )

            if existing_conversation is not None:
                return existing_conversation, False

            raise

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def create_group(
        db: AsyncSession,
        creator_id: UUID,
        name: str,
        member_ids: list[UUID],
    ) -> Conversation:
        if creator_id in member_ids:
            member_ids = [member_id for member_id in member_ids if member_id != creator_id]
        if not member_ids:
            raise ValueError("A group must include at least one other member")

        try:
            unique_ids = set(member_ids)
            users = []
            for member_id in unique_ids:
                user = await UserRepository.get_by_id(db, member_id)
                if user is None or not user.is_active:
                    raise ValueError("One or more group members are unavailable")
                users.append(user)

            conversation = Conversation(
                conversation_type="group",
                name=name.strip(),
                created_by=creator_id,
            )
            await ConversationRepository.create(db, conversation)
            await ConversationRepository.add_member(
                db,
                ConversationMember(
                    conversation_id=conversation.id,
                    user_id=creator_id,
                    role="admin",
                ),
            )
            for user in users:
                await ConversationRepository.add_member(
                    db,
                    ConversationMember(
                        conversation_id=conversation.id,
                        user_id=user.id,
                        role="member",
                    ),
                )
            await db.commit()
            return await ConversationRepository.get_by_id(db, conversation.id)
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def _require_group_admin(
        db: AsyncSession,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation:
        conversation = await ConversationRepository.get_by_id(
            db,
            conversation_id,
        )
        if conversation is None or conversation.conversation_type != "group":
            raise ValueError("Group not found")
        member = await ConversationRepository.get_member(
            db,
            conversation_id,
            user_id,
        )
        if member is None:
            raise PermissionError("You are not a member of this group")
        if member.role != "admin":
            raise PermissionError("Only group admins can perform this action")
        return conversation

    @staticmethod
    async def rename_group(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        name: str,
    ) -> Conversation:
        try:
            conversation = await ConversationManager._require_group_admin(
                db, conversation_id, current_user_id
            )
            conversation.name = name.strip()
            await db.commit()
            return await ConversationRepository.get_by_id(db, conversation_id)
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def add_group_member(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        new_user_id: UUID,
    ) -> Conversation:
        try:
            await ConversationManager._require_group_admin(
                db, conversation_id, current_user_id
            )
            user = await UserRepository.get_by_id(db, new_user_id)
            if user is None or not user.is_active:
                raise ValueError("User is unavailable")
            existing = await ConversationRepository.get_member(
                db, conversation_id, new_user_id
            )
            if existing is not None:
                raise ValueError("User is already a group member")
            await ConversationRepository.add_member(
                db,
                ConversationMember(
                    conversation_id=conversation_id,
                    user_id=new_user_id,
                    role="member",
                ),
            )
            await db.commit()
            return await ConversationRepository.get_by_id(db, conversation_id)
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def remove_group_member(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
        member_user_id: UUID,
    ) -> None:
        try:
            await ConversationManager._require_group_admin(
                db, conversation_id, current_user_id
            )
            member = await ConversationRepository.get_member(
                db, conversation_id, member_user_id
            )
            if member is None:
                raise ValueError("Group member not found")
            if member.role == "admin":
                raise ValueError("Transfer admin role before removing an admin")
            await ConversationRepository.remove_member(db, member)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def leave_group(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
    ) -> None:
        try:
            conversation = await ConversationRepository.get_by_id(
                db, conversation_id
            )
            if conversation is None or conversation.conversation_type != "group":
                raise ValueError("Group not found")
            member = await ConversationRepository.get_member(
                db, conversation_id, current_user_id
            )
            if member is None:
                raise ValueError("You are not a member of this group")
            if member.role == "admin":
                remaining = [
                    item for item in conversation.members
                    if item.user_id != current_user_id
                ]
                if remaining:
                    successor = min(remaining, key=lambda item: item.joined_at)
                    successor.role = "admin"
                else:
                    await db.delete(conversation)
                    await db.commit()
                    return
            await ConversationRepository.remove_member(db, member)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_user_conversations(
        db: AsyncSession,
        current_user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:

        if limit < 1 or limit > 100:
            raise ValueError("Limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("Offset cannot be negative")

        conversations = await ConversationRepository.get_user_conversations(
            db=db,
            user_id=current_user_id,
            limit=limit,
            offset=offset,
        )

        return conversations

    @staticmethod
    async def get_conversation_details(
        db: AsyncSession,
        conversation_id: UUID,
        current_user_id: UUID,
    ) -> Conversation:

        conversation = await ConversationRepository.get_by_id(
            db=db,
            conversation_id=conversation_id,
        )

        if conversation is None:
            raise ValueError("Conversation not found")

        is_member = await ConversationRepository.is_member(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user_id,
        )

        if not is_member:
            raise PermissionError("You are not a member of this conversation")

        return conversation
