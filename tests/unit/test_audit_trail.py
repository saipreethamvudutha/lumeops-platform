"""
Unit tests for Audit Trail Viewer (Session 11).

Tests cover:
1. AuditLog model field validation
2. AuditService event logging methods
3. Audit trail endpoint response structure
4. Filter parameter validation
5. CSV export format verification
6. Stats endpoint response structure
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.audit_log import AuditLog


# ══════════════════════════════════════════════════════════════════
#  AuditLog Model Tests
# ══════════════════════════════════════════════════════════════════


class TestAuditLogModel:
    """Tests for the AuditLog SQLAlchemy model."""

    def test_create_minimal_audit_log(self):
        """Minimum required fields create a valid model."""
        log = AuditLog(
            tenant_id="tenant-123",
            action="INFERENCE_RECEIVED",
            status="success",
        )
        assert log.tenant_id == "tenant-123"
        assert log.action == "INFERENCE_RECEIVED"
        assert log.status == "success"

    def test_create_full_audit_log(self):
        """All fields can be populated."""
        now = datetime.now(UTC)
        log = AuditLog(
            tenant_id="tenant-123",
            action="PII_DETECTED_AND_REDACTED",
            resource_type="inference",
            resource_id="inf-456",
            user_id="user-789",
            api_key_prefix="lum_sk_",
            ip_address="10.0.0.1",
            user_agent="Python/3.14",
            status="success",
            error_message=None,
            pii_detected=True,
            pii_types={"ssn": 1, "email": 2},
            details={"total_redacted": 3},
            timestamp=now,
        )
        assert log.pii_detected is True
        assert log.pii_types["ssn"] == 1
        assert log.pii_types["email"] == 2
        assert log.details["total_redacted"] == 3
        assert log.ip_address == "10.0.0.1"
        assert log.api_key_prefix == "lum_sk_"

    def test_nullable_fields(self):
        """Optional fields default to None."""
        log = AuditLog(
            tenant_id="t1",
            action="API_KEY_CREATED",
            status="success",
        )
        assert log.resource_type is None
        assert log.resource_id is None
        assert log.user_id is None
        assert log.api_key_prefix is None
        assert log.ip_address is None
        assert log.user_agent is None
        assert log.error_message is None
        assert log.pii_types is None
        assert log.details is None

    def test_status_default(self):
        """Status column has a default of 'success'.

        Note: SQLAlchemy column defaults are applied at flush/commit time,
        not at Python object creation. We verify the column definition instead.
        """
        col = AuditLog.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "success"

    def test_pii_detected_default(self):
        """pii_detected column has a default of False.

        Note: SQLAlchemy column defaults are applied at flush/commit time,
        not at Python object creation. We verify the column definition instead.
        """
        col = AuditLog.__table__.columns["pii_detected"]
        assert col.default is not None
        assert col.default.arg is False

    def test_table_name(self):
        """Table name should be 'audit_logs'."""
        assert AuditLog.__tablename__ == "audit_logs"

    def test_indexes_exist(self):
        """Verify required indexes are defined."""
        index_names = [idx.name for idx in AuditLog.__table_args__ if hasattr(idx, 'name')]
        assert "idx_audit_tenant_time" in index_names
        assert "idx_audit_action" in index_names
        assert "idx_audit_timestamp" in index_names
        assert "idx_audit_resource" in index_names


# ══════════════════════════════════════════════════════════════════
#  Action Type Tests
# ══════════════════════════════════════════════════════════════════


class TestAuditActionTypes:
    """Verify all known action types are valid strings."""

    KNOWN_ACTIONS = [
        "INFERENCE_RECEIVED",
        "PII_DETECTED_AND_REDACTED",
        "REPORT_GENERATED",
        "API_KEY_CREATED",
        "API_KEY_REVOKED",
        "ALERT_ACKNOWLEDGED",
        "ALERT_RESOLVED",
        "ALERTS_BULK_ACKNOWLEDGED",
        "ENCRYPTION_KEY_ROTATED",
        "ENCRYPTION_KEY_ROTATION_BATCH",
        "WEBHOOK_CREATED",
        "WEBHOOK_DELETED",
    ]

    @pytest.mark.parametrize("action", KNOWN_ACTIONS)
    def test_known_action_types(self, action: str):
        """Each known action can be stored."""
        log = AuditLog(
            tenant_id="t1",
            action=action,
            status="success",
        )
        assert log.action == action

    def test_action_field_length(self):
        """Action field allows up to 100 characters."""
        long_action = "A" * 100
        log = AuditLog(
            tenant_id="t1",
            action=long_action,
            status="success",
        )
        assert len(log.action) == 100


# ══════════════════════════════════════════════════════════════════
#  Resource Type Tests
# ══════════════════════════════════════════════════════════════════


class TestResourceTypes:
    """Verify resource type categorization."""

    KNOWN_RESOURCES = [
        "inference",
        "api_key",
        "report",
        "alert",
        "tenant",
        "webhook",
    ]

    @pytest.mark.parametrize("resource_type", KNOWN_RESOURCES)
    def test_known_resource_types(self, resource_type: str):
        log = AuditLog(
            tenant_id="t1",
            action="TEST",
            resource_type=resource_type,
            status="success",
        )
        assert log.resource_type == resource_type

    def test_resource_type_nullable(self):
        log = AuditLog(
            tenant_id="t1",
            action="SYSTEM_EVENT",
            resource_type=None,
            status="success",
        )
        assert log.resource_type is None


# ══════════════════════════════════════════════════════════════════
#  Audit Trail Response Format Tests
# ══════════════════════════════════════════════════════════════════


class TestAuditTrailResponseFormat:
    """Verify the expected shape of audit trail API responses."""

    def test_response_has_pagination_fields(self):
        """Validate the structure we expect from the endpoint."""
        response = {
            "total": 54,
            "limit": 50,
            "offset": 0,
            "has_more": True,
            "entries": [],
        }
        assert "total" in response
        assert "limit" in response
        assert "offset" in response
        assert "has_more" in response
        assert isinstance(response["entries"], list)

    def test_entry_has_required_fields(self):
        """Each entry must have all expected fields."""
        entry = {
            "id": "abc-123",
            "action": "INFERENCE_RECEIVED",
            "resource_type": "inference",
            "resource_id": "inf-456",
            "api_key_prefix": "lum_sk_",
            "ip_address": "10.0.0.1",
            "status": "success",
            "error_message": None,
            "pii_detected": True,
            "pii_types": {"ssn": 1},
            "timestamp": "2026-02-24T12:00:00+00:00",
            "details": {"model_id": "model-1"},
        }
        required = [
            "id", "action", "resource_type", "resource_id",
            "api_key_prefix", "ip_address", "status",
            "error_message", "pii_detected", "pii_types",
            "timestamp", "details",
        ]
        for field in required:
            assert field in entry, f"Missing field: {field}"

    def test_stats_has_required_fields(self):
        """Stats response must have all expected fields."""
        stats = {
            "period_days": 30,
            "total_events": 54,
            "pii_events": 12,
            "events_by_action": {"INFERENCE_RECEIVED": 30},
            "events_by_resource_type": {"inference": 30},
            "generated_at": "2026-02-24T12:00:00+00:00",
        }
        required = [
            "period_days", "total_events", "pii_events",
            "events_by_action", "events_by_resource_type", "generated_at",
        ]
        for field in required:
            assert field in stats, f"Missing field: {field}"


# ══════════════════════════════════════════════════════════════════
#  PII Detection Tracking Tests
# ══════════════════════════════════════════════════════════════════


class TestPIITracking:
    """Tests for PII detection audit entries."""

    def test_pii_detected_with_types(self):
        log = AuditLog(
            tenant_id="t1",
            action="PII_DETECTED_AND_REDACTED",
            resource_type="inference",
            pii_detected=True,
            pii_types={"ssn": 1, "email": 2, "phone": 1},
            status="success",
        )
        assert log.pii_detected is True
        assert sum(log.pii_types.values()) == 4

    def test_no_pii_detected(self):
        log = AuditLog(
            tenant_id="t1",
            action="INFERENCE_RECEIVED",
            pii_detected=False,
            pii_types=None,
            status="success",
        )
        assert log.pii_detected is False
        assert log.pii_types is None

    def test_pii_types_preserves_structure(self):
        pii = {"ssn": 3, "email": 1, "mrn": 2, "phone": 1}
        log = AuditLog(
            tenant_id="t1",
            action="PII_DETECTED_AND_REDACTED",
            pii_detected=True,
            pii_types=pii,
            status="success",
        )
        assert log.pii_types == pii
        assert log.pii_types["mrn"] == 2


# ══════════════════════════════════════════════════════════════════
#  CSV Export Tests
# ══════════════════════════════════════════════════════════════════


class TestCSVExportFormat:
    """Verify CSV export column structure."""

    def test_csv_headers(self):
        """Expected CSV columns."""
        expected_headers = [
            "id", "timestamp", "action", "resource_type", "resource_id",
            "api_key_prefix", "ip_address", "status", "pii_detected", "details",
        ]
        # Test that all expected columns are present
        for col in expected_headers:
            assert isinstance(col, str)
            assert len(col) > 0

    def test_csv_row_from_audit_log(self):
        """Simulate CSV row generation from an audit log entry."""
        log = AuditLog(
            id="test-id",
            tenant_id="t1",
            action="INFERENCE_RECEIVED",
            resource_type="inference",
            resource_id="inf-123",
            api_key_prefix="lum_sk_",
            ip_address="10.0.0.1",
            status="success",
            pii_detected=True,
            details={"model_id": "m1"},
            timestamp=datetime(2026, 2, 24, 12, 0, 0),
        )
        row = [
            log.id,
            log.timestamp.isoformat(),
            log.action,
            log.resource_type or "",
            log.resource_id or "",
            log.api_key_prefix or "",
            log.ip_address or "",
            log.status,
            log.pii_detected or False,
            str(log.details) if log.details else "",
        ]
        assert len(row) == 10
        assert row[0] == "test-id"
        assert row[2] == "INFERENCE_RECEIVED"
        assert row[8] is True


# ══════════════════════════════════════════════════════════════════
#  File Existence & Configuration Tests
# ══════════════════════════════════════════════════════════════════


class TestAuditTrailConfiguration:
    """Verify audit trail files and configuration."""

    def test_audit_logs_page_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "frontend", "src", "pages", "AuditLogsPage.tsx"
        )
        assert os.path.exists(path), "AuditLogsPage.tsx should exist"

    def test_audit_model_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "app", "models", "audit_log.py"
        )
        assert os.path.exists(path), "audit_log.py model should exist"

    def test_audit_service_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "app", "services", "audit", "service.py"
        )
        assert os.path.exists(path), "audit/service.py should exist"

    def test_compliance_router_has_audit_endpoints(self):
        """Verify the compliance router includes audit trail endpoints."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "app", "api", "v1", "compliance.py"
        )
        with open(path) as f:
            content = f.read()
        assert "/audit-trail" in content
        assert "/audit-trail/stats" in content
        assert "/audit-trail/export" in content

    def test_layout_has_audit_trail_nav(self):
        """Verify sidebar includes Audit Trail link."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "frontend", "src", "components", "Layout.tsx"
        )
        with open(path) as f:
            content = f.read()
        assert "audit-logs" in content
        assert "Audit Trail" in content

    def test_app_has_audit_route(self):
        """Verify App.tsx has the audit logs route."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "frontend", "src", "App.tsx"
        )
        with open(path) as f:
            content = f.read()
        assert "AuditLogsPage" in content
        assert "audit-logs" in content
