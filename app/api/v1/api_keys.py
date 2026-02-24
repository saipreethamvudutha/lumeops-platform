"""
API Key management endpoints.

POST /api/v1/apikeys     - Create a new API key
GET  /api/v1/apikeys     - List all API keys
DELETE /api/v1/apikeys/{id} - Revoke an API key
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListItem,
    APIKeyListResponse,
)
from app.core.database import get_db_session
from app.core.security import generate_api_key
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.api_key import APIKey
from app.services.audit import AuditService

router = APIRouter()


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    payload: APIKeyCreateRequest,
    request: Request,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> APIKeyCreateResponse:
    """
    Generate a new API key for the tenant.

    The plaintext key is returned ONCE in this response.
    Only the hash is stored in the database.
    Requires 'admin' scope (enforced by dependency).
    """
    plaintext_key, key_hash = generate_api_key()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=payload.expires_in_days)

    api_key = APIKey(
        tenant_id=auth.tenant_id,
        key_hash=key_hash,
        key_suffix=plaintext_key[-6:],
        name=payload.name,
        scopes=payload.scopes,
        expires_at=expires_at,
        is_active=True,
    )

    db.add(api_key)
    await db.flush()

    # Audit log
    audit = AuditService(db)
    await audit.log_api_key_event(
        tenant_id=auth.tenant_id,
        key_id=api_key.id,
        action="API_KEY_CREATED",
        ip_address=request.client.host if request.client else None,
    )

    return APIKeyCreateResponse(
        api_key=plaintext_key,
        name=api_key.name,
        created_at=now,
        expires_at=expires_at,
        scopes=payload.scopes,
    )


@router.get(
    "",
    response_model=APIKeyListResponse,
    summary="List all API keys",
)
async def list_api_keys(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> APIKeyListResponse:
    """List all API keys for the tenant (no plaintext keys shown)."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.tenant_id == auth.tenant_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()

    return APIKeyListResponse(
        keys=[
            APIKeyListItem(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                key_suffix=k.key_suffix,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
                is_active=k.is_active,
                scopes=k.scopes,
            )
            for k in keys
        ]
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    request: Request,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Revoke (deactivate) an API key. Requires 'admin' scope (enforced by dependency)."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.tenant_id == auth.tenant_id,
        )
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    api_key.revoked_at = datetime.now(UTC)
    api_key.revocation_reason = "Revoked by admin"

    # Audit log
    audit = AuditService(db)
    await audit.log_api_key_event(
        tenant_id=auth.tenant_id,
        key_id=key_id,
        action="API_KEY_REVOKED",
        ip_address=request.client.host if request.client else None,
    )

    return {
        "status": "revoked",
        "key_id": key_id,
        "revoked_at": datetime.now(UTC).isoformat(),
    }
