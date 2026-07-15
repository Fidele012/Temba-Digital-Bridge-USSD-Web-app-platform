import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    COMMUNITY = "community"
    PROVIDER = "provider"
    ADMIN = "admin"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.COMMUNITY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rwanda administrative location (optional — used by community members)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    village: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Notification preferences (set during registration, editable in profile)
    sms_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # USSD PIN (hashed 4-digit PIN for feature-phone access)
    ussd_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Verification / password-reset
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    reports: Mapped[list["Report"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    provider_profile: Mapped["Provider | None"] = relationship(back_populates="user", uselist=False)  # type: ignore[name-defined]
