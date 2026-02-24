"""Data quality metrics aggregation model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class DataQualityMetric(Base, TimestampMixin):
    """
    Aggregated data quality metrics per model per period.

    Computed periodically (hourly/daily) from inference records.
    """

    __tablename__ = "data_quality_metrics"

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

    # Metrics
    total_inferences: Mapped[int] = mapped_column(Integer, nullable=False)
    inferences_with_issues: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    quality_rate: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # (total - issues) / total

    # Issue breakdown
    missing_fields_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    null_values_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    out_of_range_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    type_error_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # PII metrics
    total_pii_redacted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    pii_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Period
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # hourly, daily

    __table_args__ = (
        Index("idx_dq_tenant_model", "tenant_id", "model_id"),
        Index("idx_dq_period", "period_end"),
    )
