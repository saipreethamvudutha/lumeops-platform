"""
Inference Ingestion API -- the core endpoint of LumeOps.

POST /api/v1/ingest

Processing flow:
1. Validate request schema (Pydantic)
2. Authenticate API key
3. Rate limit check
4. Classify all fields by sensitivity level
5. PHI redaction (CRITICAL fields redacted, HIGH fields noted for encryption)
6. Data quality validation
7. Baseline outlier check
8. Encrypt and store (with classification metadata)
9. Audit log
10. Return response

LEARNING NOTE:
    The key change from the original flow is step 4: classification.
    We now classify EVERY field before deciding what to do with it.
    This means the storage layer knows exactly which fields are
    clinical data (HIGH) vs identity data (CRITICAL) vs system data (LOW).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import InferenceRequest, InferenceResponse
from app.core.database import get_db_session
from app.core.pubsub import event_publisher
from app.core.security import encrypt_dict, generate_inference_id
from app.middleware.auth import AuthenticatedRequest
from app.middleware.rate_limit import require_scope_rate_limited
from app.models.alert import Alert
from app.models.inference import Inference
from app.models.model import MLModel
from app.services.audit import AuditService
from app.services.monitoring.baselines import BaselineService
from app.services.monitoring.data_quality import DataQualityService
from app.services.redaction import PIIRedactionEngine
from app.services.webhooks import WebhookService

router = APIRouter()


@router.post(
    "/ingest",
    response_model=InferenceResponse,
    summary="Ingest an inference",
    description=(
        "Submit inference data for PII redaction, quality checking, "
        "and secure storage. PII is automatically detected and masked."
    ),
)
async def ingest_inference(
    payload: InferenceRequest,
    request: Request,
    auth: AuthenticatedRequest = Depends(require_scope_rate_limited("ingest")),
    db: AsyncSession = Depends(get_db_session),
) -> InferenceResponse:
    """
    Process and store a healthcare AI inference securely.

    This is the primary endpoint that customers integrate with.
    Requires the 'ingest' scope.
    """
    tenant_id = auth.tenant_id
    inference_id = generate_inference_id()
    now = datetime.now(UTC)

    # ── 1. Look up or auto-register model ────────────────────────
    result = await db.execute(
        select(MLModel).where(
            MLModel.tenant_id == tenant_id,
            MLModel.model_name == payload.model_id,
            MLModel.is_active.is_(True),
        )
    )
    model = result.scalar_one_or_none()

    if model is None:
        # Auto-register model on first inference
        model = MLModel(
            tenant_id=tenant_id,
            model_name=payload.model_id,
            model_version=None,
            is_active=True,
        )
        db.add(model)
        await db.flush()

    # ── 2. PII Redaction ─────────────────────────────────────────
    redaction_engine = PIIRedactionEngine()
    redaction_result = redaction_engine.redact(payload.input_features)

    # ── 3. Data Quality Check ────────────────────────────────────
    dq_service = DataQualityService()
    dq_result = dq_service.check(
        input_features=redaction_result.redacted_data,
        required_fields=model.required_fields,
        field_ranges=model.field_ranges,
        field_types=model.field_types,
    )

    # ── 4. Baseline / Outlier Check ──────────────────────────────
    baseline_service = BaselineService(db)
    outlier_result = await baseline_service.check_outlier(
        model_id=model.id,
        prediction=payload.prediction,
        sigma_threshold=model.outlier_sigma,
    )

    # ── 5. Extract classification metadata ───────────────────────
    # LEARNING NOTE:
    #   We extract several pieces of metadata from the redaction result
    #   to store alongside the inference. This enables:
    #   - Fast queries: "show all inferences with behavioral health data"
    #   - Compliance reports: "X% of payloads contained genetic data"
    #   - Dashboard aggregation: breakdown by sensitivity level

    classification_summary = redaction_result.classification_summary
    high_fields = redaction_result.report.get("high_sensitivity_fields", [])
    sensitivity_breakdown = redaction_result.report.get("classification_breakdown", {})

    # Determine data type flags from classification summary categories
    categories_present = (
        classification_summary.get("by_category", {}) if classification_summary else {}
    )
    clinical_categories = {
        "diagnosis", "lab_result", "medication", "procedure",
        "vital_sign", "clinical_note", "imaging_reference",
    }
    behavioral_categories = {"behavioral_health"}
    genetic_categories = {"genetic"}

    contains_clinical = any(
        cat in categories_present for cat in clinical_categories
    )
    contains_behavioral = any(
        cat in categories_present for cat in behavioral_categories
    )
    contains_genetic = any(
        cat in categories_present for cat in genetic_categories
    )

    max_sensitivity = (
        classification_summary.get("highest_sensitivity")
        if classification_summary
        else None
    )

    # ── 6. Encrypt redacted data with per-tenant key isolation ────
    # LEARNING NOTE:
    #   We pass tenant_id AND key_version to encrypt_dict so that:
    #   - Each tenant's data is encrypted with a unique key
    #   - The key version matches what the tenant record tracks
    #   - During key rotation, new inferences use the new key version
    #     while old records retain their original key_version marker
    current_key_version = auth.tenant.encryption_key_version
    encrypted_features = encrypt_dict(
        redaction_result.redacted_data,
        tenant_id=tenant_id,
        key_version=current_key_version,
    )

    inference = Inference(
        id=inference_id,
        tenant_id=tenant_id,
        model_id=model.id,
        prediction=payload.prediction,
        confidence=payload.confidence,
        input_features_encrypted=encrypted_features,
        encryption_key_version=current_key_version,
        # PHI redaction metadata
        pii_detected=redaction_result.report["total_pii_found"] > 0,
        pii_redaction_count=redaction_result.report["total_pii_found"],
        pii_types_found=redaction_result.report["redactions"] or None,
        # Classification metadata
        classification_summary=classification_summary,
        high_sensitivity_fields=high_fields or None,
        max_sensitivity_level=max_sensitivity,
        sensitivity_counts=sensitivity_breakdown or None,
        # Data type flags
        contains_clinical_data=contains_clinical,
        contains_behavioral_health=contains_behavioral,
        contains_genetic_data=contains_genetic,
        data_categories_present=categories_present or None,
        # Data quality
        has_quality_issues=not dq_result.is_valid,
        quality_issues=(
            {"issues": [i.to_dict() for i in dq_result.issues]}
            if dq_result.issues
            else None
        ),
        is_outlier=outlier_result.is_outlier,
        outlier_reason=outlier_result.reason,
        received_at=now,
        request_id=payload.request_id,
        source_ip=request.client.host if request.client else None,
        metadata_json=payload.metadata,
    )

    db.add(inference)

    # ── 7. Create alerts if needed ───────────────────────────────
    alerts_list: list[dict[str, str]] = []

    if outlier_result.is_outlier:
        alert = Alert(
            tenant_id=tenant_id,
            model_id=model.id,
            alert_type="outlier",
            severity="warning",
            message=outlier_result.reason or "Prediction outlier detected",
            triggered_at=now,
            inference_id=inference_id,
            details={"bounds": outlier_result.bounds},
        )
        db.add(alert)
        alerts_list.append({
            "type": "outlier",
            "message": outlier_result.reason or "Prediction outlier detected",
        })

    if not dq_result.is_valid and dq_result.severity == "critical":
        alert = Alert(
            tenant_id=tenant_id,
            model_id=model.id,
            alert_type="data_quality",
            severity=dq_result.severity,
            message=f"Data quality issues: {dq_result.issue_count} problems found",
            triggered_at=now,
            inference_id=inference_id,
            details={"issues": [i.to_dict() for i in dq_result.issues]},
        )
        db.add(alert)
        alerts_list.append({
            "type": "data_quality",
            "message": f"{dq_result.issue_count} data quality issue(s) found",
        })

    # ── 8. Audit logging ─────────────────────────────────────────
    audit_service = AuditService(db)
    await audit_service.log_inference_received(
        tenant_id=tenant_id,
        inference_id=inference_id,
        model_id=model.id,
        pii_count=redaction_result.report["total_pii_found"],
        pii_types=redaction_result.report["redactions"] or None,
        ip_address=request.client.host if request.client else None,
    )

    if redaction_result.report["total_pii_found"] > 0:
        await audit_service.log_pii_redaction(
            tenant_id=tenant_id,
            inference_id=inference_id,
            pii_types=redaction_result.report["redactions"],
            total_redacted=redaction_result.report["total_pii_found"],
        )

    # ── 9. Publish real-time event (fire-and-forget) ─────────────
    # LEARNING NOTE:
    #   We publish AFTER the database write and audit log, so the event
    #   reflects committed state. The publish is best-effort: if Redis
    #   is down, the inference is still stored — real-time push is a
    #   nice-to-have, not a critical path. The payload contains only
    #   metadata (no encrypted features or PHI) to maintain HIPAA
    #   compliance even over the pub/sub channel.
    await event_publisher.publish(
        tenant_id=str(tenant_id),
        event_type="inference_received",
        payload={
            "inference_id": inference_id,
            "model_name": model.model_name,
            "prediction": payload.prediction,
            "confidence": payload.confidence,
            "pii_redacted": redaction_result.report["total_pii_found"],
            "is_outlier": outlier_result.is_outlier,
            "has_quality_issues": not dq_result.is_valid,
            "max_sensitivity": max_sensitivity,
            "timestamp": now.isoformat(),
        },
    )

    # Publish alert events separately (for real-time alert banners)
    for alert_info in alerts_list:
        await event_publisher.publish(
            tenant_id=str(tenant_id),
            event_type="alert_created",
            payload={
                "inference_id": inference_id,
                "alert_type": alert_info["type"],
                "message": alert_info["message"],
                "timestamp": now.isoformat(),
            },
        )

    # ── 9b. Webhook notifications (fire-and-forget) ──────────────
    # LEARNING NOTE:
    #   Webhooks deliver event payloads to tenant-configured HTTP endpoints.
    #   Like Redis pub/sub, this is best-effort and non-blocking.
    #   Payloads contain NO PHI — only metadata (alert type, inference ID,
    #   model name, counts). This ensures HIPAA compliance even if the
    #   receiving endpoint is outside the covered entity.
    try:
        webhook_service = WebhookService(db)

        # Dispatch alert events to subscribed webhooks
        for alert_info in alerts_list:
            event_type = (
                "outlier_detected"
                if alert_info["type"] == "outlier"
                else "data_quality_issue"
                if alert_info["type"] == "data_quality"
                else "alert_created"
            )
            await webhook_service.dispatch_event(
                tenant_id=str(tenant_id),
                event_type=event_type,
                payload={
                    "inference_id": inference_id,
                    "model_name": model.model_name,
                    "alert_type": alert_info["type"],
                    "message": alert_info["message"],
                    "prediction": payload.prediction,
                    "timestamp": now.isoformat(),
                },
                event_id=inference_id,
            )

            # Also dispatch generic alert_created for all alerts
            if event_type != "alert_created":
                await webhook_service.dispatch_event(
                    tenant_id=str(tenant_id),
                    event_type="alert_created",
                    payload={
                        "inference_id": inference_id,
                        "model_name": model.model_name,
                        "alert_type": alert_info["type"],
                        "message": alert_info["message"],
                        "timestamp": now.isoformat(),
                    },
                    event_id=inference_id,
                )

        # Dispatch PII detection event if PHI was found
        if redaction_result.report["total_pii_found"] > 0:
            await webhook_service.dispatch_event(
                tenant_id=str(tenant_id),
                event_type="pii_detected",
                payload={
                    "inference_id": inference_id,
                    "model_name": model.model_name,
                    "pii_count": redaction_result.report["total_pii_found"],
                    "pii_types": list(
                        (redaction_result.report.get("redactions") or {}).keys()
                    ),
                    "max_sensitivity": max_sensitivity,
                    "timestamp": now.isoformat(),
                },
                event_id=inference_id,
            )
    except Exception:
        # Webhook failure must NEVER break inference processing
        pass

    # ── 10. Check if we have enough data to initialize baseline ──
    if outlier_result.baseline_id is None:
        count = await baseline_service.get_inference_count(model.id, tenant_id)
        # +1 for the current inference (not yet committed)
        if count + 1 >= model.baseline_required_samples:
            predictions = await baseline_service.get_recent_predictions(
                model.id, tenant_id, model.baseline_required_samples
            )
            predictions.append(payload.prediction)
            if len(predictions) >= model.baseline_required_samples:
                await baseline_service.initialize_baseline(
                    tenant_id=tenant_id,
                    model_id=model.id,
                    predictions=predictions,
                )

    # ── 11. Build response ────────────────────────────────────────
    quality_issue_messages = [i.message for i in dq_result.issues]
    message = "Inference stored safely"
    if redaction_result.report["total_pii_found"] > 0:
        message += f". {redaction_result.report['total_pii_found']} PHI item(s) redacted"
    if high_fields:
        message += f". {len(high_fields)} field(s) marked for encryption"
    if outlier_result.is_outlier:
        message += ". Marked as outlier"
    if not dq_result.is_valid:
        message += f". {dq_result.issue_count} data quality issue(s)"

    return InferenceResponse(
        status="received",
        message=message,
        inference_id=inference_id,
        pii_redacted=redaction_result.report["total_pii_found"],
        data_quality_issues=quality_issue_messages,
        alerts=alerts_list if alerts_list else None,
        timestamp=now,
    )
