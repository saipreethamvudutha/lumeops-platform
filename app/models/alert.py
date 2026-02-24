"""Alert model for tracking monitoring alerts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Alert(Base, TimestampMixin):
    """
    Alert record triggered by monitoring checks.

    Types: outlier, data_quality, system_error
    Severity: info, warning, critical
    """

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )

    # Model reference
    model_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("ml_models.id"), nullable=False
    )

    # Alert details
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # outlier, data_quality, system_error
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # info, warning, critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Trigger context
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    inference_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("inferences.id"), nullable=True
    )

    # Resolution
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notification tracking
    notified_email: Mapped[bool] = mapped_column(default=False, nullable=False)
    notified_slack: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("idx_alert_tenant", "tenant_id"),
        Index("idx_alert_unresolved", "resolved_at"),
        Index("idx_alert_triggered", "triggered_at"),
        Index("idx_alert_model", "model_id"),
    )
