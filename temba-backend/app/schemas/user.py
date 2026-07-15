from uuid import UUID
from datetime import datetime

from pydantic import EmailStr, Field, computed_field, field_validator

from app.models.user import UserRole
from app.schemas.common import ORMModel


class UserCreate(ORMModel):
    email: EmailStr
    phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole = UserRole.COMMUNITY

    # Optional location
    province: str | None = None
    district: str | None = None
    sector: str | None = None
    cell: str | None = None
    village: str | None = None

    # Notification preferences
    sms_notifications: bool = True
    email_notifications: bool = True
    in_app_alerts: bool = True

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class UserUpdate(ORMModel):
    full_name: str | None = Field(None, min_length=2, max_length=255)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{9,15}$")
    province: str | None = None
    district: str | None = None
    sector: str | None = None
    cell: str | None = None
    village: str | None = None
    sms_notifications: bool | None = None
    email_notifications: bool | None = None
    in_app_alerts: bool | None = None


class UserPublic(ORMModel):
    id: UUID
    email: str  # may be {digits}@ussd.temba.rw for USSD-originated accounts
    phone: str | None
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    avatar_url: str | None
    province: str | None
    district: str | None
    sector: str | None
    cell: str | None
    village: str | None
    created_at: datetime
    ussd_pin_hash: str | None = Field(None, exclude=True)
    sms_notifications: bool = True
    email_notifications: bool = True
    in_app_alerts: bool = True

    @computed_field
    @property
    def is_ussd_profile(self) -> bool:
        return (self.email or '').endswith('@ussd.temba.rw')

    @computed_field
    @property
    def has_ussd_pin(self) -> bool:
        return self.ussd_pin_hash is not None


class UserAdminUpdate(ORMModel):
    is_active: bool | None = None
    is_verified: bool | None = None
    role: UserRole | None = None
