"""
Pydantic schemas for API request/response validation.

All external data passes through these schemas.
No raw user input reaches the database without validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ══════════════════════════════════════════════════════════════════
#  Inference Schemas
# ══════════════════════════════════════════════════════════════════


class InferenceRequest(BaseModel):
    """What the customer sends to POST /api/v1/ingest."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="AI model identifier",
    )
    prediction: float = Field(
        ...,
        description="Model prediction value",
    )
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Prediction confidence (0-1)",
    )
    input_features: dict[str, Any] = Field(
        ...,
        description="Input features (will be scanned for PII and redacted)",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Optional metadata (not scanned for PII)",
    )
    request_id: str | None = Field(
        None,
        max_length=255,
        description="Optional client-side request ID for idempotency",
    )

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("model_id cannot be empty")
        return v

    @field_validator("input_features")
    @classmethod
    def validate_input_features(cls, v: dict) -> dict:
        if not v:
            raise ValueError("input_features cannot be empty")
        # Limit size to prevent abuse (1MB max when serialized)
        import orjson
        serialized = orjson.dumps(v)
        if len(serialized) > 1_048_576:  # 1MB
            raise ValueError("input_features exceeds maximum size of 1MB")
        return v


class InferenceResponse(BaseModel):
    """Response to inference ingestion."""

    status: str = "received"
    message: str
    inference_id: str
    pii_redacted: int
    data_quality_issues: list[str]
    alerts: list[dict[str, str]] | None = None
    timestamp: datetime


# ══════════════════════════════════════════════════════════════════
#  Dashboard Schemas
# ══════════════════════════════════════════════════════════════════


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics."""

    inferences: dict[str, int]  # today, this_week, this_month, all_time
    data_quality: dict[str, Any]
    predictions: dict[str, Any]
    pii_protection: dict[str, Any]
    alerts: dict[str, Any]
    system: dict[str, Any]
    generated_at: datetime


# ══════════════════════════════════════════════════════════════════
#  API Key Schemas
# ══════════════════════════════════════════════════════════════════


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name for this key",
    )
    expires_in_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description="Key expiration in days",
    )
    scopes: list[str] = Field(
        default=["ingest", "read"],
        description="Permission scopes for this key",
    )

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        valid_scopes = {"ingest", "read", "audit", "admin"}
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(
                    f"Invalid scope: {scope}. Valid: {valid_scopes}"
                )
        return v


class APIKeyCreateResponse(BaseModel):
    """Response with the newly created API key (shown ONCE)."""

    api_key: str
    name: str
    created_at: datetime
    expires_at: datetime
    scopes: list[str]
    warning: str = "Save this key now. You will not see it again."


class APIKeyListItem(BaseModel):
    """API key info for listing (no plaintext key)."""

    id: str
    name: str
    key_prefix: str
    key_suffix: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    scopes: list[str] | None


class APIKeyListResponse(BaseModel):
    """List of API keys."""

    keys: list[APIKeyListItem]


# ══════════════════════════════════════════════════════════════════
#  Compliance Report Schemas
# ══════════════════════════════════════════════════════════════════


class ComplianceReportRequest(BaseModel):
    """Parameters for compliance report generation."""

    model_id: str | None = None
    days: int = Field(default=30, ge=1, le=365)
    format: str = Field(default="json", pattern="^(json|pdf)$")


class ComplianceChecklistItem(BaseModel):
    """Single item in the compliance checklist."""

    requirement: str
    status: str  # PASS, FAIL, N/A
    evidence: str


class ComplianceReportResponse(BaseModel):
    """HIPAA compliance report."""

    report_id: str
    generated_at: datetime
    period: dict[str, Any]
    executive_summary: dict[str, Any]
    personal_information_safeguarding: dict[str, Any]
    access_controls: dict[str, Any]
    audit_logging: dict[str, Any]
    compliance_checklist: list[ComplianceChecklistItem]


# ══════════════════════════════════════════════════════════════════
#  Model Registration Schemas
# ══════════════════════════════════════════════════════════════════


class ModelRegisterRequest(BaseModel):
    """Request to register a new model for monitoring."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=255)
    model_version: str | None = None
    description: str | None = None
    framework: str | None = None
    required_fields: list[str] | None = None
    field_ranges: dict[str, dict[str, float]] | None = None
    field_types: dict[str, str] | None = None
    tags: dict[str, str] | None = None


