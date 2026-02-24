"""Add encryption key version columns for key rotation.

Adds encryption_key_version to both tenants and inferences tables.
Adds last_key_rotation and key_rotation_count to tenants table.

WHY:
    Key rotation is a HIPAA best practice. When a key is rotated,
    we need to know:
    - Which version each inference was encrypted with (to decrypt it)
    - What the tenant's current key version is (for new encryptions)
    - When the last rotation happened (for compliance reporting)
    - How many rotations have occurred (for audit trail)

Revision ID: 14832d1f3ea8
Revises: 41b66f2e6d1f
Create Date: 2026-02-24
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "14832d1f3ea8"
down_revision: Union[str, None] = "41b66f2e6d1f"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ── Tenants: track current key version and rotation history ────
    op.add_column(
        "tenants",
        sa.Column(
            "encryption_key_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "last_key_rotation",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "key_rotation_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # ── Inferences: track which key version encrypted each record ──
    op.add_column(
        "inferences",
        sa.Column(
            "encryption_key_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )

    # Index for efficient batch queries during key rotation
    # "Find all inferences for tenant X still on old key version"
    op.create_index(
        "idx_inf_encryption_key_version",
        "inferences",
        ["tenant_id", "encryption_key_version"],
    )


def downgrade() -> None:
    op.drop_index("idx_inf_encryption_key_version", table_name="inferences")
    op.drop_column("inferences", "encryption_key_version")
    op.drop_column("tenants", "key_rotation_count")
    op.drop_column("tenants", "last_key_rotation")
    op.drop_column("tenants", "encryption_key_version")
