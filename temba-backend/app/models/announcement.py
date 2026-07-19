import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class AnnouncementAudience(str, enum.Enum):
    ALL = "all"
    COMMUNITY = "community"
    PROVIDERS = "providers"


class Announcement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "announcements"

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Provider that posted this announcement (nullable — system announcements have no provider)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    announcement_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    audience: Mapped[AnnouncementAudience] = mapped_column(
        Enum(AnnouncementAudience), nullable=False, default=AnnouncementAudience.ALL
    )
    # JSON location target: { level, provinces, districts, sectors, cells, villages }
    target: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
