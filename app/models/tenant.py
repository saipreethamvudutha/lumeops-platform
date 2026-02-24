"""
Tenant model for multi-tenancy.

LEARNING NOTE ON ENCRYPTION KEY VERSIONING:
    Each tenant tracks its current encryption_key_version (integer).
    When a key rotation is triggered:
    1. encryption_key_version increments (e.g., 1 → 2)
    2. The salt for PBKDF2 changes: "lumeops-tenant-{id}-v1" → "...-v2"
    3. All existing inferences are re-encrypted with the new key
    4. last_key_rotation records when rotation happened

    WHY VERSION IN THE SALT:
        Changing the version in the salt means PBKDF2 derives a
        completely different key from the same master key + tenant_id.
        This is equivalent to rotating the key material itself, without
        needing to store or manage separate key material per tenant.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Tenant(Base, TimestampMixin):
    """
    Tenant represents a customer organization.

    Multi-tenancy is enforced at the application level:
    every query filters by tenant_id.
    """

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # hospital, insurer, vendor

    # Contact
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Billing
    plan: Mapped[str] = mapped_column(
        String(50), default="starter", nullable=False
    )  # starter, professional, enterprise
    monthly_fee: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Settings
    encryption_key_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # AWS KMS key ID
    alert_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alert_slack_webhook: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    data_residency: Mapped[str] = mapped_column(
        String(50), default="us-east-1", nullable=False
    )

    # ── Encryption Key Rotation ─────────────────────────────────────
    # Tracks the current key version for per-tenant encryption.
    # The version is embedded in the PBKDF2 salt: "lumeops-tenant-{id}-v{version}"
    # When rotated, all inference records are re-encrypted with the new version.
    encryption_key_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    last_key_rotation: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    key_rotation_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Metadata
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=dict
    )

    # Relationships
    api_keys = relationship("APIKey", back_populates="tenant", lazy="selectin")
    models = relationship("MLModel", back_populates="tenant", lazy="selectin")

    __table_args__ = (
        Index("idx_tenant_active", "is_active"),
        Index("idx_tenant_plan", "plan"),
    )
