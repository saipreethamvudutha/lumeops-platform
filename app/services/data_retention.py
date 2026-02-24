"""
Data Retention Service — configurable TTL-based data cleanup.

LEARNING NOTE — Why Data Retention Matters:

    1. COMPLIANCE:
       While HIPAA requires *minimum* 6-year retention, many organizations
       need to enforce *maximum* retention to limit liability. If a breach
       occurs, data that no longer exists can't be exposed.

    2. STORAGE COSTS:
       At scale, inference logs grow fast: 1M inferences/day * 1KB each =
       ~1GB/day = ~365GB/year per tenant. Without cleanup, costs compound.

    3. CUSTOMER CONTRACTS:
       Enterprise customers often have specific data retention requirements
       in their contracts. Per-tenant TTL configuration supports this.

    4. RIGHT TO ERASURE:
       While HIPAA doesn't include a "right to erasure" like GDPR, some
       state privacy laws (e.g., CCPA) do. Having retention machinery
       already in place makes compliance easier.

    The service supports three independent retention policies:
    - Inference records: Clinical data, often kept longest
    - Alert records: Only resolved alerts are eligible (open/ack stay)
    - Webhook delivery logs: Usually shortest retention (default 90 days)

    IMPORTANT: Only *resolved* alerts are cleaned up. Open and acknowledged
    alerts are never deleted, regardless of age — they represent active
    incidents that may still need attention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.inference import Inference
from app.models.tenant import Tenant
from app.models.webhook import WebhookDelivery

logger = get_logger("data_retention")


class DataRetentionService:
    """
    Service for managing data retention policies and executing cleanup.

    Provides:
    - Get/update retention settings for a tenant
    - Run cleanup for a specific tenant or all tenants
    - Report cleanup statistics
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════
    #  Retention Policy Management
    # ══════════════════════════════════════════════════════════════

    async def get_retention_policy(
        self, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get the current retention policy for a tenant."""
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        return {
            "inference_retention_days": tenant.inference_retention_days,
            "alert_retention_days": tenant.alert_retention_days,
            "webhook_delivery_retention_days": tenant.webhook_delivery_retention_days,
            "retention_policy_updated_at": (
                tenant.retention_policy_updated_at.isoformat()
                if tenant.retention_policy_updated_at
                else None
            ),
            "last_retention_cleanup_at": (
                tenant.last_retention_cleanup_at.isoformat()
                if tenant.last_retention_cleanup_at
                else None
            ),
        }

    async def update_retention_policy(
        self,
        tenant_id: str,
        inference_retention_days: int | None = ...,
        alert_retention_days: int | None = ...,
        webhook_delivery_retention_days: int | None = ...,
    ) -> dict[str, Any] | None:
        """
        Update retention policy for a tenant.

        Validates constraints:
        - inference_retention_days: Must be >= 365 (HIPAA minimum 1 year,
          though 6 years is recommended) or None (keep forever)
        - alert_retention_days: Must be >= 30 or None
        - webhook_delivery_retention_days: Must be >= 7 or None

        Uses sentinel default (...) to distinguish "not provided" from
        "explicitly set to None" — setting to None means "keep forever."
        """
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        now = datetime.now(UTC)
        changed = False

        if inference_retention_days is not ...:
            if inference_retention_days is not None and inference_retention_days < 365:
                raise ValueError(
                    "inference_retention_days must be >= 365 (HIPAA compliance) or null"
                )
            tenant.inference_retention_days = inference_retention_days
            changed = True

        if alert_retention_days is not ...:
            if alert_retention_days is not None and alert_retention_days < 30:
                raise ValueError(
                    "alert_retention_days must be >= 30 or null"
                )
            tenant.alert_retention_days = alert_retention_days
            changed = True

        if webhook_delivery_retention_days is not ...:
            if (
                webhook_delivery_retention_days is not None
                and webhook_delivery_retention_days < 7
            ):
                raise ValueError(
                    "webhook_delivery_retention_days must be >= 7 or null"
                )
            tenant.webhook_delivery_retention_days = webhook_delivery_retention_days
            changed = True

        if changed:
            tenant.retention_policy_updated_at = now
            await self.db.flush()

        return await self.get_retention_policy(tenant_id)

    # ══════════════════════════════════════════════════════════════
    #  Cleanup Execution
    # ══════════════════════════════════════════════════════════════

    async def cleanup_tenant(
        self, tenant_id: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Run retention cleanup for a single tenant.

        Returns summary of what was (or would be) deleted.
        If dry_run=True, only counts records — doesn't delete.
        """
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return {"error": "tenant_not_found"}

        now = datetime.now(UTC)
        summary = {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "dry_run": dry_run,
            "inferences_deleted": 0,
            "alerts_deleted": 0,
            "webhook_deliveries_deleted": 0,
            "executed_at": now.isoformat(),
        }

        # ── Inference Cleanup ──────────────────────────────────
        if tenant.inference_retention_days is not None:
            cutoff = now - timedelta(days=tenant.inference_retention_days)
            if dry_run:
                count_result = await self.db.execute(
                    select(func.count(Inference.id)).where(
                        Inference.tenant_id == tenant_id,
                        Inference.received_at < cutoff,
                    )
                )
                summary["inferences_deleted"] = count_result.scalar() or 0
            else:
                del_result = await self.db.execute(
                    delete(Inference).where(
                        Inference.tenant_id == tenant_id,
                        Inference.received_at < cutoff,
                    )
                )
                summary["inferences_deleted"] = del_result.rowcount

        # ── Alert Cleanup (resolved only) ──────────────────────
        if tenant.alert_retention_days is not None:
            cutoff = now - timedelta(days=tenant.alert_retention_days)
            if dry_run:
                count_result = await self.db.execute(
                    select(func.count(Alert.id)).where(
                        Alert.tenant_id == tenant_id,
                        Alert.resolved_at.is_not(None),
                        Alert.resolved_at < cutoff,
                    )
                )
                summary["alerts_deleted"] = count_result.scalar() or 0
            else:
                del_result = await self.db.execute(
                    delete(Alert).where(
                        Alert.tenant_id == tenant_id,
                        Alert.resolved_at.is_not(None),
                        Alert.resolved_at < cutoff,
                    )
                )
                summary["alerts_deleted"] = del_result.rowcount

        # ── Webhook Delivery Cleanup ───────────────────────────
        if tenant.webhook_delivery_retention_days is not None:
            cutoff = now - timedelta(
                days=tenant.webhook_delivery_retention_days
            )
            if dry_run:
                count_result = await self.db.execute(
                    select(func.count(WebhookDelivery.id)).where(
                        WebhookDelivery.tenant_id == tenant_id,
                        WebhookDelivery.delivered_at < cutoff,
                    )
                )
                summary["webhook_deliveries_deleted"] = (
                    count_result.scalar() or 0
                )
            else:
                del_result = await self.db.execute(
                    delete(WebhookDelivery).where(
                        WebhookDelivery.tenant_id == tenant_id,
                        WebhookDelivery.delivered_at < cutoff,
                    )
                )
                summary["webhook_deliveries_deleted"] = del_result.rowcount

        # Update last cleanup timestamp
        if not dry_run:
            tenant.last_retention_cleanup_at = now
            await self.db.flush()

        total = (
            summary["inferences_deleted"]
            + summary["alerts_deleted"]
            + summary["webhook_deliveries_deleted"]
        )
        summary["total_deleted"] = total

        logger.info(
            "retention_cleanup_completed",
            tenant_id=tenant_id,
            dry_run=dry_run,
            inferences=summary["inferences_deleted"],
            alerts=summary["alerts_deleted"],
            webhooks=summary["webhook_deliveries_deleted"],
            total=total,
        )

        return summary

    async def cleanup_all_tenants(
        self, dry_run: bool = False
    ) -> list[dict[str, Any]]:
        """
        Run retention cleanup for all active tenants.

        Returns a list of cleanup summaries, one per tenant.
        Only processes tenants that have at least one retention policy set.
        """
        result = await self.db.execute(
            select(Tenant).where(
                Tenant.is_active.is_(True),
                # At least one policy is configured
                (
                    Tenant.inference_retention_days.is_not(None)
                    | Tenant.alert_retention_days.is_not(None)
                    | Tenant.webhook_delivery_retention_days.is_not(None)
                ),
            )
        )
        tenants = result.scalars().all()

        summaries = []
        for tenant in tenants:
            summary = await self.cleanup_tenant(tenant.id, dry_run=dry_run)
            summaries.append(summary)

        logger.info(
            "retention_cleanup_all_completed",
            tenants_processed=len(summaries),
            dry_run=dry_run,
        )

        return summaries

    # ══════════════════════════════════════════════════════════════
    #  Tenant Settings Management
    # ══════════════════════════════════════════════════════════════

    async def get_tenant_settings(
        self, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get full tenant settings for the Settings page."""
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        return {
            # Identity
            "id": tenant.id,
            "name": tenant.name,
            "customer_type": tenant.customer_type,
            # Contact
            "contact_email": tenant.contact_email,
            "contact_phone": tenant.contact_phone,
            # Plan
            "plan": tenant.plan,
            "is_active": tenant.is_active,
            # Settings
            "timezone": tenant.timezone,
            "data_residency": tenant.data_residency,
            # Notifications
            "alert_email": tenant.alert_email,
            "alert_slack_webhook": _mask_url(tenant.alert_slack_webhook),
            "notification_preferences": tenant.notification_preferences or {
                "email": False,
                "slack": False,
                "webhook": True,
            },
            # Encryption
            "encryption_key_version": tenant.encryption_key_version,
            "last_key_rotation": (
                tenant.last_key_rotation.isoformat()
                if tenant.last_key_rotation
                else None
            ),
            "key_rotation_count": tenant.key_rotation_count,
            # Retention
            "retention": {
                "inference_retention_days": tenant.inference_retention_days,
                "alert_retention_days": tenant.alert_retention_days,
                "webhook_delivery_retention_days": tenant.webhook_delivery_retention_days,
                "policy_updated_at": (
                    tenant.retention_policy_updated_at.isoformat()
                    if tenant.retention_policy_updated_at
                    else None
                ),
                "last_cleanup_at": (
                    tenant.last_retention_cleanup_at.isoformat()
                    if tenant.last_retention_cleanup_at
                    else None
                ),
            },
            # Metadata
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        }

    async def update_tenant_settings(
        self,
        tenant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update tenant settings (contact info, timezone, notifications).

        Only updates fields that are explicitly provided.
        Does NOT update: plan, is_active, encryption (separate endpoints).
        """
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        # Allowed settings fields
        allowed_fields = {
            "name", "customer_type", "contact_email", "contact_phone",
            "timezone", "alert_email", "alert_slack_webhook",
            "notification_preferences",
        }

        for field, value in updates.items():
            if field in allowed_fields and hasattr(tenant, field):
                setattr(tenant, field, value)

        await self.db.flush()
        return await self.get_tenant_settings(tenant_id)


def _mask_url(url: str | None) -> str | None:
    """Mask webhook URLs for display — show only the domain."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/****"
    except Exception:
        return "****"
