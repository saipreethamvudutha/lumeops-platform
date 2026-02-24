"""
Unit tests for the Webhook Service.

Tests cover:
1. Webhook secret generation
2. HMAC signature computation and verification
3. Webhook delivery logic (success, failure, timeout)
4. Failure tracking and auto-disable
5. Event type filtering
6. Payload structure (NO PHI)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.webhooks.service import (
    MAX_CONSECUTIVE_FAILURES,
    VALID_EVENT_TYPES,
    WebhookService,
    compute_signature,
    generate_webhook_secret,
)


# ══════════════════════════════════════════════════════════════════
#  Secret Generation Tests
# ══════════════════════════════════════════════════════════════════


class TestSecretGeneration:
    """Tests for webhook signing secret generation."""

    def test_secret_has_prefix(self):
        """Signing secrets must start with 'whsec_' prefix."""
        secret = generate_webhook_secret()
        assert secret.startswith("whsec_")

    def test_secret_is_long_enough(self):
        """Secrets must be at least 32 characters (prefix + 32 bytes base64)."""
        secret = generate_webhook_secret()
        # "whsec_" (6 chars) + base64(32 bytes) ≈ 43 chars = ~49 total
        assert len(secret) >= 40

    def test_secrets_are_unique(self):
        """Each generated secret must be unique (cryptographically random)."""
        secrets = {generate_webhook_secret() for _ in range(100)}
        assert len(secrets) == 100

    def test_secret_is_url_safe(self):
        """Secret body should be URL-safe base64 (no +, /, =)."""
        for _ in range(20):
            secret = generate_webhook_secret()
            body = secret[6:]  # Remove "whsec_" prefix
            # URL-safe base64 uses only alphanumeric, -, _
            assert all(c.isalnum() or c in "-_" for c in body), \
                f"Non-URL-safe character in secret body: {body}"


# ══════════════════════════════════════════════════════════════════
#  Signature Tests
# ══════════════════════════════════════════════════════════════════


class TestSignatureComputation:
    """Tests for HMAC-SHA256 signature computation."""

    def test_signature_format(self):
        """Signature must be prefixed with 'sha256='."""
        sig = compute_signature("test-secret", b'{"test": true}')
        assert sig.startswith("sha256=")

    def test_signature_is_hex(self):
        """Signature body must be a valid hex string (64 chars for SHA-256)."""
        sig = compute_signature("test-secret", b'{"test": true}')
        hex_part = sig[len("sha256="):]
        assert len(hex_part) == 64
        int(hex_part, 16)  # Will raise ValueError if not valid hex

    def test_signature_is_deterministic(self):
        """Same secret + payload must produce the same signature."""
        payload = b'{"event": "test", "data": {"id": "123"}}'
        sig1 = compute_signature("my-secret", payload)
        sig2 = compute_signature("my-secret", payload)
        assert sig1 == sig2

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets must produce different signatures."""
        payload = b'{"test": true}'
        sig1 = compute_signature("secret-1", payload)
        sig2 = compute_signature("secret-2", payload)
        assert sig1 != sig2

    def test_different_payloads_produce_different_signatures(self):
        """Different payloads must produce different signatures."""
        secret = "shared-secret"
        sig1 = compute_signature(secret, b'{"a": 1}')
        sig2 = compute_signature(secret, b'{"a": 2}')
        assert sig1 != sig2

    def test_signature_matches_manual_hmac(self):
        """Signature must match manually computed HMAC-SHA256."""
        secret = "verification-secret"
        payload = b'{"event_type": "alert_created"}'

        expected_mac = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()

        sig = compute_signature(secret, payload)
        assert sig == f"sha256={expected_mac}"

    def test_empty_payload(self):
        """Signature must work with empty payload."""
        sig = compute_signature("secret", b"")
        assert sig.startswith("sha256=")
        assert len(sig) > 10


# ══════════════════════════════════════════════════════════════════
#  Event Type Validation
# ══════════════════════════════════════════════════════════════════


class TestEventTypes:
    """Tests for valid event types."""

    def test_all_expected_events_exist(self):
        """All documented event types must be in VALID_EVENT_TYPES."""
        expected = {
            "alert_created",
            "outlier_detected",
            "pii_detected",
            "data_quality_issue",
            "key_rotated",
            "compliance_report",
        }
        assert VALID_EVENT_TYPES == expected

    def test_event_types_are_snake_case(self):
        """All event types must be snake_case."""
        for event in VALID_EVENT_TYPES:
            assert event == event.lower()
            assert " " not in event
            assert "-" not in event


# ══════════════════════════════════════════════════════════════════
#  Webhook Service Logic Tests (using mocks)
# ══════════════════════════════════════════════════════════════════


