from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageReceiptResponse(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageReceiptListResponse(BaseModel):
    receipts: list[MessageReceiptResponse]
