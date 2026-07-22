"""Celery tasks — background email/SMS sending, SLA enforcement, and appointment reminders."""
import uuid
from datetime import datetime, timedelta, timezone

from app.services.notification_service import send_email_background, send_sms_background
from app.worker import celery_app

# Hours beyond the SLA deadline required to escalate each level
_ESCALATION_HOURS = {
    1: 0,   # Officer/Coordinator: notify as soon as overdue
    2: 24,  # Supervisor: +24 h
}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to: str, subject: str, template: str, context: dict) -> None:
    try:
        send_email_background(to, subject, template, context)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def send_sms_task(self, to: str, message: str) -> None:
    try:
        send_sms_background(to, message)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.auto_close_unverified")
def auto_close_unverified() -> dict:
    """Daily task: auto-close cases where provider submitted a resolution but
    the community did not verify within 7 days.  These are marked
    CLOSED_UNVERIFIED — the provider receives no verification credit."""
    from datetime import timedelta

    from sqlalchemy import and_, create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.notification import Notification, NotificationType
    from app.models.provider import Provider
    from app.models.report import Report, ReportStatus
    from app.models.service_request import ServiceRequest, ServiceRequestStatus

    CUTOFF_DAYS = 7
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=CUTOFF_DAYS)
    closed = {"reports": 0, "appointments": 0, "service_requests": 0}

    engine = create_engine(settings.DATABASE_URL_SYNC)

    def _close_notif(session, user_id, entity_label: str, ref_id: str, ref_type: str) -> None:
        session.add(Notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM,
            title="Case auto-closed — no community response",
            body=(f"{entity_label} was auto-closed after {CUTOFF_DAYS} days without community verification. "
                  "No verification credit has been awarded."),
            is_read=False,
            reference_id=ref_id,
            reference_type=ref_type,
        ))

    with Session(engine) as session:
        # Reports
        for report in session.execute(
            select(Report).where(
                and_(
                    Report.status == ReportStatus.RESOLUTION_SUBMITTED,
                    Report.resolution_submitted_at.isnot(None),
                    Report.resolution_submitted_at < cutoff,
                )
            )
        ).scalars().all():
            report.status = ReportStatus.CLOSED_UNVERIFIED
            closed["reports"] += 1
            if report.provider_id:
                prov = session.get(Provider, report.provider_id)
                if prov:
                    _close_notif(session, prov.user_id, f"Report '{report.title}'",
                                 str(report.id), "report")

        # Service requests
        for sr in session.execute(
            select(ServiceRequest).where(
                and_(
                    ServiceRequest.status == ServiceRequestStatus.RESOLUTION_SUBMITTED,
                    ServiceRequest.resolution_submitted_at.isnot(None),
                    ServiceRequest.resolution_submitted_at < cutoff,
                )
            )
        ).scalars().all():
            sr.status = ServiceRequestStatus.CLOSED_UNVERIFIED
            closed["service_requests"] += 1
            if sr.provider_id:
                prov = session.get(Provider, sr.provider_id)
                if prov:
                    _close_notif(session, prov.user_id,
                                 f"Service request ({sr.request_type.value})",
                                 str(sr.id), "service_request")

        # Appointments
        for appt in session.execute(
            select(Appointment).where(
                and_(
                    Appointment.status == AppointmentStatus.RESOLUTION_SUBMITTED,
                    Appointment.resolution_submitted_at.isnot(None),
                    Appointment.resolution_submitted_at < cutoff,
                )
            )
        ).scalars().all():
            appt.status = AppointmentStatus.CLOSED_UNVERIFIED
            closed["appointments"] += 1
            prov = session.get(Provider, appt.provider_id)
            if prov:
                _close_notif(session, prov.user_id,
                             f"Appointment on {appt.appointment_date}",
                             str(appt.id), "appointment")

        session.commit()

    return closed


