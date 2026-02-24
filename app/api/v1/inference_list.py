"""
Inference listing endpoints for the log viewer.

GET /api/v1/inferences          - List inferences with pagination and filters
GET /api/v1/inferences/{id}     - Get single inference details

LEARNING NOTE ON THE INFERENCE LOG VIEWER:
    Healthcare compliance officers need to:
    1. Search for specific inferences ("show me all inferences with PHI")
    2. Filter by model, date range, sensitivity level
    3. See what PII was redacted and what data types were present
    4. Verify that encryption is active on all records

    The encrypted feature data is NOT returned in the list view —
    only metadata. This is intentional:
    - Reduces response size
    - Avoids unnecessary decryption (expensive)
    - Follows minimum necessary principle (HIPAA 164.502(b))
    - Encrypted data only decrypted when explicitly requested
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.inference import Inference

router = APIRouter()


@router.get(
    "",
    summary="List inferences with pagination and filters",
    description=(
        "Returns inference records with metadata (no encrypted data). "
        "Supports filtering by model, date range, sensitivity, and PII detection."
    ),
)
async def list_inferences(
    model_id: str | None = Query(None, description="Filter by model ID"),
    days: int = Query(7, ge=1, le=365, description="Time range in days"),
    has_pii: bool | None = Query(None, description="Filter by PII detection"),
    is_outlier: bool | None = Query(None, description="Filter by outlier status"),
    has_quality_issues: bool | None = Query(None, description="Filter by quality issues"),
    max_sensitivity: str | None = Query(
        None,
        pattern="^(CRITICAL|HIGH|MODERATE|LOW)$",
        description="Filter by max sensitivity level",
    ),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    List inference records for the authenticated tenant.

    Returns metadata only (no decrypted features).
    Follows HIPAA minimum necessary principle.
    """
    tenant_id = auth.tenant_id
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Build filters
    filters = [
        Inference.tenant_id == tenant_id,
        Inference.received_at >= cutoff,
    ]
    if model_id:
        filters.append(Inference.model_id == model_id)
    if has_pii is not None:
        filters.append(Inference.pii_detected == has_pii)
    if is_outlier is not None:
        filters.append(Inference.is_outlier == is_outlier)
    if has_quality_issues is not None:
        filters.append(Inference.has_quality_issues == has_quality_issues)
    if max_sensitivity:
        filters.append(Inference.max_sensitivity_level == max_sensitivity)

    # Count total matching records
    count_result = await db.execute(
        select(func.count(Inference.id)).where(*filters)
    )
    total = count_result.scalar_one()

    # Fetch records
    result = await db.execute(
        select(Inference)
        .where(*filters)
        .order_by(Inference.received_at.desc())
        .limit(limit)
        .offset(offset)
    )
    inferences = result.scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "inferences": [
            {
                "id": inf.id,
                "model_id": inf.model_id,
                "prediction": inf.prediction,
                "confidence": inf.confidence,
                # PII metadata
                "pii_detected": inf.pii_detected,
                "pii_redaction_count": inf.pii_redaction_count,
                "pii_types_found": inf.pii_types_found,
                # Classification
                "max_sensitivity_level": inf.max_sensitivity_level,
                "sensitivity_counts": inf.sensitivity_counts,
                "contains_clinical_data": inf.contains_clinical_data,
                "contains_behavioral_health": inf.contains_behavioral_health,
                "contains_genetic_data": inf.contains_genetic_data,
                # Quality
                "has_quality_issues": inf.has_quality_issues,
                "is_outlier": inf.is_outlier,
                "outlier_reason": inf.outlier_reason,
                # Encryption
                "encryption_key_version": inf.encryption_key_version,
                # Audit
                "received_at": inf.received_at.isoformat(),
                "request_id": inf.request_id,
                "source_ip": inf.source_ip,
            }
            for inf in inferences
        ],
    }


@router.get(
    "/{inference_id}",
    summary="Get inference details",
    description="Returns full metadata for a single inference (no decrypted features).",
)
async def get_inference(
    inference_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get detailed metadata for a single inference record."""
    result = await db.execute(
        select(Inference).where(
            Inference.id == inference_id,
            Inference.tenant_id == auth.tenant_id,
        )
    )
    inf = result.scalar_one_or_none()

    if inf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inference not found",
        )

    return {
        "id": inf.id,
        "tenant_id": inf.tenant_id,
        "model_id": inf.model_id,
        "prediction": inf.prediction,
        "confidence": inf.confidence,
        # PII
        "pii_detected": inf.pii_detected,
        "pii_redaction_count": inf.pii_redaction_count,
        "pii_types_found": inf.pii_types_found,
        # Classification
        "classification_summary": inf.classification_summary,
        "high_sensitivity_fields": inf.high_sensitivity_fields,
        "max_sensitivity_level": inf.max_sensitivity_level,
        "sensitivity_counts": inf.sensitivity_counts,
        "contains_clinical_data": inf.contains_clinical_data,
        "contains_behavioral_health": inf.contains_behavioral_health,
        "contains_genetic_data": inf.contains_genetic_data,
        "data_categories_present": inf.data_categories_present,
        # Quality
        "has_quality_issues": inf.has_quality_issues,
        "quality_issues": inf.quality_issues,
        "is_outlier": inf.is_outlier,
        "outlier_reason": inf.outlier_reason,
        # Encryption
        "encryption_key_version": inf.encryption_key_version,
        "encrypted": True,  # Always encrypted
        # Audit
        "received_at": inf.received_at.isoformat(),
        "request_id": inf.request_id,
        "source_ip": inf.source_ip,
        "api_version": inf.api_version,
        "metadata": inf.metadata_json,
        # Ground truth
        "ground_truth": inf.ground_truth,
        "ground_truth_received_at": (
            inf.ground_truth_received_at.isoformat()
            if inf.ground_truth_received_at
            else None
        ),
    }
