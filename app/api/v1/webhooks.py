"""
Webhook Management API.

CRUD endpoints for managing webhook configurations, plus test delivery.

Endpoints:
    POST   /api/v1/webhooks          — Create a new webhook
    GET    /api/v1/webhooks          — List all webhooks for tenant
    GET    /api/v1/webhooks/{id}     — Get single webhook details
    PATCH  /api/v1/webhooks/{id}     — Update webhook configuration
    DELETE /api/v1/webhooks/{id}     — Delete a webhook
    POST   /api/v1/webhooks/{id}/test — Send test delivery
    GET    /api/v1/webhooks/{id}/deliveries — Get delivery history

LEARNING NOTE:
    All endpoints require the 'admin' scope. Webhooks are a configuration
    resource, not a data-plane operation, so they sit behind admin RBAC.

    The signing secret is shown ONCE at creation time (like API keys).
    After that, only a masked version is available. If the user loses
    the secret, they must create a new webhook.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookTestResponse,
    WebhookUpdateRequest,
)
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.webhook import WebhookConfig, WebhookDelivery
from app.services.audit import AuditService
from app.services.webhooks.service import WebhookService, generate_webhook_secret

router = APIRouter()


def _webhook_to_response(wh: WebhookConfig) -> WebhookResponse:
    """Convert a WebhookConfig model to API response."""
    return WebhookResponse(
        id=wh.id,
        name=wh.name,
        url=wh.url,
        description=wh.description,
        events=wh.events or [],
        is_active=wh.is_active,
        last_triggered_at=wh.last_triggered_at,
        last_success_at=wh.last_success_at,
        last_failure_at=wh.last_failure_at,
        last_http_status=wh.last_http_status,
        last_error=wh.last_error,
        consecutive_failures=wh.consecutive_failures or 0,
        total_deliveries=wh.total_deliveries or 0,
        total_failures=wh.total_failures or 0,
        created_at=wh.created_at,
        updated_at=wh.updated_at,
    )


# ══════════════════════════════════════════════════════════════════
#  CREATE
# ══════════════════════════════════════════════════════════════════


@router.post(
    "",
    response_model=WebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook",
    description="Register a new webhook endpoint for event notifications.",
)
async def create_webhook(
    payload: WebhookCreateRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookCreateResponse:
    """Create a new webhook configuration for the tenant."""
    tenant_id = auth.tenant_id

    # Generate signing secret
    secret = generate_webhook_secret()

    webhook = WebhookConfig(
        tenant_id=tenant_id,
        name=payload.name,
        url=payload.url,
        description=payload.description,
        events=payload.events,
        secret=secret,
        headers=payload.headers,
        is_active=True,
    )

    db.add(webhook)
    await db.flush()

    # Audit log
    audit = AuditService(db)
    await audit.log_event(
        tenant_id=tenant_id,
        action="WEBHOOK_CREATED",
        resource_type="webhook",
        resource_id=webhook.id,
        details={
            "name": webhook.name,
            "url": webhook.url,
            "events": webhook.events,
        },
    )

    return WebhookCreateResponse(
        id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        events=webhook.events or [],
        secret=secret,
        is_active=True,
        created_at=webhook.created_at,
    )


# ══════════════════════════════════════════════════════════════════
#  LIST
# ══════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=WebhookListResponse,
    summary="List webhooks",
    description="List all webhook configurations for the tenant.",
)
async def list_webhooks(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookListResponse:
    """List all webhooks for the authenticated tenant."""
    tenant_id = auth.tenant_id

    result = await db.execute(
        select(WebhookConfig)
        .where(WebhookConfig.tenant_id == tenant_id)
        .order_by(WebhookConfig.created_at.desc())
    )
    webhooks = result.scalars().all()

    return WebhookListResponse(
        total=len(webhooks),
        webhooks=[_webhook_to_response(wh) for wh in webhooks],
    )


# ══════════════════════════════════════════════════════════════════
#  GET SINGLE
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Get webhook",
    description="Get details of a specific webhook.",
)
async def get_webhook(
    webhook_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookResponse:
    """Get a single webhook by ID."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == webhook_id,
            WebhookConfig.tenant_id == auth.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    return _webhook_to_response(webhook)


# ══════════════════════════════════════════════════════════════════
#  UPDATE
# ══════════════════════════════════════════════════════════════════


