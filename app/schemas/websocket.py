from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.message import MessageCreate


class WebSocketMessageSend(BaseModel):
    type: Literal["message.send"]
    conversation_id: UUID
    data: MessageCreate

    model_config = ConfigDict(extra="forbid")


class WebSocketMessageRead(BaseModel):
    type: Literal["message.read"]
    message_id: UUID

    model_config = ConfigDict(extra="forbid")
