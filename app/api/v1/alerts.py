"""
Alert Management API.

Endpoints for listing, filtering, acknowledging, and resolving alerts.

Endpoints:
    GET    /api/v1/alerts           — List alerts with filters
    GET    /api/v1/alerts/stats     — Aggregated alert statistics
    GET    /api/v1/alerts/{id}      — Get single alert details
    POST   /api/v1/alerts/{id}/ack  — Acknowledge an alert
    POST   /api/v1/alerts/{id}/resolve — Resolve an alert
    POST   /api/v1/alerts/bulk-ack  — Bulk acknowledge alerts
    POST   /api/v1/alerts/bulk-resolve — Bulk resolve alerts

LEARNING NOTE:
    Alerts follow a standard lifecycle:
        1. OPEN      → triggered by ingest pipeline (outlier / data quality / system)
        2. ACKNOWLEDGED → operator has seen and is working on it
        3. RESOLVED  → root cause addressed, alert closed

    This three-state workflow is standard in ops tooling (PagerDuty,
    OpsGenie, Datadog). It provides:
    - MTTA (Mean Time to Acknowledge): measures team responsiveness
    - MTTR (Mean Time to Resolve): measures incident resolution speed
    - Accountability: acknowledged_by tracks who owns the alert

    The 'read' scope allows listing alerts, but acknowledge/resolve
    require the 'admin' scope (state-changing operations).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    AlertAcknowledgeRequest,
    AlertBulkActionRequest,
    AlertBulkActionResponse,
    AlertDetailResponse,
    AlertListResponse,
    AlertResolveRequest,
    AlertStatsResponse,
)
from app.core.database import get_db_session
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.alert import Alert
from app.services.audit import AuditService

router = APIRouter()


def _alert_to_detail(alert: Alert) -> AlertDetailResponse:
    """Convert an Alert model to the full detail response."""
    return AlertDetailResponse(
        id=alert.id,
        model_id=alert.model_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        message=alert.message,
        details=alert.details,
        triggered_at=alert.triggered_at,
        inference_id=alert.inference_id,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
        notified_email=alert.notified_email,
        notified_slack=alert.notified_slack,
        created_at=alert.created_at,
    )


# ══════════════════════════════════════════════════════════════════
#  LIST (with filters)
# ══════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List alerts",
    description="List alerts with filtering by status, severity, type, and time range.",
)
async def list_alerts(
    # Filters
    alert_status: str | None = Query(
        None,
        pattern="^(open|acknowledged|resolved)$",
        description="Filter by lifecycle status",
    ),
    severity: str | None = Query(
        None,
        pattern="^(info|warning|critical)$",
        description="Filter by severity",
    ),
    alert_type: str | None = Query(
        None,
        pattern="^(outlier|data_quality|system_error)$",
        description="Filter by alert type",
    ),
    model_id: str | None = Query(None, description="Filter by model ID"),
    days: int = Query(default=7, ge=1, le=365, description="Lookback period in days"),
    # Pagination
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Sort
    sort_by: str = Query(
        default="triggered_at",
        pattern="^(triggered_at|severity|alert_type)$",
    ),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    # Auth
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertListResponse:
    """
    List alerts for the tenant with comprehensive filtering.

    Status semantics:
      - open: triggered_at set, acknowledged_at NULL, resolved_at NULL
      - acknowledged: acknowledged_at set, resolved_at NULL
      - resolved: resolved_at set
    """
    from datetime import timedelta

    tenant_id = auth.tenant_id
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Build filter conditions
    filters = [
        Alert.tenant_id == tenant_id,
        Alert.triggered_at >= cutoff,
    ]

    if alert_status == "open":
        filters.append(Alert.acknowledged_at.is_(None))
        filters.append(Alert.resolved_at.is_(None))
    elif alert_status == "acknowledged":
        filters.append(Alert.acknowledged_at.isnot(None))
        filters.append(Alert.resolved_at.is_(None))
    elif alert_status == "resolved":
        filters.append(Alert.resolved_at.isnot(None))

    if severity:
        filters.append(Alert.severity == severity)
    if alert_type:
        filters.append(Alert.alert_type == alert_type)
    if model_id:
        filters.append(Alert.model_id == model_id)

    # Count total matching
    count_result = await db.execute(
        select(func.count(Alert.id)).where(*filters)
    )
    total = count_result.scalar_one()

    # Determine sort column
    sort_col = {
        "triggered_at": Alert.triggered_at,
        "severity": Alert.severity,
        "alert_type": Alert.alert_type,
    }[sort_by]

    order = sort_col.desc() if sort_order == "desc" else sort_col.asc()

    # Fetch page
    result = await db.execute(
        select(Alert)
        .where(*filters)
        .order_by(order)
        .limit(limit)
        .offset(offset)
    )
    alerts = result.scalars().all()

    return AlertListResponse(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
        alerts=[_alert_to_detail(a) for a in alerts],
    )


# ══════════════════════════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/stats",
    response_model=AlertStatsResponse,
    summary="Alert statistics",
    description="Aggregated alert metrics including MTTA and MTTR.",
)
async def get_alert_stats(
    days: int = Query(default=30, ge=1, le=365),
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertStatsResponse:
    """
    Get aggregated alert statistics for the tenant.

    Includes MTTA (Mean Time to Acknowledge) and MTTR (Mean Time to Resolve)
    which are key operational metrics for healthcare IT teams.
    """
    from datetime import timedelta

    tenant_id = auth.tenant_id
    cutoff = datetime.now(UTC) - timedelta(days=days)

    base_filter = [
        Alert.tenant_id == tenant_id,
        Alert.triggered_at >= cutoff,
    ]

    # ── Count by status ───────────────────────────────────────────
    active_result = await db.execute(
        select(func.count(Alert.id)).where(
            *base_filter,
            Alert.resolved_at.is_(None),
            Alert.acknowledged_at.is_(None),
        )
    )
    total_active = active_result.scalar_one()

    acked_result = await db.execute(
        select(func.count(Alert.id)).where(
            *base_filter,
            Alert.acknowledged_at.isnot(None),
            Alert.resolved_at.is_(None),
        )
    )
    total_acknowledged = acked_result.scalar_one()

    resolved_result = await db.execute(
        select(func.count(Alert.id)).where(
            *base_filter,
            Alert.resolved_at.isnot(None),
        )
    )
    total_resolved = resolved_result.scalar_one()

    # ── Count by severity ─────────────────────────────────────────
    severity_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(*base_filter)
        .group_by(Alert.severity)
    )
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # ── Count by type ─────────────────────────────────────────────
    type_result = await db.execute(
        select(Alert.alert_type, func.count(Alert.id))
        .where(*base_filter)
        .group_by(Alert.alert_type)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}

    # ── MTTA: Mean Time to Acknowledge ────────────────────────────
    # Average seconds between triggered_at and acknowledged_at
    mtta_result = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    Alert.acknowledged_at - Alert.triggered_at,
                )
            )
        ).where(
            *base_filter,
            Alert.acknowledged_at.isnot(None),
        )
    )
    mtta_seconds = mtta_result.scalar_one()
    mtta_minutes = round(mtta_seconds / 60, 1) if mtta_seconds else None

    # ── MTTR: Mean Time to Resolve ────────────────────────────────
    mttr_result = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    Alert.resolved_at - Alert.triggered_at,
                )
            )
        ).where(
            *base_filter,
            Alert.resolved_at.isnot(None),
        )
    )
    mttr_seconds = mttr_result.scalar_one()
    mttr_minutes = round(mttr_seconds / 60, 1) if mttr_seconds else None

    return AlertStatsResponse(
        total_active=total_active,
        total_acknowledged=total_acknowledged,
        total_resolved=total_resolved,
        by_severity=by_severity,
        by_type=by_type,
        mean_time_to_acknowledge_minutes=mtta_minutes,
        mean_time_to_resolve_minutes=mttr_minutes,
        generated_at=datetime.now(UTC),
    )


# ══════════════════════════════════════════════════════════════════
#  GET SINGLE
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/{alert_id}",
    response_model=AlertDetailResponse,
    summary="Get alert",
    description="Get full details of a specific alert.",
)
async def get_alert(
    alert_id: str,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertDetailResponse:
    """Get a single alert by ID."""
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == auth.tenant_id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    return _alert_to_detail(alert)


# ══════════════════════════════════════════════════════════════════
#  ACKNOWLEDGE
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/{alert_id}/ack",
    response_model=AlertDetailResponse,
    summary="Acknowledge alert",
    description="Mark an alert as acknowledged. Requires admin scope.",
)
async def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertDetailResponse:
    """
    Acknowledge an alert — indicates someone is looking into it.

    Idempotent: acknowledging an already-acknowledged alert is a no-op.
    """
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == auth.tenant_id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    if alert.resolved_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot acknowledge an already-resolved alert",
        )

    now = datetime.now(UTC)

    # Only update if not already acknowledged (idempotent)
    if not alert.acknowledged_at:
        alert.acknowledged_at = now
        alert.acknowledged_by = payload.acknowledged_by

        # Audit log
        audit = AuditService(db)
        await audit.log_event(
            tenant_id=auth.tenant_id,
            action="ALERT_ACKNOWLEDGED",
            resource_type="alert",
            resource_id=alert.id,
            details={
                "acknowledged_by": payload.acknowledged_by,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
            },
        )

    return _alert_to_detail(alert)


# ══════════════════════════════════════════════════════════════════
#  RESOLVE
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertDetailResponse,
    summary="Resolve alert",
    description="Mark an alert as resolved. Requires admin scope.",
)
async def resolve_alert(
    alert_id: str,
    payload: AlertResolveRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertDetailResponse:
    """
    Resolve an alert — marks the root cause as addressed.

    Can resolve directly (without prior acknowledge).
    Idempotent: resolving an already-resolved alert is a no-op.
    """
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == auth.tenant_id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    now = datetime.now(UTC)

    # Only update if not already resolved (idempotent)
    if not alert.resolved_at:
        alert.resolved_at = now

        # Auto-acknowledge if not already done
        if not alert.acknowledged_at:
            alert.acknowledged_at = now
            alert.acknowledged_by = "auto (resolved)"

        # Store resolution note in details
        if payload.resolution_note:
            existing_details = alert.details or {}
            existing_details["resolution_note"] = payload.resolution_note
            alert.details = existing_details

        # Audit log
        audit = AuditService(db)
        await audit.log_event(
            tenant_id=auth.tenant_id,
            action="ALERT_RESOLVED",
            resource_type="alert",
            resource_id=alert.id,
            details={
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "resolution_note": payload.resolution_note,
                "time_to_resolve_seconds": (
                    (now - alert.triggered_at).total_seconds()
                    if alert.triggered_at
                    else None
                ),
            },
        )

    return _alert_to_detail(alert)


# ══════════════════════════════════════════════════════════════════
#  BULK ACKNOWLEDGE
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/bulk-ack",
    response_model=AlertBulkActionResponse,
    summary="Bulk acknowledge",
    description="Acknowledge multiple alerts at once.",
)
async def bulk_acknowledge(
    payload: AlertBulkActionRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertBulkActionResponse:
    """Bulk acknowledge multiple alerts."""
    if not payload.acknowledged_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="acknowledged_by is required for bulk acknowledge",
        )

    now = datetime.now(UTC)
    tenant_id = auth.tenant_id

    # Fetch matching alerts
    result = await db.execute(
        select(Alert).where(
            Alert.id.in_(payload.alert_ids),
            Alert.tenant_id == tenant_id,
            Alert.acknowledged_at.is_(None),
            Alert.resolved_at.is_(None),
        )
    )
    alerts = result.scalars().all()

    processed_ids = []
    for alert in alerts:
        alert.acknowledged_at = now
        alert.acknowledged_by = payload.acknowledged_by
        processed_ids.append(alert.id)

    skipped = len(payload.alert_ids) - len(processed_ids)

    if processed_ids:
        audit = AuditService(db)
        await audit.log_event(
            tenant_id=tenant_id,
            action="ALERTS_BULK_ACKNOWLEDGED",
            resource_type="alert",
            details={
                "count": len(processed_ids),
                "acknowledged_by": payload.acknowledged_by,
                "alert_ids": processed_ids[:10],  # Cap for log size
            },
        )

    return AlertBulkActionResponse(
        processed=len(processed_ids),
        skipped=skipped,
        alert_ids=processed_ids,
    )


# ══════════════════════════════════════════════════════════════════
#  BULK RESOLVE
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/bulk-resolve",
    response_model=AlertBulkActionResponse,
    summary="Bulk resolve",
    description="Resolve multiple alerts at once.",
)
async def bulk_resolve(
    payload: AlertBulkActionRequest,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> AlertBulkActionResponse:
    """Bulk resolve multiple alerts."""
    now = datetime.now(UTC)
    tenant_id = auth.tenant_id

    result = await db.execute(
        select(Alert).where(
            Alert.id.in_(payload.alert_ids),
            Alert.tenant_id == tenant_id,
            Alert.resolved_at.is_(None),
        )
    )
    alerts = result.scalars().all()

    processed_ids = []
    for alert in alerts:
        alert.resolved_at = now
        if not alert.acknowledged_at:
            alert.acknowledged_at = now
            alert.acknowledged_by = "auto (bulk resolved)"
        processed_ids.append(alert.id)

    skipped = len(payload.alert_ids) - len(processed_ids)

    if processed_ids:
        audit = AuditService(db)
        await audit.log_event(
            tenant_id=tenant_id,
            action="ALERTS_BULK_RESOLVED",
            resource_type="alert",
            details={
                "count": len(processed_ids),
                "alert_ids": processed_ids[:10],
            },
        )

    return AlertBulkActionResponse(
        processed=len(processed_ids),
        skipped=skipped,
        alert_ids=processed_ids,
    )
