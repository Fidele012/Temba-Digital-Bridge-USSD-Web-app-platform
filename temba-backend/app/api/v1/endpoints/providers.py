"""
Provider endpoints.
POST /providers/register        → create provider profile (provider role)
GET  /providers/me              → get own profile
GET  /providers/me/stats        → performance stats for the authenticated provider
PUT  /providers/me              → update own profile
PUT  /providers/me/availability → update working hours / availability
GET  /providers               → list approved providers (public)
GET  /providers/{id}          → get provider (public)
PUT  /providers/{id}/status   → approve/suspend (admin)
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_admin, require_provider, write_audit
from app.core.provider_utils import get_provider_for_user
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.provider import Provider, ProviderServiceArea, ProviderStaff, ProviderStatus
from app.models.report import Report, ReportStatus
from app.models.service_request import ServiceRequest, ServiceRequestStatus
from app.models.rating import Rating
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams
from app.schemas.provider import (
    AvailabilityUpdate,
    ProviderCreate,
    ProviderPublic,
    ProviderStaffCreate,
    ProviderStaffPublic,
    ProviderStatusUpdate,
    ProviderUpdate,
    SlaContactsUpdate,
)
from app.services.notification_service import notify_user, send_email_background


class ProviderStats(BaseModel):
    total_reports: int
    resolved_reports: int
    resolution_rate: float
    overdue_reports: int
    total_appointments: int
    completed_appointments: int
    pending_appointments: int
    overdue_appointments: int
    total_service_requests: int
    completed_service_requests: int
    overdue_service_requests: int
    avg_rating: float | None = None
    total_ratings: int = 0

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/providers", tags=["providers"])


def _load_provider(q):
    return q.options(selectinload(Provider.service_areas))


@router.post("/register", response_model=ProviderPublic, status_code=status.HTTP_201_CREATED)
async def register_provider(
    body: ProviderCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:

    if current_user.role != UserRole.PROVIDER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only accounts registered as 'provider' may create a provider profile",
        )
    result = await db.execute(select(Provider).where(Provider.user_id == current_user.id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider profile already exists")

    provider = Provider(
        user_id=current_user.id,
        organization_name=body.organization_name,
        registration_number=body.registration_number,
        service_categories=body.service_categories,
        custom_services=body.custom_services,
        description=body.description,
        website=body.website,
        phone=body.phone,
        email=body.email,
        status=ProviderStatus.APPROVED,
        sla_response_hours=body.sla_response_hours,
        sla_resolution_hours=body.sla_resolution_hours,
        officer_name=body.officer.name,
        officer_email=body.officer.email,
        officer_phone=body.officer.phone,
        supervisor_name=body.supervisor.name,
        supervisor_email=body.supervisor.email,
        supervisor_phone=body.supervisor.phone,
    )
    db.add(provider)
    await db.flush()

    for area in body.service_areas:
        db.add(ProviderServiceArea(provider_id=provider.id, **area.model_dump()))

    await write_audit(db, request, "provider.register", "provider", str(provider.id), actor=current_user)
    await db.refresh(provider, ["service_areas"])

    background_tasks.add_task(
        send_email_background,
        to="tembadigitalbridge@gmail.com",
        subject=f"New Provider Registration — {body.organization_name} (Review Required)",
        template="provider_verification",
        context={
            "org_name": body.organization_name,
            "reg_number": body.registration_number or "Not provided",
            "description": body.description,
            "website": body.website or "Not provided",
            "phone": body.phone or "Not provided",
            "email": body.email or current_user.email,
            "sla_response": f"{body.sla_response_hours} hours",
            "sla_resolution": f"{body.sla_resolution_hours} hours",
            "officer_name": body.officer.name,
            "officer_email": body.officer.email,
            "officer_phone": body.officer.phone,
            "supervisor_name": body.supervisor.name,
            "supervisor_email": body.supervisor.email,
            "supervisor_phone": body.supervisor.phone,
            "service_areas": ", ".join(
                f"{a.province}{' / ' + a.district if a.district else ''}"
                for a in body.service_areas
            ) or "Not specified",
            "categories": ", ".join(body.service_categories),
            "registered_by": current_user.full_name,
            "registered_email": current_user.email,
        },
    )
    log.info("provider_registered_approved", provider_id=str(provider.id), org=body.organization_name)

    return provider


@router.get("/me", response_model=ProviderPublic)
async def get_my_provider(
    current_user: Annotated[User, Depends(require_provider)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")
    await db.refresh(provider, ["service_areas"])
    return provider


@router.get("/me/stats", response_model=ProviderStats)
async def get_my_stats(
    current_user: Annotated[User, Depends(require_provider)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")

    pid = provider.id
    _RESOLVED_REPORT = {ReportStatus.RESOLVED, ReportStatus.CLOSED, ReportStatus.VERIFIED, ReportStatus.CLOSED_UNVERIFIED}
    _PENDING_APPT = {AppointmentStatus.PENDING, AppointmentStatus.APPROVED}

    total_reports = (await db.execute(select(func.count()).where(Report.provider_id == pid))).scalar_one()
    resolved_reports = (await db.execute(
        select(func.count()).where(Report.provider_id == pid, Report.status.in_(_RESOLVED_REPORT))
    )).scalar_one()
    overdue_reports = (await db.execute(
        select(func.count()).where(Report.provider_id == pid, Report.overdue_flagged == True)  # noqa: E712
    )).scalar_one()

    total_appointments = (await db.execute(select(func.count()).where(Appointment.provider_id == pid))).scalar_one()
    completed_appointments = (await db.execute(
        select(func.count()).where(Appointment.provider_id == pid, Appointment.status == AppointmentStatus.COMPLETED)
    )).scalar_one()
    pending_appointments = (await db.execute(
        select(func.count()).where(Appointment.provider_id == pid, Appointment.status.in_(_PENDING_APPT))
    )).scalar_one()
    overdue_appointments = (await db.execute(
        select(func.count()).where(Appointment.provider_id == pid, Appointment.overdue_flagged == True)  # noqa: E712
    )).scalar_one()

    total_srs = (await db.execute(select(func.count()).where(ServiceRequest.provider_id == pid))).scalar_one()
    completed_srs = (await db.execute(
        select(func.count()).where(ServiceRequest.provider_id == pid, ServiceRequest.status == ServiceRequestStatus.COMPLETED)
    )).scalar_one()
    overdue_srs = (await db.execute(
        select(func.count()).where(ServiceRequest.provider_id == pid, ServiceRequest.overdue_flagged == True)  # noqa: E712
    )).scalar_one()

    resolution_rate = round(resolved_reports / total_reports * 100, 1) if total_reports else 0.0

    rating_row = (await db.execute(
        select(func.avg(Rating.score).label("avg"), func.count(Rating.id).label("cnt"))
        .where(Rating.provider_id == pid)
    )).one()

    return {
        "total_reports": total_reports,
        "resolved_reports": resolved_reports,
        "resolution_rate": resolution_rate,
        "overdue_reports": overdue_reports,
        "total_appointments": total_appointments,
        "completed_appointments": completed_appointments,
        "pending_appointments": pending_appointments,
        "overdue_appointments": overdue_appointments,
        "total_service_requests": total_srs,
        "completed_service_requests": completed_srs,
        "overdue_service_requests": overdue_srs,
        "avg_rating": round(float(rating_row.avg), 1) if rating_row.avg else None,
        "total_ratings": rating_row.cnt or 0,
    }


@router.put("/me", response_model=ProviderPublic)
async def update_my_provider(
    body: ProviderUpdate,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(provider, field, value)

    await write_audit(db, request, "provider.update", "provider", str(provider.id), actor=current_user)
    await db.refresh(provider, ["service_areas"])
    return provider


@router.put("/me/availability", response_model=ProviderPublic)
async def update_availability(
    body: AvailabilityUpdate,
    current_user: Annotated[User, Depends(require_provider)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(provider, field, value)
    await db.refresh(provider, ["service_areas"])
    return provider


# ── SLA escalation contacts ─────────────────────────────────────────────────

@router.put("/me/sla-contacts", response_model=ProviderPublic)
async def update_sla_contacts(
    body: SlaContactsUpdate,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(provider, field, value)

    await write_audit(db, request, "provider.sla_contacts.update", "provider", str(provider.id), actor=current_user)
    await db.refresh(provider, ["service_areas"])
    return provider


# ── Staff management ────────────────────────────────────────────────────────

@router.get("/me/staff", response_model=list[ProviderStaffPublic])
async def list_staff(
    current_user: Annotated[User, Depends(require_provider)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    provider = await get_provider_for_user(current_user, db)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")

    rows = (await db.execute(
        select(ProviderStaff).where(ProviderStaff.provider_id == provider.id)
        .options(selectinload(ProviderStaff.user))
        .order_by(ProviderStaff.created_at)
    )).scalars().all()

    return [
        {
            "id": r.id,
            "provider_id": r.provider_id,
            "user_id": r.user_id,
            "staff_role": r.staff_role,
            "created_at": r.created_at,
            "staff_name": r.user.full_name if r.user else None,
            "staff_email": r.user.email if r.user else None,
        }
        for r in rows
    ]


@router.post("/me/staff", response_model=ProviderStaffPublic, status_code=status.HTTP_201_CREATED)
async def add_staff(
    body: ProviderStaffCreate,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Only the primary account holder may manage staff
    primary = (await db.execute(select(Provider).where(Provider.user_id == current_user.id))).scalar_one_or_none()
    if not primary:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the primary account holder can manage staff")

    target = (await db.execute(
        select(User).where(User.email == body.email)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Temba account found with that email")
    if target.role != UserRole.PROVIDER:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Staff members must have a provider-role Temba account")
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot add yourself as a staff member")

    existing = (await db.execute(
        select(ProviderStaff).where(ProviderStaff.provider_id == primary.id, ProviderStaff.user_id == target.id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user is already a staff member")

    staff = ProviderStaff(provider_id=primary.id, user_id=target.id, staff_role=body.staff_role)
    db.add(staff)
    await db.flush()
    await write_audit(db, request, "provider.staff.add", "provider_staff", str(staff.id), actor=current_user)

    await notify_user(
        db,
        user_id=target.id,
        notification_type="system",
        title="Added to provider team",
        body=f"You have been added to {primary.organization_name}'s team as {body.staff_role.value.replace('_', ' ').title()}.",
        reference_id=str(primary.id),
        reference_type="provider",
    )

    return {
        "id": staff.id,
        "provider_id": staff.provider_id,
        "user_id": staff.user_id,
        "staff_role": staff.staff_role,
        "created_at": staff.created_at,
        "staff_name": target.full_name,
        "staff_email": target.email,
    }


@router.delete("/me/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_staff(
    staff_id: UUID,
    current_user: Annotated[User, Depends(require_provider)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    primary = (await db.execute(select(Provider).where(Provider.user_id == current_user.id))).scalar_one_or_none()
    if not primary:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the primary account holder can manage staff")

    staff = (await db.execute(
        select(ProviderStaff).where(ProviderStaff.id == staff_id, ProviderStaff.provider_id == primary.id)
    )).scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff record not found")

    await db.delete(staff)
    await write_audit(db, request, "provider.staff.remove", "provider_staff", str(staff_id), actor=current_user)


@router.get("/{provider_id}/ratings")
async def get_provider_ratings(
    provider_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(
            func.avg(Rating.score).label("average_score"),
            func.count(Rating.id).label("total_ratings"),
        ).where(Rating.provider_id == provider_id)
    )
    row = result.one()
    return {
        "provider_id": str(provider_id),
        "average_score": round(float(row.average_score or 0), 1),
        "total_ratings": row.total_ratings,
    }


@router.get("", response_model=PaginatedResponse[ProviderPublic])
async def list_providers(
    params: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    base_q = select(Provider).where(Provider.status == ProviderStatus.APPROVED)
    all_rows = (await db.execute(_load_provider(base_q).order_by(Provider.organization_name))).scalars().all()

    # Deduplicate by org name — keep only the most recently created provider per org
    seen: dict[str, Provider] = {}
    for p in all_rows:
        key = (p.organization_name or "").lower()
        if key not in seen or p.created_at > seen[key].created_at:
            seen[key] = p
    deduped = sorted(seen.values(), key=lambda p: (p.organization_name or "").lower())

    total = len(deduped)
    page_items = deduped[params.offset : params.offset + params.size]

    # Batch-fetch rating aggregates for this page (single query, no N+1)
    page_ids = [p.id for p in page_items]
    rating_map: dict[str, tuple[float | None, int]] = {}
    if page_ids:
        rating_rows = (await db.execute(
            select(
                Rating.provider_id,
                func.avg(Rating.score).label("avg"),
                func.count(Rating.id).label("cnt"),
            )
            .where(Rating.provider_id.in_(page_ids))
            .group_by(Rating.provider_id)
        )).all()
        for r in rating_rows:
            rating_map[str(r.provider_id)] = (round(float(r.avg), 1) if r.avg else None, r.cnt or 0)

    items_out = []
    for p in page_items:
        data = ProviderPublic.model_validate(p).model_dump()
        avg, cnt = rating_map.get(str(p.id), (None, 0))
        data["avg_rating"] = avg
        data["total_ratings"] = cnt
        items_out.append(data)

    return {
        "items": items_out,
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": -(-total // params.size),
    }


@router.get("/{provider_id}", response_model=ProviderPublic)
async def get_provider(provider_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    result = await db.execute(_load_provider(select(Provider).where(Provider.id == provider_id)))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    row = (await db.execute(
        select(func.avg(Rating.score).label("avg"), func.count(Rating.id).label("cnt"))
        .where(Rating.provider_id == provider_id)
    )).one()

    data = ProviderPublic.model_validate(provider).model_dump()
    data["avg_rating"] = round(float(row.avg), 1) if row.avg else None
    data["total_ratings"] = row.cnt or 0
    return data


@router.put("/{provider_id}/status", response_model=ProviderPublic)
async def update_provider_status(
    provider_id: UUID,
    body: ProviderStatusUpdate,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Provider:
    result = await db.execute(_load_provider(select(Provider).where(Provider.id == provider_id)))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    provider.status = body.status
    await write_audit(
        db, request, f"admin.provider_{body.status.value}", "provider",
        str(provider_id), actor=admin, extra={"reason": body.reason},
    )
    await notify_user(
        db,
        user_id=provider.user_id,
        notification_type="system",
        title=f"Provider profile {body.status.value}",
        body=body.reason or f"Your provider profile has been {body.status.value}.",
        reference_id=str(provider_id),
        reference_type="provider",
    )
    return provider
