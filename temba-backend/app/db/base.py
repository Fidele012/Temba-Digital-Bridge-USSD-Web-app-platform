"""
Alembic model collector.
Re-exports base classes and imports every model so Alembic autogenerate
sees all tables. Application code should import from app.db.base_class.
"""
from app.db.base_class import Base, TimestampMixin, UUIDMixin  # noqa: F401

# ── Import all models so Alembic picks them up ──────────────────────────────
from app.models.user import User  # noqa: F401
from app.models.provider import Provider, ProviderServiceArea  # noqa: F401
from app.models.report import Report, ReportMedia  # noqa: F401
from app.models.service_request import ServiceRequest  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.announcement import Announcement  # noqa: F401
from app.models.rating import Rating  # noqa: F401
from app.models.token_store import UserToken  # noqa: F401