class ModelResponse(BaseModel):
    """Model info response."""

    id: str
    model_name: str
    model_version: str | None
    description: str | None
    is_active: bool
    baseline_required_samples: int
    outlier_sigma: float
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  Alert Schemas
# ══════════════════════════════════════════════════════════════════


class AlertResponse(BaseModel):
    """Alert info (basic)."""

    id: str
    model_id: str
    alert_type: str
    severity: str
    message: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertDetailResponse(BaseModel):
    """Full alert details including metadata and resolution info."""

    id: str
    model_id: str
    alert_type: str
    severity: str
    message: str
    details: dict[str, Any] | None
    triggered_at: datetime
    inference_id: str | None
    # Resolution workflow
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    # Notification status
    notified_email: bool
    notified_slack: bool
    # Timestamps
    created_at: datetime


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    total: int
    limit: int
    offset: int
    has_more: bool
    alerts: list[AlertDetailResponse]


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""

    model_config = ConfigDict(extra="forbid")

    acknowledged_by: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Who is acknowledging this alert (name or email)",
    )


class AlertResolveRequest(BaseModel):
    """Request to resolve an alert."""

    model_config = ConfigDict(extra="forbid")

    resolution_note: str | None = Field(
        None,
        max_length=2000,
        description="Optional note about how the alert was resolved",
    )


class AlertStatsResponse(BaseModel):
    """Aggregated alert statistics."""

    total_active: int
    total_acknowledged: int
    total_resolved: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    mean_time_to_acknowledge_minutes: float | None
    mean_time_to_resolve_minutes: float | None
    generated_at: datetime


class AlertBulkActionRequest(BaseModel):
    """Bulk acknowledge or resolve multiple alerts."""

    model_config = ConfigDict(extra="forbid")

    alert_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of alert IDs to act on",
    )
    acknowledged_by: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Who is acknowledging (required for acknowledge action)",
    )


class AlertBulkActionResponse(BaseModel):
    """Result of a bulk action."""

    processed: int
    skipped: int
    alert_ids: list[str]


# ══════════════════════════════════════════════════════════════════
#  Health Check
# ══════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime
    services: dict[str, str] | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str
    request_id: str | None = None


# ══════════════════════════════════════════════════════════════════
#  Webhook Schemas
# ══════════════════════════════════════════════════════════════════


class WebhookCreateRequest(BaseModel):
    """Request to create a new webhook configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-friendly label for this webhook",
    )
    url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        description="Delivery URL (must be HTTPS in production)",
    )
    description: str | None = Field(
        None,
        max_length=1000,
        description="Optional description of what this webhook does",
    )
    events: list[str] = Field(
        ...,
        min_length=1,
        description="Event types to subscribe to",
    )
    headers: dict[str, str] | None = Field(
        None,
        description="Optional custom headers to include with deliveries",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        v = v.strip()
        if not v.startswith(("https://", "http://")):
            raise ValueError("URL must start with https:// or http://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        """Validate event types against allowed set."""
        valid_events = {
            "alert_created",
            "outlier_detected",
            "pii_detected",
            "data_quality_issue",
            "key_rotated",
            "compliance_report",
        }
        for event in v:
            if event not in valid_events:
                raise ValueError(
                    f"Invalid event type: {event}. "
                    f"Valid types: {sorted(valid_events)}"
                )
        return v


class WebhookUpdateRequest(BaseModel):
    """Request to update an existing webhook."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    url: str | None = Field(None, min_length=10, max_length=2048)
    description: str | None = None
    events: list[str] | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v.startswith(("https://", "http://")):
                raise ValueError("URL must start with https:// or http://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            valid_events = {
                "alert_created", "outlier_detected", "pii_detected",
                "data_quality_issue", "key_rotated", "compliance_report",
            }
            for event in v:
                if event not in valid_events:
                    raise ValueError(
                        f"Invalid event type: {event}. "
                        f"Valid types: {sorted(valid_events)}"
                    )
        return v


class WebhookResponse(BaseModel):
    """Webhook info response (secret partially masked)."""

    id: str
    name: str
    url: str
    description: str | None
    events: list[str]
    is_active: bool
    # Delivery tracking
    last_triggered_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_http_status: int | None
    last_error: str | None
    consecutive_failures: int
    total_deliveries: int
    total_failures: int
    # Metadata
    created_at: datetime
    updated_at: datetime


