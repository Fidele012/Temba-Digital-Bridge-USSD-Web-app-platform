import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class UserToken(Base):
    """DB-backed store for short-lived tokens: refresh tokens and password-reset OTPs.
    Replaces Redis so the app works on Railway without a Redis add-on.
    """
    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "refresh" | "otp"
    value: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_user_tokens_user_type", "user_id", "token_type"),
    )
