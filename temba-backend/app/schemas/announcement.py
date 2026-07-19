import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=255)
    body: str
    announcement_type: str = "general"
    target: dict | None = None  # {level, provinces, districts, sectors, cells, villages}


class AnnouncementPublic(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    announcement_type: str | None = None
    target: dict | None = None
    provider_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