@celery_app.task(name="app.tasks.check_sla_deadlines")
def check_sla_deadlines() -> dict:
    """Hourly task: flag overdue items and escalate through the provider staff chain."""
    from sqlalchemy import and_, create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.notification import Notification, NotificationType
    from app.models.provider import Provider, ProviderStaff, ProviderStaffRole
    from app.models.report import Report, ReportStatus
    from app.models.service_request import ServiceRequest, ServiceRequestStatus

    CLOSED_REPORT = {ReportStatus.RESOLVED, ReportStatus.CLOSED}
    CLOSED_APPT = {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.REJECTED}
    CLOSED_SR = {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED, ServiceRequestStatus.REJECTED}

    # Staff role → escalation level number
    _ROLE_TO_LEVEL = {
        ProviderStaffRole.SUPERVISOR: 2,
        ProviderStaffRole.REGIONAL_MANAGER: 3,
        ProviderStaffRole.EXECUTIVE: 4,
    }

    now = datetime.now(timezone.utc)
    stats = {"reports": 0, "appointments": 0, "service_requests": 0, "escalations": 0}

    engine = create_engine(settings.DATABASE_URL_SYNC)

    def _hours_overdue(deadline: datetime) -> float:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return max(0.0, (now - deadline).total_seconds() / 3600)

    def _notif(session: Session, user_id: uuid.UUID, title: str, body: str,
               ref_id: str, ref_type: str) -> None:
        session.add(Notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM,
            title=title,
            body=body,
            is_read=False,
            reference_id=ref_id,
            reference_type=ref_type,
        ))

    def _escalate(session: Session, provider: Provider, current_level: int,
                  hours_over: float, title: str, body: str,
                  ref_id: str, ref_type: str,
                  report_context: dict | None = None) -> int:
        """Send escalation notifications and emails to Officer/Supervisor contacts.
        Returns the highest level notified."""
        highest = current_level
        for level, threshold in _ESCALATION_HOURS.items():
            if level <= current_level:
                continue
            if hours_over < threshold:
                continue

            if level == 1 and provider.officer_email:
                _notif(session, provider.user_id, title, body, ref_id, ref_type)
                if report_context:
                    send_email_background(
                        to=provider.officer_email,
                        subject=f"Overdue Report Alert — {report_context.get('reference', ref_id)}",
                        template="sla_escalation",
                        context={**report_context, "level": 1,
                                 "recipient_name": provider.officer_name or "Officer"},
                    )
                highest = 1
                stats["escalations"] += 1

            elif level == 2 and provider.supervisor_email:
                _notif(session, provider.user_id, title,
                       f"ESCALATED TO SUPERVISOR: {body}", ref_id, ref_type)
                if report_context:
                    send_email_background(
                        to=provider.supervisor_email,
                        subject=f"ESCALATION Level 2 — {report_context.get('reference', ref_id)}",
                        template="sla_escalation",
                        context={**report_context, "level": 2,
                                 "recipient_name": provider.supervisor_name or "Supervisor",
                                 "officer_name": provider.officer_name or "Officer",
                                 "officer_notified_ago": f"{int(hours_over)}h"},
                    )
                highest = 2
                stats["escalations"] += 1

        return highest

    with Session(engine) as session:
        # ── Reports ────────────────────────────────────────────────────────
        overdue_reports = session.execute(
            select(Report).where(
                and_(
                    Report.sla_deadline.isnot(None),
                    Report.sla_deadline < now,
                    Report.status.notin_(CLOSED_REPORT),
                )
            )
        ).scalars().all()

        for report in overdue_reports:
            hours_over = _hours_overdue(report.sla_deadline)
            if not report.overdue_flagged:
                report.overdue_flagged = True
                stats["reports"] += 1

            prov = session.get(Provider, report.provider_id) if report.provider_id else None
            if not prov:
                continue

            # Build context for escalation email template
            from app.models.user import User
            reporter = session.get(User, report.user_id) if report.user_id else None
            loc_parts = [p for p in [report.sector, report.district, report.province] if p]
            rpt_ctx = {
                "reference": report.reference_number or str(report.id)[:8],
                "category": report.category.value.replace("_", " ").title(),
                "urgency": report.urgency.value.title(),
                "location": ", ".join(loc_parts) if loc_parts else "Not specified",
                "submitted_at": report.created_at.strftime("%Y-%m-%d %H:%M") if report.created_at else "Unknown",
                "overdue_hours": str(int(hours_over)),
                "community_name": reporter.full_name if reporter else "Community Member",
                "community_phone": reporter.phone or "N/A" if reporter else "N/A",
            }
            new_level = _escalate(
                session, prov, report.escalation_level, hours_over,
                title=f"SLA overdue — Report: {report.title}",
                body=(f"Report '{report.title}' has been overdue for "
                      f"{int(hours_over)}h. Immediate action required."),
                ref_id=str(report.id), ref_type="report",
                report_context=rpt_ctx,
            )
            report.escalation_level = new_level

        # ── Appointments ───────────────────────────────────────────────────
        overdue_appts = session.execute(
            select(Appointment).where(
                and_(
                    Appointment.sla_deadline.isnot(None),
                    Appointment.sla_deadline < now,
                    Appointment.status.notin_(CLOSED_APPT),
                )
            )
        ).scalars().all()

        for appt in overdue_appts:
            hours_over = _hours_overdue(appt.sla_deadline)
            if not appt.overdue_flagged:
                appt.overdue_flagged = True
                stats["appointments"] += 1

            prov = session.get(Provider, appt.provider_id)
            if not prov:
                continue

            new_level = _escalate(
                session, prov, appt.escalation_level, hours_over,
                title=f"SLA overdue — Appointment on {appt.appointment_date}",
                body=(f"Appointment for {appt.appointment_date} at {appt.appointment_time} "
                      f"has been overdue for {int(hours_over)}h."),
                ref_id=str(appt.id), ref_type="appointment",
            )
            appt.escalation_level = new_level

        # ── Service Requests ───────────────────────────────────────────────
        overdue_srs = session.execute(
            select(ServiceRequest).where(
                and_(
                    ServiceRequest.sla_deadline.isnot(None),
                    ServiceRequest.sla_deadline < now,
                    ServiceRequest.status.notin_(CLOSED_SR),
                )
            )
        ).scalars().all()

        for sr in overdue_srs:
            hours_over = _hours_overdue(sr.sla_deadline)
            if not sr.overdue_flagged:
                sr.overdue_flagged = True
                stats["service_requests"] += 1

            prov = session.get(Provider, sr.provider_id) if sr.provider_id else None
            if not prov:
                continue

            new_level = _escalate(
                session, prov, sr.escalation_level, hours_over,
                title=f"SLA overdue — {sr.request_type.value.replace('_', ' ').title()}",
                body=(f"Service request ({sr.request_type.value}) has been overdue "
                      f"for {int(hours_over)}h."),
                ref_id=str(sr.id), ref_type="service_request",
            )
            sr.escalation_level = new_level

        session.commit()

    return stats


