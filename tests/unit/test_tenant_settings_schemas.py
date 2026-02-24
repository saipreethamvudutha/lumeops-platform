"""
Unit tests for Tenant Settings & Data Retention schemas and service utilities.

Tests cover:
1. Tenant settings update schema validation
2. Retention policy schema validation (min values, null handling)
3. Cleanup response schema
4. Data retention service utility (mask_url)
5. Retention policy constraints
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    RetentionCleanupResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
    TenantSettingsResponse,
    TenantSettingsUpdateRequest,
)
from app.services.data_retention import _mask_url


# ══════════════════════════════════════════════════════════════════
#  URL Masking Utility Tests
# ══════════════════════════════════════════════════════════════════


class TestMaskUrl:
    """Tests for the _mask_url utility function."""

    def test_none_returns_none(self):
        assert _mask_url(None) is None

    def test_empty_returns_none(self):
        assert _mask_url("") is None

    def test_https_url_masked(self):
        result = _mask_url("https://hooks.slack.com/services/T00/B00/xxx")
        assert result == "https://hooks.slack.com/****"

    def test_http_url_masked(self):
        result = _mask_url("http://example.com/webhook/secret")
        assert result == "http://example.com/****"

    def test_url_with_port(self):
        result = _mask_url("https://example.com:8443/webhook")
        assert result == "https://example.com:8443/****"

    def test_invalid_url_returns_masked(self):
        result = _mask_url("not-a-valid-url")
        # Should not crash, returns some masked form
        assert result is not None


# ══════════════════════════════════════════════════════════════════
#  Tenant Settings Schema Tests
# ══════════════════════════════════════════════════════════════════


class TestTenantSettingsSchemas:
    """Tests for tenant settings request/response schemas."""

    def test_valid_update_request(self):
        req = TenantSettingsUpdateRequest(
            name="New Hospital Name",
            contact_email="admin@hospital.org",
            timezone="US/Eastern",
        )
        assert req.name == "New Hospital Name"
        assert req.timezone == "US/Eastern"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            TenantSettingsUpdateRequest(name="")

    def test_invalid_timezone_rejected(self):
        with pytest.raises(ValidationError):
            TenantSettingsUpdateRequest(timezone="Mars/Olympus")

    def test_valid_timezones(self):
        for tz in ["UTC", "US/Eastern", "US/Pacific", "Europe/London",
                    "Asia/Tokyo", "America/New_York"]:
            req = TenantSettingsUpdateRequest(timezone=tz)
            assert req.timezone == tz

    def test_invalid_customer_type_rejected(self):
        with pytest.raises(ValidationError):
            TenantSettingsUpdateRequest(customer_type="alien")

    def test_valid_customer_types(self):
        for ct in ["hospital", "insurer", "vendor", "research", "government"]:
            req = TenantSettingsUpdateRequest(customer_type=ct)
            assert req.customer_type == ct

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            TenantSettingsUpdateRequest(name="Test", plan="enterprise")

    def test_all_fields_none_valid(self):
        """All-None request is valid (nothing to update logic is in the endpoint)."""
        req = TenantSettingsUpdateRequest()
        assert req.name is None
        assert req.timezone is None

    def test_notification_preferences(self):
        req = TenantSettingsUpdateRequest(
            notification_preferences={"email": True, "slack": False, "webhook": True}
        )
        assert req.notification_preferences["email"] is True

    def test_settings_response(self):
        now = datetime.now(UTC)
        resp = TenantSettingsResponse(
            id="tenant-123",
            name="Test Hospital",
            customer_type="hospital",
            contact_email="admin@test.org",
            contact_phone="+1234567890",
            plan="professional",
            is_active=True,
            timezone="US/Eastern",
            data_residency="us-east-1",
            alert_email="alerts@test.org",
            alert_slack_webhook="https://hooks.slack.com/****",
            notification_preferences={"email": True, "slack": False, "webhook": True},
            encryption_key_version=3,
            last_key_rotation=now,
            key_rotation_count=2,
            retention={
                "inference_retention_days": 730,
                "alert_retention_days": 90,
                "webhook_delivery_retention_days": 30,
                "policy_updated_at": now.isoformat(),
                "last_cleanup_at": None,
            },
            created_at=now,
        )
        assert resp.plan == "professional"
        assert resp.encryption_key_version == 3
        assert resp.retention["inference_retention_days"] == 730


# ══════════════════════════════════════════════════════════════════
#  Retention Policy Schema Tests
# ══════════════════════════════════════════════════════════════════


class TestRetentionPolicySchemas:
    """Tests for data retention policy schemas."""

    def test_valid_retention_update(self):
        req = RetentionPolicyUpdateRequest(
            inference_retention_days=730,
            alert_retention_days=90,
            webhook_delivery_retention_days=30,
        )
        assert req.inference_retention_days == 730
        assert req.alert_retention_days == 90

    def test_inference_below_minimum_rejected(self):
        """Must be >= 365 (HIPAA)."""
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(inference_retention_days=30)

    def test_inference_at_minimum_valid(self):
        req = RetentionPolicyUpdateRequest(inference_retention_days=365)
        assert req.inference_retention_days == 365

    def test_alert_below_minimum_rejected(self):
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(alert_retention_days=10)

    def test_alert_at_minimum_valid(self):
        req = RetentionPolicyUpdateRequest(alert_retention_days=30)
        assert req.alert_retention_days == 30

    def test_webhook_below_minimum_rejected(self):
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(webhook_delivery_retention_days=3)

    def test_webhook_at_minimum_valid(self):
        req = RetentionPolicyUpdateRequest(webhook_delivery_retention_days=7)
        assert req.webhook_delivery_retention_days == 7

    def test_null_means_forever(self):
        """NULL values mean keep forever."""
        req = RetentionPolicyUpdateRequest(
            inference_retention_days=None,
            alert_retention_days=None,
            webhook_delivery_retention_days=None,
        )
        assert req.inference_retention_days is None
        assert req.alert_retention_days is None
        assert req.webhook_delivery_retention_days is None

    def test_partial_update_valid(self):
        """Only update some fields."""
        req = RetentionPolicyUpdateRequest(inference_retention_days=365)
        assert req.inference_retention_days == 365
        assert req.alert_retention_days is None

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(
                inference_retention_days=365,
                extra_field="nope",
            )

    def test_large_values_valid(self):
        """3650 days = ~10 years — perfectly valid."""
        req = RetentionPolicyUpdateRequest(
            inference_retention_days=3650,
            alert_retention_days=365,
            webhook_delivery_retention_days=365,
        )
        assert req.inference_retention_days == 3650

    def test_retention_response(self):
        now = datetime.now(UTC)
        resp = RetentionPolicyResponse(
            inference_retention_days=730,
            alert_retention_days=90,
            webhook_delivery_retention_days=30,
            retention_policy_updated_at=now,
            last_retention_cleanup_at=None,
        )
        assert resp.inference_retention_days == 730
        assert resp.last_retention_cleanup_at is None


# ══════════════════════════════════════════════════════════════════
#  Cleanup Response Schema Tests
# ══════════════════════════════════════════════════════════════════


class TestCleanupResponseSchemas:
    """Tests for retention cleanup response schemas."""

    def test_cleanup_response_dry_run(self):
        resp = RetentionCleanupResponse(
            tenant_id="t-1",
            tenant_name="Test Hospital",
            dry_run=True,
            inferences_deleted=100,
            alerts_deleted=5,
            webhook_deliveries_deleted=50,
            total_deleted=155,
            executed_at=datetime.now(UTC),
        )
        assert resp.dry_run is True
        assert resp.total_deleted == 155

    def test_cleanup_response_actual(self):
        resp = RetentionCleanupResponse(
            tenant_id="t-1",
            tenant_name="Test Hospital",
            dry_run=False,
            inferences_deleted=0,
            alerts_deleted=0,
            webhook_deliveries_deleted=0,
            total_deleted=0,
            executed_at=datetime.now(UTC),
        )
        assert resp.dry_run is False
        assert resp.total_deleted == 0

    def test_cleanup_large_numbers(self):
        """Production systems may delete millions of records."""
        resp = RetentionCleanupResponse(
            tenant_id="t-1",
            tenant_name="Big Hospital",
            dry_run=False,
            inferences_deleted=1_500_000,
            alerts_deleted=25_000,
            webhook_deliveries_deleted=100_000,
            total_deleted=1_625_000,
            executed_at=datetime.now(UTC),
        )
        assert resp.inferences_deleted == 1_500_000
        assert resp.total_deleted == 1_625_000


# ══════════════════════════════════════════════════════════════════
#  Retention Policy Constraint Tests (Business Logic)
# ══════════════════════════════════════════════════════════════════


class TestRetentionConstraints:
    """Tests for retention policy business logic constraints."""

    def test_hipaa_inference_minimum(self):
        """HIPAA requires at least 1 year (365 days) for medical records."""
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(inference_retention_days=364)

    def test_hipaa_inference_boundary(self):
        """Exactly 365 days is the minimum allowed."""
        req = RetentionPolicyUpdateRequest(inference_retention_days=365)
        assert req.inference_retention_days == 365

    def test_six_year_retention(self):
        """6-year retention (HIPAA recommended)."""
        req = RetentionPolicyUpdateRequest(inference_retention_days=2190)
        assert req.inference_retention_days == 2190

    def test_seven_year_retention(self):
        """7-year retention (matching audit log policy)."""
        req = RetentionPolicyUpdateRequest(inference_retention_days=2555)
        assert req.inference_retention_days == 2555

    def test_negative_values_rejected(self):
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(inference_retention_days=-1)

    def test_zero_values_rejected(self):
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(inference_retention_days=0)

    def test_alert_one_month_minimum(self):
        """Alerts need at least 30 days for trend analysis."""
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(alert_retention_days=29)

    def test_webhook_one_week_minimum(self):
        """Webhook logs need at least 7 days for debugging."""
        with pytest.raises(ValidationError):
            RetentionPolicyUpdateRequest(webhook_delivery_retention_days=6)
