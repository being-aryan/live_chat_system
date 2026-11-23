from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PresenceResponse(BaseModel):
    user_id: UUID
    is_online: bool
    last_seen: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