@celery_app.task(name="app.tasks.send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """Every 5 minutes: send 30-minute pre-appointment reminders via email and in-app.

    Finds APPROVED appointments whose scheduled time is 25–35 minutes from now
    and have not yet received a reminder (reminder_sent=False).
    """
    from sqlalchemy import and_, create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.appointment import Appointment, AppointmentStatus, MeetingType
    from app.models.notification import Notification, NotificationType
    from app.models.user import User

    now = datetime.now(timezone.utc)
    # Africa/Kigali = UTC+2; window: appointment is 25–35 min from now
    window_start = now + timedelta(minutes=25)
    window_end = now + timedelta(minutes=35)
    sent = 0

    engine = create_engine(settings.DATABASE_URL_SYNC)

    with Session(engine) as session:
        appts = session.execute(
            select(Appointment).where(
                and_(
                    Appointment.status == AppointmentStatus.APPROVED,
                    Appointment.reminder_sent == False,  # noqa: E712
                )
            )
        ).scalars().all()

        for appt in appts:
            # Reconstruct appointment datetime in UTC (Kigali = UTC+2)
            try:
                h, m = map(int, appt.appointment_time.split(":"))
                appt_dt_naive = datetime(
                    appt.appointment_date.year,
                    appt.appointment_date.month,
                    appt.appointment_date.day,
                    h, m,
                )
                kigali_tz = timezone(timedelta(hours=2))
                appt_dt_utc = appt_dt_naive.replace(tzinfo=kigali_tz).astimezone(timezone.utc)
            except Exception:
                continue

            if not (window_start <= appt_dt_utc <= window_end):
                continue

            # Mark reminder sent first to avoid duplicates on retry
            appt.reminder_sent = True

            meeting_label = {
                MeetingType.PHONE_CALL: "Phone Call",
                MeetingType.IN_PERSON: "In-Person Visit",
                MeetingType.SITE_VISIT: "Site Visit",
            }.get(appt.meeting_type, "Appointment")

            meeting_hint = {
                MeetingType.PHONE_CALL: "Please be near your phone — the provider may call you, or view their number on your Temba dashboard.",
                MeetingType.IN_PERSON: "Please proceed to the provider's office. Have your appointment reference ready.",
                MeetingType.SITE_VISIT: "Please be at your location — a technician will arrive shortly.",
            }.get(appt.meeting_type, "Please be ready for your appointment.")

            # In-app notification to community member
            community_user = session.get(User, appt.user_id)
            if community_user:
                session.add(Notification(
                    user_id=appt.user_id,
                    notification_type=NotificationType.APPOINTMENT_UPDATE,
                    title=f"Reminder: {meeting_label} in 30 minutes",
                    body=(
                        f"Your {meeting_label} with {appt.provider.organization_name if appt.provider else 'the provider'} "
                        f"is at {appt.appointment_time} today. {meeting_hint}"
                    ),
                    is_read=False,
                    reference_id=str(appt.id),
                    reference_type="appointment",
                ))

                # Email reminder
                if (
                    community_user.email_notifications
                    and community_user.email
                    and not community_user.email.endswith("@ussd.temba.rw")
                ):
                    send_email_background(
                        to=community_user.email,
                        subject=f"Temba — {meeting_label} reminder: {appt.appointment_time} today",
                        template="appointment_reminder",
                        context={
                            "name": (community_user.full_name or "").split()[0] or "there",
                            "meeting_type": meeting_label,
                            "appointment_date": str(appt.appointment_date),
                            "appointment_time": appt.appointment_time,
                            "provider_name": appt.provider.organization_name if appt.provider else "your provider",
                            "meeting_hint": meeting_hint,
                            "ref": str(appt.id)[:8].upper(),
                        },
                    )

            # In-app notification to provider org
            if appt.provider and appt.provider.user_id:
                session.add(Notification(
                    user_id=appt.provider.user_id,
                    notification_type=NotificationType.APPOINTMENT_UPDATE,
                    title=f"Upcoming {meeting_label} in 30 minutes",
                    body=(
                        f"{meeting_label} with {community_user.full_name if community_user else 'a community member'} "
                        f"is scheduled at {appt.appointment_time}. "
                        f"Community phone: {community_user.phone or 'N/A' if community_user else 'N/A'}"
                    ),
                    is_read=False,
                    reference_id=str(appt.id),
                    reference_type="appointment",
                ))

            sent += 1

        session.commit()

    return {"reminders_sent": sent}


@celery_app.task(name="app.tasks.auto_complete_confirmed_appointments")
def auto_complete_confirmed_appointments() -> dict:
    """Hourly: auto-advance to RESOLUTION_SUBMITTED when one party confirmed
    the appointment and the 24-hour auto-complete window has passed without dispute."""
    from sqlalchemy import and_, create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.notification import Notification, NotificationType

    now = datetime.now(timezone.utc)
    completed = 0

    engine = create_engine(settings.DATABASE_URL_SYNC)

    with Session(engine) as session:
        appts = session.execute(
            select(Appointment).where(
                and_(
                    Appointment.status == AppointmentStatus.APPROVED,
                    Appointment.auto_complete_at.isnot(None),
                    Appointment.auto_complete_at <= now,
                    Appointment.conflict_flagged == False,  # noqa: E712
                )
            )
        ).scalars().all()

        for appt in appts:
            # Only auto-complete if at least one party confirmed
            if appt.community_confirmed is True or appt.provider_confirmed is True:
                appt.status = AppointmentStatus.RESOLUTION_SUBMITTED
                appt.resolution_submitted_at = now
                appt.auto_complete_at = None

                # Notify community member to verify
                if appt.user_id:
                    session.add(Notification(
                        user_id=appt.user_id,
                        notification_type=NotificationType.APPOINTMENT_UPDATE,
                        title="Appointment auto-completed",
                        body=(
                            f"Your appointment on {appt.appointment_date} has been automatically marked as completed "
                            "after the 24-hour confirmation window. Please verify the outcome on your dashboard."
                        ),
                        is_read=False,
                        reference_id=str(appt.id),
                        reference_type="appointment",
                    ))

                completed += 1

        session.commit()

    return {"auto_completed": completed}
