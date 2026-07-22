"""
Appointment endpoints.
POST   /appointments                         → book (community)
GET    /appointments                         → list (own / provider's / all)
GET    /appointments/{id}
GET    /appointments/{id}/contact            → reveal phone numbers during meeting window
POST   /appointments/{id}/cancel            → cancel with required reason (community or provider)
POST   /appointments/{id}/reschedule-request → user asks for new slot
POST   /appointments/{id}/provider-reschedule → provider proposes new slot
POST   /appointments/{id}/accept-reschedule  → user accepts provider's proposal
POST   /appointments/{id}/reject-reschedule  → user rejects provider's proposal
PUT    /appointments/{id}/status             → approve/reject/complete/cancel (provider)
POST   /appointments/{id}/confirm            → both parties confirm meeting took place
POST   /appointments/{id}/outcome            → record post-meeting outcome
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_provider, write_audit
from app.core.provider_utils import get_provider_for_user
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.provider import Provider
from app.models.user import User, UserRole
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentConfirmBody,
    AppointmentCreate,
    AppointmentOutcomeBody,
    AppointmentPublic,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdate,
    ProviderRescheduleProposal,
)
from app.schemas.common import PaginatedResponse, PaginationParams
from app.core.sla import resolution_deadline_for, sla_deadline_for
from app.schemas.report import VerificationVerdict
from app.services.notification_service import notify_community_user, notify_org, notify_user

_PROVIDER_APPT_STATUSES = {
    AppointmentStatus.APPROVED,
    AppointmentStatus.REJECTED,
    AppointmentStatus.CANCELLED,
    AppointmentStatus.RESOLUTION_SUBMITTED,
}

# How wide (minutes) the contact-reveal window is around the appointment time
_CONTACT_WINDOW_BEFORE_MIN = 30
_CONTACT_WINDOW_AFTER_MIN = 120

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _with_relations(q):
    return q.options(selectinload(Appointment.user), selectinload(Appointment.provider))


async def _get_appointment_or_404(appt_id: UUID, db: AsyncSession) -> Appointment:
    result = await db.execute(_with_relations(select(Appointment).where(Appointment.id == appt_id)))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


async def _get_provider_for_user(user: User, db: AsyncSession) -> Provider | None:
    return await get_provider_for_user(user, db)


def _is_same_org(appt: Appointment, prov: Provider) -> bool:
    if appt.provider_id == prov.id:
        return True
    appt_org = (appt.provider.organization_name or "").lower() if appt.provider else ""
    return appt_org == (prov.organization_name or "").lower()


def _appt_datetime_utc(appt: Appointment) -> datetime:
    """Return appointment date+time as an aware UTC datetime (Africa/Kigali = UTC+2)."""
    h, m = map(int, appt.appointment_time.split(":"))
    dt_naive = datetime(
        appt.appointment_date.year,
        appt.appointment_date.month,
        appt.appointment_date.day,
        h, m,
    )
    kigali_offset = timedelta(hours=2)
    return dt_naive.replace(tzinfo=timezone(kigali_offset)).astimezone(timezone.utc)


def _in_contact_window(appt: Appointment) -> bool:
    now = datetime.now(timezone.utc)
    appt_dt = _appt_datetime_utc(appt)
    return (appt_dt - timedelta(minutes=_CONTACT_WINDOW_BEFORE_MIN)) <= now <= (appt_dt + timedelta(minutes=_CONTACT_WINDOW_AFTER_MIN))


@router.post("", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: AppointmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    prov_result = await db.execute(select(Provider).where(Provider.id == body.provider_id))
    provider = prov_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    appt = Appointment(user_id=current_user.id, **body.model_dump())
    db.add(appt)
    await db.flush()
    appt.sla_deadline = sla_deadline_for(body.reason.value, appt.created_at, "appointment")
    appt.resolution_deadline = resolution_deadline_for(appt.created_at, item_type="appointment")
    await write_audit(db, request, "appointment.create", "appointment", str(appt.id), actor=current_user)

    meeting_label = {"in_person": "In-Person", "phone_call": "Phone Call", "site_visit": "Site Visit"}.get(body.meeting_type.value, body.meeting_type.value)

    await notify_org(
        db,
        provider=provider,
        notification_type="appointment_update",
        title="New appointment request",
        body=f"New {meeting_label} appointment request for {body.appointment_date} at {body.appointment_time}",
        reference_id=str(appt.id),
        reference_type="appointment",
    )
    await notify_community_user(
        db, background_tasks,
        user=current_user,
        notification_type="appointment_update",
        title="Appointment request submitted",
        body_text=(
            f"Your {meeting_label} appointment with {provider.organization_name} on "
            f"{body.appointment_date} at {body.appointment_time} has been submitted and is pending approval."
        ),
        email_subject=f"Temba — Appointment request with {provider.organization_name}",
        sms_message=f"Temba: Your appointment with {provider.organization_name} on {body.appointment_date} at {body.appointment_time} is pending. Track on your dashboard.",
        reference_id=str(appt.id),
        reference_type="appointment",
        email_context={
            "ref": str(appt.id)[:8].upper(),
            "meeting_type": meeting_label,
            "appointment_date": str(body.appointment_date),
            "appointment_time": body.appointment_time,
            "provider_name": provider.organization_name,
        },
    )
    return appt


@router.get("", response_model=PaginatedResponse[AppointmentPublic])
async def list_appointments(
    params: Annotated[PaginationParams, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: AppointmentStatus | None = None,
    tracking_code: str | None = None,
) -> dict:
    q = select(Appointment)
    if current_user.role == UserRole.COMMUNITY:
        q = q.where(Appointment.user_id == current_user.id)
    elif current_user.role == UserRole.PROVIDER:
        prov = await _get_provider_for_user(current_user, db)
        if prov:
            same_org_provs = (await db.execute(
                select(Provider.id).where(
                    func.lower(Provider.organization_name) == func.lower(prov.organization_name)
                )
            )).scalars().all()
            q = q.where(Appointment.provider_id.in_(same_org_provs))
        else:
            q = q.where(False)

    if status_filter:
        q = q.where(Appointment.status == status_filter)

    if tracking_code:
        code = tracking_code.strip().upper()
        q = q.where(func.upper(cast(Appointment.id, String)).like(f"{code}%"))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(_with_relations(q).order_by(Appointment.created_at.desc()).offset(params.offset).limit(params.size))
    return {
        "items": result.scalars().all(),
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": -(-total // params.size),
    }


@router.get("/by-code/{tracking_code}", response_model=AppointmentPublic)
async def get_appointment_by_tracking_code(
    tracking_code: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    code = tracking_code.strip().upper()
    q = _with_relations(
        select(Appointment).where(func.upper(cast(Appointment.id, String)).like(f"{code}%"))
    )
    appt = (await db.execute(q)).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if current_user.role == UserRole.COMMUNITY and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return appt


@router.get("/{appt_id}", response_model=AppointmentPublic)
async def get_appointment(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if current_user.role == UserRole.COMMUNITY and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return appt


@router.get("/{appt_id}/contact")
async def get_contact_info(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the other party's phone number — only available during the meeting window
    (30 min before → 2 hours after the scheduled appointment time)."""
    appt = await _get_appointment_or_404(appt_id, db)

    # Access control
    is_community = current_user.role == UserRole.COMMUNITY
    if is_community and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not is_community:
        prov = await _get_provider_for_user(current_user, db)
        if not prov or not _is_same_org(appt, prov):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if appt.status not in {AppointmentStatus.APPROVED, AppointmentStatus.RESCHEDULED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact information is only available for approved appointments.",
        )

    if not _in_contact_window(appt):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Contact information is only revealed {_CONTACT_WINDOW_BEFORE_MIN} minutes before "
                f"and {_CONTACT_WINDOW_AFTER_MIN} minutes after the scheduled appointment time."
            ),
        )

    # Load provider's user to get their phone number
    prov_user: User | None = None
    if appt.provider and appt.provider.user_id:
        prov_user = (await db.execute(select(User).where(User.id == appt.provider.user_id))).scalar_one_or_none()

    community_phone = appt.user.phone if appt.user else None
    provider_phone = prov_user.phone if prov_user else None

    return {
        "community_phone": community_phone,
        "provider_phone": provider_phone,
        "meeting_type": appt.meeting_type.value,
        "appointment_date": str(appt.appointment_date),
        "appointment_time": appt.appointment_time,
    }


