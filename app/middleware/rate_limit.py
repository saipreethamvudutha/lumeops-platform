"""
Rate limiting middleware using Redis sliding window.

Enforces per-API-key rate limits based on the tenant's plan.
"""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.middleware.auth import AuthenticatedRequest, get_current_tenant


class RateLimiter:
    """
    Sliding window rate limiter backed by Redis.

    Falls back to allowing requests if Redis is unavailable
    (graceful degradation).
    """

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                settings = get_settings()
                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                )
            except Exception:
                return None
        return self._redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """
        Check if request is within rate limit.

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        redis = await self._get_redis()
        if redis is None:
            # Redis unavailable: allow request (graceful degradation)
            return True, limit

        try:
            now = time.time()
            window_start = now - window_seconds
            pipe_key = f"ratelimit:{key}"

            # Sliding window using sorted set
            pipe = redis.pipeline()
            pipe.zremrangebyscore(pipe_key, 0, window_start)
            pipe.zadd(pipe_key, {str(now): now})
            pipe.zcard(pipe_key)
            pipe.expire(pipe_key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[2]
            remaining = max(0, limit - current_count)
            is_allowed = current_count <= limit

            return is_allowed, remaining

        except Exception:
            # Redis error: allow request (graceful degradation)
            return True, limit

    def get_plan_limit(self, plan: str) -> int:
        """Get rate limit for a plan tier."""
        settings = get_settings()
        limits = {
            "starter": settings.RATE_LIMIT_STARTER,
            "professional": settings.RATE_LIMIT_PROFESSIONAL,
            "enterprise": settings.RATE_LIMIT_ENTERPRISE,
        }
        return limits.get(plan, settings.RATE_LIMIT_STARTER)


# Singleton rate limiter
rate_limiter = RateLimiter()


async def check_rate_limit(
    request: Request,
    auth: AuthenticatedRequest = Depends(get_current_tenant),
) -> AuthenticatedRequest:
    """
    Rate limiting dependency for API endpoints.

    Checks the rate limit and raises 429 if exceeded.
    """
    limit = rate_limiter.get_plan_limit(auth.plan)

    # Use API key ID as the rate limit key
    is_allowed, remaining = await rate_limiter.check_rate_limit(
        key=auth.api_key_id,
        limit=limit,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Limit: {limit} requests/minute",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    # Add rate limit headers to response
    request.state.rate_limit_limit = limit
    request.state.rate_limit_remaining = remaining

    return auth


def require_scope_rate_limited(scope: str):
    """
    Combined dependency: scope check + rate limiting.

    This is the standard dependency for protected endpoints.
    It first checks that the API key has the required scope,
    then enforces the tenant's rate limit.

    RBAC scope mapping:
        ingest  — POST /ingest (write inference data)
        read    — GET endpoints (dashboard, inferences, models, encryption status)
        audit   — Compliance reports and audit trail access
        admin   — API key management, encryption rotation, model registration

    Usage:
        @router.get("/data", summary="...")
        async def get_data(
            auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
        ):
    """

    async def _check(
        request: Request,
        auth: AuthenticatedRequest = Depends(get_current_tenant),
    ) -> AuthenticatedRequest:
        # 1. Scope check
        if scope not in auth.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key does not have required scope: {scope}",
            )

        # 2. Rate limit check
        limit = rate_limiter.get_plan_limit(auth.plan)
        is_allowed, remaining = await rate_limiter.check_rate_limit(
            key=auth.api_key_id,
            limit=limit,
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Limit: {limit} requests/minute",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        request.state.rate_limit_limit = limit
        request.state.rate_limit_remaining = remaining
        return auth

    return _check
