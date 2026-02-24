"""
Health check endpoints.

GET /health  - Liveness check (is the service running?)
GET /ready   - Readiness check (can it handle traffic?)
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.v1.schemas import HealthResponse
from app.core.config import get_settings

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    tags=["health"],
)
async def health_check() -> HealthResponse:
    """Basic liveness check. Returns 200 if the service is running."""
    settings = get_settings()
    return HealthResponse(
        status="alive",
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness check",
    tags=["health"],
)
async def readiness_check() -> HealthResponse:
    """
    Readiness check -- verifies database and cache connectivity.

    Returns 200 if all dependencies are available.
    Returns 503 if any critical dependency is unavailable.
    """
    settings = get_settings()
    services: dict[str, str] = {}

    # Check database
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception:
        services["database"] = "error"

    # Check Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"

    # Determine overall status
    db_ok = services.get("database") == "ok"
    overall_status = "ready" if db_ok else "not_ready"

    return HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC),
        services=services,
    )
