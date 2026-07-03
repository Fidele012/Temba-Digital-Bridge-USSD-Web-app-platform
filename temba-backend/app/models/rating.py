import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDMixin


class Rating(UUIDMixin, TimestampMixin, Base):
    """Anonymous post-verification rating. NO user_id column by design."""
    __tablename__ = "ratings"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False, index=True, unique=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["Report"] = relationship()  # type: ignore[name-defined]
    provider: Mapped["Provider"] = relationship()  # type: ignore[name-defined]
