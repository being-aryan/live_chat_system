from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class MessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=5000,
        description="Message content",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message cannot be empty")

        return value


class MessageUpdate(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=5000,
        description="Updated message content",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message cannot be empty")

        return value


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_username: str | None = None
    content: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    is_delivered: bool = False
    is_read: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    limit: int
    has_more: bool
    next_before_created_at: datetime | None = None
    next_before_id: UUID | None = None
