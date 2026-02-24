"""Add data retention and tenant settings fields.

Revision ID: c7d9e4f2a3b1
Revises: b5e8d3f1a2c6
Create Date: 2025-02-24 22:00:00.000000

Adds per-tenant data retention policy fields:
- inference_retention_days: How long to keep inference records
- alert_retention_days: How long to keep alert records
- webhook_delivery_retention_days: How long to keep webhook delivery logs
- retention_policy_updated_at: When the retention policy was last changed
- last_retention_cleanup_at: When data was last cleaned up

Also adds tenant settings:
- timezone: Preferred timezone for reports and UI
- notification_preferences: JSONB for notification config
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c7d9e4f2a3b1"
down_revision = "b5e8d3f1a2c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Data Retention Fields ─────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "inference_retention_days",
            sa.Integer(),
            nullable=True,
            comment="Days to keep inference records (NULL = keep forever)",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "alert_retention_days",
            sa.Integer(),
            nullable=True,
            comment="Days to keep resolved alerts (NULL = keep forever)",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "webhook_delivery_retention_days",
            sa.Integer(),
            nullable=True,
            server_default="90",
            comment="Days to keep webhook delivery logs (default 90)",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "retention_policy_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "last_retention_cleanup_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ── Tenant Settings ───────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "timezone",
            sa.String(50),
            server_default="UTC",
            nullable=False,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "notification_preferences",
            postgresql.JSONB(),
            nullable=True,
            comment="Alert notification config: {email: bool, slack: bool, webhook: bool}",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "notification_preferences")
    op.drop_column("tenants", "timezone")
    op.drop_column("tenants", "last_retention_cleanup_at")
    op.drop_column("tenants", "retention_policy_updated_at")
    op.drop_column("tenants", "webhook_delivery_retention_days")
    op.drop_column("tenants", "alert_retention_days")
    op.drop_column("tenants", "inference_retention_days")
