import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class PriorityClass(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ReportCategory(str, enum.Enum):
    CONTAMINATION = "contamination"
    PIPE_BURST = "pipe_burst"
    LOW_PRESSURE = "low_pressure"
    NO_SUPPLY = "no_supply"
    WATER_QUALITY = "water_quality"
    BILLING = "billing"
    METER = "meter"
    OTHER = "other"


class ReportUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    UNDER_REVIEW = "under_review"
    IN_PROGRESS = "in_progress"
    RESOLUTION_SUBMITTED = "resolution_submitted"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    MANAGEMENT_REVIEW = "management_review"
    VERIFIED = "verified"
    CLOSED_UNVERIFIED = "closed_unverified"
    RESOLVED = "resolved"   # legacy — kept for backward compatibility
    CLOSED = "closed"       # legacy — kept for backward compatibility


class Report(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    category: Mapped[ReportCategory] = mapped_column(Enum(ReportCategory), nullable=False)
    urgency: Mapped[ReportUrgency] = mapped_column(Enum(ReportUrgency), nullable=False, default=ReportUrgency.MEDIUM)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), nullable=False, default=ReportStatus.OPEN)
    priority_class: Mapped[PriorityClass | None] = mapped_column(Enum(PriorityClass), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    overdue_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    routed_via_national_authority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    affected_scale: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Location
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    village: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="reports")  # type: ignore[name-defined]
    provider: Mapped["Provider | None"] = relationship("Provider", foreign_keys=[provider_id], back_populates="reports")  # type: ignore[name-defined]
    media: Mapped[list["ReportMedia"]] = relationship(back_populates="report", cascade="all, delete-orphan")

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


class ReportMedia(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "report_media"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False, default="image")  # image | video | document
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)

    report: Mapped["Report"] = relationship(back_populates="media")
