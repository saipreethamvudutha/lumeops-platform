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
    """Alert info."""

    id: str
    model_id: str
    alert_type: str
    severity: str
    message: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


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
