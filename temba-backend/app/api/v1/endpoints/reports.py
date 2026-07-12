"""
Report endpoints.
POST   /reports              → create (community)
GET    /reports              → list (filtered by role)
GET    /reports/{id}
PUT    /reports/{id}         → update status/notes (provider/admin)
DELETE /reports/{id}         → soft-close (admin)
POST   /reports/{id}/media   → attach files
"""
import random
import string
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_admin, require_staff, write_audit
from app.core.provider_utils import get_provider_for_user
from app.core.sla import classify_priority, resolution_deadline_for, sla_deadline_for
from app.db.session import get_db
from app.models.provider import Provider
from app.models.report import PriorityClass, Report, ReportMedia, ReportStatus
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse, PaginationParams
from app.models.rating import Rating
from app.schemas.rating import RatingCreate, RatingPublic
from app.schemas.report import ReportCreate, ReportPublic, ReportUpdate, VerificationVerdict
from app.services.file_service import upload_report_media
from app.services.notification_service import notify_org, notify_user

_PROVIDER_REPORT_STATUSES = {
    ReportStatus.ACKNOWLEDGED,
    ReportStatus.UNDER_REVIEW,
    ReportStatus.IN_PROGRESS,
    ReportStatus.RESOLUTION_SUBMITTED,
}
_CLOSED_REPORT = {
    ReportStatus.VERIFIED, ReportStatus.CLOSED_UNVERIFIED,
    ReportStatus.RESOLVED, ReportStatus.CLOSED,
}

router = APIRouter(prefix="/reports", tags=["reports"])


def _with_media(q):
    return q.options(selectinload(Report.media))


def _with_relations(q):
    return q.options(selectinload(Report.media), selectinload(Report.user), selectinload(Report.provider))


