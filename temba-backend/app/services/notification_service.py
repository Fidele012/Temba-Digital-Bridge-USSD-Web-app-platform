"""
Notification service — creates in-app notification rows and dispatches
SMS via Africa's Talking (fire-and-forget in a background task).
Email: uses Resend API (HTTPS) when RESEND_API_KEY is set, otherwise falls back to SMTP.
Railway blocks outbound SMTP (port 587/465), so Resend is required in production.
"""
from __future__ import annotations

import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
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

def _effective_from_email() -> str:
    """Use SMTP_USER as the From address when EMAILS_FROM_EMAIL is still the placeholder."""
    if settings.EMAILS_FROM_EMAIL and settings.EMAILS_FROM_EMAIL != "noreply@temba.rw":
        return settings.EMAILS_FROM_EMAIL
    return settings.SMTP_USER or settings.EMAILS_FROM_EMAIL


def _send_via_resend(to: str, subject: str, html_body: str, txt_body: str) -> None:
    """Send via Resend HTTPS API — works on Railway (no port 587 blocking)."""
    from_addr = _effective_from_email()
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{settings.EMAILS_FROM_NAME} <{from_addr}>",
                "to": [to],
                "subject": subject,
                "html": html_body,
                "text": txt_body,
            },
        )
        resp.raise_for_status()
        log.info("Email sent via Resend", to=to, subject=subject, status=resp.status_code)


def _send_via_smtp(to: str, subject: str, html_body: str, txt_body: str) -> None:
    """Fallback SMTP sender — note: Railway blocks port 587, use Resend instead."""
    from_email = _effective_from_email()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{from_email}>"
    msg["To"] = to
    msg.attach(MIMEText(txt_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(from_email, to, msg.as_string())
    log.info("Email sent via SMTP", to=to, subject=subject)


def send_email_background(to: str, subject: str, template: str, context: dict) -> None:
    """Called as a BackgroundTask — runs in a thread, not async.

    Tries Resend first (works on Railway over HTTPS).
    Falls back to SMTP if no Resend key is configured (local dev only).
    """
    env = _get_jinja()
    try:
        html_body = env.get_template(f"{template}.html").render(**context)
        txt_body  = env.get_template(f"{template}.txt").render(**context)
    except Exception:
        log.exception("Failed to render email template", template=template)
        return

    if settings.RESEND_API_KEY:
        try:
            _send_via_resend(to, subject, html_body, txt_body)
        except httpx.HTTPStatusError as exc:
            log.error("Resend API error", to=to, status=exc.response.status_code, body=exc.response.text)
        except Exception:
            log.exception("Failed to send email via Resend", to=to)
        return

    if settings.SMTP_USER and settings.SMTP_PASSWORD not in ("", "change-me"):
        try:
            _send_via_smtp(to, subject, html_body, txt_body)
        except smtplib.SMTPAuthenticationError:
            log.error("SMTP auth failed — check SMTP_USER / SMTP_PASSWORD", smtp_user=settings.SMTP_USER)
        except smtplib.SMTPException as exc:
            log.error("SMTP error (Railway likely blocks port 587 — use Resend instead)", error=str(exc))
        except Exception:
            log.exception("Failed to send email via SMTP", to=to)
        return

    log.warning("No email provider configured — set RESEND_API_KEY in Railway env vars", to=to)


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
