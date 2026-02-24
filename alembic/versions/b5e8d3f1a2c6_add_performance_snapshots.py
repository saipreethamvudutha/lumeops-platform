"""Add model_performance_snapshots table.

Revision ID: b5e8d3f1a2c6
Revises: a3f7c9d2e1b4
Create Date: 2026-02-24

Stores pre-computed periodic performance metrics for each model:
- Volume (inference count, ground truth coverage)
- Prediction distribution (mean, std, percentiles)
- Accuracy (MAE, RMSE, mean error) — requires ground truth
- Health (outlier rate, quality rate, PII rate)
- Drift detection (normalized shift from baseline)
- Alert summary (triggered alerts by severity)
- Confidence distribution
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "b5e8d3f1a2c6"
down_revision = "a3f7c9d2e1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_performance_snapshots",
        # Identity
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(255),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            sa.String(255),
            sa.ForeignKey("ml_models.id"),
            nullable=False,
        ),
        # Period
        sa.Column(
            "period_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "period_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(20), nullable=False),
        # Volume
        sa.Column("total_inferences", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "inferences_with_ground_truth",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "ground_truth_coverage",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        # Prediction distribution
        sa.Column("prediction_mean", sa.Float, nullable=True),
        sa.Column("prediction_std", sa.Float, nullable=True),
        sa.Column("prediction_min", sa.Float, nullable=True),
        sa.Column("prediction_max", sa.Float, nullable=True),
        sa.Column("prediction_p50", sa.Float, nullable=True),
        sa.Column("prediction_p95", sa.Float, nullable=True),
        sa.Column("prediction_p99", sa.Float, nullable=True),
        # Accuracy (requires ground truth)
        sa.Column("mae", sa.Float, nullable=True),
        sa.Column("rmse", sa.Float, nullable=True),
        sa.Column("mean_error", sa.Float, nullable=True),
        # Health
        sa.Column("outlier_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("outlier_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "quality_issue_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("quality_rate", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "pii_detected_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "total_pii_redacted", sa.Integer, nullable=False, server_default="0"
        ),
        # Drift
        sa.Column("drift_score", sa.Float, nullable=True),
        sa.Column("baseline_mean", sa.Float, nullable=True),
        sa.Column("baseline_std", sa.Float, nullable=True),
        # Alerts
        sa.Column("alerts_triggered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alerts_by_severity", JSONB, nullable=True),
        # Confidence
        sa.Column("avg_confidence", sa.Float, nullable=True),
        sa.Column("min_confidence", sa.Float, nullable=True),
        sa.Column("max_confidence", sa.Float, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Performance indexes
    op.create_index(
        "idx_perf_tenant_model_period",
        "model_performance_snapshots",
        ["tenant_id", "model_id", "period_start"],
    )
    op.create_index(
        "idx_perf_period_type",
        "model_performance_snapshots",
        ["period_type"],
    )
    op.create_index(
        "idx_perf_model_drift",
        "model_performance_snapshots",
        ["model_id", "drift_score"],
    )


def downgrade() -> None:
    op.drop_index("idx_perf_model_drift")
    op.drop_index("idx_perf_period_type")
    op.drop_index("idx_perf_tenant_model_period")
    op.drop_table("model_performance_snapshots")
