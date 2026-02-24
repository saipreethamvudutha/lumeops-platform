"""
Inference model -- the core data record of LumeOps.

WHAT THIS STORES:
    Every inference that flows through our system becomes an Inference record.
    The record contains:
    - The model's prediction (what the AI said)
    - Encrypted input features (the data the AI used, with PHI redacted)
    - Classification metadata (what types of data were in the payload)
    - Data quality flags (were there issues with the input?)
    - Outlier detection results (was this prediction unusual?)
    - Full audit metadata (who, when, from where)

LEARNING NOTE:
    Notice that we store THREE levels of data protection metadata:
    1. pii_* fields: What identifiers were found and redacted
    2. classification_* fields: Full sensitivity breakdown of the payload
    3. high_sensitivity_fields: Which fields need encryption by storage layer

    This redundancy is intentional. Different consumers need different views:
    - Compliance reporting uses pii_* fields
    - Storage layer uses high_sensitivity_fields
    - Dashboards use classification_summary for aggregation
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Inference(Base, TimestampMixin):
    """
    Stores a single inference record with PHI already redacted.

    The input_features_encrypted field contains Fernet-encrypted JSON
    of the redacted input features. Even though PHI is redacted,
    we still encrypt at rest as defense-in-depth.

    DESIGN NOTE:
        This model uses JSONB columns for flexible metadata storage.
        PostgreSQL JSONB supports indexing, so queries like
        "find all inferences with SSN redactions" are efficient:
        WHERE pii_types_found ? 'SSN'
    """

    __tablename__ = "inferences"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # Tenant isolation -- every query MUST filter by this
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Model reference
    model_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("ml_models.id"), nullable=False
    )
    model = relationship("MLModel", back_populates="inferences")

    # Prediction data
    prediction: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Protected Input Features ──────────────────────────────────
    # Encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
    # Contains the redacted input features as encrypted JSON
    input_features_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    # Tracks which key version was used to encrypt this record.
    # Essential for key rotation: we need to know which key to
    # use for decryption before re-encrypting with the new key.
    encryption_key_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )

    # ── PHI Redaction Metadata ────────────────────────────────────
    # What identifiers were found and removed
    pii_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pii_redaction_count: Mapped[int] = mapped_column(default=0, nullable=False)
    pii_types_found: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"SSN": 1, "EMAIL": 2}

    # ── Classification Metadata ───────────────────────────────────
    # Full sensitivity breakdown of the payload
    #
    # LEARNING NOTE:
    #   This field stores the output of DataClassifier.get_payload_summary().
    #   It tells us things like:
    #   - How many CRITICAL fields were in the payload (should be 0 after redaction)
    #   - How many HIGH fields need encryption
    #   - What categories of data were present (diagnosis, lab, medication, etc.)
    #
    #   This data is essential for compliance reporting:
    #   "In Q4 2024, 15% of inferences contained clinical diagnoses"
    classification_summary: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # Which fields were classified HIGH and need encryption
    # Stored separately for quick access by the storage/encryption layer
    high_sensitivity_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # [{"field_path": "diagnosis_code", "sensitivity": "HIGH", "action": "encrypt"}]

    # The highest sensitivity level found in this payload
    # LEARNING NOTE: This enables fast queries like
    # "show me all inferences that contained CRITICAL data"
    # without parsing the full classification_summary JSONB
    max_sensitivity_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # "CRITICAL", "HIGH", "MODERATE", "LOW"

    # Count of fields by sensitivity level (for dashboard aggregation)
    sensitivity_counts: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"CRITICAL": 2, "HIGH": 5, "MODERATE": 3, "LOW": 4}

    # ── Data Quality Flags ────────────────────────────────────────
    has_quality_issues: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    quality_issues: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # [{"type": "missing_field", "field": "age"}]

    # ── Baseline Comparison ───────────────────────────────────────
    is_outlier: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    outlier_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Audit Information ─────────────────────────────────────────
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )  # For idempotency

    # Request metadata (no PHI)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    api_version: Mapped[str | None] = mapped_column(
        String(10), default="v1", nullable=True
    )

    # Generic metadata
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Ground Truth ──────────────────────────────────────────────
    # Filled later when actual outcomes are known (if available)
    ground_truth: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_truth_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Data Type Tracking ────────────────────────────────────────
    # What kind of healthcare data was in this inference
    # Enables queries like "show all inferences containing lab results"
    #
    # LEARNING NOTE:
    #   These boolean flags exist for fast SQL filtering.
    #   The full breakdown is in classification_summary (JSONB),
    #   but boolean columns with indexes are much faster for
    #   WHERE clauses than JSONB path queries.
    contains_clinical_data: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    contains_behavioral_health: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    contains_genetic_data: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    data_categories_present: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {"diagnosis": 2, "lab_result": 3, "medication": 1}

    __table_args__ = (
        Index("idx_inf_tenant_model_time", "tenant_id", "model_id", "received_at"),
        Index("idx_inf_received_at", "received_at"),
        Index("idx_inf_is_outlier", "is_outlier"),
        Index("idx_inf_has_quality_issues", "has_quality_issues"),
        Index("idx_inf_request_id", "request_id"),
        Index("idx_inf_max_sensitivity", "max_sensitivity_level"),
        Index("idx_inf_contains_clinical", "contains_clinical_data"),
        Index("idx_inf_contains_behavioral", "contains_behavioral_health"),
        Index("idx_inf_contains_genetic", "contains_genetic_data"),
    )
