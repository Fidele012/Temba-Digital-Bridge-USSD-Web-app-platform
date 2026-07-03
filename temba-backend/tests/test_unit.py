"""
Unit tests — testing individual functions and modules in complete isolation.

Strategy: each test calls a single pure function with no HTTP, no database,
and no external services. This confirms the core business logic is correct
regardless of the surrounding infrastructure.

Functions under test:
  - classify_priority()     (app/core/sla.py)
  - sla_deadline_for()      (app/core/sla.py)
  - hash_password()         (app/core/security.py)
  - verify_password()       (app/core/security.py)
  - create_access_token()   (app/core/security.py)
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.security import create_access_token, hash_password, verify_password
from app.core.sla import classify_priority, sla_deadline_for


# ── Priority Classification Unit Tests ───────────────────────────────────────

class TestClassifyPriority:
    """Unit tests for the P1/P2/P3 auto-classification matrix."""

    def test_contamination_any_urgency_is_p1(self):
        """Contamination is always P1 regardless of urgency — FR6."""
        assert classify_priority("contamination", "low") == "P1"
        assert classify_priority("contamination", "medium") == "P1"
        assert classify_priority("contamination", "high") == "P1"
        assert classify_priority("contamination", "critical") == "P1"

    def test_pipe_burst_high_is_p1(self):
        assert classify_priority("pipe_burst", "high") == "P1"

    def test_pipe_burst_critical_is_p1(self):
        assert classify_priority("pipe_burst", "critical") == "P1"

    def test_pipe_burst_medium_is_p2(self):
        assert classify_priority("pipe_burst", "medium") == "P2"

    def test_no_supply_critical_is_p1(self):
        assert classify_priority("no_supply", "critical") == "P1"

    def test_no_supply_high_is_p2(self):
        assert classify_priority("no_supply", "high") == "P2"

    def test_low_pressure_high_is_p2(self):
        assert classify_priority("low_pressure", "high") == "P2"

    def test_water_quality_high_is_p2(self):
        assert classify_priority("water_quality", "high") == "P2"

    def test_billing_any_urgency_is_p3(self):
        assert classify_priority("billing", "low") == "P3"
        assert classify_priority("billing", "high") == "P3"

    def test_other_any_urgency_is_p3(self):
        assert classify_priority("other", "critical") == "P3"

    def test_low_pressure_low_is_p3(self):
        assert classify_priority("low_pressure", "low") == "P3"


# ── SLA Deadline Unit Tests ───────────────────────────────────────────────────

class TestSlaDeadlineFor:
    """Unit tests for the SLA deadline calculator — FR6, FR12."""

    _NOW = datetime(2026, 6, 15, 8, 0, 0, tzinfo=timezone.utc)

    def test_p1_report_gets_4_hour_deadline(self):
        deadline = sla_deadline_for("contamination", self._NOW, "report", priority_class="P1")
        diff_h = (deadline - self._NOW).total_seconds() / 3600
        assert diff_h == pytest.approx(4.0)

    def test_p2_report_gets_24_hour_deadline(self):
        deadline = sla_deadline_for("pipe_burst", self._NOW, "report", priority_class="P2")
        diff_h = (deadline - self._NOW).total_seconds() / 3600
        assert diff_h == pytest.approx(24.0)

    def test_p3_report_gets_72_hour_deadline(self):
        deadline = sla_deadline_for("other", self._NOW, "report", priority_class="P3")
        diff_h = (deadline - self._NOW).total_seconds() / 3600
        assert diff_h == pytest.approx(72.0)

    def test_appointment_inspection_gets_72_hour_deadline(self):
        deadline = sla_deadline_for("inspection", self._NOW, "appointment")
        diff_h = (deadline - self._NOW).total_seconds() / 3600
        assert diff_h == pytest.approx(72.0)

    def test_service_request_tank_delivery_gets_48_hour_deadline(self):
        deadline = sla_deadline_for("tank_delivery", self._NOW, "service_request")
        diff_h = (deadline - self._NOW).total_seconds() / 3600
        assert diff_h == pytest.approx(48.0)

    def test_naive_datetime_handled(self):
        naive = datetime(2026, 6, 15, 8, 0, 0)
        deadline = sla_deadline_for("contamination", naive, "report", priority_class="P1")
        assert deadline.tzinfo is not None


# ── Password Hashing Unit Tests ───────────────────────────────────────────────

class TestPasswordHashing:
    """Unit tests for bcrypt hashing — NFR4."""

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("MySecret@123")
        assert hashed != "MySecret@123"

    def test_correct_password_verifies(self):
        hashed = hash_password("MySecret@123")
        assert verify_password("MySecret@123", hashed) is True

    def test_wrong_password_does_not_verify(self):
        hashed = hash_password("MySecret@123")
        assert verify_password("WrongPass@999", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        h1 = hash_password("Same@Pass1")
        h2 = hash_password("Same@Pass1")
        assert h1 != h2


# ── JWT Token Unit Tests ──────────────────────────────────────────────────────

class TestJwtToken:
    """Unit tests for JWT access token creation — NFR4."""

    def test_token_is_non_empty_string(self):
        token = create_access_token(uuid4(), "community")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_different_users_get_different_tokens(self):
        t1 = create_access_token(uuid4(), "community")
        t2 = create_access_token(uuid4(), "community")
        assert t1 != t2
