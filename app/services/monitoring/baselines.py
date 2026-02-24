"""
Baseline computation and outlier detection service.

Uses 3-sigma rule: if prediction is outside [mean - 3*std, mean + 3*std],
it's flagged as an outlier.

Simple, auditable, and effective for healthcare AI monitoring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.baseline import Baseline
from app.models.inference import Inference

logger = get_logger("baseline_service")


class OutlierResult:
    """Result of an outlier check."""

    __slots__ = ("is_outlier", "reason", "bounds", "baseline_id")

    def __init__(
        self,
        is_outlier: bool,
        reason: str | None = None,
        bounds: dict[str, float] | None = None,
        baseline_id: str | None = None,
    ):
        self.is_outlier = is_outlier
        self.reason = reason
        self.bounds = bounds
        self.baseline_id = baseline_id


class BaselineService:
    """Service for computing baselines and detecting outliers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def get_current_baseline(
        self, model_id: str
    ) -> Baseline | None:
        """Get the current active baseline for a model."""
        result = await self.db.execute(
            select(Baseline)
            .where(
                Baseline.model_id == model_id,
                Baseline.is_current.is_(True),
            )
            .order_by(Baseline.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def initialize_baseline(
        self,
        tenant_id: str,
        model_id: str,
        predictions: list[float],
    ) -> Baseline:
        """
        Initialize a baseline from a set of predictions.

        Called when enough samples have been collected for a model.
        """
        if len(predictions) < self.settings.BASELINE_MIN_SAMPLES:
            raise ValueError(
                f"Need at least {self.settings.BASELINE_MIN_SAMPLES} samples, "
                f"got {len(predictions)}"
            )

        arr = np.array(predictions, dtype=np.float64)

        # Mark any existing baselines as not current
        await self.db.execute(
            update(Baseline)
            .where(
                Baseline.model_id == model_id,
                Baseline.is_current.is_(True),
            )
            .values(is_current=False, valid_until=datetime.now(UTC))
        )

        # Create new baseline
        baseline = Baseline(
            tenant_id=tenant_id,
            model_id=model_id,
            mean=float(np.mean(arr)),
            std=float(np.std(arr)),
            median=float(np.median(arr)),
            min_val=float(np.min(arr)),
            max_val=float(np.max(arr)),
            sample_size=len(predictions),
            computation_method="initial",
            valid_from=datetime.now(UTC),
            is_current=True,
        )

        self.db.add(baseline)
        await self.db.flush()

        logger.info(
            "baseline_initialized",
            model_id=model_id,
            mean=baseline.mean,
            std=baseline.std,
            sample_size=baseline.sample_size,
        )

        return baseline

    async def check_outlier(
        self,
        model_id: str,
        prediction: float,
        sigma_threshold: float | None = None,
    ) -> OutlierResult:
        """
        Check if a prediction is an outlier against the current baseline.

        Uses the 3-sigma rule by default.
        """
        baseline = await self.get_current_baseline(model_id)

        if baseline is None:
            return OutlierResult(
                is_outlier=False,
                reason="No baseline available yet",
            )

        threshold = sigma_threshold or self.settings.OUTLIER_SIGMA_THRESHOLD

        # Avoid division by zero if std is 0
        if baseline.std == 0:
            is_outlier = prediction != baseline.mean
            reason = (
                f"Prediction {prediction:.4f} differs from constant baseline {baseline.mean:.4f}"
                if is_outlier
                else None
            )
            return OutlierResult(
                is_outlier=is_outlier,
                reason=reason,
                bounds={"lower": baseline.mean, "upper": baseline.mean},
                baseline_id=baseline.id,
            )

        lower_bound = baseline.mean - (threshold * baseline.std)
        upper_bound = baseline.mean + (threshold * baseline.std)
        is_outlier = prediction < lower_bound or prediction > upper_bound

        reason = None
        if is_outlier:
            if prediction < lower_bound:
                reason = (
                    f"Prediction {prediction:.4f} below lower bound "
                    f"{lower_bound:.4f} (mean={baseline.mean:.4f}, "
                    f"std={baseline.std:.4f}, threshold={threshold}sigma)"
                )
            else:
                reason = (
                    f"Prediction {prediction:.4f} above upper bound "
                    f"{upper_bound:.4f} (mean={baseline.mean:.4f}, "
                    f"std={baseline.std:.4f}, threshold={threshold}sigma)"
                )

        return OutlierResult(
            is_outlier=is_outlier,
            reason=reason,
            bounds={"lower": float(lower_bound), "upper": float(upper_bound)},
            baseline_id=baseline.id,
        )

    async def get_inference_count(
        self, model_id: str, tenant_id: str
    ) -> int:
        """Get total inference count for a model."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(Inference.id)).where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
            )
        )
        return result.scalar_one()

    async def get_recent_predictions(
        self, model_id: str, tenant_id: str, limit: int = 1000
    ) -> list[float]:
        """Get recent prediction values for baseline computation."""
        result = await self.db.execute(
            select(Inference.prediction)
            .where(
                Inference.model_id == model_id,
                Inference.tenant_id == tenant_id,
            )
            .order_by(Inference.received_at.desc())
            .limit(limit)
        )
        return [row[0] for row in result.all()]
