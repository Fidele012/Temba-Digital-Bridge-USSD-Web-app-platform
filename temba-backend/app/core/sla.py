"""SLA deadline configuration, priority classification, and accountability scoring."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

_REPORT_SLA_H: dict[str, int] = {
    "contamination": 48,
    "pipe_burst": 168,
    "low_pressure": 72,
    "no_supply": 72,
    "water_quality": 72,
    "billing": 120,
    "meter": 120,
    "other": 120,
}

_APPOINTMENT_SLA_H: dict[str, int] = {
    "water_connection": 336,
    "meter_reading": 120,
    "pipe_repair": 168,
    "consultation": 120,
    "inspection": 72,
    "billing": 120,
    "other": 120,
}

_SERVICE_REQUEST_SLA_H: dict[str, int] = {
    "water_connection": 336,
    "tank_delivery": 48,
    "truck_delivery": 48,
    "meter_support": 120,
    "inspection": 72,
}

_DEFAULT_SLA_H = 120

# Response SLA (first acknowledgement): P1 = 4h, P2 = 24h, P3 = 72h
_PRIORITY_SLA_H = {"P1": 4, "P2": 24, "P3": 72}

# Resolution SLA (full fix): 6× the response deadline
_PRIORITY_RESOLUTION_H = {"P1": 24, "P2": 96, "P3": 240}
_DEFAULT_RESOLUTION_H = 240

_P1_CATEGORIES = {"contamination"}
_P1_CAT_URG = {
    ("pipe_burst", "high"), ("pipe_burst", "critical"),
    ("no_supply", "critical"),
}
_P2_CAT_URG = {
    ("pipe_burst", "medium"),
    ("no_supply", "high"), ("no_supply", "medium"),
    ("low_pressure", "high"), ("low_pressure", "critical"),
    ("water_quality", "high"),
}


def classify_priority(category: str, urgency: str) -> str:
    if category in _P1_CATEGORIES:
        return "P1"
    if (category, urgency) in _P1_CAT_URG:
        return "P1"
    if (category, urgency) in _P2_CAT_URG:
        return "P2"
    return "P3"


def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def sla_deadline_for(
    category: str,
    created_at: datetime,
    item_type: str = "report",
    priority_class: str | None = None,
) -> datetime:
    """Response SLA deadline — when the provider must first acknowledge."""
    if priority_class and item_type == "report":
        hours = _PRIORITY_SLA_H.get(priority_class, _DEFAULT_SLA_H)
    elif item_type == "appointment":
        hours = _APPOINTMENT_SLA_H.get(category, _DEFAULT_SLA_H)
    elif item_type == "service_request":
        hours = _SERVICE_REQUEST_SLA_H.get(category, _DEFAULT_SLA_H)
    else:
        hours = _REPORT_SLA_H.get(category, _DEFAULT_SLA_H)
    return _ensure_tz(created_at) + timedelta(hours=hours)


def resolution_deadline_for(
    created_at: datetime,
    priority_class: str | None = None,
    item_type: str = "report",
) -> datetime:
    """Resolution SLA deadline — when the issue must be fully fixed."""
    if item_type == "report":
        hours = _PRIORITY_RESOLUTION_H.get(priority_class or "P3", _DEFAULT_RESOLUTION_H)
    else:
        # For appointments / service requests, use the same resolution window as P3
        hours = _DEFAULT_RESOLUTION_H
    return _ensure_tz(created_at) + timedelta(hours=hours)


async def batch_accountability_scores(
    db,  # AsyncSession — avoid circular import
    provider_ids: list[UUID],
) -> dict[str, float]:
    """
    Compute accountability scores for a list of providers in two queries.

    Score = response_compliance×0.25 + resolution_compliance×0.25
            + verified_rate×0.35 + avg_stars_norm×0.15

    Returns {str(provider_id): score_0_to_100}.
    """
    if not provider_ids:
        return {}

    from sqlalchemy import and_, case, func, select

    from app.models.rating import Rating
    from app.models.report import Report, ReportStatus

    _CLOSED = (
        ReportStatus.VERIFIED,
        ReportStatus.CLOSED_UNVERIFIED,
        ReportStatus.RESOLVED,
        ReportStatus.CLOSED,
    )

    report_rows = (await db.execute(
        select(
            Report.provider_id,
            func.count(case(
                (and_(
                    Report.first_responded_at.isnot(None),
                    Report.sla_deadline.isnot(None),
                    Report.first_responded_at <= Report.sla_deadline,
                ), 1)
            )).label("resp_on_time"),
            func.count(case((Report.sla_deadline.isnot(None), 1))).label("resp_base"),
            func.count(case(
                (and_(
                    Report.resolution_deadline.isnot(None),
                    Report.status.in_(_CLOSED),
                    func.coalesce(Report.verified_at, Report.resolution_submitted_at).isnot(None),
                    func.coalesce(Report.verified_at, Report.resolution_submitted_at) <= Report.resolution_deadline,
                ), 1)
            )).label("res_on_time"),
            func.count(case(
                (and_(Report.resolution_deadline.isnot(None), Report.status.in_(_CLOSED)), 1)
            )).label("res_base"),
            func.count(case((Report.status == ReportStatus.VERIFIED, 1))).label("verified"),
            func.count(case((Report.status == ReportStatus.CLOSED_UNVERIFIED, 1))).label("auto_closed"),
        )
        .where(Report.provider_id.in_(provider_ids))
        .group_by(Report.provider_id)
    )).all()

    rating_rows = (await db.execute(
        select(Rating.provider_id, func.avg(Rating.score).label("avg"))
        .where(Rating.provider_id.in_(provider_ids))
        .group_by(Rating.provider_id)
    )).all()

    report_map = {str(r.provider_id): r for r in report_rows}
    rating_map = {str(r.provider_id): float(r.avg or 0) for r in rating_rows}

    scores: dict[str, float] = {}
    for pid in provider_ids:
        key = str(pid)
        r = report_map.get(key)
        if r is None:
            scores[key] = 0.0
            continue
        resp = (r.resp_on_time / r.resp_base * 100) if r.resp_base else 0.0
        res = (r.res_on_time / r.res_base * 100) if r.res_base else 0.0
        vbase = r.verified + r.auto_closed
        vrate = (r.verified / vbase * 100) if vbase else 0.0
        stars = rating_map.get(key, 0) / 5.0 * 100
        scores[key] = round(resp * 0.25 + res * 0.25 + vrate * 0.35 + stars * 0.15, 1)

    return scores
