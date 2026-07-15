"""
Notification service — creates in-app notification rows and dispatches
SMS via Africa's Talking (fire-and-forget in a background task).
Email is dispatched via Jinja2 template + SMTP.
"""
from __future__ import annotations

import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import BackgroundTasks
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationType

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.user import User

log = structlog.get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "email"
_jinja_env: Environment | None = None


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "txt"]),
        )
    return _jinja_env


# ── In-app notifications ───────────────────────────────────────────────────────

async def notify_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        notification_type=NotificationType(notification_type),
        title=title,
        body=body,
        reference_id=reference_id,
        reference_type=reference_type,
    )
    db.add(notif)
    await db.flush()
    return notif


async def notify_org(
    db: AsyncSession,
    *,
    provider: "Provider",
    notification_type: str,
    title: str,
    body: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
) -> None:
    """Send a notification to ALL users linked to providers sharing the same
    organization name (handles seeded-vs-web-registered provider duplicates)."""
    from app.models.provider import Provider as _Provider  # avoid circular import

    rows = (await db.execute(
        select(_Provider).where(
            func.lower(_Provider.organization_name) == func.lower(provider.organization_name)
        )
    )).scalars().all()

    seen: set[uuid.UUID] = set()
    for prov in rows:
        if prov.user_id and prov.user_id not in seen:
            seen.add(prov.user_id)
            notif = Notification(
                user_id=prov.user_id,
                notification_type=NotificationType(notification_type),
                title=title,
                body=body,
                reference_id=reference_id,
                reference_type=reference_type,
            )
            db.add(notif)
    if seen:
        await db.flush()


async def notify_org_background(
    org_name: str,
    *,
    notification_type: str,
    title: str,
    body: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
) -> None:
    """Fire-and-forget variant of notify_org that opens its own DB session.
    Safe to use with asyncio.create_task — does not share the request session."""
    from app.db.session import AsyncSessionLocal
    from app.models.provider import Provider as _Provider

    try:
        async with AsyncSessionLocal() as bg_db:
            rows = (await bg_db.execute(
                select(_Provider).where(
                    func.lower(_Provider.organization_name) == func.lower(org_name)
                )
            )).scalars().all()
            seen: set[uuid.UUID] = set()
            for prov in rows:
                if prov.user_id and prov.user_id not in seen:
                    seen.add(prov.user_id)
                    bg_db.add(Notification(
                        user_id=prov.user_id,
                        notification_type=NotificationType(notification_type),
                        title=title,
                        body=body,
                        reference_id=reference_id,
                        reference_type=reference_type,
                    ))
            if seen:
                await bg_db.commit()
    except Exception:
        log.warning("notify_org_background_failed", org=org_name)


# ── Email ──────────────────────────────────────────────────────────────────────

def send_email_background(to: str, subject: str, template: str, context: dict) -> None:
    """Called as a BackgroundTask — runs in a thread, not async."""
    if not settings.SMTP_USER or settings.SMTP_PASSWORD in ("", "change-me"):
        log.warning("SMTP not configured, skipping email", to=to, subject=subject)
        return

    try:
        env = _get_jinja()
        html_body = env.get_template(f"{template}.html").render(**context)
        txt_body = env.get_template(f"{template}.txt").render(**context)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        msg["To"] = to
        msg.attach(MIMEText(txt_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAILS_FROM_EMAIL, to, msg.as_string())

        log.info("Email sent", to=to, subject=subject)
    except Exception:
        log.exception("Failed to send email", to=to)


# ── SMS via Africa's Talking ───────────────────────────────────────────────────

def send_sms_background(to: str, message: str) -> None:
    """Called as a BackgroundTask."""
    if not settings.AT_API_KEY:
        log.warning("AT SDK not configured, skipping SMS", to=to)
        return
    try:
        import africastalking
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        sms = africastalking.SMS
        response = sms.send(message, [to], sender_id=settings.AT_SENDER_ID)
        log.info("SMS sent", to=to, response=response)
    except Exception:
        log.exception("Failed to send SMS", to=to)


# ── Multi-channel community user notification ──────────────────────────────────

async def notify_community_user(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    user: "User",
    notification_type: str,
    title: str,
    body_text: str,
    email_subject: str | None = None,
    email_context: dict | None = None,
    sms_message: str | None = None,
    reference_id: str | None = None,
    reference_type: str | None = None,
) -> None:
    """Dispatch in-app, email, and SMS notifications respecting the user's preferences."""
    if user.in_app_alerts:
        await notify_user(
            db,
            user_id=user.id,
            notification_type=notification_type,
            title=title,
            body=body_text,
            reference_id=reference_id,
            reference_type=reference_type,
        )

    if user.email_notifications and user.email and not user.email.endswith("@ussd.temba.rw"):
        background_tasks.add_task(
            send_email_background,
            to=user.email,
            subject=email_subject or title,
            template="community_notification",
            context={
                "name": user.full_name.split()[0] if user.full_name else "there",
                "title": title,
                "message": body_text,
                **(email_context or {}),
            },
        )

    if user.sms_notifications and user.phone:
        msg = sms_message or f"Temba: {title}. {body_text}"
        if len(msg) > 160:
            msg = msg[:157] + "..."
        background_tasks.add_task(send_sms_background, to=user.phone, message=msg)
