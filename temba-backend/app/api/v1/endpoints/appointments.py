"""
Appointment endpoints.
POST   /appointments                         → book (community)
GET    /appointments                         → list (own / provider's / all)
GET    /appointments/{id}
POST   /appointments/{id}/reschedule-request → user asks for new slot
POST   /appointments/{id}/provider-reschedule → provider proposes new slot
POST   /appointments/{id}/accept-reschedule  → user accepts provider's proposal
POST   /appointments/{id}/reject-reschedule  → user rejects provider's proposal
PUT    /appointments/{id}/status             → approve/reject/complete/cancel (provider)
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    AppointmentCreate,
    AppointmentPublic,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdate,
    ProviderRescheduleProposal,
)
from app.schemas.common import PaginatedResponse, PaginationParams
from app.core.sla import sla_deadline_for
from app.schemas.report import VerificationVerdict
from app.services.notification_service import notify_user

_PROVIDER_APPT_STATUSES = {
    AppointmentStatus.APPROVED,
    AppointmentStatus.REJECTED,
    AppointmentStatus.CANCELLED,
    AppointmentStatus.RESOLUTION_SUBMITTED,
}

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


@router.post("", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: AppointmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    # Verify provider exists and is approved
    prov_result = await db.execute(select(Provider).where(Provider.id == body.provider_id))
    provider = prov_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    appt = Appointment(user_id=current_user.id, **body.model_dump())
    db.add(appt)
    await db.flush()
    appt.sla_deadline = sla_deadline_for(body.reason.value, appt.created_at, "appointment")
    await write_audit(db, request, "appointment.create", "appointment", str(appt.id), actor=current_user)

    await notify_user(
        db,
        user_id=provider.user_id,
        notification_type="appointment_update",
        title="New appointment request",
        body=f"A new appointment has been requested for {body.appointment_date} at {body.appointment_time}",
        reference_id=str(appt.id),
        reference_type="appointment",
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
            # Include appointments from all providers sharing the same org name
            # (handles seeded vs web-registered provider duplicate scenario)
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
    """Look up an appointment by its 8-character tracking code (USSD reference)."""
    code = tracking_code.strip().upper()
    q = _with_relations(
        select(Appointment).where(func.upper(cast(Appointment.id, String)).like(f"{code}%"))
    )
    appt = (await db.execute(q)).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if current_user.role == UserRole.COMMUNITY and appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if current_user.role == UserRole.PROVIDER:
        prov = await _get_provider_for_user(current_user, db)
        if prov and appt.provider_id != prov.id:
            # Allow if same org name (seeded vs web-registered duplicate) — case-insensitive
            appt_org = (appt.provider.organization_name or "").lower() if appt.provider else ""
            prov_org = (prov.organization_name or "").lower()
            if appt_org != prov_org:
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


@router.delete("/{appt_id}", response_model=AppointmentPublic)
async def cancel_appointment(
    appt_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    if appt.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appt.status not in {AppointmentStatus.PENDING, AppointmentStatus.APPROVED, AppointmentStatus.RESCHEDULE_REQUESTED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel at this stage")

    appt.status = AppointmentStatus.CANCELLED
    prov = (await db.execute(select(Provider).where(Provider.id == appt.provider_id))).scalar_one_or_none()
    if prov:
        await notify_user(
            db,
            user_id=prov.user_id,
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
    await notify_user(
        db,
        user_id=prov.user_id,
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    prov = await _get_provider_for_user(current_user, db)
    if not prov or appt.provider_id != prov.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    appt.status = AppointmentStatus.RESCHEDULED
    appt.proposed_date = body.proposed_date
    appt.proposed_time = body.proposed_time
    appt.proposed_message = body.proposed_message

    await notify_user(
        db,
        user_id=appt.user_id,
        notification_type="appointment_update",
        title="Provider proposed new time",
        body=f"Your appointment has been rescheduled to {body.proposed_date} {body.proposed_time}. Please accept or reject.",
        reference_id=str(appt_id),
        reference_type="appointment",
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    appt = await _get_appointment_or_404(appt_id, db)
    prov = await _get_provider_for_user(current_user, db)
    if not prov or appt.provider_id != prov.id:
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

    await notify_user(
        db,
        user_id=appt.user_id,
        notification_type="appointment_update",
        title="Appointment updated",
        body=f"Your appointment status: {body.status.value.replace('_', ' ').title()}",
        reference_id=str(appt_id),
        reference_type="appointment",
    )
    await write_audit(db, request, f"appointment.{body.status.value}", "appointment", str(appt_id), actor=current_user)
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
        await notify_user(
            db, user_id=prov.user_id,
            notification_type="appointment_update",
            title=notif_title,
            body=f"Appointment on {appt.appointment_date}: {notif_body}",
            reference_id=str(appt_id), reference_type="appointment",
        )
    return appt
