from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
