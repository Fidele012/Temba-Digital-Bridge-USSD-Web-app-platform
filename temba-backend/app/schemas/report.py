from typing import Literal
from uuid import UUID
from datetime import date, datetime

from pydantic import Field

from app.models.report import PriorityClass, ReportCategory, ReportStatus, ReportUrgency
from app.schemas.common import ORMModel


class VerificationVerdict(ORMModel):
    verdict: Literal["verified", "partial", "not_resolved"]
    comment: str | None = Field(None, max_length=500)


class ReportCreate(ORMModel):
    category: ReportCategory
    urgency: ReportUrgency = ReportUrgency.MEDIUM
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=10)
    provider_id: UUID | None = None
    routed_via_national_authority: bool = False
    affected_scale: str | None = None

    # Location
    province: str | None = None
    district: str | None = None
    sector: str | None = None
    cell: str | None = None
    village: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class ReportUpdate(ORMModel):
    status: ReportStatus | None = None
    urgency: ReportUrgency | None = None
    resolution_notes: str | None = None
    provider_id: UUID | None = None
    expected_completion_date: date | None = None


class ReportMediaPublic(ORMModel):
    id: UUID
    url: str
    media_type: str
    file_name: str | None
    file_size: int | None


class ReportPublic(ORMModel):
    id: UUID
    user_id: UUID
    provider_id: UUID | None
    reference_number: str | None = None
    priority_class: PriorityClass | None = None
    category: ReportCategory
    urgency: ReportUrgency
    status: ReportStatus
    title: str
    description: str
    resolution_notes: str | None
    province: str | None
    district: str | None
    sector: str | None
    cell: str | None
    village: str | None
    latitude: float | None
    longitude: float | None
    media: list[ReportMediaPublic]
    created_at: datetime
    updated_at: datetime
    sla_deadline: datetime | None = None
    resolution_deadline: datetime | None = None
    expected_completion_date: date | None = None
    overdue_flagged: bool = False
    reopen_count: int = 0
    routed_via_national_authority: bool = False
    affected_scale: str | None = None
    first_responded_at: datetime | None = None
    resolution_submitted_at: datetime | None = None
    verified_at: datetime | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_email: str | None = None
    provider_name: str | None = None
