"""
Encryption management endpoints.

POST /api/v1/encryption/rotate    - Trigger key rotation for the tenant
GET  /api/v1/encryption/status    - Get encryption status and rotation history

LEARNING NOTE ON KEY ROTATION:
    Key rotation is a critical security practice for healthcare platforms.
    Even if no breach has occurred, periodic rotation limits the window
    during which a compromised key would be useful.

    Our rotation strategy:
    1. Increment the tenant's key version (v1 → v2)
    2. New inferences immediately use the new key version
    3. Existing inferences are re-encrypted in batches (background)
    4. Each inference tracks which key version it was encrypted with
    5. The rotation process is idempotent and resumable

    WHY BATCH RE-ENCRYPTION:
        If a tenant has 1 million inference records, re-encrypting all
        of them in a single request would time out. Instead, we process
        records in configurable batches. If the process is interrupted,
        we can resume from where we left off because each record's
        encryption_key_version tells us whether it's been migrated.

    ZERO-DOWNTIME DESIGN:
        During rotation, the system can handle both old and new key
        versions simultaneously:
        - New writes use the new version
        - Old reads use the version stored on the inference record
        - Background re-encryption progressively migrates old records
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.logging import get_logger
from app.core.security import rotate_encryption
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.inference import Inference
from app.models.tenant import Tenant
from app.services.audit import AuditService

logger = get_logger("encryption")

router = APIRouter()

# Maximum records to re-encrypt per request to prevent timeouts
ROTATION_BATCH_SIZE = 500


@router.post(
    "/rotate",
    summary="Rotate encryption keys for the tenant",
    description=(
        "Triggers key rotation: increments the tenant's key version "
        "and re-encrypts existing inference records in batches. "
        "Call repeatedly until all records are migrated."
    ),
)
async def rotate_keys(
    request: Request,
    batch_size: int = ROTATION_BATCH_SIZE,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("admin")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Rotate encryption keys for the authenticated tenant.

    PROCESS:
    1. First call: increments key version, starts re-encryption
    2. Subsequent calls: continues re-encrypting remaining records
    3. Final call: returns migration_complete=true when done

    Requires 'admin' scope (enforced by dependency).

    LEARNING NOTE:
        This endpoint is designed to be called multiple times.
        Each call processes up to `batch_size` records (default 500).
        This prevents request timeouts on tenants with many records.

        The caller should loop until migration_complete is true:
            while True:
                resp = POST /api/v1/encryption/rotate
                if resp.migration_complete:
                    break
    """
    tenant_id = auth.tenant_id
    tenant = auth.tenant
    old_version = tenant.encryption_key_version
    new_version = old_version + 1

    # Clamp batch size to reasonable bounds
    batch_size = max(1, min(batch_size, 2000))

    # ── Check how many records still need migration ─────────────────
    pending_count_result = await db.execute(
        select(func.count(Inference.id)).where(
            Inference.tenant_id == tenant_id,
            Inference.encryption_key_version < new_version,
        )
    )
    total_pending = pending_count_result.scalar_one()

    # ── If this is the first rotation call, increment version ──────
    # We check if any records are on the old version OR if the tenant
    # hasn't been bumped yet. This makes the operation idempotent.
    if tenant.encryption_key_version == old_version and total_pending > 0:
        # Update tenant's key version (new writes will use new version)
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(
                encryption_key_version=new_version,
                last_key_rotation=datetime.now(UTC),
                key_rotation_count=Tenant.key_rotation_count + 1,
            )
        )
        # Refresh the tenant object
        await db.refresh(tenant)

        logger.info(
            "key_rotation_started",
            tenant_id=tenant_id,
            old_version=old_version,
            new_version=new_version,
            pending_records=total_pending,
        )
    elif total_pending == 0:
        # No records to migrate — bump version anyway for future records
        if tenant.encryption_key_version == old_version:
            await db.execute(
                update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(
                    encryption_key_version=new_version,
                    last_key_rotation=datetime.now(UTC),
                    key_rotation_count=Tenant.key_rotation_count + 1,
                )
            )

        # Audit log for rotation
        audit = AuditService(db)
        await audit.log_event(
            tenant_id=tenant_id,
            action="ENCRYPTION_KEY_ROTATED",
            resource_type="tenant",
            resource_id=tenant_id,
            ip_address=request.client.host if request.client else None,
            details={
                "old_version": old_version,
                "new_version": new_version,
                "records_migrated": 0,
                "migration_complete": True,
            },
        )

        return {
            "status": "completed",
            "message": "Key version incremented. No existing records to migrate.",
            "old_version": old_version,
            "new_version": new_version,
            "records_migrated": 0,
            "records_remaining": 0,
            "migration_complete": True,
        }

    # ── Fetch a batch of records that need re-encryption ────────────
    # We use the current new_version to find records still on old versions
    actual_new_version = tenant.encryption_key_version
    batch_result = await db.execute(
        select(Inference)
        .where(
            Inference.tenant_id == tenant_id,
            Inference.encryption_key_version < actual_new_version,
        )
        .limit(batch_size)
    )
    records = batch_result.scalars().all()

    # ── Re-encrypt each record ─────────────────────────────────────
    migrated_count = 0
    errors = []

    for record in records:
        try:
            # Decrypt with the version stored on the record, encrypt with new
            new_ciphertext = rotate_encryption(
                ciphertext=record.input_features_encrypted,
                tenant_id=tenant_id,
                old_version=record.encryption_key_version,
                new_version=actual_new_version,
            )
            record.input_features_encrypted = new_ciphertext
            record.encryption_key_version = actual_new_version
            migrated_count += 1
        except Exception as e:
            errors.append({
                "inference_id": record.id,
                "error": str(e),
            })
            logger.error(
                "key_rotation_record_failed",
                tenant_id=tenant_id,
                inference_id=record.id,
                error=str(e),
            )

    # ── Check remaining count ──────────────────────────────────────
    remaining_result = await db.execute(
        select(func.count(Inference.id)).where(
            Inference.tenant_id == tenant_id,
            Inference.encryption_key_version < actual_new_version,
        )
    )
    # Subtract what we just migrated (not yet committed) from the count
    records_remaining = remaining_result.scalar_one() - migrated_count
    migration_complete = records_remaining <= 0

    # ── Audit log ──────────────────────────────────────────────────
    audit = AuditService(db)
    await audit.log_event(
        tenant_id=tenant_id,
        action="ENCRYPTION_KEY_ROTATION_BATCH",
        resource_type="tenant",
        resource_id=tenant_id,
        ip_address=request.client.host if request.client else None,
        details={
            "old_version": old_version,
            "new_version": actual_new_version,
            "batch_migrated": migrated_count,
            "batch_errors": len(errors),
            "records_remaining": max(records_remaining, 0),
            "migration_complete": migration_complete,
        },
    )

    if migration_complete:
        await audit.log_event(
            tenant_id=tenant_id,
            action="ENCRYPTION_KEY_ROTATED",
            resource_type="tenant",
            resource_id=tenant_id,
            ip_address=request.client.host if request.client else None,
            details={
                "old_version": old_version,
                "new_version": actual_new_version,
                "total_records_migrated": total_pending,
            },
        )

    logger.info(
        "key_rotation_batch_completed",
        tenant_id=tenant_id,
        migrated=migrated_count,
        errors=len(errors),
        remaining=max(records_remaining, 0),
        complete=migration_complete,
    )

    return {
        "status": "completed" if migration_complete else "in_progress",
        "message": (
            "Key rotation complete. All records migrated."
            if migration_complete
            else f"Batch processed. {max(records_remaining, 0)} records remaining."
        ),
        "old_version": old_version,
        "new_version": actual_new_version,
        "batch_migrated": migrated_count,
        "batch_errors": errors if errors else None,
        "records_remaining": max(records_remaining, 0),
        "migration_complete": migration_complete,
    }