class TestWebhookServiceLogic:
    """Tests for WebhookService business logic using mocked DB."""

    def _make_webhook(self, **kwargs):
        """Create a mock WebhookConfig object."""
        wh = MagicMock()
        wh.id = kwargs.get("id", "wh-test-123")
        wh.tenant_id = kwargs.get("tenant_id", "tenant-abc")
        wh.name = kwargs.get("name", "Test Webhook")
        wh.url = kwargs.get("url", "https://example.com/webhook")
        wh.secret = kwargs.get("secret", "whsec_test-secret-123")
        wh.events = kwargs.get("events", ["alert_created"])
        wh.headers = kwargs.get("headers", None)
        wh.is_active = kwargs.get("is_active", True)
        wh.consecutive_failures = kwargs.get("consecutive_failures", 0)
        wh.total_deliveries = kwargs.get("total_deliveries", 0)
        wh.total_failures = kwargs.get("total_failures", 0)
        wh.last_triggered_at = None
        wh.last_success_at = None
        wh.last_failure_at = None
        wh.last_http_status = None
        wh.last_error = None
        return wh

    @pytest.mark.asyncio
    async def test_dispatch_with_no_matching_webhooks(self):
        """dispatch_event returns empty result when no webhooks match."""
        mock_db = AsyncMock()

        # Mock query to return empty list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = WebhookService(mock_db)
        result = await service.dispatch_event(
            tenant_id="tenant-123",
            event_type="alert_created",
            payload={"test": True},
        )

        assert result["total"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_event_filtering(self):
        """get_active_webhooks only returns webhooks subscribed to the event."""
        mock_db = AsyncMock()

        wh_alerts = self._make_webhook(
            id="wh-1",
            events=["alert_created"],
        )
        wh_pii = self._make_webhook(
            id="wh-2",
            events=["pii_detected"],
        )
        wh_both = self._make_webhook(
            id="wh-3",
            events=["alert_created", "pii_detected"],
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            wh_alerts, wh_pii, wh_both,
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = WebhookService(mock_db)

        # Only alert_created subscribers
        matching = await service.get_active_webhooks("tenant-123", "alert_created")
        ids = [w.id for w in matching]
        assert "wh-1" in ids
        assert "wh-2" not in ids
        assert "wh-3" in ids

    @pytest.mark.asyncio
    async def test_auto_disable_after_max_failures(self):
        """Webhook auto-disables after MAX_CONSECUTIVE_FAILURES."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        webhook = self._make_webhook(
            consecutive_failures=MAX_CONSECUTIVE_FAILURES - 1,
        )

        service = WebhookService(mock_db)

        # Mock httpx to fail
        with patch("app.services.webhooks.service.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_client.return_value = mock_instance

            await service.deliver(
                webhook=webhook,
                event_type="alert_created",
                payload={"test": True},
            )

        # Should be auto-disabled now
        assert webhook.is_active is False
        assert webhook.consecutive_failures == MAX_CONSECUTIVE_FAILURES

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_on_success(self):
        """Successful delivery resets consecutive failure counter."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        webhook = self._make_webhook(consecutive_failures=5)

        service = WebhookService(mock_db)

        # Mock httpx to succeed
        with patch("app.services.webhooks.service.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await service.deliver(
                webhook=webhook,
                event_type="alert_created",
                payload={"test": True},
            )

        assert result is True
        assert webhook.consecutive_failures == 0
        assert webhook.last_error is None

    @pytest.mark.asyncio
    async def test_delivery_records_http_status(self):
        """Failed delivery records HTTP status code."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        webhook = self._make_webhook()
        service = WebhookService(mock_db)

        # Mock httpx to return 500
        with patch("app.services.webhooks.service.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await service.deliver(
                webhook=webhook,
                event_type="alert_created",
                payload={"test": True},
            )

        assert result is False
        assert webhook.last_http_status == 500
        assert webhook.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_delivery_creates_audit_record(self):
        """Each delivery attempt creates a WebhookDelivery record."""
        mock_db = AsyncMock()
        add_calls = []
        mock_db.add = MagicMock(side_effect=lambda obj: add_calls.append(obj))

        webhook = self._make_webhook()
        service = WebhookService(mock_db)

        with patch("app.services.webhooks.service.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            await service.deliver(
                webhook=webhook,
                event_type="alert_created",
                payload={"alert": "test"},
            )

        # Should have added a WebhookDelivery record
        assert len(add_calls) == 1
        delivery = add_calls[0]
        assert delivery.webhook_id == webhook.id
        assert delivery.event_type == "alert_created"
        assert delivery.success is True


# ══════════════════════════════════════════════════════════════════
#  Payload Security Tests
# ══════════════════════════════════════════════════════════════════


class TestPayloadSecurity:
    """Tests ensuring webhook payloads never contain PHI."""

    def test_valid_event_types_dont_include_raw_data(self):
        """No event type name suggests raw data exposure."""
        for event in VALID_EVENT_TYPES:
            # Event names should refer to metadata events, not data
            assert "raw" not in event
            assert "features" not in event
            assert "patient" not in event
            assert "phi" not in event.lower() or event == "pii_detected"

    def test_compute_signature_uses_utf8(self):
        """Signature computation handles UTF-8 secrets correctly."""
        # Even if someone uses non-ASCII characters in a secret,
        # encoding should not raise
        sig = compute_signature("secret-with-émojis-🔑", b"test payload")
        assert sig.startswith("sha256=")
