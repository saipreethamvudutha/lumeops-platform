"""initial_schema

Revision ID: 41b66f2e6d1f
Revises:
Create Date: 2026-02-24 00:33:41.898038

Creates all 8 tables for LumeOps Healthcare AI Observability Platform:
  - tenants: Multi-tenant organization registry
  - api_keys: HMAC-SHA256 hashed authentication keys
  - ml_models: Registered ML model definitions
  - baselines: Statistical baselines for drift detection
  - inferences: Core inference log with PII redaction metadata
  - audit_logs: Immutable HIPAA-compliant audit trail
  - data_quality_metrics: Hourly/daily quality aggregations
  - alerts: Alerting for outliers, quality issues, and system errors
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '41b66f2e6d1f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tenants ──────────────────────────────────────────────────────────
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('customer_type', sa.String(50), nullable=True),
        sa.Column('contact_email', sa.String(255), nullable=True),
        sa.Column('contact_phone', sa.String(50), nullable=True),
        sa.Column('plan', sa.String(50), nullable=False, server_default='starter'),
        sa.Column('monthly_fee', sa.Numeric(10, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('encryption_key_id', sa.String(255), nullable=True),
        sa.Column('alert_email', sa.String(255), nullable=True),
        sa.Column('alert_slack_webhook', sa.String(500), nullable=True),
        sa.Column('data_residency', sa.String(50), nullable=False, server_default='us-east-1'),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_tenant_active', 'tenants', ['is_active'])
    op.create_index('idx_tenant_plan', 'tenants', ['plan'])

    # ── api_keys ─────────────────────────────────────────────────────────
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('key_hash', sa.String(128), unique=True, nullable=False),
        sa.Column('key_prefix', sa.String(20), nullable=False, server_default='lum_sk_'),
        sa.Column('key_suffix', sa.String(10), nullable=True),
        sa.Column('name', sa.String(255), nullable=False, server_default='Default Key'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scopes', postgresql.JSONB(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.String(255), nullable=True),
        sa.Column('rate_limit', sa.Integer(), nullable=True),
        sa.Column('ip_whitelist', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_api_key_tenant', 'api_keys', ['tenant_id'])
    op.create_index('idx_api_key_active', 'api_keys', ['is_active'])
    op.create_index('idx_api_key_hash', 'api_keys', ['key_hash'])

    # ── ml_models ────────────────────────────────────────────────────────
    op.create_table(
        'ml_models',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('framework', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('baseline_required_samples', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('outlier_sigma', sa.Float(), nullable=False, server_default='3.0'),
        sa.Column('required_fields', postgresql.JSONB(), nullable=True),
        sa.Column('field_ranges', postgresql.JSONB(), nullable=True),
        sa.Column('field_types', postgresql.JSONB(), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_model_tenant', 'ml_models', ['tenant_id'])
    op.create_index('idx_model_active', 'ml_models', ['is_active'])
    op.create_index('idx_model_tenant_name', 'ml_models', ['tenant_id', 'model_name'], unique=True)

    # ── baselines ────────────────────────────────────────────────────────
    op.create_table(
        'baselines',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_id', sa.String(255), sa.ForeignKey('ml_models.id'), nullable=False),
        sa.Column('mean', sa.Float(), nullable=False),
        sa.Column('std', sa.Float(), nullable=False),
        sa.Column('median', sa.Float(), nullable=False),
        sa.Column('min_val', sa.Float(), nullable=False),
        sa.Column('max_val', sa.Float(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('computation_method', sa.String(50), nullable=False, server_default='initial'),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_baseline_model_current', 'baselines', ['model_id', 'is_current'])
    op.create_index('idx_baseline_tenant', 'baselines', ['tenant_id'])

    # ── inferences ───────────────────────────────────────────────────────
    op.create_table(
        'inferences',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_id', sa.String(255), sa.ForeignKey('ml_models.id'), nullable=False),
        sa.Column('prediction', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        # Protected input features (Fernet-encrypted JSON)
        sa.Column('input_features_encrypted', sa.Text(), nullable=False),
        # PHI redaction metadata
        sa.Column('pii_detected', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('pii_redaction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pii_types_found', postgresql.JSONB(), nullable=True),
        # Classification metadata
        sa.Column('classification_summary', postgresql.JSONB(), nullable=True),
        sa.Column('high_sensitivity_fields', postgresql.JSONB(), nullable=True),
        sa.Column('max_sensitivity_level', sa.String(20), nullable=True),
        sa.Column('sensitivity_counts', postgresql.JSONB(), nullable=True),
        # Data quality flags
        sa.Column('has_quality_issues', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('quality_issues', postgresql.JSONB(), nullable=True),
        # Baseline comparison
        sa.Column('is_outlier', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('outlier_reason', sa.String(500), nullable=True),
        # Audit information
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_id', sa.String(255), unique=True, nullable=True),
        sa.Column('source_ip', sa.String(45), nullable=True),
        sa.Column('api_version', sa.String(10), nullable=True, server_default='v1'),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        # Ground truth
        sa.Column('ground_truth', sa.Float(), nullable=True),
        sa.Column('ground_truth_received_at', sa.DateTime(timezone=True), nullable=True),
        # Data type tracking
        sa.Column('contains_clinical_data', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('contains_behavioral_health', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('contains_genetic_data', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('data_categories_present', postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_inf_tenant_model_time', 'inferences', ['tenant_id', 'model_id', 'received_at'])
    op.create_index('idx_inf_received_at', 'inferences', ['received_at'])
    op.create_index('idx_inf_is_outlier', 'inferences', ['is_outlier'])
    op.create_index('idx_inf_has_quality_issues', 'inferences', ['has_quality_issues'])
    op.create_index('idx_inf_request_id', 'inferences', ['request_id'])
    op.create_index('idx_inf_max_sensitivity', 'inferences', ['max_sensitivity_level'])
    op.create_index('idx_inf_contains_clinical', 'inferences', ['contains_clinical_data'])
    op.create_index('idx_inf_contains_behavioral', 'inferences', ['contains_behavioral_health'])
    op.create_index('idx_inf_contains_genetic', 'inferences', ['contains_genetic_data'])

    # ── audit_logs ───────────────────────────────────────────────────────
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('api_key_prefix', sa.String(20), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('pii_detected', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('pii_types', postgresql.JSONB(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_audit_tenant_time', 'audit_logs', ['tenant_id', 'timestamp'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])

    # ── data_quality_metrics ─────────────────────────────────────────────
    op.create_table(
        'data_quality_metrics',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_id', sa.String(255), sa.ForeignKey('ml_models.id'), nullable=False),
        sa.Column('total_inferences', sa.Integer(), nullable=False),
        sa.Column('inferences_with_issues', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quality_rate', sa.Float(), nullable=False),
        sa.Column('missing_fields_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('null_values_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('out_of_range_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('type_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_pii_redacted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pii_breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_type', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_dq_tenant_model', 'data_quality_metrics', ['tenant_id', 'model_id'])
    op.create_index('idx_dq_period', 'data_quality_metrics', ['period_end'])

    # ── alerts ───────────────────────────────────────────────────────────
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('tenant_id', sa.String(255), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_id', sa.String(255), sa.ForeignKey('ml_models.id'), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('inference_id', sa.String(255), sa.ForeignKey('inferences.id'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(255), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notified_email', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('notified_slack', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_alert_tenant', 'alerts', ['tenant_id'])
    op.create_index('idx_alert_unresolved', 'alerts', ['resolved_at'])
    op.create_index('idx_alert_triggered', 'alerts', ['triggered_at'])
    op.create_index('idx_alert_model', 'alerts', ['model_id'])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table('alerts')
    op.drop_table('data_quality_metrics')
    op.drop_table('audit_logs')
    op.drop_table('inferences')
    op.drop_table('baselines')
    op.drop_table('ml_models')
    op.drop_table('api_keys')
    op.drop_table('tenants')
