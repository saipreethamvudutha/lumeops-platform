"""API Key model for customer authentication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class APIKey(Base, TimestampMixin):
    """
    API Key for authenticating customer requests.

    Only the hash is stored -- the plaintext key is shown once at creation.
    Uses HMAC-SHA256 hashing with the app secret as the HMAC key.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default=generate_uuid
    )

    # Tenant relationship
    tenant_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("tenants.id"), nullable=False
    )
    tenant = relationship("Tenant", back_populates="api_keys")

    # Key data -- only hash is stored
    key_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    key_prefix: Mapped[str] = mapped_column(
        String(20), default="lum_sk_", nullable=False
    )
    key_suffix: Mapped[str] = mapped_column(
        String(10), nullable=True
    )  # Last 6 chars for identification

    # Metadata
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Default Key"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scopes: what this key can do
    scopes: Mapped[list | None] = mapped_column(
        JSONB, default=lambda: ["ingest", "read"]
    )

    # Lifecycle
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Rate limiting
    rate_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # requests/minute, None = use plan default

    # IP restrictions (optional)
    ip_whitelist: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_api_key_tenant", "tenant_id"),
        Index("idx_api_key_active", "is_active"),
        Index("idx_api_key_hash", "key_hash"),
    )
