"""
Authentication middleware for API key validation.

Every request to protected endpoints must include a valid API key.
The key is hashed and compared against the database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import hash_api_key
from app.models.api_key import APIKey
from app.models.tenant import Tenant

security_scheme = HTTPBearer(
    scheme_name="API Key",
    description="API key in Bearer token format: Bearer lum_sk_xxxxx",
)


class AuthenticatedRequest:
    """Holds the authenticated tenant and API key info for the request."""

    __slots__ = ("tenant_id", "tenant", "api_key_id", "scopes", "plan")

    def __init__(
        self,
        tenant_id: str,
        tenant: Tenant,
        api_key_id: str,
        scopes: list[str],
        plan: str,
    ):
        self.tenant_id = tenant_id
        self.tenant = tenant
        self.api_key_id = api_key_id
        self.scopes = scopes
        self.plan = plan


async def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> AuthenticatedRequest:
    """
    Validate API key and return the authenticated tenant.

    This is the main authentication dependency for all protected endpoints.

    Steps:
    1. Extract bearer token from Authorization header
    2. Hash the token
    3. Look up the hash in the database
    4. Verify the key is active and not expired
    5. Update last_used_at timestamp
    6. Return tenant info

    Raises HTTPException 401 if authentication fails.
    """
    token = credentials.credentials

    # Validate prefix
    settings = get_settings()
    if not token.startswith(settings.API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Hash the key for lookup
    key_hash = hash_api_key(token)

    # Look up in database
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active.is_(True),
        )
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check IP whitelist (if configured)
    if api_key.ip_whitelist:
        client_ip = request.client.host if request.client else None
        if client_ip and client_ip not in api_key.ip_whitelist:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request from unauthorized IP address",
            )

    # Get tenant
    tenant_result = await db.execute(
        select(Tenant).where(
            Tenant.id == api_key.tenant_id,
            Tenant.is_active.is_(True),
        )
    )
    tenant = tenant_result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found or inactive",
        )

    # Update last_used_at (fire-and-forget, don't block the request)
    await db.execute(
        update(APIKey)
        .where(APIKey.id == api_key.id)
        .values(last_used_at=datetime.now(UTC))
    )

    return AuthenticatedRequest(
        tenant_id=tenant.id,
        tenant=tenant,
        api_key_id=api_key.id,
        scopes=api_key.scopes or ["ingest", "read"],
        plan=tenant.plan,
    )


def require_scope(scope: str):
    """
    Dependency that checks if the API key has the required scope.

    Usage:
        @router.post("/admin", dependencies=[Depends(require_scope("admin"))])
    """

    async def _check_scope(
        auth: AuthenticatedRequest = Depends(get_current_tenant),
    ) -> AuthenticatedRequest:
        if scope not in auth.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key does not have required scope: {scope}",
            )
        return auth

    return _check_scope


def require_scopes(*scopes: str):
    """
    Dependency that checks if the API key has ALL of the required scopes.

    Usage:
        @router.get("/sensitive", dependencies=[Depends(require_scopes("read", "audit"))])
    """

    async def _check_scopes(
        auth: AuthenticatedRequest = Depends(get_current_tenant),
    ) -> AuthenticatedRequest:
        missing = [s for s in scopes if s not in auth.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope(s): {', '.join(missing)}",
            )
        return auth

    return _check_scopes
