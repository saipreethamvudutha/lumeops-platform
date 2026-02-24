"""
Model Performance Tracking Service.

Computes and queries aggregated model performance metrics.

LEARNING NOTE — Design Decisions:

    1. ON-DEMAND COMPUTATION:
       Snapshots are computed when requested (via API) rather than on a
       background scheduler. This simplifies deployment (no Celery/cron)
       while still being fast because PostgreSQL handles the aggregation.
       For production at scale, you'd add a periodic task (e.g., Celery beat)
       to pre-compute snapshots every hour.

    2. SQL-LEVEL AGGREGATION:
       All metric computation happens in PostgreSQL using aggregate functions
       (AVG, STDDEV, MIN, MAX, percentile_cont). This is far more efficient
       than loading all rows into Python — PostgreSQL processes millions of
       rows in seconds using indexed scans.

    3. DRIFT DETECTION:
       Drift score = |period_mean - baseline_mean| / baseline_std
       This is a simplified version of the Population Stability Index (PSI).
       A score > 2.0 suggests the model's prediction distribution has
       shifted significantly from its training baseline. In healthcare,
       this could indicate:
       - Patient population change (e.g., flu season shifts demographics)
       - Upstream data pipeline change (e.g., lab units changed)
       - Model degradation (gradual concept drift)

    4. GROUND TRUTH PIPELINE:
       The inference table has `ground_truth` and `ground_truth_received_at`
       columns already. When ground truth is submitted (via dedicated endpoint),
       accuracy metrics (MAE, RMSE) become available. Without ground truth,
       these fields remain null — the dashboard shows "N/A" instead of
       misleading zeros.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.baseline import Baseline
from app.models.inference import Inference
from app.models.model import MLModel
from app.models.performance_snapshot import ModelPerformanceSnapshot

logger = get_logger("performance_service")


class PerformanceService:
    """
    Service for computing and querying model performance metrics.

    Provides:
    - Real-time metric computation from inference data
    - Performance snapshot generation
    - Model comparison across time periods
    - Drift detection against baselines
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_model_summary(
        self,
        model_id: str,
        tenant_id: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Compute comprehensive model performance summary.

        This is the primary endpoint data source. It computes metrics
        directly from the inferences table for the specified time window.

        Returns dict with:
        - model: Model info
        - volume: Inference counts and trends
        - predictions: Distribution statistics
        - accuracy: MAE, RMSE (if ground truth available)
        - health: Outlier rate, quality rate, PII stats
        - drift: Drift score from baseline
        - confidence: Confidence distribution
        """
        now = datetime.now(UTC)
        start = now - timedelta(days=days)

        # ── Fetch model ──────────────────────────────────────────
        model_result = await self.db.execute(
            select(MLModel).where(
                MLModel.id == model_id,
                MLModel.tenant_id == tenant_id,
            )
        )
        model = model_result.scalar_one_or_none()
        if not model:
            return None

        # ── Volume metrics ───────────────────────────────────────
        volume_query = select(
            func.count(Inference.id).label("total"),
            func.count(Inference.ground_truth).label("with_ground_truth"),
        ).where(
            Inference.model_id == model_id,
            Inference.tenant_id == tenant_id,
            Inference.received_at >= start,
        )
        volume_result = await self.db.execute(volume_query)
        volume_row = volume_result.one()
        total = volume_row.total
        with_gt = volume_row.with_ground_truth

        # All-time count
        all_time_result = await self.db.execute(
            select(func.count(Inference.id)).where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
            )
        )
        all_time_count = all_time_result.scalar() or 0

        # Today count
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_result = await self.db.execute(
            select(func.count(Inference.id)).where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
                Inference.received_at >= today_start,
            )
        )
        today_count = today_result.scalar() or 0

        # ── Prediction distribution ──────────────────────────────
        if total > 0:
            pred_query = select(
                func.avg(Inference.prediction).label("mean"),
                func.stddev(Inference.prediction).label("std"),
                func.min(Inference.prediction).label("min_val"),
                func.max(Inference.prediction).label("max_val"),
            ).where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
                Inference.received_at >= start,
            )
            pred_result = await self.db.execute(pred_query)
            pred_row = pred_result.one()

            # Percentiles via SQL
            percentile_query = text("""
                SELECT
                    percentile_cont(0.50) WITHIN GROUP (ORDER BY prediction) as p50,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY prediction) as p95,
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY prediction) as p99
                FROM inferences
                WHERE model_id = :model_id
                  AND tenant_id = :tenant_id
                  AND received_at >= :start
            """)
            pct_result = await self.db.execute(
                percentile_query,
                {"model_id": model_id, "tenant_id": tenant_id, "start": start},
            )
            pct_row = pct_result.one()

            predictions = {
                "mean": _safe_round(pred_row.mean),
                "std": _safe_round(pred_row.std),
                "min": _safe_round(pred_row.min_val),
                "max": _safe_round(pred_row.max_val),
                "p50": _safe_round(pct_row.p50),
                "p95": _safe_round(pct_row.p95),
                "p99": _safe_round(pct_row.p99),
            }
        else:
            predictions = {
                "mean": None, "std": None, "min": None, "max": None,
                "p50": None, "p95": None, "p99": None,
            }

        # ── Accuracy metrics (if ground truth available) ─────────
        accuracy = {"mae": None, "rmse": None, "mean_error": None}
        if with_gt > 0:
            acc_query = select(
                func.avg(
                    func.abs(Inference.prediction - Inference.ground_truth)
                ).label("mae"),
                func.sqrt(
                    func.avg(
                        func.pow(
                            Inference.prediction - Inference.ground_truth,
                            2,
                        )
                    )
                ).label("rmse"),
                func.avg(
                    Inference.prediction - Inference.ground_truth
                ).label("mean_error"),
            ).where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
                Inference.received_at >= start,
                Inference.ground_truth.is_not(None),
            )
            acc_result = await self.db.execute(acc_query)
            acc_row = acc_result.one()
            accuracy = {
                "mae": _safe_round(acc_row.mae),
                "rmse": _safe_round(acc_row.rmse),
                "mean_error": _safe_round(acc_row.mean_error),
            }

        # ── Health metrics ───────────────────────────────────────
        health_query = select(
            func.count(Inference.id).filter(
                Inference.is_outlier.is_(True)
            ).label("outliers"),
            func.count(Inference.id).filter(
                Inference.has_quality_issues.is_(True)
            ).label("quality_issues"),
            func.count(Inference.id).filter(
                Inference.pii_detected.is_(True)
            ).label("pii_inferences"),
            func.coalesce(
                func.sum(Inference.pii_redaction_count), 0
            ).label("total_pii"),
        ).where(
            Inference.model_id == model_id,
            Inference.tenant_id == tenant_id,
            Inference.received_at >= start,
        )
        health_result = await self.db.execute(health_query)
        health_row = health_result.one()

        health = {
            "outlier_count": health_row.outliers,
            "outlier_rate": _safe_round(
                health_row.outliers / total if total > 0 else 0
            ),
            "quality_issue_count": health_row.quality_issues,
            "quality_rate": _safe_round(
                (total - health_row.quality_issues) / total if total > 0 else 1.0
            ),
            "pii_inferences": health_row.pii_inferences,
            "total_pii_redacted": health_row.total_pii,
        }

        # ── Confidence distribution ──────────────────────────────
        conf_query = select(
            func.avg(Inference.confidence).label("avg"),
            func.min(Inference.confidence).label("min_val"),
            func.max(Inference.confidence).label("max_val"),
        ).where(
            Inference.model_id == model_id,
            Inference.tenant_id == tenant_id,
            Inference.received_at >= start,
            Inference.confidence.is_not(None),
        )
        conf_result = await self.db.execute(conf_query)
        conf_row = conf_result.one()
        confidence = {
            "avg": _safe_round(conf_row.avg),
            "min": _safe_round(conf_row.min_val),
            "max": _safe_round(conf_row.max_val),
        }

        # ── Drift detection ──────────────────────────────────────
        drift = await self._compute_drift(
            model_id, tenant_id, predictions.get("mean"), predictions.get("std")
        )

        # ── Alert summary ────────────────────────────────────────
        alert_query = select(
            func.count(Alert.id).label("total"),
            Alert.severity,
        ).where(
            Alert.model_id == model_id,
            Alert.tenant_id == tenant_id,
            Alert.triggered_at >= start,
        ).group_by(Alert.severity)

        alert_result = await self.db.execute(alert_query)
        alerts_by_sev = {}
        total_alerts = 0
        for row in alert_result:
            alerts_by_sev[row.severity] = row.total
            total_alerts += row.total

        return {
            "model": {
                "id": model.id,
                "model_name": model.model_name,
                "model_version": model.model_version,
                "description": model.description,
                "framework": model.framework,
                "is_active": model.is_active,
                "tags": model.tags,
                "created_at": model.created_at.isoformat(),
            },
            "period": {
                "days": days,
                "start": start.isoformat(),
                "end": now.isoformat(),
            },
            "volume": {
                "total": total,
                "today": today_count,
                "all_time": all_time_count,
                "with_ground_truth": with_gt,
                "ground_truth_coverage": _safe_round(
                    with_gt / total if total > 0 else 0
                ),
            },
            "predictions": predictions,
            "accuracy": accuracy,
            "health": health,
            "confidence": confidence,
            "drift": drift,
            "alerts": {
                "total": total_alerts,
                "by_severity": alerts_by_sev,
            },
            "generated_at": now.isoformat(),
        }

    async def get_performance_timeseries(
        self,
        model_id: str,
        tenant_id: str,
        days: int = 7,
        granularity: str = "daily",
    ) -> list[dict[str, Any]]:
        """
        Get time-bucketed performance metrics for charts.

        Returns a list of data points, one per time bucket.
        Each point contains volume, prediction stats, health metrics.
        """
        now = datetime.now(UTC)
        start = now - timedelta(days=days)

        trunc_fn = "hour" if granularity == "hourly" else "day"

        query = text(f"""
            SELECT
                date_trunc('{trunc_fn}', received_at) as bucket,
                COUNT(*) as total,
                COUNT(ground_truth) as with_gt,
                AVG(prediction) as pred_mean,
                STDDEV(prediction) as pred_std,
                MIN(prediction) as pred_min,
                MAX(prediction) as pred_max,
                COUNT(*) FILTER (WHERE is_outlier = true) as outliers,
                COUNT(*) FILTER (WHERE has_quality_issues = true) as quality_issues,
                COUNT(*) FILTER (WHERE pii_detected = true) as pii_inferences,
                COALESCE(SUM(pii_redaction_count), 0) as total_pii,
                AVG(confidence) as avg_confidence,
                CASE WHEN COUNT(ground_truth) > 0
                    THEN AVG(ABS(prediction - ground_truth))
                    ELSE NULL
                END as mae,
                CASE WHEN COUNT(ground_truth) > 0
                    THEN SQRT(AVG(POWER(prediction - ground_truth, 2)))
                    ELSE NULL
                END as rmse
            FROM inferences
            WHERE model_id = :model_id
              AND tenant_id = :tenant_id
              AND received_at >= :start
            GROUP BY bucket
            ORDER BY bucket ASC
        """)

        result = await self.db.execute(
            query,
            {"model_id": model_id, "tenant_id": tenant_id, "start": start},
        )

        series = []
        for row in result:
            total = row.total
            series.append({
                "timestamp": row.bucket.isoformat(),
                "total_inferences": total,
                "with_ground_truth": row.with_gt,
                "prediction_mean": _safe_round(row.pred_mean),
                "prediction_std": _safe_round(row.pred_std),
                "prediction_min": _safe_round(row.pred_min),
                "prediction_max": _safe_round(row.pred_max),
                "outlier_count": row.outliers,
                "outlier_rate": _safe_round(
                    row.outliers / total if total > 0 else 0
                ),
                "quality_issue_count": row.quality_issues,
                "quality_rate": _safe_round(
                    (total - row.quality_issues) / total if total > 0 else 1.0
                ),
                "pii_inferences": row.pii_inferences,
                "total_pii_redacted": row.total_pii,
                "avg_confidence": _safe_round(row.avg_confidence),
                "mae": _safe_round(row.mae),
                "rmse": _safe_round(row.rmse),
            })

        return series

    async def submit_ground_truth(
        self,
        inference_id: str,
        tenant_id: str,
        ground_truth: float,
    ) -> dict[str, Any]:
        """
        Submit ground truth for a specific inference.

        This fills in the `ground_truth` and `ground_truth_received_at`
        columns, enabling accuracy metric computation.

        Returns the updated inference summary.
        """
        result = await self.db.execute(
            select(Inference).where(
                Inference.id == inference_id,
                Inference.tenant_id == tenant_id,
            )
        )
        inference = result.scalar_one_or_none()
        if not inference:
            return None

        now = datetime.now(UTC)
        inference.ground_truth = ground_truth
        inference.ground_truth_received_at = now

        error = abs(inference.prediction - ground_truth)

        return {
            "inference_id": inference.id,
            "model_id": inference.model_id,
            "prediction": inference.prediction,
            "ground_truth": ground_truth,
            "absolute_error": _safe_round(error),
            "submitted_at": now.isoformat(),
        }

    async def submit_ground_truth_batch(
        self,
        tenant_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Submit ground truth for multiple inferences at once.

        Each item in the list should have:
        - inference_id: str
        - ground_truth: float

        Returns summary of processed/skipped counts.
        """
        now = datetime.now(UTC)
        processed = 0
        skipped = 0
        errors_list = []

        for item in items:
            inf_id = item.get("inference_id")
            gt_val = item.get("ground_truth")

            if inf_id is None or gt_val is None:
                skipped += 1
                continue

            result = await self.db.execute(
                select(Inference).where(
                    Inference.id == inf_id,
                    Inference.tenant_id == tenant_id,
                )
            )
            inference = result.scalar_one_or_none()

            if not inference:
                skipped += 1
                errors_list.append({"inference_id": inf_id, "error": "not_found"})
                continue

            inference.ground_truth = float(gt_val)
            inference.ground_truth_received_at = now
            processed += 1

        return {
            "processed": processed,
            "skipped": skipped,
            "total": len(items),
            "errors": errors_list if errors_list else None,
        }

    async def get_models_overview(
        self,
        tenant_id: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get a quick performance overview for all models.

        Used by the Models list page to show summary stats per model.
        """
        now = datetime.now(UTC)
        start = now - timedelta(days=days)

        # Get all models with inference stats
        query = text("""
            SELECT
                m.id,
                m.model_name,
                m.model_version,
                m.framework,
                m.is_active,
                m.created_at,
                COUNT(i.id) as total_inferences,
                COUNT(i.id) FILTER (WHERE i.received_at >= :start) as recent_inferences,
                COUNT(i.id) FILTER (WHERE i.is_outlier = true AND i.received_at >= :start) as recent_outliers,
                COUNT(i.id) FILTER (WHERE i.has_quality_issues = true AND i.received_at >= :start) as recent_quality_issues,
                AVG(i.prediction) FILTER (WHERE i.received_at >= :start) as recent_pred_mean,
                AVG(i.confidence) FILTER (WHERE i.received_at >= :start) as recent_avg_confidence,
                COUNT(i.ground_truth) FILTER (WHERE i.received_at >= :start) as recent_with_gt,
                MAX(i.received_at) as last_inference_at
            FROM ml_models m
            LEFT JOIN inferences i ON i.model_id = m.id AND i.tenant_id = m.tenant_id
            WHERE m.tenant_id = :tenant_id
            GROUP BY m.id
            ORDER BY m.created_at DESC
        """)

        result = await self.db.execute(
            query, {"tenant_id": tenant_id, "start": start}
        )

        models = []
        for row in result:
            recent = row.recent_inferences or 0
            models.append({
                "id": row.id,
                "model_name": row.model_name,
                "model_version": row.model_version,
                "framework": row.framework,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "total_inferences": row.total_inferences or 0,
                "recent_inferences": recent,
                "recent_outliers": row.recent_outliers or 0,
                "recent_quality_issues": row.recent_quality_issues or 0,
                "outlier_rate": _safe_round(
                    (row.recent_outliers or 0) / recent if recent > 0 else 0
                ),
                "quality_rate": _safe_round(
                    (recent - (row.recent_quality_issues or 0)) / recent
                    if recent > 0 else 1.0
                ),
                "prediction_mean": _safe_round(row.recent_pred_mean),
                "avg_confidence": _safe_round(row.recent_avg_confidence),
                "ground_truth_coverage": _safe_round(
                    (row.recent_with_gt or 0) / recent if recent > 0 else 0
                ),
                "last_inference_at": (
                    row.last_inference_at.isoformat()
                    if row.last_inference_at else None
                ),
            })

        return models

    async def _compute_drift(
        self,
        model_id: str,
        tenant_id: str,
        current_mean: float | None,
        current_std: float | None,
    ) -> dict[str, Any]:
        """
        Compute drift score by comparing current prediction distribution
        to the model's baseline.

        Drift score = |current_mean - baseline_mean| / baseline_std

        Interpretation:
        - < 0.5: Stable (within normal variation)
        - 0.5 - 1.0: Minor drift (monitor closely)
        - 1.0 - 2.0: Moderate drift (investigate)
        - > 2.0: Significant drift (action needed)
        """
        if current_mean is None:
            return {
                "score": None,
                "status": "no_data",
                "baseline_mean": None,
                "baseline_std": None,
            }

        # Get current baseline
        baseline_result = await self.db.execute(
            select(Baseline).where(
                Baseline.model_id == model_id,
                Baseline.is_current.is_(True),
            )
        )
        baseline = baseline_result.scalar_one_or_none()

        if not baseline:
            return {
                "score": None,
                "status": "no_baseline",
                "baseline_mean": None,
                "baseline_std": None,
            }

        if baseline.std == 0 or baseline.std is None:
            return {
                "score": 0.0 if current_mean == baseline.mean else 999.0,
                "status": "constant_baseline",
                "baseline_mean": baseline.mean,
                "baseline_std": 0.0,
            }

        drift_score = abs(current_mean - baseline.mean) / baseline.std

        if drift_score < 0.5:
            status = "stable"
        elif drift_score < 1.0:
            status = "minor_drift"
        elif drift_score < 2.0:
            status = "moderate_drift"
        else:
            status = "significant_drift"

        return {
            "score": _safe_round(drift_score),
            "status": status,
            "baseline_mean": _safe_round(baseline.mean),
            "baseline_std": _safe_round(baseline.std),
        }


def _safe_round(value: Any, digits: int = 4) -> float | None:
    """Safely round a value, returning None for None/NaN/Inf."""
    if value is None:
        return None
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return round(val, digits)
    except (TypeError, ValueError):
        return None
