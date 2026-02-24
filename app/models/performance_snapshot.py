"""
Model Performance Snapshot — periodic aggregated metrics.

LEARNING NOTE — Why Snapshots?

    Real-time computation of model performance from the inferences table
    is expensive at scale. A model with 1M inferences would require scanning
    all rows to compute accuracy, drift, and error metrics.

    Instead, we pre-compute snapshots at regular intervals (hourly/daily).
    Each snapshot contains:
    - Volume metrics (inference count, ground truth coverage)
    - Accuracy metrics (MAE, RMSE, accuracy for classification)
    - Distribution metrics (mean, std, min, max, percentiles)
    - Health metrics (outlier rate, data quality rate, PII rate)
    - Drift detection (prediction distribution shift from baseline)

    This approach is standard in ML observability platforms (Evidently AI,
    WhyLabs, Arize). The snapshots are:
    - Fast to query (one row per period instead of thousands)
    - Easy to chart (each row is a data point)
    - Space-efficient (aggregates replace raw scans)
    - Cacheable (immutable once computed)

    The `drift_score` field uses a simplified distribution comparison:
    comparing the period's mean/std to the baseline's mean/std using
    the normalized difference. A drift_score > 1.0 means the distribution
    has shifted by more than 1 standard deviation from baseline.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class ModelPerformanceSnapshot(Base, TimestampMixin):
    """
    Periodic aggregation of model performance metrics.

    One row per model per period (hourly or daily).
    Used by the Model Performance dashboard for trend charts.
    """

    __tablename__ = "model_performance_snapshots"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # References
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("ml_models.id"), nullable=False
    )
    model = relationship("MLModel")

    # Period definition
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "hourly" or "daily"

    # ── Volume Metrics ────────────────────────────────────────────
    total_inferences: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    inferences_with_ground_truth: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    ground_truth_coverage: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )  # inferences_with_ground_truth / total_inferences

    # ── Prediction Distribution ───────────────────────────────────
    prediction_mean: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    prediction_std: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    prediction_min: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    prediction_max: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    prediction_p50: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Median
    prediction_p95: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    prediction_p99: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # ── Accuracy Metrics (require ground truth) ────────────────
    # Mean Absolute Error — average |prediction - ground_truth|
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Root Mean Squared Error — sqrt(mean((prediction - ground_truth)^2))
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Mean Error (bias) — mean(prediction - ground_truth)
    mean_error: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Health Metrics ────────────────────────────────────────────
    outlier_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    outlier_rate: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )  # outlier_count / total_inferences

    quality_issue_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    quality_rate: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )  # (total - quality_issues) / total

    pii_detected_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_pii_redacted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # ── Drift Detection ───────────────────────────────────────────
    # Normalized distance between current prediction distribution
    # and the baseline: |period_mean - baseline_mean| / baseline_std
    # Values > 2.0 suggest significant drift
    drift_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    baseline_mean: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    baseline_std: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # ── Alert Summary ─────────────────────────────────────────────
    alerts_triggered: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    alerts_by_severity: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"critical": 1, "warning": 3}

    # ── Confidence Distribution ───────────────────────────────────
    avg_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    min_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    max_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    __table_args__ = (
        Index(
            "idx_perf_tenant_model_period",
            "tenant_id",
            "model_id",
            "period_start",
        ),
        Index("idx_perf_period_type", "period_type"),
        Index("idx_perf_model_drift", "model_id", "drift_score"),
    )
