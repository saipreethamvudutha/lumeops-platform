"""
Time-series data endpoints for dashboard charts.

GET /api/v1/dashboard/timeseries     - Get hourly/daily time-series data
GET /api/v1/dashboard/quality-trend  - Get data quality trend

LEARNING NOTE ON TIME-SERIES FOR DASHBOARDS:
    Dashboard charts need time-bucketed data. PostgreSQL's date_trunc()
    function is ideal for this — it groups timestamps into hourly or daily
    buckets without needing a separate time-series database.

    For example, to get hourly inference counts:
        SELECT date_trunc('hour', received_at) AS bucket,
               COUNT(*) AS count
        FROM inferences
        WHERE tenant_id = :tenant_id
        GROUP BY bucket
        ORDER BY bucket

    WHY NOT A SEPARATE TIME-SERIES DB:
        For our scale (thousands of inferences/day per tenant), PostgreSQL
        with proper indexes handles time-series queries efficiently.
        Adding TimescaleDB or InfluxDB would be premature optimization
        that adds operational complexity without measurable benefit.
        If a tenant reaches millions of records/day, we'd migrate to
        a dedicated time-series solution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.inference import Inference

router = APIRouter()


@router.get(
    "/timeseries",
    summary="Get time-series data for dashboard charts",
    description=(
        "Returns time-bucketed inference counts and PII redaction stats. "
        "Supports hourly (24h) and daily (7d/30d) granularity."
    ),
)
async def get_timeseries(
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    model_id: str | None = Query(None),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Return time-bucketed inference and PII redaction data.

    Periods:
        - 24h: hourly buckets for the last 24 hours
        - 7d: daily buckets for the last 7 days
        - 30d: daily buckets for the last 30 days

    LEARNING NOTE:
        We use PostgreSQL's date_trunc() for time bucketing.
        This is more efficient than fetching all records and
        grouping in Python because:
        1. The DB only returns aggregated rows (24 or 7 or 30)
        2. The query uses the idx_inf_tenant_model_time index
        3. No large data transfer between DB and app server
    """
    tenant_id = auth.tenant_id
    now = datetime.now(UTC)

    # Determine time range and bucket granularity
    if period == "24h":
        cutoff = now - timedelta(hours=24)
        trunc_unit = "hour"
        label_format = "hour"
    elif period == "7d":
        cutoff = now - timedelta(days=7)
        trunc_unit = "day"
        label_format = "day"
    else:  # 30d
        cutoff = now - timedelta(days=30)
        trunc_unit = "day"
        label_format = "day"

    # Base filters
    filters = [
        Inference.tenant_id == tenant_id,
        Inference.received_at >= cutoff,
    ]
    if model_id:
        filters.append(Inference.model_id == model_id)

    # ── Main time-series query ─────────────────────────────────────
    # Groups by time bucket and calculates:
    # - Total inferences per bucket
    # - PII redaction count per bucket
    # - Outlier count per bucket
    bucket = func.date_trunc(trunc_unit, Inference.received_at).label("bucket")

    result = await db.execute(
        select(
            bucket,
            func.count(Inference.id).label("inferences"),
            func.coalesce(func.sum(Inference.pii_redaction_count), 0).label("pii_redacted"),
            func.sum(
                case(
                    (Inference.is_outlier.is_(True), 1),
                    else_=0,
                )
            ).label("outliers"),
            func.sum(
                case(
                    (Inference.has_quality_issues.is_(True), 1),
                    else_=0,
                )
            ).label("quality_issues"),
        )
        .where(*filters)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = result.all()

    # ── Build response with all time slots (including empty ones) ──
    # Fill in gaps where no data exists (so charts show zero, not missing)
    data_map = {}
    for row in rows:
        ts = row.bucket
        data_map[ts] = {
            "inferences": row.inferences,
            "pii_redacted": int(row.pii_redacted),
            "outliers": int(row.outliers),
            "quality_issues": int(row.quality_issues),
        }

    # Generate all expected time slots
    series = []
    if period == "24h":
        # Generate 24 hourly slots
        for i in range(24):
            slot_time = cutoff + timedelta(hours=i)
            # Round to hour
            slot_time = slot_time.replace(minute=0, second=0, microsecond=0)
            label = slot_time.strftime("%H:%M")
            entry = data_map.get(slot_time, {
                "inferences": 0,
                "pii_redacted": 0,
                "outliers": 0,
                "quality_issues": 0,
            })
            series.append({"label": label, "timestamp": slot_time.isoformat(), **entry})
    else:
        # Generate daily slots
        days = 7 if period == "7d" else 30
        for i in range(days):
            slot_time = (cutoff + timedelta(days=i)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            label = slot_time.strftime("%a %m/%d") if period == "7d" else slot_time.strftime("%m/%d")
            entry = data_map.get(slot_time, {
                "inferences": 0,
                "pii_redacted": 0,
                "outliers": 0,
                "quality_issues": 0,
            })
            series.append({"label": label, "timestamp": slot_time.isoformat(), **entry})

    # ── Totals for the period ──────────────────────────────────────
    total_inferences = sum(s["inferences"] for s in series)
    total_pii = sum(s["pii_redacted"] for s in series)
    total_outliers = sum(s["outliers"] for s in series)

    return {
        "period": period,
        "granularity": "hourly" if period == "24h" else "daily",
        "total_inferences": total_inferences,
        "total_pii_redacted": total_pii,
        "total_outliers": total_outliers,
        "series": series,
        "generated_at": now.isoformat(),
    }


@router.get(
    "/quality-trend",
    summary="Get data quality trend",
    description="Returns daily data quality rates for the specified period.",
)
async def get_quality_trend(
    days: int = Query(7, ge=1, le=90),
    model_id: str | None = Query(None),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Return daily data quality rates.

    For each day, returns:
    - total inferences
    - quality issues count
    - quality rate (0-100%)
    """
    tenant_id = auth.tenant_id
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    filters = [
        Inference.tenant_id == tenant_id,
        Inference.received_at >= cutoff,
    ]
    if model_id:
        filters.append(Inference.model_id == model_id)

    bucket = func.date_trunc("day", Inference.received_at).label("bucket")

    result = await db.execute(
        select(
            bucket,
            func.count(Inference.id).label("total"),
            func.sum(
                case(
                    (Inference.has_quality_issues.is_(True), 1),
                    else_=0,
                )
            ).label("issues"),
        )
        .where(*filters)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = result.all()

    data_map = {}
    for row in rows:
        total = row.total
        issues = int(row.issues)
        quality_rate = round(((total - issues) / total * 100), 1) if total > 0 else 100.0
        data_map[row.bucket] = {
            "total": total,
            "issues": issues,
            "quality": quality_rate,
        }

    # Fill all days
    series = []
    for i in range(days):
        slot_time = (cutoff + timedelta(days=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        label = slot_time.strftime("%a") if days <= 7 else slot_time.strftime("%m/%d")
        entry = data_map.get(slot_time, {"total": 0, "issues": 0, "quality": 100.0})
        series.append({"label": label, "timestamp": slot_time.isoformat(), **entry})

    return {
        "days": days,
        "series": series,
        "generated_at": now.isoformat(),
    }
