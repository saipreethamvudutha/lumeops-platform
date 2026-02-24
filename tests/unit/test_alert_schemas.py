"""
Unit tests for Alert Management schemas and validation.

Tests cover:
1. AlertAcknowledgeRequest validation
2. AlertResolveRequest validation
3. AlertBulkActionRequest validation
4. AlertStatsResponse structure
5. Filter parameter validation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    AlertAcknowledgeRequest,
    AlertBulkActionRequest,
    AlertBulkActionResponse,
    AlertDetailResponse,
    AlertListResponse,
    AlertResolveRequest,
    AlertStatsResponse,
)


# ══════════════════════════════════════════════════════════════════
#  Acknowledge Request Tests
# ══════════════════════════════════════════════════════════════════


class TestAcknowledgeRequest:
    """Tests for AlertAcknowledgeRequest schema."""

    def test_valid_acknowledge(self):
        """Valid acknowledge request with name."""
        req = AlertAcknowledgeRequest(acknowledged_by="Dr. Smith")
        assert req.acknowledged_by == "Dr. Smith"

    def test_valid_acknowledge_email(self):
        """Acknowledged_by can be an email."""
        req = AlertAcknowledgeRequest(acknowledged_by="ops@hospital.com")
        assert req.acknowledged_by == "ops@hospital.com"

    def test_empty_acknowledged_by_rejected(self):
        """Empty string should be rejected."""
        with pytest.raises(ValidationError):
            AlertAcknowledgeRequest(acknowledged_by="")

    def test_too_long_acknowledged_by_rejected(self):
        """String over 255 chars should be rejected."""
        with pytest.raises(ValidationError):
            AlertAcknowledgeRequest(acknowledged_by="x" * 256)

    def test_extra_fields_rejected(self):
        """Extra fields are forbidden (ConfigDict extra=forbid)."""
        with pytest.raises(ValidationError):
            AlertAcknowledgeRequest(
                acknowledged_by="Dr. Smith",
                extra_field="should fail",
            )


# ══════════════════════════════════════════════════════════════════
#  Resolve Request Tests
# ══════════════════════════════════════════════════════════════════


class TestResolveRequest:
    """Tests for AlertResolveRequest schema."""

    def test_resolve_without_note(self):
        """Resolution note is optional."""
        req = AlertResolveRequest()
        assert req.resolution_note is None

    def test_resolve_with_note(self):
        """Resolution note can be provided."""
        req = AlertResolveRequest(resolution_note="Increased baseline threshold")
        assert req.resolution_note == "Increased baseline threshold"

    def test_note_too_long_rejected(self):
        """Note over 2000 chars should be rejected."""
        with pytest.raises(ValidationError):
            AlertResolveRequest(resolution_note="x" * 2001)

    def test_extra_fields_rejected(self):
        """Extra fields are forbidden."""
        with pytest.raises(ValidationError):
            AlertResolveRequest(
                resolution_note="fix",
                extra="should fail",
            )


# ══════════════════════════════════════════════════════════════════
#  Bulk Action Request Tests
# ══════════════════════════════════════════════════════════════════


class TestBulkActionRequest:
    """Tests for AlertBulkActionRequest schema."""

    def test_valid_bulk_request(self):
        """Valid bulk request with alert IDs and acknowledged_by."""
        req = AlertBulkActionRequest(
            alert_ids=["id-1", "id-2", "id-3"],
            acknowledged_by="ops-team",
        )
        assert len(req.alert_ids) == 3
        assert req.acknowledged_by == "ops-team"

    def test_empty_alert_ids_rejected(self):
        """Empty alert_ids list should be rejected."""
        with pytest.raises(ValidationError):
            AlertBulkActionRequest(alert_ids=[])

    def test_too_many_alert_ids_rejected(self):
        """More than 100 IDs should be rejected."""
        with pytest.raises(ValidationError):
            AlertBulkActionRequest(
                alert_ids=[f"id-{i}" for i in range(101)],
            )

    def test_acknowledged_by_optional(self):
        """acknowledged_by is optional (needed only for ack, not resolve)."""
        req = AlertBulkActionRequest(alert_ids=["id-1"])
        assert req.acknowledged_by is None

    def test_single_id_valid(self):
        """Single alert ID is valid."""
        req = AlertBulkActionRequest(alert_ids=["single-id"])
        assert len(req.alert_ids) == 1


# ══════════════════════════════════════════════════════════════════
#  Response Schema Tests
# ══════════════════════════════════════════════════════════════════


class TestResponseSchemas:
    """Tests for alert response schemas."""

    def test_alert_detail_response(self):
        """AlertDetailResponse with all fields."""
        now = datetime.now(UTC)
        resp = AlertDetailResponse(
            id="alert-123",
            model_id="model-456",
            alert_type="outlier",
            severity="warning",
            message="Prediction outlier detected",
            details={"bounds": {"lower": 0.1, "upper": 0.9}},
            triggered_at=now,
            inference_id="inf-789",
            acknowledged_at=now,
            acknowledged_by="Dr. Smith",
            resolved_at=None,
            notified_email=True,
            notified_slack=False,
            created_at=now,
        )
        assert resp.alert_type == "outlier"
        assert resp.resolved_at is None
        assert resp.notified_email is True

    def test_alert_list_response(self):
        """AlertListResponse with pagination."""
        now = datetime.now(UTC)
        resp = AlertListResponse(
            total=50,
            limit=25,
            offset=0,
            has_more=True,
            alerts=[
                AlertDetailResponse(
                    id="a-1", model_id="m-1", alert_type="outlier",
                    severity="warning", message="Test",
                    details=None, triggered_at=now, inference_id=None,
                    acknowledged_at=None, acknowledged_by=None,
                    resolved_at=None, notified_email=False,
                    notified_slack=False, created_at=now,
                )
            ],
        )
        assert resp.total == 50
        assert resp.has_more is True
        assert len(resp.alerts) == 1

    def test_alert_stats_response(self):
        """AlertStatsResponse with MTTA/MTTR."""
        resp = AlertStatsResponse(
            total_active=5,
            total_acknowledged=3,
            total_resolved=12,
            by_severity={"critical": 2, "warning": 10, "info": 8},
            by_type={"outlier": 15, "data_quality": 5},
            mean_time_to_acknowledge_minutes=4.5,
            mean_time_to_resolve_minutes=23.1,
            generated_at=datetime.now(UTC),
        )
        assert resp.total_active == 5
        assert resp.mean_time_to_acknowledge_minutes == 4.5
        assert resp.by_severity["critical"] == 2

    def test_alert_stats_null_mtta_mttr(self):
        """MTTA/MTTR can be null when no data exists."""
        resp = AlertStatsResponse(
            total_active=0,
            total_acknowledged=0,
            total_resolved=0,
            by_severity={},
            by_type={},
            mean_time_to_acknowledge_minutes=None,
            mean_time_to_resolve_minutes=None,
            generated_at=datetime.now(UTC),
        )
        assert resp.mean_time_to_acknowledge_minutes is None

    def test_bulk_action_response(self):
        """AlertBulkActionResponse."""
        resp = AlertBulkActionResponse(
            processed=3,
            skipped=1,
            alert_ids=["a-1", "a-2", "a-3"],
        )
        assert resp.processed == 3
        assert resp.skipped == 1
        assert len(resp.alert_ids) == 3


# ══════════════════════════════════════════════════════════════════
#  Alert Lifecycle Tests
# ══════════════════════════════════════════════════════════════════


class TestAlertLifecycle:
    """Tests verifying alert state transition logic."""

    def test_open_alert_has_no_ack_or_resolve(self):
        """Open alert: acknowledged_at=None, resolved_at=None."""
        now = datetime.now(UTC)
        alert = AlertDetailResponse(
            id="a-1", model_id="m-1", alert_type="outlier",
            severity="critical", message="Test",
            details=None, triggered_at=now, inference_id=None,
            acknowledged_at=None, acknowledged_by=None,
            resolved_at=None, notified_email=False,
            notified_slack=False, created_at=now,
        )
        assert alert.acknowledged_at is None
        assert alert.resolved_at is None

    def test_acknowledged_alert_has_ack_but_no_resolve(self):
        """Acknowledged alert: acknowledged_at set, resolved_at=None."""
        now = datetime.now(UTC)
        alert = AlertDetailResponse(
            id="a-1", model_id="m-1", alert_type="data_quality",
            severity="warning", message="Test",
            details=None, triggered_at=now, inference_id=None,
            acknowledged_at=now, acknowledged_by="ops-team",
            resolved_at=None, notified_email=False,
            notified_slack=False, created_at=now,
        )
        assert alert.acknowledged_at is not None
        assert alert.acknowledged_by == "ops-team"
        assert alert.resolved_at is None

    def test_resolved_alert_has_both(self):
        """Resolved alert: both acknowledged_at and resolved_at set."""
        now = datetime.now(UTC)
        alert = AlertDetailResponse(
            id="a-1", model_id="m-1", alert_type="outlier",
            severity="info", message="Test",
            details=None, triggered_at=now, inference_id=None,
            acknowledged_at=now, acknowledged_by="auto (resolved)",
            resolved_at=now, notified_email=True,
            notified_slack=True, created_at=now,
        )
        assert alert.acknowledged_at is not None
        assert alert.resolved_at is not None
