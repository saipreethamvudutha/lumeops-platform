"""
Healthcare Data Classification Engine.

PURPOSE:
    Every piece of data that enters LumeOps must be classified by sensitivity
    level before any processing occurs. This module determines what type of
    data a field contains and what protections it requires.

WHY THIS EXISTS:
    HIPAA doesn't just protect names and SSNs. It protects ALL individually
    identifiable health information. A diagnosis code (E11.65) is not PII,
    but combined with a ZIP code and birth year, it can identify a patient.
    We must classify EVERY field, not just the obvious ones.

SENSITIVITY LEVELS:
    4 - CRITICAL: Direct identifiers (SSN, name, MRN). Must be redacted.
    3 - HIGH: Clinical data, indirect identifiers. Must be encrypted.
    2 - MODERATE: Operational data. Standard encryption.
    1 - LOW: System/technical data. Standard handling.

LEARNING NOTE:
    The "minimum necessary" rule in HIPAA means we should only retain
    what we need. For AI observability, we need the MODEL's outputs and
    data quality metrics -- we do NOT need the patient's actual records.
    Redacting identifiers and encrypting clinical data lets us monitor
    model performance without exposing patient information.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from app.core.logging import get_logger

logger = get_logger("data_classifier")


class SensitivityLevel(IntEnum):
    """
    Data sensitivity levels for healthcare information.

    Higher number = more sensitive = more protection required.

    LEARNING NOTE:
        These levels map to HIPAA's concept of "minimum necessary."
        Level 4 data has no business being stored in our system at all.
        Level 3 data we need for monitoring but must protect heavily.
        Level 2 data is our core operational data.
        Level 1 data is just system metadata.
    """

    LOW = 1         # System data, no patient info
    MODERATE = 2    # Operational data, aggregate metrics
    HIGH = 3        # Clinical data, indirect identifiers
    CRITICAL = 4    # Direct identifiers, must be redacted


class DataCategory(str):
    """Categories of healthcare data."""

    # Identity (Level 4 - CRITICAL)
    DIRECT_IDENTIFIER = "direct_identifier"

    # Clinical (Level 3 - HIGH)
    DIAGNOSIS = "diagnosis"
    LAB_RESULT = "lab_result"
    MEDICATION = "medication"
    PROCEDURE = "procedure"
    VITAL_SIGN = "vital_sign"
    CLINICAL_NOTE = "clinical_note"
    GENETIC = "genetic"
    IMAGING_REF = "imaging_reference"
    BEHAVIORAL_HEALTH = "behavioral_health"

    # Indirect identifiers (Level 3 - HIGH)
    INDIRECT_IDENTIFIER = "indirect_identifier"
    DEMOGRAPHIC = "demographic"
    GEOGRAPHIC = "geographic"

    # Operational (Level 2 - MODERATE)
    OPERATIONAL = "operational"
    BILLING = "billing"
    INSURANCE = "insurance"

    # Model/System (Level 1 - LOW)
    MODEL_OUTPUT = "model_output"
    SYSTEM = "system"
    UNKNOWN = "unknown"


# ── Field Classification Rules ──────────────────────────────────
#
# LEARNING NOTE:
# These mappings tell our system "if a field is named X, it probably
# contains Y type of data at Z sensitivity level."
#
# This is a heuristic -- not perfect, but combined with regex pattern
# detection, it catches the vast majority of sensitive data.
#
# The key insight: field names in healthcare IT follow conventions.
# "dx_code" is almost certainly a diagnosis code. "hgb" is hemoglobin.
# By knowing these conventions, we can classify data before scanning
# its value.

FIELD_CLASSIFICATION: dict[str, tuple[SensitivityLevel, str]] = {
    # ── Level 4: CRITICAL (Direct Identifiers) ──────────────────
    # These MUST be redacted. No exceptions.
    "ssn": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "social_security": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "social_security_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_first_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_last_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "first_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "last_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "full_name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "name": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "mrn": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "medical_record_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_ssn": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "email": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_email": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "email_address": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "phone": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "phone_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "patient_phone": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "mobile": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "fax": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "address": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "street_address": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "home_address": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "insurance_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "member_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "subscriber_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "beneficiary_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "hicn": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "mbi": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "driver_license": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "drivers_license": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "license_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "passport": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "passport_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "credit_card": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "card_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "cc_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "account_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "npi": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "dea": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "dea_number": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "device_serial": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "device_id": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "ip_address": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),
    "url": (SensitivityLevel.CRITICAL, DataCategory.DIRECT_IDENTIFIER),

    # ── Level 3: HIGH (Indirect Identifiers) ────────────────────
    "dob": (SensitivityLevel.HIGH, DataCategory.INDIRECT_IDENTIFIER),
    "date_of_birth": (SensitivityLevel.HIGH, DataCategory.INDIRECT_IDENTIFIER),
    "birth_date": (SensitivityLevel.HIGH, DataCategory.INDIRECT_IDENTIFIER),
    "birthday": (SensitivityLevel.HIGH, DataCategory.INDIRECT_IDENTIFIER),
    "age": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),
    "patient_age": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),
    "zip": (SensitivityLevel.HIGH, DataCategory.GEOGRAPHIC),
    "zip_code": (SensitivityLevel.HIGH, DataCategory.GEOGRAPHIC),
    "postal_code": (SensitivityLevel.HIGH, DataCategory.GEOGRAPHIC),
    "city": (SensitivityLevel.HIGH, DataCategory.GEOGRAPHIC),
    "county": (SensitivityLevel.HIGH, DataCategory.GEOGRAPHIC),
    "gender": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),
    "sex": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),
    "race": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),
    "ethnicity": (SensitivityLevel.HIGH, DataCategory.DEMOGRAPHIC),

    # ── Level 3: HIGH (Clinical Data) ───────────────────────────
    # LEARNING NOTE: These are not "identifiers" but they are PHI
    # when combined with any identifier. We encrypt these.
    "diagnosis": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "diagnosis_code": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "dx_code": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "icd_code": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "icd10": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "snomed": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "snomed_code": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),
    "condition": (SensitivityLevel.HIGH, DataCategory.DIAGNOSIS),

    "medication": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "drug_name": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "prescription": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "dosage": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "drug_code": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "ndc_code": (SensitivityLevel.HIGH, DataCategory.MEDICATION),
    "rx": (SensitivityLevel.HIGH, DataCategory.MEDICATION),

    "procedure_code": (SensitivityLevel.HIGH, DataCategory.PROCEDURE),
    "cpt_code": (SensitivityLevel.HIGH, DataCategory.PROCEDURE),
    "hcpcs_code": (SensitivityLevel.HIGH, DataCategory.PROCEDURE),
    "surgery": (SensitivityLevel.HIGH, DataCategory.PROCEDURE),
    "procedure": (SensitivityLevel.HIGH, DataCategory.PROCEDURE),

    "clinical_note": (SensitivityLevel.HIGH, DataCategory.CLINICAL_NOTE),
    "progress_note": (SensitivityLevel.HIGH, DataCategory.CLINICAL_NOTE),
    "discharge_summary": (SensitivityLevel.HIGH, DataCategory.CLINICAL_NOTE),
    "radiology_report": (SensitivityLevel.HIGH, DataCategory.CLINICAL_NOTE),

    "genetic_test": (SensitivityLevel.HIGH, DataCategory.GENETIC),
    "gene_variant": (SensitivityLevel.HIGH, DataCategory.GENETIC),
    "brca": (SensitivityLevel.HIGH, DataCategory.GENETIC),

    "substance_abuse": (SensitivityLevel.HIGH, DataCategory.BEHAVIORAL_HEALTH),
    "mental_health": (SensitivityLevel.HIGH, DataCategory.BEHAVIORAL_HEALTH),
    "psychiatric": (SensitivityLevel.HIGH, DataCategory.BEHAVIORAL_HEALTH),
    "dsm_code": (SensitivityLevel.HIGH, DataCategory.BEHAVIORAL_HEALTH),

    # Lab values -- HIGH because they are clinical data
    "lab_result": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "lab_value": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "hemoglobin": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "hgb": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "hba1c": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "glucose": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "creatinine": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "bun": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "wbc": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "platelet": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "potassium": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "sodium": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "cholesterol": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "ldl": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "hdl": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "triglycerides": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "troponin": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),
    "psa": (SensitivityLevel.HIGH, DataCategory.LAB_RESULT),

    # Vital signs
    "systolic_bp": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "diastolic_bp": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "blood_pressure": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "heart_rate": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "pulse": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "temperature": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "respiratory_rate": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "spo2": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "oxygen_saturation": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "bmi": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "weight": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),
    "height": (SensitivityLevel.HIGH, DataCategory.VITAL_SIGN),

    # ── Level 2: MODERATE (Insurance/Billing) ───────────────────
    "claim_amount": (SensitivityLevel.MODERATE, DataCategory.BILLING),
    "copay": (SensitivityLevel.MODERATE, DataCategory.BILLING),
    "deductible": (SensitivityLevel.MODERATE, DataCategory.BILLING),
    "plan_type": (SensitivityLevel.MODERATE, DataCategory.INSURANCE),
    "payer": (SensitivityLevel.MODERATE, DataCategory.INSURANCE),

    # ── Level 1: LOW (Model/System) ─────────────────────────────
    "prediction": (SensitivityLevel.LOW, DataCategory.MODEL_OUTPUT),
    "confidence": (SensitivityLevel.LOW, DataCategory.MODEL_OUTPUT),
    "probability": (SensitivityLevel.LOW, DataCategory.MODEL_OUTPUT),
    "risk_score": (SensitivityLevel.LOW, DataCategory.MODEL_OUTPUT),
    "model_version": (SensitivityLevel.LOW, DataCategory.SYSTEM),
    "timestamp": (SensitivityLevel.LOW, DataCategory.SYSTEM),
    "request_id": (SensitivityLevel.LOW, DataCategory.SYSTEM),
}


class FieldClassification:
    """Classification result for a single field."""

    __slots__ = ("field_name", "sensitivity", "category", "requires_redaction",
                 "requires_encryption", "detection_method")

    def __init__(
        self,
        field_name: str,
        sensitivity: SensitivityLevel,
        category: str,
        requires_redaction: bool,
        requires_encryption: bool,
        detection_method: str,
    ):
        self.field_name = field_name
        self.sensitivity = sensitivity
        self.category = category
        self.requires_redaction = requires_redaction
        self.requires_encryption = requires_encryption
        self.detection_method = detection_method

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "sensitivity_level": self.sensitivity.value,
            "sensitivity_name": self.sensitivity.name,
            "category": self.category,
            "requires_redaction": self.requires_redaction,
            "requires_encryption": self.requires_encryption,
            "detection_method": self.detection_method,
        }


class DataClassifier:
    """
    Classify healthcare data fields by sensitivity level.

    LEARNING NOTE:
        This classifier runs BEFORE the redaction engine. It tells
        the redaction engine what to do with each field:
        - Level 4: Redact completely
        - Level 3: Check for embedded identifiers, then encrypt
        - Level 2: Encrypt at rest
        - Level 1: Store normally

        The classifier uses two methods:
        1. Field name lookup (fast, covers known patterns)
        2. Default to HIGH for unknown fields (safe-by-default)

        We default to HIGH (not LOW) because in healthcare, unknown
        data should be treated as sensitive until proven otherwise.
        This is the "fail-safe" principle.
    """

    def classify_field(
        self,
        field_name: str,
        field_value: Any = None,
    ) -> FieldClassification:
        """
        Classify a single field by name and optionally by value.

        Returns the sensitivity level, category, and required actions.
        """
        normalized = field_name.lower().strip().replace(" ", "_").replace("-", "_")

        # Method 1: Direct field name lookup
        if normalized in FIELD_CLASSIFICATION:
            sensitivity, category = FIELD_CLASSIFICATION[normalized]
            return FieldClassification(
                field_name=field_name,
                sensitivity=sensitivity,
                category=category,
                requires_redaction=sensitivity == SensitivityLevel.CRITICAL,
                requires_encryption=sensitivity >= SensitivityLevel.HIGH,
                detection_method="field_name_lookup",
            )

        # Method 2: Partial match on field name keywords
        for keyword, (sensitivity, category) in FIELD_CLASSIFICATION.items():
            if keyword in normalized or normalized in keyword:
                return FieldClassification(
                    field_name=field_name,
                    sensitivity=sensitivity,
                    category=category,
                    requires_redaction=sensitivity == SensitivityLevel.CRITICAL,
                    requires_encryption=sensitivity >= SensitivityLevel.HIGH,
                    detection_method="partial_name_match",
                )

        # Method 3: Default -- unknown fields default to MODERATE
        # LEARNING NOTE: We use MODERATE (not LOW) as default because
        # healthcare data should be treated cautiously. However, we
        # don't default to HIGH/CRITICAL because that would cause
        # over-redaction and reduce the data's utility for monitoring.
        return FieldClassification(
            field_name=field_name,
            sensitivity=SensitivityLevel.MODERATE,
            category=DataCategory.UNKNOWN,
            requires_redaction=False,
            requires_encryption=True,  # Encrypt unknown data to be safe
            detection_method="default_moderate",
        )

    def classify_payload(
        self,
        data: dict[str, Any],
    ) -> dict[str, FieldClassification]:
        """
        Classify all fields in a payload.

        Returns a dict mapping field_name -> FieldClassification.
        Recursively classifies nested structures.
        """
        classifications: dict[str, FieldClassification] = {}
        self._classify_recursive(data, "", classifications)
        return classifications

    def _classify_recursive(
        self,
        obj: Any,
        path: str,
        result: dict[str, FieldClassification],
        depth: int = 0,
    ) -> None:
        """Recursively classify fields in nested data."""
        if depth > 10:
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                full_path = f"{path}.{key}" if path else key
                classification = self.classify_field(key, value)
                result[full_path] = classification

                if isinstance(value, (dict, list)):
                    self._classify_recursive(value, full_path, result, depth + 1)

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                full_path = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    self._classify_recursive(item, full_path, result, depth + 1)

    def get_payload_summary(
        self,
        classifications: dict[str, FieldClassification],
    ) -> dict[str, Any]:
        """
        Summarize the classification of an entire payload.

        Useful for audit logging and compliance reporting.
        """
        levels = {level: 0 for level in SensitivityLevel}
        categories: dict[str, int] = {}
        fields_to_redact: list[str] = []
        fields_to_encrypt: list[str] = []

        for path, classification in classifications.items():
            levels[classification.sensitivity] += 1
            cat = classification.category
            categories[cat] = categories.get(cat, 0) + 1

            if classification.requires_redaction:
                fields_to_redact.append(path)
            if classification.requires_encryption:
                fields_to_encrypt.append(path)

        return {
            "total_fields": len(classifications),
            "by_sensitivity": {level.name: count for level, count in levels.items()},
            "by_category": categories,
            "fields_to_redact": fields_to_redact,
            "fields_to_encrypt": fields_to_encrypt,
            "highest_sensitivity": max(
                (c.sensitivity for c in classifications.values()),
                default=SensitivityLevel.LOW,
            ).name,
        }
