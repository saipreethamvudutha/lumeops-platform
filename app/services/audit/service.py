"""
Audit Trail Service.

HIPAA requires logging all access to PHI and all system events.
This service provides immutable, append-only audit logging.

Dual-write strategy:
  Primary: PostgreSQL (reliable, always available, SQL queries)
  Secondary: Elasticsearch (fast search, ILM retention, full-text)

Elasticsearch writes are non-blocking and best-effort.
If ES is unavailable, PostgreSQL still captures everything.

Retention: 7 years minimum.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import index_audit_event
from app.core.logging import get_logger
from app.models.audit_log import AuditLog

logger = get_logger("audit_service")


class AuditService:
    """
    Immutable audit trail for HIPAA compliance.

    Every significant action is logged:
    - Inference received
    - PII detected and redacted
    - Data stored
    - API key used
    - Report generated
    - Alert triggered
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(
        self,
        tenant_id: str,
        action: str,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: str | None = None,
        api_key_prefix: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        error_message: str | None = None,
        pii_detected: bool = False,
        pii_types: dict | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        """
        Log a single audit event. Append-only, never updated.

        Writes to both PostgreSQL (primary) and Elasticsearch (secondary).
        ES writes are fire-and-forget — failures don't affect the request.

        Args:
            tenant_id: The tenant this event belongs to.
            action: Event type (e.g., INFERENCE_RECEIVED, PII_REDACTED).
            resource_type: Type of resource affected.
            resource_id: ID of the resource affected.
            status: success or failure.
            details: Additional context (no PII allowed).
        """
        now = datetime.now(UTC)

        # ── 1. PostgreSQL (primary, always) ──────────────────────────
        audit_log = AuditLog(
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            api_key_prefix=api_key_prefix,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
            pii_detected=pii_detected,
            pii_types=pii_types,
            details=details,
            timestamp=now,
        )

        self.db.add(audit_log)
        # Don't flush here -- let the caller's transaction handle it

        # ── 2. Elasticsearch (secondary, best-effort) ────────────────
        es_doc = {
            "tenant_id": tenant_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "api_key_prefix": api_key_prefix,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status": status,
            "error_message": error_message,
            "pii_detected": pii_detected,
            "pii_types": pii_types,
            "details": details,
            "timestamp": now,
        }
        # Remove None values to keep ES documents clean
        es_doc = {k: v for k, v in es_doc.items() if v is not None}

        try:
            await index_audit_event(es_doc)
        except Exception as e:
            # ES failure must never break the request
            logger.warning(
                "es_audit_write_failed",
                action=action,
                tenant_id=tenant_id,
                error=str(e),
            )

        return audit_log

    async def log_inference_received(
        self,
        tenant_id: str,
        inference_id: str,
        model_id: str,
        pii_count: int,
        pii_types: dict | None,
        ip_address: str | None = None,
        api_key_prefix: str | None = None,
    ) -> AuditLog:
        """Log that an inference was received and processed."""
        return await self.log_event(
            tenant_id=tenant_id,
            action="INFERENCE_RECEIVED",
            resource_type="inference",
            resource_id=inference_id,
            ip_address=ip_address,
            api_key_prefix=api_key_prefix,
            pii_detected=pii_count > 0,
            pii_types=pii_types,
            details={
                "model_id": model_id,
                "pii_redacted_count": pii_count,
            },
        )

    async def log_pii_redaction(
        self,
        tenant_id: str,
        inference_id: str,
        pii_types: dict,
        total_redacted: int,
    ) -> AuditLog:
        """Log PII detection and redaction event."""
        return await self.log_event(
            tenant_id=tenant_id,
            action="PII_DETECTED_AND_REDACTED",
            resource_type="inference",
            resource_id=inference_id,
            pii_detected=True,
            pii_types=pii_types,
            details={"total_redacted": total_redacted},
        )

    async def log_report_generated(
        self,
        tenant_id: str,
        report_id: str,
        report_type: str,
        period_days: int,
    ) -> AuditLog:
        """Log compliance report generation."""
        return await self.log_event(
            tenant_id=tenant_id,
            action="REPORT_GENERATED",
            resource_type="report",
            resource_id=report_id,
            details={
                "report_type": report_type,
                "period_days": period_days,
            },
        )

    async def log_api_key_event(
        self,
        tenant_id: str,
        key_id: str,
        action: str,  # API_KEY_CREATED, API_KEY_REVOKED
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log API key lifecycle events."""
        return await self.log_event(
            tenant_id=tenant_id,
            action=action,
            resource_type="api_key",
            resource_id=key_id,
            ip_address=ip_address,
        )

    async def get_audit_summary(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Get audit trail summary for compliance reports.
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Total events
        total_result = await self.db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.timestamp >= cutoff,
            )
        )
        total_events = total_result.scalar_one()

        # PII redaction count
        pii_result = await self.db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.timestamp >= cutoff,
                AuditLog.pii_detected.is_(True),
            )
        )
        pii_events = pii_result.scalar_one()

        # Events by action
        action_result = await self.db.execute(
            select(AuditLog.action, func.count(AuditLog.id))
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.timestamp >= cutoff,
            )
            .group_by(AuditLog.action)
        )
        events_by_action = {row[0]: row[1] for row in action_result.all()}

        return {
            "period_days": days,
            "total_events": total_events,
            "pii_redaction_events": pii_events,
            "events_by_action": events_by_action,
            "generated_at": datetime.now(UTC).isoformat(),
        }
