"""
Webhook Configuration model for tenant notification subscriptions.

LEARNING NOTE:
    Webhooks allow tenants to receive real-time HTTP callbacks when events
    occur in their LumeOps pipeline (alerts, outliers, PII detections, etc.).

    Design decisions:
    1. Per-tenant: Each tenant configures their own webhook endpoints
    2. Event filtering: Tenants choose which event types trigger notifications
    3. HMAC signing: Every payload is signed with a per-webhook secret so
       receivers can verify authenticity (same pattern as GitHub/Stripe)
    4. Retry tracking: Failed deliveries are retried with exponential backoff;
       consecutive failures are tracked and webhooks auto-disable after threshold
    5. Delivery logging: Last delivery status is stored for observability

    Security considerations:
    - The webhook secret is stored encrypted at rest (uses Fernet per-tenant key)
    - Payloads NEVER include raw PHI/PII — only metadata and aggregate info
    - URL validation prevents SSRF by rejecting private/internal IPs
    - Rate limiting on webhook test endpoint prevents abuse
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class WebhookConfig(Base, TimestampMixin):
    """
    Webhook endpoint configuration for a tenant.

    Each webhook can subscribe to specific event types and has
    independent delivery tracking and failure thresholds.
    """

    __tablename__ = "webhook_configs"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # ── Tenant isolation ──────────────────────────────────────────
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )

    # ── Endpoint configuration ────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Human-friendly label (e.g. "Slack #ops-alerts")

    url: Mapped[str] = mapped_column(
        String(2048), nullable=False
    )  # Delivery URL (HTTPS enforced in production)

    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ── Event subscriptions ───────────────────────────────────────
    # Which event types trigger this webhook. Stored as JSONB array.
    # Valid types: alert_created, outlier_detected, pii_detected,
    #              data_quality_issue, key_rotated, compliance_report
    events: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # ── Security ──────────────────────────────────────────────────
    # HMAC-SHA256 signing secret — receivers verify payload authenticity
    # Stored encrypted via Fernet (same per-tenant key as inference data)
    secret: Mapped[str] = mapped_column(
        String(500), nullable=False
    )

    # Optional: custom headers to include with each delivery
    # e.g. {"X-Custom-Auth": "bearer token123"}
    headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Lifecycle ─────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # ── Delivery tracking ─────────────────────────────────────────
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_http_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Consecutive failure count — webhook auto-disables at threshold (10)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_deliveries: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    __table_args__ = (
        Index("idx_webhook_tenant", "tenant_id"),
        Index("idx_webhook_active", "tenant_id", "is_active"),
    )


class WebhookDelivery(Base):
    """
    Individual webhook delivery attempt record.

    Provides an audit trail of every delivery attempt for debugging
    and compliance. Retained for 90 days by default.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # References
    webhook_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("webhook_configs.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )

    # What triggered this delivery
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # e.g. alert ID, inference ID

    # Delivery details
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # The sent payload (no PHI)

    # Response tracking
    http_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Truncated to 1KB for storage efficiency
    response_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Status
    success: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Retry tracking
    attempt_number: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )

    # Timestamp (not using TimestampMixin — deliveries are immutable)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_delivery_webhook", "webhook_id"),
        Index("idx_delivery_tenant", "tenant_id"),
        Index("idx_delivery_time", "delivered_at"),
    )
