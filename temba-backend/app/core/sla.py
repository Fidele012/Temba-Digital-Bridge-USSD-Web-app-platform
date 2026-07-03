"""SLA deadline configuration, priority classification, and helpers."""
from datetime import datetime, timedelta, timezone

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

_PRIORITY_SLA_H = {"P1": 4, "P2": 24, "P3": 72}

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


def sla_deadline_for(
    category: str,
    created_at: datetime,
    item_type: str = "report",
    priority_class: str | None = None,
) -> datetime:
    """Return the SLA deadline for a given category and creation timestamp."""
    if priority_class and item_type == "report":
        hours = _PRIORITY_SLA_H.get(priority_class, _DEFAULT_SLA_H)
    elif item_type == "appointment":
        hours = _APPOINTMENT_SLA_H.get(category, _DEFAULT_SLA_H)
    elif item_type == "service_request":
        hours = _SERVICE_REQUEST_SLA_H.get(category, _DEFAULT_SLA_H)
    else:
        hours = _REPORT_SLA_H.get(category, _DEFAULT_SLA_H)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return created_at + timedelta(hours=hours)