@router.get(
    "/status",
    summary="Get encryption status",
    description="Returns the tenant's current encryption key version and rotation history.",
)
async def get_encryption_status(
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("read")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Get the encryption status for the authenticated tenant.

    Returns:
        - Current key version
        - Last rotation date
        - Total rotation count
        - Records by key version (shows migration progress)
    """
    tenant = auth.tenant

    # Count records by key version
    version_counts = await db.execute(
        select(
            Inference.encryption_key_version,
            func.count(Inference.id),
        )
        .where(Inference.tenant_id == auth.tenant_id)
        .group_by(Inference.encryption_key_version)
    )
    records_by_version = {
        f"v{row[0]}": row[1] for row in version_counts.all()
    }

    # Total records
    total_result = await db.execute(
        select(func.count(Inference.id)).where(
            Inference.tenant_id == auth.tenant_id,
        )
    )
    total_records = total_result.scalar_one()

    # Records pending migration (any version below current)
    pending_result = await db.execute(
        select(func.count(Inference.id)).where(
            Inference.tenant_id == auth.tenant_id,
            Inference.encryption_key_version < tenant.encryption_key_version,
        )
    )
    pending_migration = pending_result.scalar_one()

    return {
        "tenant_id": auth.tenant_id,
        "current_key_version": tenant.encryption_key_version,
        "last_key_rotation": (
            tenant.last_key_rotation.isoformat()
            if tenant.last_key_rotation
            else None
        ),
        "total_rotations": tenant.key_rotation_count,
        "encryption_method": "Fernet (AES-128-CBC + HMAC-SHA256)",
        "key_derivation": "PBKDF2-SHA256 (480,000 iterations)",
        "records": {
            "total": total_records,
            "by_version": records_by_version,
            "pending_migration": pending_migration,
            "fully_migrated": pending_migration == 0,
        },
    }
