from uuid import UUID
from datetime import datetime

from pydantic import Field

from app.models.service_request import ServiceRequestStatus, ServiceRequestType, ServiceRequestUrgency
from app.schemas.common import ORMModel


class ServiceRequestCreate(ORMModel):
    request_type: ServiceRequestType
    urgency: ServiceRequestUrgency = ServiceRequestUrgency.MEDIUM
    description: str = Field(min_length=10)
    provider_id: UUID | None = None

    province: str | None = None
    district: str | None = None
    sector: str | None = None
    cell: str | None = None
    village: str | None = None
    address_detail: str | None = Field(None, max_length=500)


class ServiceRequestUpdate(ORMModel):
    status: ServiceRequestStatus | None = None
    provider_notes: str | None = None
    provider_id: UUID | None = None


class ServiceRequestPublic(ORMModel):
    id: UUID
    reference_number: str | None = None
    user_id: UUID
    provider_id: UUID | None
    request_type: ServiceRequestType
    urgency: ServiceRequestUrgency
    status: ServiceRequestStatus
    description: str
    provider_notes: str | None
    province: str | None
    district: str | None
    sector: str | None
    cell: str | None
    village: str | None
    address_detail: str | None
    created_at: datetime
    updated_at: datetime
    sla_deadline: datetime | None = None
    overdue_flagged: bool = False
    reopen_count: int = 0
    first_responded_at: datetime | None = None
    resolution_submitted_at: datetime | None = None
    verified_at: datetime | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_email: str | None = None
    provider_name: str | None = None
