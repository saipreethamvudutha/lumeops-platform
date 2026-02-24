"""Audit log model for immutable event tracking."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class AuditLog(Base):
    """
    Immutable audit log entry.

    HIPAA requires audit logging of all access to PHI.
    These records are append-only -- never updated or deleted.
    Retention: 7 years minimum.

    This is the PostgreSQL backup for audit logs.
    Primary audit storage is Elasticsearch for search performance.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # Tenant
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Event
    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # INFERENCE_RECEIVED, PII_REDACTED, etc.
    resource_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # inference, api_key, report
    resource_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Actor
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_prefix: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    # Request context (no PII)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(
        String(20), default="success", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # PII-specific
    pii_detected: Mapped[bool | None] = mapped_column(default=False, nullable=True)
    pii_types: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Additional context
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamp -- separate from created_at for precision
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "timestamp"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )
