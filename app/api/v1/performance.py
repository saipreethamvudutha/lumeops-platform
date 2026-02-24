"""
Model Performance Tracking API.

Endpoints for viewing model performance metrics, submitting ground truth,
and monitoring prediction drift.

Endpoints:
    GET    /api/v1/models/overview      — All models with summary stats
    GET    /api/v1/models/{id}/perf     — Detailed model performance
    GET    /api/v1/models/{id}/perf/ts  — Performance timeseries for charts
    POST   /api/v1/models/{id}/gt       — Submit ground truth for one inference
    POST   /api/v1/models/gt/batch      — Batch submit ground truth

LEARNING NOTE:
    Model performance tracking is the core differentiator of ML observability
    platforms vs. generic monitoring tools. Traditional APM tracks request
    latency and error rates; ML monitoring adds:

    1. PREDICTION DISTRIBUTION: Are predictions shifting? (drift detection)
    2. ACCURACY METRICS: How close are predictions to reality? (requires ground truth)
    3. DATA QUALITY: Is input data degrading? (feature monitoring)
    4. OUTLIER RATE: Are unusual predictions increasing? (anomaly monitoring)

    Healthcare-specific considerations:
    - Ground truth may come days/weeks later (e.g., patient outcome after treatment)
    - Accuracy metrics must NOT include patient identifiers
    - Drift in a clinical model could indicate population shift or model degradation
    - Both are reportable events under some regulatory frameworks

    The ground truth pipeline uses a simple PATCH-style approach:
    submit the actual outcome for an inference_id, and accuracy metrics
    automatically become available in the performance dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    GroundTruthBatchRequest,
    GroundTruthBatchResponse,
    GroundTruthSubmitRequest,
    GroundTruthSubmitResponse,
    ModelOverviewItem,
    ModelPerformanceSummary,
    ModelsOverviewResponse,
    PerformanceTimeseriesPoint,
    PerformanceTimeseriesResponse,
)
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.services.monitoring.performance import PerformanceService

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
#  Models Overview
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/overview",
    response_model=ModelsOverviewResponse,
    summary="All models with performance summary",
)
async def models_overview(
    days: int = Query(default=7, ge=1, le=365),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> ModelsOverviewResponse:
    """
    Get all models with their recent performance summary.

    Returns a list of models with volume, outlier rate, quality rate,
    and ground truth coverage for the specified time window.
    """
    service = PerformanceService(db)
    models = await service.get_models_overview(
        tenant_id=auth.tenant_id, days=days
    )

    from datetime import UTC, datetime

    return ModelsOverviewResponse(
        total=len(models),
        days=days,
        models=[ModelOverviewItem(**m) for m in models],
        generated_at=datetime.now(UTC),
    )


# ══════════════════════════════════════════════════════════════════
#  Model Performance Detail
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/{model_id}/performance",
    response_model=ModelPerformanceSummary,
    summary="Detailed model performance metrics",
)
async def model_performance(
    model_id: str,
    days: int = Query(default=7, ge=1, le=365),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> ModelPerformanceSummary:
    """
    Get comprehensive performance metrics for a specific model.

    Includes prediction distribution, accuracy (if ground truth available),
    health metrics (outlier rate, quality rate), drift detection, and
    confidence distribution.
    """
    service = PerformanceService(db)
    summary = await service.get_model_summary(
        model_id=model_id,
        tenant_id=auth.tenant_id,
        days=days,
    )

    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    return ModelPerformanceSummary(**summary)


# ══════════════════════════════════════════════════════════════════
#  Performance Timeseries
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/{model_id}/performance/timeseries",
    response_model=PerformanceTimeseriesResponse,
    summary="Performance timeseries for charts",
)
async def performance_timeseries(
    model_id: str,
    days: int = Query(default=7, ge=1, le=90),
    granularity: str = Query(
        default="daily",
        pattern="^(hourly|daily)$",
    ),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> PerformanceTimeseriesResponse:
    """
    Get time-bucketed performance data for charts.

    Returns one data point per time bucket (hourly or daily), each
    containing volume, prediction stats, health metrics, and accuracy.
    """
    service = PerformanceService(db)
    series = await service.get_performance_timeseries(
        model_id=model_id,
        tenant_id=auth.tenant_id,
        days=days,
        granularity=granularity,
    )

    from datetime import UTC, datetime

    return PerformanceTimeseriesResponse(
        model_id=model_id,
        days=days,
        granularity=granularity,
        series=[PerformanceTimeseriesPoint(**p) for p in series],
        generated_at=datetime.now(UTC),
    )


# ══════════════════════════════════════════════════════════════════
#  Ground Truth Submission
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/{model_id}/ground-truth/{inference_id}",
    response_model=GroundTruthSubmitResponse,
    summary="Submit ground truth for an inference",
)
async def submit_ground_truth(
    model_id: str,
    inference_id: str,
    payload: GroundTruthSubmitRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("ingest")),
    db: AsyncSession = Depends(get_db_session),
) -> GroundTruthSubmitResponse:
    """
    Submit the actual outcome (ground truth) for a specific inference.

    Once ground truth is submitted, accuracy metrics (MAE, RMSE) become
    available in the model performance dashboard. Ground truth can be
    submitted days or weeks after the original inference — common in
    healthcare where outcomes are known only after treatment.

    Requires 'ingest' scope (same as submitting inferences).
    """
    service = PerformanceService(db)
    result = await service.submit_ground_truth(
        inference_id=inference_id,
        tenant_id=auth.tenant_id,
        ground_truth=payload.ground_truth,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inference not found",
        )

    return GroundTruthSubmitResponse(**result)


@router.post(
    "/ground-truth/batch",
    response_model=GroundTruthBatchResponse,
    summary="Batch submit ground truth",
)
async def submit_ground_truth_batch(
    payload: GroundTruthBatchRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("ingest")),
    db: AsyncSession = Depends(get_db_session),
) -> GroundTruthBatchResponse:
    """
    Submit ground truth for multiple inferences at once.

    Accepts up to 500 inference_id + ground_truth pairs.
    Each is processed independently — failures don't affect other items.

    Requires 'ingest' scope.
    """
    service = PerformanceService(db)
    result = await service.submit_ground_truth_batch(
        tenant_id=auth.tenant_id,
        items=[item.model_dump() for item in payload.items],
    )

    return GroundTruthBatchResponse(**result)
