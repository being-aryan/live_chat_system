from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DirectConversationCreate(BaseModel):
    other_user_id: UUID


class ConversationResponse(BaseModel):
    id: UUID
    conversation_type: str
    name: str | None = None
    created_by: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationMemberResponse(BaseModel):
    user_id: UUID
    username: str | None = None
    joined_at: datetime
    role: str

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(ConversationResponse):
    members: list[ConversationMemberResponse] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationDetailResponse]
    limit: int
    offset: int


class ConversationInboxItem(BaseModel):
    conversation: ConversationDetailResponse
    other_user_id: UUID | None = None
    other_username: str | None = None
    last_message_id: UUID | None = None
    last_message_content: str | None = None
    last_message_created_at: datetime | None = None
    unread_count: int


class ConversationInboxResponse(BaseModel):
    conversations: list[ConversationInboxItem]


class GroupConversationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    member_ids: list[UUID] = Field(min_length=1, max_length=99)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Group name cannot be empty")
        return value

    @field_validator("member_ids")
    @classmethod
    def validate_members(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Group member IDs must be unique")
        return value


class GroupMemberAdd(BaseModel):
    user_id: UUID


class GroupNameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Group name cannot be empty")
        return value