@router.patch(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Update webhook",
    description="Update an existing webhook configuration.",
)
async def update_webhook(
    webhook_id: str,
    payload: WebhookUpdateRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookResponse:
    """Update a webhook's configuration."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == webhook_id,
            WebhookConfig.tenant_id == auth.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Apply partial updates
    changes = {}
    if payload.name is not None:
        webhook.name = payload.name
        changes["name"] = payload.name
    if payload.url is not None:
        webhook.url = payload.url
        changes["url"] = payload.url
    if payload.description is not None:
        webhook.description = payload.description
        changes["description"] = payload.description
    if payload.events is not None:
        webhook.events = payload.events
        changes["events"] = payload.events
    if payload.headers is not None:
        webhook.headers = payload.headers
        changes["headers"] = "updated"
    if payload.is_active is not None:
        webhook.is_active = payload.is_active
        changes["is_active"] = payload.is_active
        # Reset failure counter when re-enabling
        if payload.is_active:
            webhook.consecutive_failures = 0

    webhook.updated_at = datetime.now(UTC)

    # Audit log
    audit = AuditService(db)
    await audit.log_event(
        tenant_id=auth.tenant_id,
        action="WEBHOOK_UPDATED",
        resource_type="webhook",
        resource_id=webhook.id,
        details={"changes": changes},
    )

    return _webhook_to_response(webhook)


# ══════════════════════════════════════════════════════════════════
#  DELETE
# ══════════════════════════════════════════════════════════════════


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete webhook",
    description="Permanently delete a webhook configuration.",
)
async def delete_webhook(
    webhook_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a webhook and its delivery history."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == webhook_id,
            WebhookConfig.tenant_id == auth.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Audit log BEFORE deletion
    audit = AuditService(db)
    await audit.log_event(
        tenant_id=auth.tenant_id,
        action="WEBHOOK_DELETED",
        resource_type="webhook",
        resource_id=webhook.id,
        details={
            "name": webhook.name,
            "url": webhook.url,
        },
    )

    # Delete delivery history first (FK constraint)
    from sqlalchemy import delete

    await db.execute(
        delete(WebhookDelivery).where(
            WebhookDelivery.webhook_id == webhook_id
        )
    )

    await db.delete(webhook)


# ══════════════════════════════════════════════════════════════════
#  TEST DELIVERY
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestResponse,
    summary="Test webhook",
    description="Send a test payload to verify webhook configuration.",
)
async def test_webhook(
    webhook_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookTestResponse:
    """Send a test delivery to verify the webhook endpoint."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == webhook_id,
            WebhookConfig.tenant_id == auth.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    service = WebhookService(db)
    test_result = await service.send_test(webhook)

    # Audit log
    audit = AuditService(db)
    await audit.log_event(
        tenant_id=auth.tenant_id,
        action="WEBHOOK_TEST_SENT",
        resource_type="webhook",
        resource_id=webhook.id,
        status="success" if test_result["success"] else "failure",
        details={
            "http_status": test_result.get("http_status"),
            "message": test_result.get("message"),
        },
    )

    return WebhookTestResponse(**test_result)


# ══════════════════════════════════════════════════════════════════
#  DELIVERY HISTORY
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/{webhook_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
    summary="Delivery history",
    description="Get delivery history for a specific webhook.",
)
async def list_deliveries(
    webhook_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookDeliveryListResponse:
    """Get paginated delivery history for a webhook."""
    # Verify webhook belongs to tenant
    wh_result = await db.execute(
        select(WebhookConfig.id).where(
            WebhookConfig.id == webhook_id,
            WebhookConfig.tenant_id == auth.tenant_id,
        )
    )
    if not wh_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Count total
    count_result = await db.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.webhook_id == webhook_id,
        )
    )
    total = count_result.scalar_one()

    # Fetch deliveries
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.delivered_at.desc())
        .limit(limit)
        .offset(offset)
    )
    deliveries = result.scalars().all()

    return WebhookDeliveryListResponse(
        total=total,
        deliveries=[
            WebhookDeliveryResponse(
                id=d.id,
                event_type=d.event_type,
                event_id=d.event_id,
                http_status=d.http_status,
                response_time_ms=d.response_time_ms,
                success=d.success,
                error=d.error,
                attempt_number=d.attempt_number,
                delivered_at=d.delivered_at,
            )
            for d in deliveries
        ],
    )
