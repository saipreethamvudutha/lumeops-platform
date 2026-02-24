"""
LumeOps Application Entry Point.

HIPAA-compliant Healthcare AI Observability Platform.

This module creates the FastAPI application with:
- Security middleware (CORS, trusted hosts)
- API routing (v1 prefix)
- Health checks
- Startup/shutdown lifecycle hooks
- Global error handling
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import (
    alerts, api_keys, compliance, dashboard, encryption, health,
    inference_list, ingest, models, performance, timeseries, webhooks, ws,
)
from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.core.elasticsearch import close_es_client, setup_audit_indices
from app.core.logging import get_logger, setup_logging
from app.core.pubsub import event_publisher

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────────────
    setup_logging()
    logger.info(
        "starting_lumeops",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    # Initialize database tables (dev only; production uses Alembic)
    if settings.is_development:
        await init_db()
        logger.info("database_initialized")

    # Initialize Elasticsearch audit indices
    es_ok = await setup_audit_indices()
    if es_ok:
        logger.info("elasticsearch_audit_indices_ready")
    else:
        logger.warning("elasticsearch_audit_indices_unavailable")

    # Initialize Redis pub/sub publisher for real-time WebSocket events
    await event_publisher.connect()
    logger.info("pubsub_publisher_initialized")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await event_publisher.close()
    await close_es_client()
    await close_db()
    logger.info("lumeops_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="LumeOps API",
        description=(
            "HIPAA-compliant Healthcare AI Observability Platform. "
            "Automatic PII redaction, secure storage, audit trail, "
            "and compliance reporting for healthcare AI inferences."
        ),
        version=settings.APP_VERSION,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # ── Middleware ────────────────────────────────────────────────

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # Trusted hosts (production only)
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    # ── Global Exception Handler ─────────────────────────────────

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all exception handler. Never leaks internal details."""
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": "An internal error occurred",
            },
        )

    # ── Request ID Middleware ────────────────────────────────────

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Add request ID and timing to every response."""
        from app.core.security import generate_request_id

        request_id = generate_request_id()
        request.state.request_id = request_id

        start = datetime.now(UTC)
        response = await call_next(request)
        duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"

        # Inject rate limit headers (set by check_rate_limit dependency)
        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(
                request.state.rate_limit_limit
            )
            response.headers["X-RateLimit-Remaining"] = str(
                request.state.rate_limit_remaining
            )

        # Log request (no PII in logs)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 1),
            request_id=request_id,
        )

        return response

    # ── Security Headers Middleware ───────────────────────────────

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Add security headers to every response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    # ── Routes ───────────────────────────────────────────────────

    # Health checks (no auth required)
    app.include_router(health.router, tags=["health"])

    # API v1 routes (auth required)
    prefix = settings.API_V1_PREFIX
    app.include_router(
        ingest.router,
        prefix=prefix,
        tags=["inference"],
    )
    app.include_router(
        api_keys.router,
        prefix=f"{prefix}/apikeys",
        tags=["api-keys"],
    )
    # Model performance tracking (registered BEFORE models router
    # so /overview and /ground-truth/batch match before /{model_id})
    app.include_router(
        performance.router,
        prefix=f"{prefix}/models",
        tags=["model-performance"],
    )
    app.include_router(
        models.router,
        prefix=f"{prefix}/models",
        tags=["models"],
    )
    app.include_router(
        dashboard.router,
        prefix=f"{prefix}/dashboard",
        tags=["dashboard"],
    )
    app.include_router(
        timeseries.router,
        prefix=f"{prefix}/dashboard",
        tags=["dashboard"],
    )
    app.include_router(
        compliance.router,
        prefix=f"{prefix}/reports",
        tags=["compliance"],
    )
    app.include_router(
        encryption.router,
        prefix=f"{prefix}/encryption",
        tags=["encryption"],
    )
    app.include_router(
        inference_list.router,
        prefix=f"{prefix}/inferences",
        tags=["inferences"],
    )

    # Alert management
    app.include_router(
        alerts.router,
        prefix=f"{prefix}/alerts",
        tags=["alerts"],
    )

    # Webhook management
    app.include_router(
        webhooks.router,
        prefix=f"{prefix}/webhooks",
        tags=["webhooks"],
    )

    # WebSocket endpoint for real-time updates (auth via query param)
    app.include_router(
        ws.router,
        prefix=prefix,
        tags=["websocket"],
    )

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),
    )