@router.post("/{appt_id}/cancel", response_model=AppointmentPublic)
async def cancel_appointment(
    appt_id: UUID,
    body: AppointmentCancel,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Cancel with a required reason. Both community members and providers may cancel."""
    appt = await _get_appointment_or_404(appt_id, db)

    is_community = current_user.role == UserRole.COMMUNITY
    is_provider = current_user.role == UserRole.PROVIDER

    if is_community and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if is_provider:
        prov = await _get_provider_for_user(current_user, db)
        if not prov or not _is_same_org(appt, prov):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if appt.status not in {
        AppointmentStatus.PENDING,
        AppointmentStatus.APPROVED,
        AppointmentStatus.RESCHEDULE_REQUESTED,
        AppointmentStatus.RESCHEDULED,
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel at this stage")

    appt.status = AppointmentStatus.CANCELLED
    appt.cancellation_reason = body.reason

    cancelled_by = "community" if is_community else "provider"

    if is_community:
        # Notify provider org
        prov = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one_or_none()
        if prov:
            await notify_org(
                db,
                provider=prov,
                notification_type="appointment_update",
                title="Appointment cancelled",
                body=f"A community member cancelled their appointment on {appt.appointment_date}. Reason: {body.reason}",
                reference_id=str(appt_id),
                reference_type="appointment",
            )
    else:
        # Notify community member
        appt_owner = (await db.execute(select(User).where(User.id == appt.user_id))).scalar_one_or_none()
        if appt_owner:
            await notify_community_user(
                db, background_tasks,
                user=appt_owner,
                notification_type="appointment_update",
                title="Appointment cancelled by provider",
                body_text=(
                    f"Your appointment on {appt.appointment_date} at {appt.appointment_time} was cancelled by the provider. "
                    f"Reason: {body.reason}"
                ),
                email_subject="Temba — Your appointment has been cancelled",
                sms_message=f"Temba: Your appointment on {appt.appointment_date} was cancelled by the provider. {body.reason[:80]}",
                reference_id=str(appt_id),
                reference_type="appointment",
            )

    await write_audit(db, request, f"appointment.cancel.{cancelled_by}", "appointment", str(appt_id), actor=current_user)
    return appt


# Keep DELETE for backward compatibility with existing frontend code
@router.delete("/{appt_id}", response_model=AppointmentPublic)
async def cancel_appointment_legacy(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Legacy cancel endpoint — no reason required. Use POST /cancel instead."""
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appt.status not in {AppointmentStatus.PENDING, AppointmentStatus.APPROVED, AppointmentStatus.RESCHEDULE_REQUESTED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel at this stage")

    appt.status = AppointmentStatus.CANCELLED
    prov = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one_or_none()
    if prov:
        await notify_org(
            db,
            provider=prov,
            notification_type="appointment_update",
            title="Appointment cancelled",
            body=f"A community member cancelled their appointment scheduled for {appt.appointment_date}",
            reference_id=str(appt_id),
            reference_type="appointment",
        )
    await write_audit(db, request, "appointment.cancel", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/reschedule-request", response_model=AppointmentPublic)
async def request_reschedule(
    appt_id: UUID,
    body: AppointmentRescheduleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appt.status not in {AppointmentStatus.PENDING, AppointmentStatus.APPROVED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reschedule at this stage")

    appt.status = AppointmentStatus.RESCHEDULE_REQUESTED
    appt.requested_date = body.requested_date
    appt.requested_time = body.requested_time
    appt.reschedule_reason = body.reschedule_reason

    prov = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one()
    await notify_org(
        db,
        provider=prov,
        notification_type="appointment_update",
        title="Reschedule request",
        body=f"A user has requested to reschedule appointment to {body.requested_date} {body.requested_time}",
        reference_id=str(appt_id),
        reference_type="appointment",
    )
    await write_audit(db, request, "appointment.reschedule_request", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/provider-reschedule", response_model=AppointmentPublic)
async def provider_propose_reschedule(
    appt_id: UUID,
    body: ProviderRescheduleProposal,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    prov = await _get_provider_for_user(current_user, db)
    if not prov:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not _is_same_org(appt, prov):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    appt.status = AppointmentStatus.RESCHEDULED
    appt.proposed_date = body.proposed_date
    appt.proposed_time = body.proposed_time
    appt.proposed_message = body.proposed_message

    reschedule_owner = (await db.execute(select(User).where(User.id == appt.user_id))).scalar_one_or_none()
    if reschedule_owner:
        await notify_community_user(
            db, background_tasks,
            user=reschedule_owner,
            notification_type="appointment_update",
            title="Provider proposed a new appointment time",
            body_text=f"Your appointment has been proposed to be rescheduled to {body.proposed_date} at {body.proposed_time}. Please accept or reject on your dashboard.",
            email_subject="Temba — Provider proposed a new appointment time",
            sms_message=f"Temba: Your appointment has been rescheduled to {body.proposed_date} at {body.proposed_time}. Accept or reject on your dashboard.",
            reference_id=str(appt_id),
            reference_type="appointment",
            email_context={"ref": str(appt_id)[:8].upper()},
        )
    await write_audit(db, request, "appointment.provider_reschedule", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/accept-reschedule", response_model=AppointmentPublic)
async def accept_reschedule(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appt.status != AppointmentStatus.RESCHEDULED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending reschedule proposal")

    appt.appointment_date = appt.proposed_date
    appt.appointment_time = appt.proposed_time
    appt.proposed_date = None
    appt.proposed_time = None
    appt.proposed_message = None
    appt.status = AppointmentStatus.APPROVED
    return appt


@router.post("/{appt_id}/reject-reschedule", response_model=AppointmentPublic)
async def reject_reschedule(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appt.status != AppointmentStatus.RESCHEDULED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending reschedule proposal")

    appt.status = AppointmentStatus.CANCELLED
    appt.proposed_date = None
    appt.proposed_time = None
    return appt


@router.put("/{appt_id}/status", response_model=AppointmentPublic)
async def update_appointment_status(
    appt_id: UUID,
    body: AppointmentStatusUpdate,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    prov = await _get_provider_for_user(current_user, db)
    if not prov:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not _is_same_org(appt, prov):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.status not in _PROVIDER_APPT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Providers may only set status to: {', '.join(s.value for s in _PROVIDER_APPT_STATUSES)}. "
                   "Submit a resolution and let the community verify to close the appointment.",
        )

    now = datetime.now(timezone.utc)
    if body.status == AppointmentStatus.RESOLUTION_SUBMITTED:
        appt.resolution_submitted_at = now

    appt.status = body.status
    if body.provider_note:
        appt.provider_note = body.provider_note

    notif_title = "Appointment updated"
    notif_body = f"Your appointment status has been updated to: {body.status.value.replace('_', ' ').title()}."
    if body.status == AppointmentStatus.APPROVED:
        notif_title = "Appointment approved"
        notif_body = "Your appointment has been approved by the provider. Please prepare for the scheduled time."
    elif body.status == AppointmentStatus.REJECTED:
        notif_title = "Appointment not approved"
        notif_body = "The provider could not accommodate your appointment at this time. Please book again or contact them directly."
    elif body.status == AppointmentStatus.RESOLUTION_SUBMITTED:
        notif_title = "Appointment marked as completed"
        notif_body = "The provider has marked your appointment as completed. Please confirm on your dashboard whether the service was delivered."

    appt_owner = (await db.execute(select(User).where(User.id == appt.user_id))).scalar_one_or_none()
    if appt_owner:
        await notify_community_user(
            db, background_tasks,
            user=appt_owner,
            notification_type="appointment_update",
            title=notif_title,
            body_text=notif_body,
            email_subject=f"Temba — {notif_title}",
            sms_message=f"Temba: {notif_title}. {notif_body[:100]} Check your dashboard.",
            reference_id=str(appt_id),
            reference_type="appointment",
            email_context={"ref": str(appt_id)[:8].upper()},
        )
    await write_audit(db, request, f"appointment.{body.status.value}", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/confirm", response_model=AppointmentPublic)
async def confirm_appointment(
    appt_id: UUID,
    body: AppointmentConfirmBody,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Both parties independently confirm whether the appointment took place.

    - Community calls this after the scheduled time to confirm the meeting happened.
    - Provider calls this to confirm from their side.
    - If both confirm True → auto-advance to RESOLUTION_SUBMITTED.
    - If one confirms True and the other hasn't responded → set 24h auto-complete window.
    - If responses conflict (one True, one False) → flag for follow-up.
    """
    appt = await _get_appointment_or_404(appt_id, db)

    is_community = current_user.role == UserRole.COMMUNITY
    is_provider = current_user.role == UserRole.PROVIDER

    if is_community and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if is_provider:
        prov = await _get_provider_for_user(current_user, db)
        if not prov or not _is_same_org(appt, prov):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Only valid when the appointment is approved (meeting time should have passed)
    if appt.status not in {AppointmentStatus.APPROVED, AppointmentStatus.RESCHEDULED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation is only available for approved appointments after the scheduled time.",
        )

    now = datetime.now(timezone.utc)

    if is_community:
        appt.community_confirmed = body.confirmed
    else:
        appt.provider_confirmed = body.confirmed

    community_conf = appt.community_confirmed
    provider_conf = appt.provider_confirmed

    # Determine new state based on both parties' responses
    if community_conf is True and provider_conf is True:
        # Both confirmed → meeting happened → auto-advance to resolution submitted
        appt.status = AppointmentStatus.RESOLUTION_SUBMITTED
        appt.resolution_submitted_at = now
        appt.conflict_flagged = False
        appt.auto_complete_at = None
        state = "both_confirmed"
    elif community_conf is True and provider_conf is False:
        appt.conflict_flagged = True
        appt.auto_complete_at = None
        state = "conflict"
    elif community_conf is False and provider_conf is True:
        appt.conflict_flagged = True
        appt.auto_complete_at = None
        state = "conflict"
    elif community_conf is True and provider_conf is None:
        # Community confirmed, waiting for provider (or vice versa)
        appt.auto_complete_at = now + timedelta(hours=24)
        state = "community_confirmed_waiting"
    elif community_conf is None and provider_conf is True:
        appt.auto_complete_at = now + timedelta(hours=24)
        state = "provider_confirmed_waiting"
    else:
        # Neither or one/both said no
        state = "pending_or_denied"

    # Notify the other party
    if is_community:
        prov_obj = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one_or_none()
        if prov_obj:
            notif_title = "Community confirmed the appointment" if body.confirmed else "Community denied the appointment"
            notif_body = (
                f"The community member confirmed the appointment on {appt.appointment_date} took place."
                if body.confirmed else
                f"The community member reported the appointment on {appt.appointment_date} did not take place."
            )
            if state == "both_confirmed":
                notif_body += " The case has been moved to resolution for verification."
            elif state == "conflict":
                notif_body += " Responses conflict — this appointment has been flagged for follow-up."
            await notify_org(
                db, provider=prov_obj,
                notification_type="appointment_update",
                title=notif_title,
                body=notif_body,
                reference_id=str(appt_id),
                reference_type="appointment",
            )
    else:
        appt_owner = (await db.execute(select(User).where(User.id == appt.user_id))).scalar_one_or_none()
        if appt_owner:
            notif_title = "Provider confirmed the appointment" if body.confirmed else "Provider denied the appointment"
            notif_body = (
                f"The provider confirmed your appointment on {appt.appointment_date} took place."
                if body.confirmed else
                f"The provider reported your appointment on {appt.appointment_date} did not take place."
            )
            if state == "both_confirmed":
                notif_body += " The case has been moved to resolution for your verification."
            elif state == "conflict":
                notif_body += " Responses conflict — this appointment has been flagged for review."
            await notify_community_user(
                db, background_tasks,
                user=appt_owner,
                notification_type="appointment_update",
                title=notif_title,
                body_text=notif_body,
                email_subject=f"Temba — {notif_title}",
                sms_message=f"Temba: {notif_title}. Check your dashboard.",
                reference_id=str(appt_id),
                reference_type="appointment",
            )

    await write_audit(db, request, f"appointment.confirm.{state}", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/outcome", response_model=AppointmentPublic)
async def record_outcome(
    appt_id: UUID,
    body: AppointmentOutcomeBody,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Record post-meeting outcome.

    Community: Was your issue addressed? (yes / partially / no)
    Provider:  Brief notes on the discussion.
    Available after RESOLUTION_SUBMITTED or VERIFIED status.
    """
    appt = await _get_appointment_or_404(appt_id, db)

    is_community = current_user.role == UserRole.COMMUNITY
    is_provider = current_user.role == UserRole.PROVIDER

    if is_community and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if is_provider:
        prov = await _get_provider_for_user(current_user, db)
        if not prov or not _is_same_org(appt, prov):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    allowed_statuses = {
        AppointmentStatus.RESOLUTION_SUBMITTED,
        AppointmentStatus.VERIFIED,
        AppointmentStatus.CLOSED_UNVERIFIED,
    }
    if appt.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outcome can only be recorded after the appointment resolution stage.",
        )

    if is_community and body.community_outcome is not None:
        appt.community_outcome = body.community_outcome

    if is_provider and body.provider_outcome_notes is not None:
        appt.provider_outcome_notes = body.provider_outcome_notes

    await write_audit(db, request, "appointment.outcome", "appointment", str(appt_id), actor=current_user)
    return appt


@router.post("/{appt_id}/verify", response_model=AppointmentPublic)
async def verify_appointment(
    appt_id: UUID,
    body: VerificationVerdict,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the appointment owner can verify")
    if appt.status != AppointmentStatus.RESOLUTION_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This appointment has no pending resolution to verify",
        )

    now = datetime.now(timezone.utc)
    prov = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one_or_none()

    if body.verdict == "verified":
        appt.status = AppointmentStatus.VERIFIED
        appt.verified_at = now
        notif_title = "Appointment verified"
        notif_body = body.comment or "The community member confirmed the appointment was completed satisfactorily."
    elif body.verdict == "partial":
        appt.status = AppointmentStatus.APPROVED  # reopen for follow-up
        notif_title = "Appointment disputed — follow-up required"
        notif_body = body.comment or "The community member reported the appointment outcome was only partially satisfactory."
    else:
        appt.status = AppointmentStatus.APPROVED  # reopen
        notif_title = "Appointment rejected — case reopened"
        notif_body = body.comment or "The community member reported the appointment outcome was not satisfactory."

    await write_audit(db, request, f"appointment.verify.{body.verdict}", "appointment", str(appt_id), actor=current_user)

    if prov:
        await notify_org(
            db, provider=prov,
            notification_type="appointment_update",
            title=notif_title,
            body=f"Appointment on {appt.appointment_date}: {notif_body}",
            reference_id=str(appt_id), reference_type="appointment",
        )
    return appt
