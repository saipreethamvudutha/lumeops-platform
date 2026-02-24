"""ML Model registration for monitoring."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class MLModel(Base, TimestampMixin):
    """
    Represents a deployed AI/ML model that sends inferences to LumeOps.

    Each model belongs to a tenant and has its own baseline configuration.
    """

    __tablename__ = "ml_models"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # Tenant relationship
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )
    tenant = relationship("Tenant", back_populates="models")

    # Identification
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    framework: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # tensorflow, pytorch, sklearn

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Monitoring configuration
    baseline_required_samples: Mapped[int] = mapped_column(
        Integer, default=1000, nullable=False
    )
    outlier_sigma: Mapped[float] = mapped_column(
        Float, default=3.0, nullable=False
    )

    # Data quality configuration
    required_fields: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # ["age", "symptom_1", "lab_value"]
    field_ranges: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"age": {"min": 0, "max": 120}}
    field_types: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"age": "float", "symptom": "string"}

    # Tags for categorization
    tags: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"type": "diagnostic", "specialty": "radiology"}

    # Relationships
    inferences = relationship("Inference", back_populates="model", lazy="dynamic")
    baselines = relationship("Baseline", back_populates="model", lazy="selectin")

    __table_args__ = (
        Index("idx_model_tenant", "tenant_id"),
        Index("idx_model_active", "is_active"),
        Index("idx_model_tenant_name", "tenant_id", "model_name", unique=True),
    )