@router.post("", response_model=ReportPublic, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    ref = f"RPT-{date.today().strftime('%Y%m%d')}-{suffix}"
    priority = classify_priority(body.category.value, body.urgency.value)
    report = Report(
        user_id=current_user.id,
        reference_number=ref,
        priority_class=PriorityClass(priority),
        **body.model_dump(),
    )
    db.add(report)
    await db.flush()
    report.sla_deadline = sla_deadline_for(body.category.value, report.created_at, priority_class=priority)
    report.resolution_deadline = resolution_deadline_for(report.created_at, priority_class=priority)
    await write_audit(db, request, "report.create", "report", str(report.id), actor=current_user)
    await db.refresh(report, ["media"])
    return report


@router.get("", response_model=PaginatedResponse[ReportPublic])
async def list_reports(
    params: Annotated[PaginationParams, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: ReportStatus | None = None,
) -> dict:
    q = select(Report)

    if current_user.role == UserRole.COMMUNITY:
        q = q.where(Report.user_id == current_user.id)
    elif current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if prov:
            same_org = (await db.execute(
                select(Provider.id).where(
                    func.lower(Provider.organization_name) == func.lower(prov.organization_name)
                )
            )).scalars().all()
            q = q.where(Report.provider_id.in_(same_org))
        else:
            q = q.where(False)

    if status_filter:
        q = q.where(Report.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    priority_order = case(
        (Report.priority_class == PriorityClass.P1, 0),
        (Report.priority_class == PriorityClass.P2, 1),
        else_=2,
    )
    result = await db.execute(
        _with_relations(q).order_by(priority_order, Report.created_at.desc()).offset(params.offset).limit(params.size)
    )
    return {
        "items": result.scalars().all(),
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": -(-total // params.size),
    }


@router.get("/{report_id}", response_model=ReportPublic)
async def get_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    result = await db.execute(_with_relations(select(Report).where(Report.id == report_id)))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Community can only view their own
    if current_user.role == UserRole.COMMUNITY and report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return report


@router.put("/{report_id}", response_model=ReportPublic)
async def update_report(
    report_id: UUID,
    body: ReportUpdate,
    current_user: Annotated[User, Depends(require_staff)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    result = await db.execute(_with_relations(select(Report).where(Report.id == report_id)))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if not prov:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if report.provider_id is not None and report.provider_id != prov.id:
            rpt_org = (report.provider.organization_name or "").lower() if report.provider else ""
            if rpt_org != (prov.organization_name or "").lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.status:
        if current_user.role == UserRole.PROVIDER and body.status not in _PROVIDER_REPORT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Providers may only set status to: {', '.join(s.value for s in _PROVIDER_REPORT_STATUSES)}. "
                       "To close a case, submit a resolution and let the community verify it.",
            )
        now = datetime.now(timezone.utc)
        if report.first_responded_at is None:
            report.first_responded_at = now
        if body.status == ReportStatus.RESOLUTION_SUBMITTED:
            report.resolution_submitted_at = now

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(report, field, value)

    await write_audit(db, request, "report.update", "report", str(report_id), actor=current_user)

    if body.status:
        ref = report.reference_number or str(report_id)[:8]
        if body.status == ReportStatus.RESOLUTION_SUBMITTED:
            notif_title = f"Your issue {ref} has been marked as resolved"
            notif_body = (
                "The water provider has submitted a resolution for your report. "
                "Please open your dashboard to confirm whether the issue has actually been resolved. "
                "If not resolved, you can reopen the case."
            )
        else:
            notif_title = f"Report {ref} updated"
            notif_body = f"Your report status changed to: {body.status.value.replace('_', ' ').title()}"
        await notify_user(
            db,
            user_id=report.user_id,
            notification_type="report_update",
            title=notif_title,
            body=notif_body,
            reference_id=str(report_id),
            reference_type="report",
        )
    return report


@router.post("/{report_id}/verify", response_model=ReportPublic)
async def verify_report(
    report_id: UUID,
    body: VerificationVerdict,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    result = await db.execute(_with_relations(select(Report).where(Report.id == report_id)))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the report owner can verify")
    if report.status != ReportStatus.RESOLUTION_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This report has no pending resolution to verify",
        )

    now = datetime.now(timezone.utc)

    if body.verdict == "verified":
        report.status = ReportStatus.VERIFIED
        report.verified_at = now
        notif_title = "Resolution verified"
        notif_body = (body.comment or "The community member confirmed the issue has been resolved.")
    elif body.verdict == "partial":
        report.reopen_count += 1
        report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.FOLLOW_UP_REQUIRED
        notif_title = "Resolution disputed — follow-up required"
        notif_body = (body.comment or "The community member reported the issue is only partially resolved.")
    else:  # not_resolved
        report.reopen_count += 1
        report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.IN_PROGRESS
        notif_title = "Resolution rejected — case reopened"
        notif_body = (body.comment or "The community member reported the issue was not resolved.")

    await write_audit(db, request, f"report.verify.{body.verdict}", "report", str(report_id), actor=current_user)

    if report.provider_id:
        prov = (await db.execute(select(Provider).where(Provider.id == report.provider_id))).scalar_one_or_none()
        if prov:
            await notify_org(
                db, provider=prov,
                notification_type="report_update",
                title=notif_title,
                body=f"Report '{report.title}': {notif_body}",
                reference_id=str(report_id), reference_type="report",
            )
    return report


@router.post("/{report_id}/media", response_model=ReportPublic)
async def attach_media(
    report_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> Report:
    result = await db.execute(_with_relations(select(Report).where(Report.id == report_id)))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.user_id != current_user.id and current_user.role not in (UserRole.PROVIDER, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for f in files:
        url, media_type = await upload_report_media(f, str(report_id))
        db.add(ReportMedia(report_id=report_id, url=url, media_type=media_type, file_name=f.filename))

    await db.refresh(report, ["media"])
    return report


_DELETABLE_STATUSES = {
    ReportStatus.VERIFIED, ReportStatus.CLOSED_UNVERIFIED,
    ReportStatus.RESOLVED, ReportStatus.CLOSED,
}


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(_with_relations(select(Report).where(Report.id == report_id)))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if current_user.role == UserRole.COMMUNITY:
        if report.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if report.status not in _DELETABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can only delete reports that are fully resolved or closed.",
            )
    elif current_user.role == UserRole.PROVIDER:
        prov = await get_provider_for_user(current_user, db)
        if not prov:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if report.provider_id != prov.id:
            rpt_org = (report.provider.organization_name or "").lower() if report.provider else ""
            if rpt_org != (prov.organization_name or "").lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if report.status not in _DELETABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can only delete reports that are fully resolved or closed.",
            )
    # admin can delete anything

    await write_audit(db, request, "report.delete", "report", str(report_id), actor=current_user)
    await db.delete(report)


@router.post("/{report_id}/rate", response_model=RatingPublic, status_code=status.HTTP_201_CREATED)
async def rate_report(
    report_id: UUID,
    body: RatingCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Rating:
    report = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the reporter can rate")
    if report.status != ReportStatus.VERIFIED:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Can only rate verified reports")
    existing = (await db.execute(select(Rating).where(Rating.report_id == report_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already rated")

    rating = Rating(
        report_id=report_id,
        provider_id=report.provider_id,
        score=body.score,
        comment=body.comment,
    )
    db.add(rating)
    await db.flush()
    return rating
