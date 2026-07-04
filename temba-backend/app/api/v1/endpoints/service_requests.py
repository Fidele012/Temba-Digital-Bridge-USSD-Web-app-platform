"""
Service Request endpoints.
POST /service-requests          → create (community)
GET  /service-requests          → list (own for community; assigned for provider; all for admin)
GET  /service-requests/{id}
PUT  /service-requests/{id}     → update status (provider/admin)
DELETE /service-requests/{id}   → cancel (community, only if submitted/reviewing)
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select  # func used for case-insensitive org match
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_staff, write_audit
from app.core.provider_utils import get_provider_for_user
from app.core.sla import sla_deadline_for
from app.db.session import get_db
from app.models.provider import Provider
from app.models.service_request import ServiceRequest, ServiceRequestStatus
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.report import VerificationVerdict
from app.schemas.service_request import ServiceRequestCreate, ServiceRequestPublic, ServiceRequestUpdate
from app.services.notification_service import notify_org, notify_user

router = APIRouter(prefix="/service-requests", tags=["service-requests"])

_CANCELLABLE = {ServiceRequestStatus.SUBMITTED, ServiceRequestStatus.REVIEWING}
_DELETABLE_SR = {
    ServiceRequestStatus.COMPLETED, ServiceRequestStatus.VERIFIED,
    ServiceRequestStatus.CANCELLED, ServiceRequestStatus.REJECTED, ServiceRequestStatus.CLOSED_UNVERIFIED,
}
_PROVIDER_SR_STATUSES = {
    ServiceRequestStatus.ACKNOWLEDGED,
    ServiceRequestStatus.REVIEWING,
    ServiceRequestStatus.APPROVED,
    ServiceRequestStatus.IN_PROGRESS,
    ServiceRequestStatus.RESOLUTION_SUBMITTED,
}


def _with_relations(q):
    return q.options(selectinload(ServiceRequest.user), selectinload(ServiceRequest.provider))


@router.post("", response_model=ServiceRequestPublic, status_code=status.HTTP_201_CREATED)
async def create_service_request(
    body: ServiceRequestCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceRequest:
    sr = ServiceRequest(user_id=current_user.id, **body.model_dump())
    db.add(sr)
    await db.flush()
    sr.sla_deadline = sla_deadline_for(body.request_type.value, sr.created_at, "service_request")
    await write_audit(db, request, "service_request.create", "service_request", str(sr.id), actor=current_user)
    return sr


@router.get("", response_model=PaginatedResponse[ServiceRequestPublic])
async def list_service_requests(
    params: Annotated[PaginationParams, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: ServiceRequestStatus | None = None,
) -> dict:
    q = select(ServiceRequest)
    if current_user.role == UserRole.COMMUNITY:
        q = q.where(ServiceRequest.user_id == current_user.id)
    elif current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if prov:
            same_org = (await db.execute(
                select(Provider.id).where(
                    func.lower(Provider.organization_name) == func.lower(prov.organization_name)
                )
            )).scalars().all()
            q = q.where(ServiceRequest.provider_id.in_(same_org))
        else:
            q = q.where(False)

    if status_filter:
        q = q.where(ServiceRequest.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(_with_relations(q).order_by(ServiceRequest.created_at.desc()).offset(params.offset).limit(params.size))
    return {
        "items": result.scalars().all(),
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": -(-total // params.size),
    }


@router.get("/{sr_id}", response_model=ServiceRequestPublic)
async def get_service_request(
    sr_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceRequest:
    result = await db.execute(_with_relations(select(ServiceRequest).where(ServiceRequest.id == sr_id)))
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service request not found")
    if current_user.role == UserRole.COMMUNITY and sr.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return sr


@router.put("/{sr_id}", response_model=ServiceRequestPublic)
async def update_service_request(
    sr_id: UUID,
    body: ServiceRequestUpdate,
    current_user: Annotated[User, Depends(require_staff)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceRequest:
    result = await db.execute(_with_relations(select(ServiceRequest).where(ServiceRequest.id == sr_id)))
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service request not found")

    if current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if not prov:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if sr.provider_id is not None and sr.provider_id != prov.id:
            sr_org = (sr.provider.organization_name or "").lower() if sr.provider else ""
            if sr_org != (prov.organization_name or "").lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.status:
        if current_user.role == UserRole.PROVIDER and body.status not in _PROVIDER_SR_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Providers may only set status to: {', '.join(s.value for s in _PROVIDER_SR_STATUSES)}. "
                       "Submit a resolution and let the community verify it to close the case.",
            )
        now = datetime.now(timezone.utc)
        if sr.first_responded_at is None:
            sr.first_responded_at = now
        if body.status == ServiceRequestStatus.RESOLUTION_SUBMITTED:
            sr.resolution_submitted_at = now

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sr, field, value)

    await write_audit(db, request, "service_request.update", "service_request", str(sr_id), actor=current_user)

    if body.status:
        ref = sr.reference_number or str(sr_id)[:8]
        if body.status == ServiceRequestStatus.RESOLUTION_SUBMITTED:
            notif_title = f"Action needed: confirm if your service request {ref} was completed"
            notif_body = (
                "The water service provider has submitted a resolution for your request. "
                "Please open your dashboard to confirm whether the work has actually been completed. "
                "If not completed, you can reopen the case."
            )
        else:
            notif_title = f"Service request {ref} updated"
            notif_body = f"Status changed to: {body.status.value.replace('_', ' ').title()}"
        await notify_user(
            db,
            user_id=sr.user_id,
            notification_type="service_request_update",
            title=notif_title,
            body=notif_body,
            reference_id=str(sr_id),
            reference_type="service_request",
        )
    return sr


@router.post("/{sr_id}/verify", response_model=ServiceRequestPublic)
async def verify_service_request(
    sr_id: UUID,
    body: VerificationVerdict,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceRequest:
    result = await db.execute(_with_relations(select(ServiceRequest).where(ServiceRequest.id == sr_id)))
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service request not found")
    if sr.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can verify")
    if sr.status != ServiceRequestStatus.RESOLUTION_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This service request has no pending resolution to verify",
        )

    now = datetime.now(timezone.utc)

    if body.verdict == "verified":
        sr.status = ServiceRequestStatus.VERIFIED
        sr.verified_at = now
        notif_title = "Service request verified"
        notif_body = body.comment or "The community member confirmed the service was completed."
    elif body.verdict == "partial":
        sr.reopen_count += 1
        sr.status = ServiceRequestStatus.MANAGEMENT_REVIEW if sr.reopen_count >= 2 else ServiceRequestStatus.FOLLOW_UP_REQUIRED
        notif_title = "Service request disputed — follow-up required"
        notif_body = body.comment or "The community member reported the service is only partially complete."
    else:
        sr.reopen_count += 1
        sr.status = ServiceRequestStatus.MANAGEMENT_REVIEW if sr.reopen_count >= 2 else ServiceRequestStatus.IN_PROGRESS
        notif_title = "Service request rejected — case reopened"
        notif_body = body.comment or "The community member reported the service was not completed."

    await write_audit(db, request, f"service_request.verify.{body.verdict}", "service_request", str(sr_id), actor=current_user)

    if sr.provider_id:
        prov = (await db.execute(select(Provider).where(Provider.id == sr.provider_id))).scalar_one_or_none()
        if prov:
            await notify_org(
                db, provider=prov,
                notification_type="service_request_update",
                title=notif_title,
                body=f"Service request ({sr.request_type.value}): {notif_body}",
                reference_id=str(sr_id), reference_type="service_request",
            )
    return sr


@router.delete("/{sr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_or_delete_service_request(
    sr_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(_with_relations(select(ServiceRequest).where(ServiceRequest.id == sr_id)))
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service request not found")

    if current_user.role == UserRole.COMMUNITY:
        if sr.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if sr.status in _DELETABLE_SR:
            # Terminal — hard delete
            await write_audit(db, request, "service_request.delete", "service_request", str(sr_id), actor=current_user)
            await db.delete(sr)
            return
        if sr.status not in _CANCELLABLE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel at this stage")
        # In-progress — mark cancelled
        sr.status = ServiceRequestStatus.CANCELLED
        await write_audit(db, request, "service_request.cancel", "service_request", str(sr_id), actor=current_user)

    elif current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if not prov:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if sr.provider_id != prov.id:
            sr_org = (sr.provider.organization_name or "").lower() if sr.provider else ""
            if sr_org != (prov.organization_name or "").lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if sr.status not in _DELETABLE_SR:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Providers can only delete completed, verified, or cancelled service requests.",
            )
        await write_audit(db, request, "service_request.delete", "service_request", str(sr_id), actor=current_user)
        await db.delete(sr)

    else:  # admin
        await write_audit(db, request, "service_request.delete", "service_request", str(sr_id), actor=current_user)
        await db.delete(sr)
