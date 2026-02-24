"""
Model registration and management endpoints.

POST /api/v1/models      - Register a new model
GET  /api/v1/models      - List registered models
GET  /api/v1/models/{id} - Get model details
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import ModelRegisterRequest, ModelResponse
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.model import MLModel

router = APIRouter()


@router.post(
    "",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new model",
)
async def register_model(
    payload: ModelRegisterRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> ModelResponse:
    """
    Register an AI model for monitoring.

    Define required fields, ranges, and types for data quality checks.
    """
    # Check for duplicate
    existing = await db.execute(
        select(MLModel).where(
            MLModel.tenant_id == auth.tenant_id,
            MLModel.model_name == payload.model_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{payload.model_name}' already exists",
        )

    model = MLModel(
        tenant_id=auth.tenant_id,
        model_name=payload.model_name,
        model_version=payload.model_version,
        description=payload.description,
        framework=payload.framework,
        required_fields=payload.required_fields,
        field_ranges=payload.field_ranges,
        field_types=payload.field_types,
        tags=payload.tags,
        is_active=True,
    )

    db.add(model)
    await db.flush()

    return ModelResponse(
        id=model.id,
        model_name=model.model_name,
        model_version=model.model_version,
        description=model.description,
        is_active=model.is_active,
        baseline_required_samples=model.baseline_required_samples,
        outlier_sigma=model.outlier_sigma,
        created_at=model.created_at,
    )


@router.get(
    "",
    response_model=list[ModelResponse],
    summary="List registered models",
)
async def list_models(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> list[ModelResponse]:
    """List all models registered for the tenant."""
    result = await db.execute(
        select(MLModel)
        .where(MLModel.tenant_id == auth.tenant_id)
        .order_by(MLModel.created_at.desc())
    )
    models = result.scalars().all()

    return [
        ModelResponse(
            id=m.id,
            model_name=m.model_name,
            model_version=m.model_version,
            description=m.description,
            is_active=m.is_active,
            baseline_required_samples=m.baseline_required_samples,
            outlier_sigma=m.outlier_sigma,
            created_at=m.created_at,
        )
        for m in models
    ]


@router.get(
    "/{model_id}",
    response_model=ModelResponse,
    summary="Get model details",
)
async def get_model(
    model_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> ModelResponse:
    """Get details of a specific model."""
    result = await db.execute(
        select(MLModel).where(
            MLModel.id == model_id,
            MLModel.tenant_id == auth.tenant_id,
        )
    )
    model = result.scalar_one_or_none()

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    return ModelResponse(
        id=model.id,
        model_name=model.model_name,
        model_version=model.model_version,
        description=model.description,
        is_active=model.is_active,
        baseline_required_samples=model.baseline_required_samples,
        outlier_sigma=model.outlier_sigma,
        created_at=model.created_at,
    )
