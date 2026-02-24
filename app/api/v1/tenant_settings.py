"""
Tenant Settings & Data Retention API.

Endpoints for managing tenant configuration, data retention policies,
and executing retention cleanup.

Endpoints:
    GET    /api/v1/settings              — Get tenant settings
    PUT    /api/v1/settings              — Update tenant settings
    GET    /api/v1/settings/retention    — Get retention policy
    PUT    /api/v1/settings/retention    — Update retention policy
    POST   /api/v1/settings/retention/cleanup — Run retention cleanup
    POST   /api/v1/settings/retention/preview — Preview cleanup (dry run)

LEARNING NOTE:
    Tenant settings live under /settings rather than /tenants because:
    1. The authenticated user already "is" the tenant (via API key)
    2. There's no need for a tenant ID in the URL — it comes from auth
    3. /settings is the natural REST resource for self-service config
    4. /tenants/{id} would be for a super-admin multi-tenant management
       endpoint (not implemented yet — would be Session 10+)

    The retention cleanup is a POST (not DELETE) because:
    - It's an action, not a resource deletion
    - It supports dry_run mode (preview before delete)
    - It returns a summary of what was deleted
    - Multiple resources are affected (inferences, alerts, webhooks)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    RetentionCleanupResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
    TenantSettingsResponse,
    TenantSettingsUpdateRequest,
)
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.services.data_retention import DataRetentionService

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
#  Tenant Settings
# ══════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=TenantSettingsResponse,
    summary="Get tenant settings",
)
async def get_settings(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> TenantSettingsResponse:
    """
    Get the full settings for the current tenant.

    Returns identity, contact info, plan, timezone, notification config,
    encryption status, and data retention policies.
    """
    service = DataRetentionService(db)
    settings = await service.get_tenant_settings(auth.tenant_id)

    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return TenantSettingsResponse(**settings)


@router.put(
    "",
    response_model=TenantSettingsResponse,
    summary="Update tenant settings",
)
async def update_settings(
    payload: TenantSettingsUpdateRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> TenantSettingsResponse:
    """
    Update tenant settings (name, contact info, timezone, notifications).

    Only provided fields are updated — omitted fields remain unchanged.
    Requires 'admin' scope.
    """
    service = DataRetentionService(db)

    # Build updates dict from non-None values
    updates = {
        k: v
        for k, v in payload.model_dump(exclude_unset=True).items()
        if v is not None
    }

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    result = await service.update_tenant_settings(auth.tenant_id, updates)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return TenantSettingsResponse(**result)


# ══════════════════════════════════════════════════════════════════
#  Data Retention Policy
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/retention",
    response_model=RetentionPolicyResponse,
    summary="Get data retention policy",
)
async def get_retention_policy(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> RetentionPolicyResponse:
    """
    Get the current data retention policy for this tenant.

    Returns TTL settings for inferences, alerts, and webhook deliveries.
    NULL values mean "keep forever" (no auto-deletion).
    """
    service = DataRetentionService(db)
    policy = await service.get_retention_policy(auth.tenant_id)

    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return RetentionPolicyResponse(**policy)


@router.put(
    "/retention",
    response_model=RetentionPolicyResponse,
    summary="Update data retention policy",
)
async def update_retention_policy(
    payload: RetentionPolicyUpdateRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> RetentionPolicyResponse:
    """
    Update data retention policy for this tenant.

    Constraints:
    - inference_retention_days: >= 365 (HIPAA) or null (forever)
    - alert_retention_days: >= 30 or null (forever)
    - webhook_delivery_retention_days: >= 7 or null (forever)

    Only provided fields are updated. Requires 'admin' scope.
    """
    service = DataRetentionService(db)

    kwargs = {}
    data = payload.model_dump(exclude_unset=True)

    if "inference_retention_days" in data:
        kwargs["inference_retention_days"] = data["inference_retention_days"]
    if "alert_retention_days" in data:
        kwargs["alert_retention_days"] = data["alert_retention_days"]
    if "webhook_delivery_retention_days" in data:
        kwargs["webhook_delivery_retention_days"] = data[
            "webhook_delivery_retention_days"
        ]

    if not kwargs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No retention fields to update",
        )

    try:
        result = await service.update_retention_policy(
            auth.tenant_id, **kwargs
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return RetentionPolicyResponse(**result)


# ══════════════════════════════════════════════════════════════════
#  Retention Cleanup
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/retention/preview",
    response_model=RetentionCleanupResponse,
    summary="Preview retention cleanup (dry run)",
)
async def preview_retention_cleanup(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> RetentionCleanupResponse:
    """
    Preview what would be deleted by running retention cleanup.

    This is a dry run — no data is actually deleted. Returns the count
    of records that would be removed based on current retention policies.
    """
    service = DataRetentionService(db)
    result = await service.cleanup_tenant(auth.tenant_id, dry_run=True)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )

    return RetentionCleanupResponse(**result)


@router.post(
    "/retention/cleanup",
    response_model=RetentionCleanupResponse,
    summary="Execute retention cleanup",
)
async def execute_retention_cleanup(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> RetentionCleanupResponse:
    """
    Execute retention cleanup — permanently deletes expired data.

    Deletes records older than the configured TTL for each data type:
    - Inferences older than inference_retention_days
    - Resolved alerts older than alert_retention_days
    - Webhook deliveries older than webhook_delivery_retention_days

    IMPORTANT: Only resolved alerts are deleted. Open and acknowledged
    alerts are never removed, regardless of age.

    Requires 'admin' scope. This action is IRREVERSIBLE.
    """
    service = DataRetentionService(db)
    result = await service.cleanup_tenant(auth.tenant_id, dry_run=False)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )

    return RetentionCleanupResponse(**result)
