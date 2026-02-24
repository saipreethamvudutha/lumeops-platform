"""
Dashboard metrics endpoints.

GET /api/v1/dashboard/stats - Get dashboard metrics
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import DashboardStatsResponse
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.alert import Alert
from app.models.inference import Inference

router = APIRouter()


@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    summary="Get dashboard statistics",
)
async def get_dashboard_stats(
    model_id: str | None = Query(None, description="Filter by model ID"),
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardStatsResponse:
    """
    Get aggregated metrics for the dashboard.

    Includes: inference counts, data quality, PII stats, alerts, system health.
    """
    tenant_id = auth.tenant_id
    now = datetime.now(UTC)

    # Time periods
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # Base query filter
    base_filter = [Inference.tenant_id == tenant_id]
    if model_id:
        base_filter.append(Inference.model_id == model_id)

    # ── Inference counts ─────────────────────────────────────────
    today_count = await _count_inferences(db, base_filter, today_start)
    week_count = await _count_inferences(db, base_filter, week_start)
    month_count = await _count_inferences(db, base_filter, month_start)
    total_count = await _count_inferences(db, base_filter, None)

    # ── Data quality ─────────────────────────────────────────────
    quality_issues_today = await db.execute(
        select(func.count(Inference.id)).where(
            *base_filter,
            Inference.received_at >= today_start,
            Inference.has_quality_issues.is_(True),
        )
    )
    issues_today = quality_issues_today.scalar_one()

    quality_rate = (
        (today_count - issues_today) / today_count
        if today_count > 0
        else 1.0
    )

    # ── PII protection ───────────────────────────────────────────
    pii_total = await db.execute(
        select(func.sum(Inference.pii_redaction_count)).where(
            *base_filter,
            Inference.received_at >= today_start,
        )
    )
    pii_redacted_today = pii_total.scalar_one() or 0

    # ── Outliers ─────────────────────────────────────────────────
    outlier_count = await db.execute(
        select(func.count(Inference.id)).where(
            *base_filter,
            Inference.received_at >= today_start,
            Inference.is_outlier.is_(True),
        )
    )
    outliers_today = outlier_count.scalar_one()

    # ── Alerts ───────────────────────────────────────────────────
    alert_filter = [Alert.tenant_id == tenant_id]
    if model_id:
        alert_filter.append(Alert.model_id == model_id)

    active_alerts = await db.execute(
        select(func.count(Alert.id)).where(
            *alert_filter,
            Alert.resolved_at.is_(None),
        )
    )
    active_count = active_alerts.scalar_one()

    # Recent alerts
    recent_alerts_result = await db.execute(
        select(Alert)
        .where(*alert_filter)
        .order_by(Alert.triggered_at.desc())
        .limit(5)
    )
    recent_alerts = recent_alerts_result.scalars().all()

    return DashboardStatsResponse(
        inferences={
            "today": today_count,
            "this_week": week_count,
            "this_month": month_count,
            "all_time": total_count,
        },
        data_quality={
            "quality_rate": round(quality_rate, 4),
            "issues_today": issues_today,
        },
        predictions={
            "outliers_today": outliers_today,
        },
        pii_protection={
            "total_redacted_today": pii_redacted_today,
        },
        alerts={
            "active": active_count,
            "recent": [
                {
                    "id": a.id,
                    "type": a.alert_type,
                    "severity": a.severity,
                    "message": a.message,
                    "triggered_at": a.triggered_at.isoformat(),
                }
                for a in recent_alerts
            ],
        },
        system={
            "status": "healthy",
            "version": "0.1.0",
        },
        generated_at=now,
    )


async def _count_inferences(
    db: AsyncSession,
    base_filter: list,
    since: datetime | None,
) -> int:
    """Count inferences with optional time filter."""
    filters = list(base_filter)
    if since:
        filters.append(Inference.received_at >= since)

    result = await db.execute(
        select(func.count(Inference.id)).where(*filters)
    )
    return result.scalar_one()
