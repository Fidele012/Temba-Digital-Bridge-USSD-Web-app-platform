import enum
import uuid

from sqlalchemy import ARRAY, Boolean, Enum, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class ProviderStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class ServiceCategory(str, enum.Enum):
    WATER_SUPPLY = "water_supply"
    SANITATION = "sanitation"
    WATER_QUALITY = "water_quality"
    INFRASTRUCTURE = "infrastructure"
    WATER_STORAGE = "water_storage"
    TRUCK_DELIVERY = "truck_delivery"
    METER_SERVICES = "meter_services"
    BOREHOLE = "borehole"


class ProviderStaffRole(str, enum.Enum):
    SUPERVISOR = "supervisor"
    REGIONAL_MANAGER = "regional_manager"
    EXECUTIVE = "executive"


class Provider(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[ProviderStatus] = mapped_column(
        Enum(ProviderStatus), nullable=False, default=ProviderStatus.PENDING
    )
    service_categories: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    custom_services: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SLA commitment (mandatory during registration)
    sla_response_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_resolution_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Escalation contacts — Level 1: Officer/Coordinator
    officer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    officer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    officer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Escalation contacts — Level 2: Supervisor
    supervisor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supervisor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supervisor_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Availability
    working_days: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    work_start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "08:00"
    work_end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)    # "17:00"
    max_appointments_per_day: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    unavailable_dates: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="provider_profile")  # type: ignore[name-defined]
    service_areas: Mapped[list["ProviderServiceArea"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    staff: Mapped[list["ProviderStaff"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="provider")  # type: ignore[name-defined]
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="provider")  # type: ignore[name-defined]
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="provider")  # type: ignore[name-defined]


class ProviderServiceArea(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "provider_service_areas"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)

    provider: Mapped["Provider"] = relationship(back_populates="service_areas")


class ProviderStaff(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "provider_staff"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    staff_role: Mapped[ProviderStaffRole] = mapped_column(Enum(ProviderStaffRole), nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="staff")
    user: Mapped["User"] = relationship()  # type: ignore[name-defined]
