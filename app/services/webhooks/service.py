"""
Webhook Delivery Service.

Handles sending HTTP callbacks to tenant-configured webhook endpoints
when events occur (alerts, outliers, PII detections, etc.).

LEARNING NOTE — Design Decisions:

    1. FIRE-AND-FORGET PATTERN:
       Webhook delivery does NOT block the inference pipeline. If a delivery
       fails, it's logged and the inference is still stored successfully.
       This follows the same pattern as Elasticsearch writes and Redis pub/sub.

    2. HMAC-SHA256 SIGNING:
       Every payload is signed with the webhook's secret key using the same
       approach as GitHub/Stripe webhooks. Receivers compute:
           expected = HMAC-SHA256(secret, request_body)
       and compare with the X-LumeOps-Signature header. This prevents:
       - Spoofed webhook deliveries (only LumeOps knows the secret)
       - Tampered payloads (signature covers the entire body)

    3. EXPONENTIAL BACKOFF:
       Failed deliveries don't retry immediately. Each webhook tracks its
       consecutive failure count. After 10 consecutive failures, the webhook
       auto-disables to prevent wasting resources on dead endpoints.

    4. NO PHI IN PAYLOADS:
       Webhook payloads NEVER contain raw patient data, input features,
       or any PHI. Only metadata: alert type, inference ID, model name,
       counts, timestamps. This ensures HIPAA compliance even if the
       receiving endpoint is outside the covered entity.

    5. DELIVERY AUDIT TRAIL:
       Every delivery attempt is recorded in webhook_deliveries for
       debugging and compliance. These records include HTTP status,
       response time, and error details.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.webhook import WebhookConfig, WebhookDelivery

logger = get_logger("webhook_service")

# ── Constants ─────────────────────────────────────────────────────
MAX_CONSECUTIVE_FAILURES = 10  # Auto-disable after this many
DELIVERY_TIMEOUT_SECONDS = 10  # HTTP timeout per delivery
MAX_RESPONSE_BODY_SIZE = 1024  # Truncate response body to 1KB

# Valid event types that webhooks can subscribe to
VALID_EVENT_TYPES = {
    "alert_created",
    "outlier_detected",
    "pii_detected",
    "data_quality_issue",
    "key_rotated",
    "compliance_report",
}


def generate_webhook_secret() -> str:
    """
    Generate a cryptographically secure webhook signing secret.

    Format: whsec_ prefix + 32 bytes of random data (URL-safe base64).
    The prefix helps identify these as webhook secrets in logs/config.
    """
    return f"whsec_{secrets.token_urlsafe(32)}"


def compute_signature(secret: str, payload_bytes: bytes) -> str:
    """
    Compute HMAC-SHA256 signature for webhook payload verification.

    The receiver should compute the same signature and compare it
    with the X-LumeOps-Signature header to verify authenticity.

    Args:
        secret: The webhook's signing secret
        payload_bytes: The raw JSON body bytes

    Returns:
        Hex-encoded HMAC-SHA256 signature prefixed with "sha256="
    """
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


class WebhookService:
    """
    Service for managing and delivering webhook notifications.

    Handles:
    - Delivery of event payloads to configured endpoints
    - HMAC signing for payload verification
    - Failure tracking and auto-disable
    - Delivery audit trail logging
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_webhooks(
        self,
        tenant_id: str,
        event_type: str,
    ) -> list[WebhookConfig]:
        """
        Fetch all active webhooks for a tenant that subscribe to
        the given event type.

        Args:
            tenant_id: The tenant to look up webhooks for
            event_type: The event type to filter by (e.g. "alert_created")

        Returns:
            List of active WebhookConfig objects that match
        """
        result = await self.db.execute(
            select(WebhookConfig).where(
                WebhookConfig.tenant_id == tenant_id,
                WebhookConfig.is_active.is_(True),
            )
        )
        webhooks = result.scalars().all()

        # Filter by event type (stored in JSONB array)
        return [
            wh for wh in webhooks
            if event_type in (wh.events or [])
        ]

    async def deliver(
        self,
        webhook: WebhookConfig,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ) -> bool:
        """
        Deliver a payload to a single webhook endpoint.

        This is the core delivery method. It:
        1. Serializes the payload to JSON
        2. Computes HMAC-SHA256 signature
        3. Sends HTTP POST with signature header
        4. Records the delivery attempt
        5. Updates webhook failure tracking

        Args:
            webhook: The webhook configuration
            event_type: Type of event (for logging)
            payload: The event data (must NOT contain PHI)
            event_id: Optional reference ID (alert ID, inference ID)

        Returns:
            True if delivery succeeded, False otherwise
        """
        import orjson

        now = datetime.now(UTC)
        start_time = now

        # Build the full payload with metadata envelope
        delivery_payload = {
            "event_type": event_type,
            "event_id": event_id,
            "webhook_id": webhook.id,
            "tenant_id": webhook.tenant_id,
            "timestamp": now.isoformat(),
            "data": payload,
        }

        payload_bytes = orjson.dumps(delivery_payload)
        signature = compute_signature(webhook.secret, payload_bytes)

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LumeOps-Webhook/1.0",
            "X-LumeOps-Signature": signature,
            "X-LumeOps-Event": event_type,
            "X-LumeOps-Delivery-Id": str(WebhookDelivery.__table__.c.id.default.arg())
            if False else secrets.token_urlsafe(16),
        }

        # Merge custom headers (if configured)
        if webhook.headers:
            headers.update(webhook.headers)

        # ── Attempt delivery ──────────────────────────────────────
        http_status = None
        response_body = None
        response_time_ms = None
        error_msg = None
        success = False

        try:
            async with httpx.AsyncClient(
                timeout=DELIVERY_TIMEOUT_SECONDS,
                follow_redirects=False,  # Don't follow redirects (security)
            ) as client:
                response = await client.post(
                    webhook.url,
                    content=payload_bytes,
                    headers=headers,
                )

                end_time = datetime.now(UTC)
                response_time_ms = int(
                    (end_time - start_time).total_seconds() * 1000
                )
                http_status = response.status_code

                # Truncate response body for storage
                raw_body = response.text
                response_body = raw_body[:MAX_RESPONSE_BODY_SIZE]

                # Success: 2xx status codes
                success = 200 <= response.status_code < 300

                if not success:
                    error_msg = (
                        f"HTTP {response.status_code}: "
                        f"{response_body[:200]}"
                    )

        except httpx.TimeoutException:
            error_msg = f"Timeout after {DELIVERY_TIMEOUT_SECONDS}s"
            logger.warning(
                "webhook_delivery_timeout",
                webhook_id=webhook.id,
                url=webhook.url,
            )
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {str(e)[:200]}"
            logger.warning(
                "webhook_delivery_connect_error",
                webhook_id=webhook.id,
                url=webhook.url,
                error=str(e)[:200],
            )
        except Exception as e:
            error_msg = f"Delivery error: {str(e)[:200]}"
            logger.error(
                "webhook_delivery_error",
                webhook_id=webhook.id,
                url=webhook.url,
                error=str(e)[:200],
            )

        # ── Record delivery attempt ───────────────────────────────
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            tenant_id=webhook.tenant_id,
            event_type=event_type,
            event_id=event_id,
            payload=delivery_payload,
            http_status=http_status,
            response_body=response_body,
            response_time_ms=response_time_ms,
            success=success,
            error=error_msg,
            attempt_number=1,
            delivered_at=now,
        )
        self.db.add(delivery)

        # ── Update webhook tracking ───────────────────────────────
        webhook.last_triggered_at = now
        webhook.total_deliveries = (webhook.total_deliveries or 0) + 1

        if success:
            webhook.last_success_at = now
            webhook.last_http_status = http_status
            webhook.last_error = None
            webhook.consecutive_failures = 0

            logger.info(
                "webhook_delivered",
                webhook_id=webhook.id,
                event_type=event_type,
                http_status=http_status,
                response_time_ms=response_time_ms,
            )
        else:
            webhook.last_failure_at = now
            webhook.last_http_status = http_status
            webhook.last_error = error_msg
            webhook.consecutive_failures = (
                webhook.consecutive_failures or 0
            ) + 1
            webhook.total_failures = (webhook.total_failures or 0) + 1

            # Auto-disable after too many consecutive failures
            if webhook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                webhook.is_active = False
                logger.warning(
                    "webhook_auto_disabled",
                    webhook_id=webhook.id,
                    consecutive_failures=webhook.consecutive_failures,
                    reason="Max consecutive failures reached",
                )

            logger.warning(
                "webhook_delivery_failed",
                webhook_id=webhook.id,
                event_type=event_type,
                http_status=http_status,
                error=error_msg,
                consecutive_failures=webhook.consecutive_failures,
            )

        return success

    async def dispatch_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch an event to all matching webhooks for a tenant.

        This is the high-level method called from the ingest pipeline
        and other event sources. It:
        1. Finds all active webhooks subscribed to this event type
        2. Delivers to each one (sequentially for now; parallel in future)
        3. Returns a summary of delivery results

        Args:
            tenant_id: The tenant that owns the event
            event_type: Type of event (must be in VALID_EVENT_TYPES)
            payload: Event data (NO PHI allowed)
            event_id: Optional reference ID

        Returns:
            Summary dict with total, succeeded, failed counts
        """
        webhooks = await self.get_active_webhooks(tenant_id, event_type)

        if not webhooks:
            return {"total": 0, "succeeded": 0, "failed": 0}

        succeeded = 0
        failed = 0

        for webhook in webhooks:
            try:
                ok = await self.deliver(
                    webhook=webhook,
                    event_type=event_type,
                    payload=payload,
                    event_id=event_id,
                )
                if ok:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                # Never let a webhook failure crash the caller
                failed += 1
                logger.error(
                    "webhook_dispatch_error",
                    webhook_id=webhook.id,
                    error=str(e)[:200],
                )

        return {
            "total": len(webhooks),
            "succeeded": succeeded,
            "failed": failed,
        }

    async def send_test(self, webhook: WebhookConfig) -> dict[str, Any]:
        """
        Send a test payload to verify webhook configuration.

        Returns delivery result details for the UI to display.
        """
        test_payload = {
            "test": True,
            "message": "This is a test webhook delivery from LumeOps",
            "webhook_name": webhook.name,
            "configured_events": webhook.events,
        }

        now = datetime.now(UTC)
        import orjson

        payload_bytes = orjson.dumps({
            "event_type": "test",
            "event_id": None,
            "webhook_id": webhook.id,
            "tenant_id": webhook.tenant_id,
            "timestamp": now.isoformat(),
            "data": test_payload,
        })
        signature = compute_signature(webhook.secret, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LumeOps-Webhook/1.0",
            "X-LumeOps-Signature": signature,
            "X-LumeOps-Event": "test",
        }

        if webhook.headers:
            headers.update(webhook.headers)

        try:
            async with httpx.AsyncClient(
                timeout=DELIVERY_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    webhook.url,
                    content=payload_bytes,
                    headers=headers,
                )

                return {
                    "success": 200 <= response.status_code < 300,
                    "http_status": response.status_code,
                    "response_body": response.text[:MAX_RESPONSE_BODY_SIZE],
                    "message": (
                        "Test delivery successful"
                        if 200 <= response.status_code < 300
                        else f"Received HTTP {response.status_code}"
                    ),
                }

        except httpx.TimeoutException:
            return {
                "success": False,
                "http_status": None,
                "response_body": None,
                "message": f"Timeout after {DELIVERY_TIMEOUT_SECONDS}s",
            }
        except httpx.ConnectError as e:
            return {
                "success": False,
                "http_status": None,
                "response_body": None,
                "message": f"Connection error: {str(e)[:200]}",
            }
        except Exception as e:
            return {
                "success": False,
                "http_status": None,
                "response_body": None,
                "message": f"Error: {str(e)[:200]}",
            }
