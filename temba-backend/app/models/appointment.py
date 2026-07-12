import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class AppointmentReason(str, enum.Enum):
    WATER_CONNECTION = "water_connection"
    METER_READING = "meter_reading"
    PIPE_REPAIR = "pipe_repair"
    CONSULTATION = "consultation"
    INSPECTION = "inspection"
    BILLING = "billing"
    OTHER = "other"


class MeetingType(str, enum.Enum):
    IN_PERSON = "in_person"
    PHONE_CALL = "phone_call"
    SITE_VISIT = "site_visit"


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESCHEDULED = "rescheduled"
    RESCHEDULE_REQUESTED = "reschedule_requested"
    CANCELLED = "cancelled"
    RESOLUTION_SUBMITTED = "resolution_submitted"
    VERIFIED = "verified"
    CLOSED_UNVERIFIED = "closed_unverified"
    COMPLETED = "completed"   # legacy — kept for backward compatibility


class Appointment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "appointments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    reason: Mapped[AppointmentReason] = mapped_column(Enum(AppointmentReason), nullable=False)
    meeting_type: Mapped[MeetingType] = mapped_column(
        Enum(MeetingType), nullable=False, default=MeetingType.IN_PERSON
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.PENDING
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Confirmed date/time
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    appointment_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"

    # User reschedule request
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    reschedule_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider counter-proposal
    proposed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    proposed_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider rejection / cancellation note
    provider_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overdue_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolution_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="appointments")  # type: ignore[name-defined]
    provider: Mapped["Provider"] = relationship(back_populates="appointments")  # type: ignore[name-defined]

    @property
    def user_name(self) -> str | None:
        try:
            return self.user.full_name if self.user else None
        except Exception:
            return None

    @property
    def user_phone(self) -> str | None:
        try:
            return self.user.phone if self.user else None
        except Exception:
            return None

    @property
    def provider_name(self) -> str | None:
        try:
            return self.provider.organization_name if self.provider else None
        except Exception:
            return None
