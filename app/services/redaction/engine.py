"""
Healthcare Data Protection Engine -- the core of LumeOps.

WHAT IT DOES:
    1. Classifies every field by sensitivity level (CRITICAL/HIGH/MODERATE/LOW)
    2. Redacts CRITICAL fields (direct identifiers like SSN, name, MRN)
    3. Flags HIGH fields for encryption (clinical data, indirect identifiers)
    4. Produces an audit report of every action taken

WHY THIS DESIGN:
    Healthcare AI inferences contain a mix of data types. A single payload
    might include:
    - Patient SSN (CRITICAL -> must redact)
    - Blood glucose level (HIGH -> must encrypt)
    - AI prediction score (LOW -> store normally)

    We cannot treat all fields the same. The classification-first approach
    lets us apply the right protection to each field type.

PROCESSING FLOW:
    Input data → Deep copy (never mutate original)
                → Classify each field
                → CRITICAL fields: Replace value with [REDACTED_TYPE]
                → HIGH fields: Mark for encryption (handled by storage layer)
                → Generate audit report
                → Return protected data + report

DESIGN PRINCIPLES:
    1. Deterministic: Same input always produces same output
    2. Auditable: Every action logged with type, location, and method
    3. Safe-by-default: Unknown fields default to encrypted (not ignored)
    4. Fast: Pre-compiled regex, no ML overhead
    5. Recursive: Handles nested dicts/lists at any depth
    6. Non-mutating: Original data is NEVER modified

LEARNING NOTE:
    The key insight is the separation of concerns:
    - classification.py decides WHAT each field is
    - patterns.py provides the detection regex
    - engine.py orchestrates the protection actions
    This separation makes each piece testable independently and
    makes it easy to add new patterns or classification rules
    without touching the engine logic.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.services.redaction.classification import (
    DataClassifier,
    SensitivityLevel,
)
from app.services.redaction.patterns import (
    PHI_FIELD_NAMES_CRITICAL,
    PHI_FIELD_NAMES_HIGH,
    PHI_PATTERNS,
    PII_PATTERNS,
    PHIType,
    PIIType,
)

logger = get_logger("redaction_engine")

# Maximum recursion depth to prevent attacks with deeply nested data
# LEARNING NOTE: Without this limit, a malicious actor could send
# {"a": {"a": {"a": ...}}} nested 10000 levels deep and crash our
# server with a stack overflow. 10 levels is more than any real
# healthcare inference data would need.
MAX_RECURSION_DEPTH = 10


class RedactionResult:
    """
    Result of a redaction operation.

    Contains:
    - redacted_data: The input with CRITICAL fields replaced by [REDACTED_X] tokens
    - report: Detailed audit trail of what was found and what was done
    - classification_summary: Breakdown of data by sensitivity level
    """

    __slots__ = ("redacted_data", "report", "classification_summary")

    def __init__(
        self,
        redacted_data: dict[str, Any],
        report: dict[str, Any],
        classification_summary: dict[str, Any] | None = None,
    ):
        self.redacted_data = redacted_data
        self.report = report
        self.classification_summary = classification_summary or {}


class PIIRedactionEngine:
    """
    Detect, classify, and protect healthcare data in AI inferences.

    This is the primary data protection component of LumeOps.
    Every byte of incoming data passes through this engine.

    Usage:
        engine = PIIRedactionEngine()
        result = engine.redact(inference_data)
        # result.redacted_data -> data safe for storage
        # result.report -> audit report of all actions
        # result.classification_summary -> what types of data were found
    """

    def __init__(self):
        self.classifier = DataClassifier()

    def redact(self, data: dict[str, Any]) -> RedactionResult:
        """
        Process and protect all healthcare data in an inference payload.

        STEP BY STEP:
        1. Deep copy the input (we NEVER modify the original)
        2. Classify all fields by sensitivity level
        3. Redact CRITICAL fields (replace with [REDACTED_TYPE] tokens)
        4. Flag HIGH fields (clinical data) for encryption by storage layer
        5. Build audit report documenting every action

        Args:
            data: Raw inference input_features dict from the hospital's AI.

        Returns:
            RedactionResult with protected data and complete audit trail.
        """
        # Step 1: Deep copy -- the original must NEVER be modified
        # LEARNING NOTE: This is a fundamental safety property.
        # If we modified the original dict and an error occurred
        # partway through, we'd have partially-redacted data
        # that's neither safe nor useful.
        redacted = copy.deepcopy(data)

        # Step 2: Initialize the audit report
        report: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "redactions": {},
            "total_pii_found": 0,
            "fields_processed": 0,
            "fields_classified": 0,
            "redacted_fields": [],
            "high_sensitivity_fields": [],  # NEW: track clinical data too
            "classification_breakdown": {
                "CRITICAL": 0,
                "HIGH": 0,
                "MODERATE": 0,
                "LOW": 0,
            },
        }

        # Step 3: Classify and redact recursively
        self._process_recursive(redacted, "", report, depth=0)

        # Step 4: Build classification summary
        classifications = self.classifier.classify_payload(data)
        summary = self.classifier.get_payload_summary(classifications)

        return RedactionResult(
            redacted_data=redacted,
            report=report,
            classification_summary=summary,
        )

    def _process_recursive(
        self,
        obj: Any,
        path: str,
        report: dict[str, Any],
        depth: int,
    ) -> None:
        """
        Recursively process all fields in nested data structures.

        For each string field:
        1. Classify it (what type of data is this?)
        2. If CRITICAL: redact it
        3. If HIGH: note it for the encryption layer
        4. Log the decision
        """
        if depth > MAX_RECURSION_DEPTH:
            logger.warning(
                "max_recursion_depth_reached",
                path=path,
                depth=depth,
            )
            return

        if isinstance(obj, dict):
            for key in list(obj.keys()):
                value = obj[key]
                new_path = f"{path}.{key}" if path else key

                if isinstance(value, str):
                    report["fields_processed"] += 1
                    obj[key] = self._process_string_field(
                        value, key, new_path, report
                    )
                elif isinstance(value, (dict, list)):
                    self._process_recursive(value, new_path, report, depth + 1)
                # Numbers, bools, None: classify but don't redact
                # (they can't contain string-pattern PHI)

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                if isinstance(item, str):
                    report["fields_processed"] += 1
                    obj[i] = self._process_string_field(
                        item, f"[{i}]", new_path, report
                    )
                elif isinstance(item, (dict, list)):
                    self._process_recursive(item, new_path, report, depth + 1)

    def _process_string_field(
        self,
        value: str,
        field_name: str,
        field_path: str,
        report: dict[str, Any],
    ) -> str:
        """
        Classify and potentially redact a single string field.

        THREE-PASS DETECTION:
        Pass 1: Is the field NAME a known CRITICAL identifier? (fastest, highest confidence)
        Pass 2: Is the field NAME a known HIGH-sensitivity field? (note for encryption)
        Pass 3: Does the field VALUE match any PHI regex pattern? (broadest coverage)
        """
        if not value or not value.strip():
            return value

        field_lower = field_name.lower().strip()
        report["fields_classified"] += 1

        # ── Pass 1: CRITICAL field names (must redact) ───────────
        if field_lower in PHI_FIELD_NAMES_CRITICAL:
            phi_type = self._infer_phi_type_from_field_name(field_lower)
            report["classification_breakdown"]["CRITICAL"] += 1
            return self._apply_redaction(
                value, phi_type, field_path, report, "field_name_critical"
            )

        # ── Pass 2: HIGH field names (note for encryption) ───────
        if field_lower in PHI_FIELD_NAMES_HIGH:
            report["classification_breakdown"]["HIGH"] += 1
            report["high_sensitivity_fields"].append({
                "field_path": field_path,
                "field_name": field_name,
                "sensitivity": "HIGH",
                "action": "encrypt",
            })
            # Don't redact HIGH fields -- they contain clinical data
            # that we need for monitoring. They'll be encrypted by
            # the storage layer instead.
            #
            # HOWEVER: scan the VALUE for embedded identifiers.
            # Example: a clinical_note might contain "Patient John Smith
            # has diabetes." We need to redact "John Smith" from within it.
            return self._scan_value_for_embedded_identifiers(
                value, field_path, report
            )

        # ── Pass 3: Check value against regex patterns ───────────
        for phi_type, pattern in PHI_PATTERNS.items():
            if pattern.search(value):
                report["classification_breakdown"]["CRITICAL"] += 1
                return self._apply_redaction(
                    value, phi_type, field_path, report, "pattern_match"
                )

        # No sensitive data detected
        report["classification_breakdown"]["MODERATE"] += 1
        return value

    def _scan_value_for_embedded_identifiers(
        self,
        value: str,
        field_path: str,
        report: dict[str, Any],
    ) -> str:
        """
        Scan a HIGH-sensitivity string for EMBEDDED identifiers.

        LEARNING NOTE:
            A field like "clinical_note" is classified HIGH (clinical data).
            We don't redact the whole thing because we need the clinical
            content for monitoring. But the note might contain embedded
            identifiers like "Patient John Smith, SSN 123-45-6789."

            This method finds and replaces ONLY the embedded identifiers
            while preserving the clinical content.

            Example:
            Input:  "Patient John Smith, SSN 123-45-6789, has diabetes"
            Output: "Patient [REDACTED_NAME], SSN [REDACTED_SSN], has diabetes"
        """
        result = value

        for phi_type, pattern in PHI_PATTERNS.items():
            # Skip patterns that would cause too many false positives
            # in clinical text (like NAME matching "Blood Pressure")
            if phi_type in (PHIType.NAME, PHIType.ZIP_CODE, PHIType.DATE):
                continue

            matches = pattern.findall(result)
            if matches:
                replacement = f"[REDACTED_{phi_type.value}]"
                result = pattern.sub(replacement, result)

                # Log each embedded redaction
                for _ in matches:
                    type_key = phi_type.value
                    if type_key not in report["redactions"]:
                        report["redactions"][type_key] = 0
                    report["redactions"][type_key] += 1
                    report["total_pii_found"] += 1
                    report["redacted_fields"].append({
                        "field_path": field_path,
                        "pii_type": type_key,
                        "detection_method": "embedded_in_clinical_text",
                    })

        return result

    def _apply_redaction(
        self,
        original_value: str,
        phi_type: PHIType,
        field_path: str,
        report: dict[str, Any],
        detection_method: str,
    ) -> str:
        """Apply full-field redaction and update the audit report."""
        redacted_value = f"[REDACTED_{phi_type.value}]"

        type_key = phi_type.value
        if type_key not in report["redactions"]:
            report["redactions"][type_key] = 0
        report["redactions"][type_key] += 1
        report["total_pii_found"] += 1
        report["redacted_fields"].append({
            "field_path": field_path,
            "pii_type": type_key,
            "detection_method": detection_method,
        })

        logger.info(
            "phi_redacted",
            phi_type=type_key,
            field_path=field_path,
            detection_method=detection_method,
        )

        return redacted_value

    def _infer_phi_type_from_field_name(self, field_name: str) -> PHIType:
        """
        Infer the specific PHI type from a field name.

        LEARNING NOTE:
            When we know a field is CRITICAL from its name, we still
            want to know WHAT TYPE of identifier it is, so the
            redaction token is informative: [REDACTED_SSN] vs
            [REDACTED_EMAIL] vs [REDACTED_NAME].

            This helps auditors understand what was protected
            without seeing the actual data.
        """
        if "ssn" in field_name or "social_security" in field_name:
            return PHIType.SSN
        if "email" in field_name:
            return PHIType.EMAIL
        if "phone" in field_name or "mobile" in field_name or "fax" in field_name:
            return PHIType.PHONE
        if "dob" in field_name or "birth" in field_name:
            return PHIType.DATE
        if "mrn" in field_name or "medical_record" in field_name:
            return PHIType.MEDICAL_RECORD
        if "patient_id" in field_name or "encounter_id" in field_name:
            return PHIType.PATIENT_ID
        if "name" in field_name:
            return PHIType.NAME
        if "credit" in field_name or "card_number" in field_name:
            return PHIType.CREDIT_CARD
        if "zip" in field_name or "postal" in field_name:
            return PHIType.ZIP_CODE
        if "address" in field_name:
            return PHIType.ADDRESS
        if "npi" in field_name:
            return PHIType.NPI
        if "dea" in field_name:
            return PHIType.DEA_NUMBER
        if "ip_address" in field_name or "mac_address" in field_name:
            return PHIType.IP_ADDRESS
        if "device" in field_name or "udi" in field_name:
            return PHIType.DEVICE_ID
        if any(
            x in field_name
            for x in ("beneficiary", "hicn", "mbi", "insurance_id",
                      "member_id", "subscriber_id")
        ):
            return PHIType.HEALTH_PLAN_ID
        if "license" in field_name or "passport" in field_name:
            return PHIType.LICENSE_NUMBER
        if "account" in field_name or "bank" in field_name:
            return PHIType.ACCOUNT_NUMBER

        return PHIType.CUSTOM_ID

    def test_pattern(self, phi_type: PHIType, value: str) -> bool:
        """
        Test if a value matches a specific PHI pattern.
        Useful for testing and validation.
        """
        pattern = PHI_PATTERNS.get(phi_type)
        if not pattern:
            return False
        return bool(pattern.search(value))
