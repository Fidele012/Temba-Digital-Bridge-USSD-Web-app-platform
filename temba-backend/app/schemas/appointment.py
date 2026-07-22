from uuid import UUID
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.models.appointment import AppointmentReason, AppointmentStatus, MeetingType
from app.schemas.common import ORMModel


class AppointmentCreate(ORMModel):
    provider_id: UUID
    reason: AppointmentReason
    meeting_type: MeetingType = MeetingType.IN_PERSON
    appointment_date: date
    appointment_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    notes: str | None = None


class AppointmentRescheduleRequest(ORMModel):
    """Community member requests a new slot."""
    requested_date: date
    requested_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    reschedule_reason: str | None = None


class ProviderRescheduleProposal(ORMModel):
    """Provider proposes an alternative slot."""
    proposed_date: date
    proposed_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    proposed_message: str | None = None


class AppointmentStatusUpdate(ORMModel):
    status: AppointmentStatus
    provider_note: str | None = None


class AppointmentCancel(ORMModel):
    """Required cancellation reason — both community and provider must supply one."""
    reason: str = Field(min_length=5, max_length=500)


class AppointmentConfirmBody(ORMModel):
    """Confirm whether the appointment actually took place."""
    confirmed: bool


class AppointmentOutcomeBody(ORMModel):
    """Record post-appointment outcome. Community fills outcome; provider fills notes."""
    community_outcome: Literal["yes", "partially", "no"] | None = None
    provider_outcome_notes: str | None = Field(None, max_length=1000)


class AppointmentPublic(ORMModel):
    id: UUID
    user_id: UUID
    provider_id: UUID
    reason: AppointmentReason
    meeting_type: MeetingType
    status: AppointmentStatus
    notes: str | None
    appointment_date: date
    appointment_time: str
    requested_date: date | None
    requested_time: str | None
    reschedule_reason: str | None
    proposed_date: date | None
    proposed_time: str | None
    proposed_message: str | None
    provider_note: str | None
    created_at: datetime
    updated_at: datetime
    sla_deadline: datetime | None = None
    overdue_flagged: bool = False
    resolution_submitted_at: datetime | None = None
    verified_at: datetime | None = None
    user_name: str | None = None
    user_phone: str | None = None
    provider_name: str | None = None
    # New meeting enhancement fields
    cancellation_reason: str | None = None
    community_confirmed: bool | None = None
    provider_confirmed: bool | None = None
    conflict_flagged: bool = False
    auto_complete_at: datetime | None = None
    community_outcome: str | None = None
    provider_outcome_notes: str | None = None
    reminder_sent: bool = False
