"""
Celery application — background task queue for emails, SMS, and SLA enforcement.
Tasks are called via .delay() from endpoint background tasks.
Beat schedule runs the SLA checker hourly.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "temba",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Kigali",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "check-sla-deadlines-hourly": {
            "task": "app.tasks.check_sla_deadlines",
            "schedule": crontab(minute=0),  # top of every hour
        },
        "auto-close-unverified-daily": {
            "task": "app.tasks.auto_close_unverified",
            "schedule": crontab(hour=1, minute=0),  # 01:00 Kigali time daily
        },
        "send-appointment-reminders": {
            "task": "app.tasks.send_appointment_reminders",
            "schedule": crontab(minute="*/5"),  # every 5 minutes
        },
        "auto-complete-confirmed-appointments": {
            "task": "app.tasks.auto_complete_confirmed_appointments",
            "schedule": crontab(minute=30),  # half-past every hour
        },
    },
)
