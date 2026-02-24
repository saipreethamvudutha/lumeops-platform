"""Baseline model for prediction statistics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Baseline(Base, TimestampMixin):
    """
    Prediction baseline statistics computed from inference history.

    Used for outlier detection via 3-sigma rule.
    """

    __tablename__ = "baselines"

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
    model = relationship("MLModel", back_populates="baselines")

    # Statistical properties
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    std: Mapped[float] = mapped_column(Float, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    min_val: Mapped[float] = mapped_column(Float, nullable=False)
    max_val: Mapped[float] = mapped_column(Float, nullable=False)

    # Computation info
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    computation_method: Mapped[str] = mapped_column(
        String(50), default="initial", nullable=False
    )  # initial, hourly_refresh, manual

    # Validity period
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        Index("idx_baseline_model_current", "model_id", "is_current"),
        Index("idx_baseline_tenant", "tenant_id"),
    )