class WebhookCreateResponse(BaseModel):
    """Response after creating a webhook (includes full secret once)."""

    id: str
    name: str
    url: str
    events: list[str]
    secret: str
    is_active: bool
    created_at: datetime
    warning: str = (
        "Save the signing secret now. "
        "You will not be able to see it again."
    )


class WebhookListResponse(BaseModel):
    """List of webhooks."""

    total: int
    webhooks: list[WebhookResponse]


class WebhookTestResponse(BaseModel):
    """Result of a webhook test delivery."""

    success: bool
    http_status: int | None
    response_body: str | None
    message: str


class WebhookDeliveryResponse(BaseModel):
    """Individual delivery record."""

    id: str
    event_type: str
    event_id: str | None
    http_status: int | None
    response_time_ms: int | None
    success: bool
    error: str | None
    attempt_number: int
    delivered_at: datetime


class WebhookDeliveryListResponse(BaseModel):
    """List of webhook deliveries."""

    total: int
    deliveries: list[WebhookDeliveryResponse]


# ══════════════════════════════════════════════════════════════════
#  Model Performance Schemas
# ══════════════════════════════════════════════════════════════════


class ModelPerformanceSummary(BaseModel):
    """Comprehensive model performance metrics."""

    model: dict[str, Any]
    period: dict[str, Any]
    volume: dict[str, Any]
    predictions: dict[str, Any]
    accuracy: dict[str, Any]
    health: dict[str, Any]
    confidence: dict[str, Any]
    drift: dict[str, Any]
    alerts: dict[str, Any]
    generated_at: datetime


class ModelOverviewItem(BaseModel):
    """Summary stats for a single model in the models list."""

    id: str
    model_name: str
    model_version: str | None
    framework: str | None
    is_active: bool
    created_at: datetime | None
    total_inferences: int
    recent_inferences: int
    recent_outliers: int
    recent_quality_issues: int
    outlier_rate: float
    quality_rate: float
    prediction_mean: float | None
    avg_confidence: float | None
    ground_truth_coverage: float
    last_inference_at: datetime | None


class ModelsOverviewResponse(BaseModel):
    """List of models with performance overview."""

    total: int
    days: int
    models: list[ModelOverviewItem]
    generated_at: datetime


class PerformanceTimeseriesPoint(BaseModel):
    """Single data point in performance timeseries."""

    timestamp: datetime
    total_inferences: int
    with_ground_truth: int
    prediction_mean: float | None
    prediction_std: float | None
    prediction_min: float | None
    prediction_max: float | None
    outlier_count: int
    outlier_rate: float
    quality_issue_count: int
    quality_rate: float
    pii_inferences: int
    total_pii_redacted: int
    avg_confidence: float | None
    mae: float | None
    rmse: float | None


class PerformanceTimeseriesResponse(BaseModel):
    """Time-bucketed performance data for charts."""

    model_id: str
    days: int
    granularity: str
    series: list[PerformanceTimeseriesPoint]
    generated_at: datetime


class GroundTruthSubmitRequest(BaseModel):
    """Submit ground truth for a single inference."""

    model_config = ConfigDict(extra="forbid")

    ground_truth: float = Field(
        ...,
        description="Actual observed outcome value",
    )


class GroundTruthSubmitResponse(BaseModel):
    """Response after submitting ground truth."""

    inference_id: str
    model_id: str
    prediction: float
    ground_truth: float
    absolute_error: float
    submitted_at: datetime


class GroundTruthBatchItem(BaseModel):
    """Single item in a ground truth batch submission."""

    model_config = ConfigDict(extra="forbid")

    inference_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="ID of the inference to attach ground truth to",
    )
    ground_truth: float = Field(
        ...,
        description="Actual observed outcome value",
    )


class GroundTruthBatchRequest(BaseModel):
    """Batch ground truth submission (up to 500 items)."""

    model_config = ConfigDict(extra="forbid")

    items: list[GroundTruthBatchItem] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of inference ID + ground truth pairs",
    )


class GroundTruthBatchResponse(BaseModel):
    """Result of batch ground truth submission."""

    processed: int
    skipped: int
    total: int
    errors: list[dict[str, str]] | None = None
