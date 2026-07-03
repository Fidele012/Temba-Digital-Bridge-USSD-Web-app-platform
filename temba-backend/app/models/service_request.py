import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class ServiceRequestType(str, enum.Enum):
    WATER_CONNECTION = "water_connection"
    TANK_DELIVERY = "tank_delivery"
    TRUCK_DELIVERY = "truck_delivery"
    METER_SUPPORT = "meter_support"
    INSPECTION = "inspection"


class ServiceRequestUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ServiceRequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    RESOLUTION_SUBMITTED = "resolution_submitted"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    MANAGEMENT_REVIEW = "management_review"
    VERIFIED = "verified"
    CLOSED_UNVERIFIED = "closed_unverified"
    COMPLETED = "completed"   # legacy — kept for backward compatibility
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ServiceRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    request_type: Mapped[ServiceRequestType] = mapped_column(Enum(ServiceRequestType), nullable=False)
    urgency: Mapped[ServiceRequestUrgency] = mapped_column(
        Enum(ServiceRequestUrgency), nullable=False, default=ServiceRequestUrgency.MEDIUM
    )
    status: Mapped[ServiceRequestStatus] = mapped_column(
        Enum(ServiceRequestStatus), nullable=False, default=ServiceRequestStatus.SUBMITTED
    )
    reference_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    provider_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overdue_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Location
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    village: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped["User"] = relationship(back_populates="service_requests")  # type: ignore[name-defined]
    provider: Mapped["Provider | None"] = relationship(back_populates="service_requests")  # type: ignore[name-defined]

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
    def user_email(self) -> str | None:
        try:
            return self.user.email if self.user else None
        except Exception:
            return None

    @property
    def provider_name(self) -> str | None:
        try:
            return self.provider.organization_name if self.provider else None
        except Exception:
            return None
