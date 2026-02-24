"""
HIPAA Minimum Necessary Rule Enforcement.

WHAT THIS DOES:
    Implements HIPAA's "minimum necessary" standard (45 CFR 164.502(b)).
    Before any data is stored or returned in a response, this filter
    removes fields that are NOT needed for the intended purpose.

WHY THIS IS CRITICAL:
    HIPAA doesn't just say "protect PHI." It says you must ONLY use
    the minimum amount of PHI needed for the task at hand.

    For LumeOps (AI monitoring), we need:
    ✓ Model predictions and confidence scores
    ✓ Data quality metrics (completeness, ranges)
    ✓ Statistical aggregates (mean, median, outlier rates)
    ✓ Anonymized clinical data (for monitoring model performance)

    We do NOT need:
    ✗ Patient names, SSNs, or any direct identifiers
    ✗ Raw clinical notes (only anonymized summaries)
    ✗ Full medical records
    ✗ Contact information
    ✗ Financial account details

HOW IT WORKS:
    The filter defines "purpose profiles" -- for each API purpose
    (monitoring, compliance reporting, dashboards), there's a list
    of what data categories are permitted. Everything else is stripped.

PROCESSING ORDER:
    Input → Redaction Engine (removes CRITICAL) → Minimum Necessary
    Filter (strips unnecessary fields) → Encryption → Storage

    The Minimum Necessary Filter runs AFTER redaction because:
    1. Redaction removes identifiers (safety-critical)
    2. Minimum necessary removes unnecessary fields (compliance)
    3. These are independent concerns that should be separated

LEARNING NOTE:
    This is one of the most commonly overlooked HIPAA requirements.
    Many systems redact SSNs but still store full clinical notes
    when all they need is "patient has diabetes." The minimum
    necessary filter ensures we only keep what we actually use.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.core.logging import get_logger
from app.services.redaction.classification import (
    DataCategory,
    DataClassifier,
    SensitivityLevel,
)

logger = get_logger("minimum_necessary")


class DataPurpose(str, Enum):
    """
    Intended purpose of data access.

    LEARNING NOTE:
        Each purpose has different data needs. A dashboard showing
        model performance only needs predictions and quality scores.
        A compliance report needs more metadata but still no raw PHI.
        This is the "role-based" aspect of minimum necessary.
    """

    # AI model performance monitoring
    MODEL_MONITORING = "model_monitoring"

    # Data quality assessment
    DATA_QUALITY = "data_quality"

    # HIPAA compliance reporting
    COMPLIANCE_REPORTING = "compliance_reporting"

    # Dashboard display
    DASHBOARD = "dashboard"

    # Full audit trail (most permissive -- still no raw PHI)
    AUDIT = "audit"

    # Inference storage (default processing)
    STORAGE = "storage"


# ── Purpose-Based Data Category Permissions ─────────────────────
#
# LEARNING NOTE:
#   Each purpose defines which data categories it's allowed to see.
#   This implements "role-based minimum necessary" -- different
#   functions in the system have different data needs.
#
#   Important: Even the most permissive purpose (AUDIT) never
#   includes direct identifiers. Those are ALWAYS stripped by the
#   redaction engine before this filter even runs.

PURPOSE_PERMISSIONS: dict[DataPurpose, set[str]] = {
    DataPurpose.MODEL_MONITORING: {
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.VITAL_SIGN,       # For monitoring data quality
        DataCategory.LAB_RESULT,       # For monitoring value ranges
        DataCategory.OPERATIONAL,
    },

    DataPurpose.DATA_QUALITY: {
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.VITAL_SIGN,
        DataCategory.LAB_RESULT,
        DataCategory.DIAGNOSIS,         # Need diagnosis codes for accuracy
        DataCategory.MEDICATION,        # Need med codes for accuracy
        DataCategory.OPERATIONAL,
    },

    DataPurpose.COMPLIANCE_REPORTING: {
        # Compliance needs metadata about what was found, not the data itself
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.OPERATIONAL,
        DataCategory.BILLING,
        DataCategory.INSURANCE,
    },

    DataPurpose.DASHBOARD: {
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.OPERATIONAL,
    },

    DataPurpose.AUDIT: {
        # Audit can see everything except direct identifiers
        # (which are already redacted at this point)
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.OPERATIONAL,
        DataCategory.BILLING,
        DataCategory.INSURANCE,
        DataCategory.VITAL_SIGN,
        DataCategory.LAB_RESULT,
        DataCategory.DIAGNOSIS,
        DataCategory.MEDICATION,
        DataCategory.PROCEDURE,
        DataCategory.CLINICAL_NOTE,
        DataCategory.IMAGING_REF,
        DataCategory.DEMOGRAPHIC,
        DataCategory.GEOGRAPHIC,
    },

    DataPurpose.STORAGE: {
        # Storage keeps everything (after redaction + encryption)
        # because we may need clinical data for future analysis.
        # But direct identifiers are already redacted.
        DataCategory.MODEL_OUTPUT,
        DataCategory.SYSTEM,
        DataCategory.OPERATIONAL,
        DataCategory.BILLING,
        DataCategory.INSURANCE,
        DataCategory.VITAL_SIGN,
        DataCategory.LAB_RESULT,
        DataCategory.DIAGNOSIS,
        DataCategory.MEDICATION,
        DataCategory.PROCEDURE,
        DataCategory.CLINICAL_NOTE,
        DataCategory.IMAGING_REF,
        DataCategory.GENETIC,
        DataCategory.BEHAVIORAL_HEALTH,
        DataCategory.DEMOGRAPHIC,
        DataCategory.GEOGRAPHIC,
        DataCategory.INDIRECT_IDENTIFIER,
        DataCategory.UNKNOWN,
    },
}


class MinimumNecessaryResult:
    """Result of applying the minimum necessary filter."""

    __slots__ = (
        "filtered_data", "fields_removed", "fields_retained",
        "purpose", "removal_report",
    )

    def __init__(
        self,
        filtered_data: dict[str, Any],
        fields_removed: list[str],
        fields_retained: list[str],
        purpose: DataPurpose,
        removal_report: list[dict[str, str]],
    ):
        self.filtered_data = filtered_data
        self.fields_removed = fields_removed
        self.fields_retained = fields_retained
        self.purpose = purpose
        self.removal_report = removal_report

    def to_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose.value,
            "fields_removed_count": len(self.fields_removed),
            "fields_retained_count": len(self.fields_retained),
            "fields_removed": self.fields_removed,
            "removal_report": self.removal_report,
        }


class MinimumNecessaryFilter:
    """
    Apply HIPAA minimum necessary rule to data.

    USAGE:
        filter = MinimumNecessaryFilter()

        # For dashboard display -- only model outputs
        result = filter.apply(data, purpose=DataPurpose.DASHBOARD)

        # For storage -- keep everything after redaction
        result = filter.apply(data, purpose=DataPurpose.STORAGE)

    LEARNING NOTE:
        This filter works on already-redacted data. By the time data
        reaches this filter:
        1. All CRITICAL identifiers are replaced with [REDACTED_X] tokens
        2. All HIGH fields are marked for encryption

        The minimum necessary filter then further reduces the data
        based on the purpose. A dashboard doesn't need clinical notes
        even if they're anonymized.
    """

    def __init__(self):
        self.classifier = DataClassifier()

    def apply(
        self,
        data: dict[str, Any],
        purpose: DataPurpose = DataPurpose.STORAGE,
    ) -> MinimumNecessaryResult:
        """
        Apply minimum necessary filtering to data.

        Args:
            data: The data to filter (should be already redacted).
            purpose: The intended purpose determines what's allowed.

        Returns:
            MinimumNecessaryResult with filtered data and removal report.
        """
        permitted_categories = PURPOSE_PERMISSIONS.get(
            purpose, PURPOSE_PERMISSIONS[DataPurpose.DASHBOARD]
        )

        filtered = {}
        removed: list[str] = []
        retained: list[str] = []
        removal_report: list[dict[str, str]] = []

        for key, value in data.items():
            classification = self.classifier.classify_field(key, value)

            if classification.category in permitted_categories:
                filtered[key] = value
                retained.append(key)
            else:
                removed.append(key)
                removal_report.append({
                    "field": key,
                    "category": classification.category,
                    "sensitivity": classification.sensitivity.name,
                    "reason": (
                        f"Category '{classification.category}' not permitted "
                        f"for purpose '{purpose.value}'"
                    ),
                })

                logger.info(
                    "field_filtered_minimum_necessary",
                    field=key,
                    category=classification.category,
                    purpose=purpose.value,
                )

        return MinimumNecessaryResult(
            filtered_data=filtered,
            fields_removed=removed,
            fields_retained=retained,
            purpose=purpose,
            removal_report=removal_report,
        )

    def check_access_permitted(
        self,
        field_name: str,
        purpose: DataPurpose,
    ) -> bool:
        """
        Check if accessing a specific field is permitted for a purpose.

        Useful for pre-flight checks before querying data.
        """
        classification = self.classifier.classify_field(field_name)
        permitted_categories = PURPOSE_PERMISSIONS.get(
            purpose, PURPOSE_PERMISSIONS[DataPurpose.DASHBOARD]
        )
        return classification.category in permitted_categories

    def get_permitted_fields(
        self,
        data: dict[str, Any],
        purpose: DataPurpose,
    ) -> list[str]:
        """
        Get list of field names that are permitted for a purpose.

        Useful for building SQL queries that only select allowed columns.
        """
        permitted_categories = PURPOSE_PERMISSIONS.get(
            purpose, PURPOSE_PERMISSIONS[DataPurpose.DASHBOARD]
        )
        permitted = []
        for key in data.keys():
            classification = self.classifier.classify_field(key)
            if classification.category in permitted_categories:
                permitted.append(key)
        return permitted
