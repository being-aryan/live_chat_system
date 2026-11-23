from pydantic import BaseModel, ConfigDict, Field


class WebSocketTicketResponse(BaseModel):
    ticket: str
    expires_in: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")
