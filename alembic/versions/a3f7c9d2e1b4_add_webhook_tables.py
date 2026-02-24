"""Add webhook configuration and delivery tables.

Creates two tables for the webhook notification system:
1. webhook_configs - Per-tenant webhook endpoint configurations
2. webhook_deliveries - Individual delivery attempt records (audit trail)

WHY:
    Webhooks make LumeOps actionable, not just observational.
    When an alert fires, a data quality issue is detected, or PII
    is found, tenants can receive real-time HTTP callbacks to their
    Slack channels, PagerDuty, custom endpoints, etc.

    Delivery tracking enables:
    - Auto-disable after consecutive failures (prevent noise)
    - Retry with exponential backoff
    - Debugging delivery issues in the dashboard
    - Compliance audit trail of all notifications sent

Revision ID: a3f7c9d2e1b4
Revises: 14832d1f3ea8
Create Date: 2026-02-24
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a3f7c9d2e1b4"
down_revision: Union[str, None] = "14832d1f3ea8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ── 1. Webhook Configurations ──────────────────────────────────
    op.create_table(
        "webhook_configs",
        sa.Column("id", sa.String(255), primary_key=True),
        # Tenant isolation
        sa.Column(
            "tenant_id",
            sa.String(255),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        # Endpoint configuration
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Event subscriptions (JSONB array of event type strings)
        sa.Column("events", JSONB(), nullable=False),
        # Security
        sa.Column("secret", sa.String(500), nullable=False),
        sa.Column("headers", JSONB(), nullable=True),
        # Lifecycle
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        # Delivery tracking
        sa.Column(
            "last_triggered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_success_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_failure_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_deliveries",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Timestamps (from TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "idx_webhook_tenant", "webhook_configs", ["tenant_id"]
    )
    op.create_index(
        "idx_webhook_active", "webhook_configs", ["tenant_id", "is_active"]
    )

    # ── 2. Webhook Deliveries (audit trail) ────────────────────────
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(255), primary_key=True),
        # References
        sa.Column(
            "webhook_id",
            sa.String(255),
            sa.ForeignKey("webhook_configs.id"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(255),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        # Event context
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        # Response tracking
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        # Status
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        # Retry
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        # Timestamp
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_delivery_webhook", "webhook_deliveries", ["webhook_id"]
    )
    op.create_index(
        "idx_delivery_tenant", "webhook_deliveries", ["tenant_id"]
    )
    op.create_index(
        "idx_delivery_time", "webhook_deliveries", ["delivered_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_delivery_time", table_name="webhook_deliveries")
    op.drop_index("idx_delivery_tenant", table_name="webhook_deliveries")
    op.drop_index("idx_delivery_webhook", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.drop_index("idx_webhook_active", table_name="webhook_configs")
    op.drop_index("idx_webhook_tenant", table_name="webhook_configs")
    op.drop_table("webhook_configs")
