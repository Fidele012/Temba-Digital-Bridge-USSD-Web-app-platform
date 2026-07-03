from uuid import UUID
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class RatingCreate(ORMModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=500)


class RatingPublic(ORMModel):
    id: UUID
    report_id: UUID
    provider_id: UUID
    score: int
    comment: str | None
    created_at: datetime


class ProviderRatingAggregate(ORMModel):
    provider_id: UUID
    average_score: float
    total_ratings: int
