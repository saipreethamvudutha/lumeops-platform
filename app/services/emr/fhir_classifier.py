"""
HL7 FHIR Resource Classification for Healthcare Data.

WHAT THIS DOES:
    Detects and classifies data that follows HL7 FHIR conventions.
    When AI inference data arrives from hospital systems, it often
    contains field names and structures that map to FHIR resources.
    This module recognizes those patterns and applies appropriate
    sensitivity classification.

WHY THIS MATTERS:
    Without FHIR awareness, we treat "resourceType: Patient" as just
    another string field. With it, we know that:
    - The payload contains a Patient resource (CRITICAL sensitivity)
    - Fields like "identifier" are direct identifiers (must redact)
    - Fields like "condition" are clinical data (must encrypt)
    - The entire resource is PHI under HIPAA

FHIR RESOURCE CATEGORIES (by sensitivity):

    CRITICAL (must redact identifiers within):
        Patient, RelatedPerson, Practitioner, Person

    HIGH (clinical data, must encrypt):
        Condition, Observation, MedicationRequest, Procedure,
        DiagnosticReport, AllergyIntolerance, Immunization,
        CarePlan, ClinicalImpression

    MODERATE (administrative/billing):
        Encounter, Claim, Coverage, ExplanationOfBenefit

    LOW (system/reference):
        Organization, Location, Device, Medication (reference only)

DESIGN CHOICE:
    We use heuristic field detection rather than full FHIR validation.
    A hospital AI might send {"patient_condition": "E11.65"} rather than
    a formal FHIR Condition resource. Our job is to recognize the
    sensitivity, not validate FHIR compliance.

LEARNING NOTE:
    FHIR defines ~150 resource types. We only handle the ones commonly
    seen in AI inference data. If a hospital sends full FHIR bundles,
    they'll need the full FHIR integration (Phase 2).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.core.logging import get_logger
from app.services.redaction.classification import DataCategory, SensitivityLevel

logger = get_logger("fhir_classifier")


class FHIRResourceType(str, Enum):
    """
    FHIR resource types commonly found in healthcare AI data.

    LEARNING NOTE:
        These are NOT all 150+ FHIR resource types. These are the ones
        that appear most often when hospital AI systems send inference
        data through our API. Each maps to a sensitivity level that
        determines how we protect it.
    """

    # ── Patient Demographics (CRITICAL) ───────────────────────────
    PATIENT = "Patient"
    RELATED_PERSON = "RelatedPerson"
    PRACTITIONER = "Practitioner"
    PERSON = "Person"

    # ── Clinical (HIGH) ───────────────────────────────────────────
    CONDITION = "Condition"                         # Diagnoses
    OBSERVATION = "Observation"                     # Lab results, vitals
    MEDICATION_REQUEST = "MedicationRequest"         # Prescriptions
    MEDICATION_STATEMENT = "MedicationStatement"     # Current meds
    PROCEDURE = "Procedure"                         # Surgical/clinical
    DIAGNOSTIC_REPORT = "DiagnosticReport"           # Lab/imaging reports
    ALLERGY_INTOLERANCE = "AllergyIntolerance"       # Allergies
    IMMUNIZATION = "Immunization"                   # Vaccines
    CARE_PLAN = "CarePlan"                          # Treatment plans
    CLINICAL_IMPRESSION = "ClinicalImpression"       # Clinical assessments
    FAMILY_MEMBER_HISTORY = "FamilyMemberHistory"    # Family history
    GENOMICS_REPORT = "GenomicsReport"               # Genetic data

    # ── Administrative (MODERATE) ─────────────────────────────────
    ENCOUNTER = "Encounter"                         # Visits/stays
    CLAIM = "Claim"                                 # Insurance claims
    COVERAGE = "Coverage"                           # Insurance info
    EXPLANATION_OF_BENEFIT = "ExplanationOfBenefit"  # EOB

    # ── Reference/System (LOW) ────────────────────────────────────
    ORGANIZATION = "Organization"                   # Hospital/clinic
    LOCATION = "Location"                           # Facility location
    DEVICE = "Device"                               # Medical devices
    MEDICATION = "Medication"                       # Drug reference data

    # ── Unknown ───────────────────────────────────────────────────
    UNKNOWN = "Unknown"


# ── Resource Type to Sensitivity Mapping ────────────────────────
# This is the core of FHIR-aware classification.

FHIR_SENSITIVITY_MAP: dict[FHIRResourceType, SensitivityLevel] = {
    # CRITICAL -- contains direct identifiers
    FHIRResourceType.PATIENT: SensitivityLevel.CRITICAL,
    FHIRResourceType.RELATED_PERSON: SensitivityLevel.CRITICAL,
    FHIRResourceType.PRACTITIONER: SensitivityLevel.CRITICAL,
    FHIRResourceType.PERSON: SensitivityLevel.CRITICAL,

    # HIGH -- clinical data
    FHIRResourceType.CONDITION: SensitivityLevel.HIGH,
    FHIRResourceType.OBSERVATION: SensitivityLevel.HIGH,
    FHIRResourceType.MEDICATION_REQUEST: SensitivityLevel.HIGH,
    FHIRResourceType.MEDICATION_STATEMENT: SensitivityLevel.HIGH,
    FHIRResourceType.PROCEDURE: SensitivityLevel.HIGH,
    FHIRResourceType.DIAGNOSTIC_REPORT: SensitivityLevel.HIGH,
    FHIRResourceType.ALLERGY_INTOLERANCE: SensitivityLevel.HIGH,
    FHIRResourceType.IMMUNIZATION: SensitivityLevel.HIGH,
    FHIRResourceType.CARE_PLAN: SensitivityLevel.HIGH,
    FHIRResourceType.CLINICAL_IMPRESSION: SensitivityLevel.HIGH,
    FHIRResourceType.FAMILY_MEMBER_HISTORY: SensitivityLevel.HIGH,
    FHIRResourceType.GENOMICS_REPORT: SensitivityLevel.HIGH,

    # MODERATE -- administrative
    FHIRResourceType.ENCOUNTER: SensitivityLevel.MODERATE,
    FHIRResourceType.CLAIM: SensitivityLevel.MODERATE,
    FHIRResourceType.COVERAGE: SensitivityLevel.MODERATE,
    FHIRResourceType.EXPLANATION_OF_BENEFIT: SensitivityLevel.MODERATE,

    # LOW -- reference data
    FHIRResourceType.ORGANIZATION: SensitivityLevel.LOW,
    FHIRResourceType.LOCATION: SensitivityLevel.LOW,
    FHIRResourceType.DEVICE: SensitivityLevel.LOW,
    FHIRResourceType.MEDICATION: SensitivityLevel.LOW,
}

# ── FHIR Resource Type to Data Category Mapping ────────────────

FHIR_CATEGORY_MAP: dict[FHIRResourceType, str] = {
    FHIRResourceType.PATIENT: DataCategory.DIRECT_IDENTIFIER,
    FHIRResourceType.RELATED_PERSON: DataCategory.DIRECT_IDENTIFIER,
    FHIRResourceType.PRACTITIONER: DataCategory.DIRECT_IDENTIFIER,
    FHIRResourceType.PERSON: DataCategory.DIRECT_IDENTIFIER,
    FHIRResourceType.CONDITION: DataCategory.DIAGNOSIS,
    FHIRResourceType.OBSERVATION: DataCategory.LAB_RESULT,
    FHIRResourceType.MEDICATION_REQUEST: DataCategory.MEDICATION,
    FHIRResourceType.MEDICATION_STATEMENT: DataCategory.MEDICATION,
    FHIRResourceType.PROCEDURE: DataCategory.PROCEDURE,
    FHIRResourceType.DIAGNOSTIC_REPORT: DataCategory.LAB_RESULT,
    FHIRResourceType.ALLERGY_INTOLERANCE: DataCategory.CLINICAL_NOTE,
    FHIRResourceType.IMMUNIZATION: DataCategory.CLINICAL_NOTE,
    FHIRResourceType.CARE_PLAN: DataCategory.CLINICAL_NOTE,
    FHIRResourceType.CLINICAL_IMPRESSION: DataCategory.CLINICAL_NOTE,
    FHIRResourceType.FAMILY_MEMBER_HISTORY: DataCategory.CLINICAL_NOTE,
    FHIRResourceType.GENOMICS_REPORT: DataCategory.GENETIC,
    FHIRResourceType.ENCOUNTER: DataCategory.OPERATIONAL,
    FHIRResourceType.CLAIM: DataCategory.BILLING,
    FHIRResourceType.COVERAGE: DataCategory.INSURANCE,
    FHIRResourceType.EXPLANATION_OF_BENEFIT: DataCategory.INSURANCE,
    FHIRResourceType.ORGANIZATION: DataCategory.OPERATIONAL,
    FHIRResourceType.LOCATION: DataCategory.OPERATIONAL,
    FHIRResourceType.DEVICE: DataCategory.OPERATIONAL,
    FHIRResourceType.MEDICATION: DataCategory.MEDICATION,
}

# ── Field Name Hints ────────────────────────────────────────────
# Common field names that suggest a FHIR resource type.
# Used when the data doesn't have an explicit "resourceType" field.
#
# LEARNING NOTE:
#   Hospital AI systems often flatten FHIR data before sending it.
#   Instead of {"resourceType": "Observation", "code": {...}},
#   they send {"observation_code": "85354-9", "observation_value": 120}.
#   These hints help us recognize the flattened FHIR structure.

FHIR_FIELD_HINTS: dict[str, FHIRResourceType] = {
    # Patient hints
    "patient_reference": FHIRResourceType.PATIENT,
    "subject_reference": FHIRResourceType.PATIENT,

    # Condition/Diagnosis hints
    "condition_code": FHIRResourceType.CONDITION,
    "condition_status": FHIRResourceType.CONDITION,
    "clinical_status": FHIRResourceType.CONDITION,
    "verification_status": FHIRResourceType.CONDITION,

    # Observation hints (labs, vitals)
    "observation_code": FHIRResourceType.OBSERVATION,
    "observation_value": FHIRResourceType.OBSERVATION,
    "loinc_code": FHIRResourceType.OBSERVATION,
    "component_code": FHIRResourceType.OBSERVATION,
    "reference_range": FHIRResourceType.OBSERVATION,

    # Medication hints
    "medication_code": FHIRResourceType.MEDICATION_REQUEST,
    "medication_reference": FHIRResourceType.MEDICATION_REQUEST,
    "dosage_instruction": FHIRResourceType.MEDICATION_REQUEST,
    "dispense_request": FHIRResourceType.MEDICATION_REQUEST,

    # Procedure hints
    "performed_period": FHIRResourceType.PROCEDURE,
    "performed_datetime": FHIRResourceType.PROCEDURE,

    # DiagnosticReport hints
    "diagnostic_code": FHIRResourceType.DIAGNOSTIC_REPORT,
    "conclusion": FHIRResourceType.DIAGNOSTIC_REPORT,
    "conclusion_code": FHIRResourceType.DIAGNOSTIC_REPORT,

    # Encounter hints
    "encounter_class": FHIRResourceType.ENCOUNTER,
    "encounter_type": FHIRResourceType.ENCOUNTER,
    "admission_source": FHIRResourceType.ENCOUNTER,
    "discharge_disposition": FHIRResourceType.ENCOUNTER,
    "length_of_stay": FHIRResourceType.ENCOUNTER,

    # Coverage/Claim hints
    "claim_type": FHIRResourceType.CLAIM,
    "coverage_type": FHIRResourceType.COVERAGE,
    "payor": FHIRResourceType.COVERAGE,
    "beneficiary": FHIRResourceType.COVERAGE,

    # Genomics hints
    "gene_studied": FHIRResourceType.GENOMICS_REPORT,
    "variant_found": FHIRResourceType.GENOMICS_REPORT,
}


class FHIRClassificationResult:
    """Result of classifying a payload for FHIR resource types."""

    __slots__ = (
        "detected_resources", "sensitivity_level", "data_categories",
        "is_fhir_data", "detection_confidence",
    )

    def __init__(
        self,
        detected_resources: list[FHIRResourceType],
        sensitivity_level: SensitivityLevel,
        data_categories: list[str],
        is_fhir_data: bool,
        detection_confidence: str,
    ):
        self.detected_resources = detected_resources
        self.sensitivity_level = sensitivity_level
        self.data_categories = data_categories
        self.is_fhir_data = is_fhir_data
        self.detection_confidence = detection_confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_resources": [r.value for r in self.detected_resources],
            "sensitivity_level": self.sensitivity_level.name,
            "data_categories": self.data_categories,
            "is_fhir_data": self.is_fhir_data,
            "detection_confidence": self.detection_confidence,
        }


class FHIRClassifier:
    """
    Detect and classify FHIR resource types in inference data.

    USAGE:
        classifier = FHIRClassifier()
        result = classifier.classify_payload(inference_data)
        # result.detected_resources -> [FHIRResourceType.OBSERVATION, ...]
        # result.sensitivity_level -> SensitivityLevel.HIGH
        # result.is_fhir_data -> True if FHIR patterns detected

    LEARNING NOTE:
        This classifier uses three detection methods:
        1. Explicit: payload has "resourceType" field (formal FHIR)
        2. Field hints: field names match known FHIR patterns
        3. Structure: data follows FHIR-like nested structures

        Methods 2 and 3 catch the common case where hospitals
        flatten or partially transform FHIR data before sending it.

    DESIGN DECISION:
        We return the HIGHEST sensitivity level found across all
        detected resource types. If a payload contains both a
        Patient resource (CRITICAL) and an Observation (HIGH),
        the overall classification is CRITICAL.
    """

    def classify_payload(
        self,
        data: dict[str, Any],
    ) -> FHIRClassificationResult:
        """
        Classify an inference payload for FHIR resource types.

        Returns a FHIRClassificationResult with detected resources,
        overall sensitivity level, and data categories.
        """
        detected: list[FHIRResourceType] = []
        confidence = "none"

        # Method 1: Explicit resourceType field
        resource_type = data.get("resourceType") or data.get("resource_type")
        if resource_type:
            fhir_type = self._resolve_resource_type(resource_type)
            if fhir_type != FHIRResourceType.UNKNOWN:
                detected.append(fhir_type)
                confidence = "high"

        # Method 2: Field name hints
        hint_resources = self._detect_from_field_names(data)
        for r in hint_resources:
            if r not in detected:
                detected.append(r)
        if hint_resources and confidence == "none":
            confidence = "medium"

        # Method 3: FHIR-like nested structures
        structure_resources = self._detect_from_structure(data)
        for r in structure_resources:
            if r not in detected:
                detected.append(r)
        if structure_resources and confidence == "none":
            confidence = "low"

        # Determine overall sensitivity
        if detected:
            max_sensitivity = max(
                FHIR_SENSITIVITY_MAP.get(r, SensitivityLevel.MODERATE)
                for r in detected
            )
        else:
            max_sensitivity = SensitivityLevel.MODERATE

        # Collect data categories
        categories = list({
            FHIR_CATEGORY_MAP.get(r, DataCategory.UNKNOWN)
            for r in detected
        })

        return FHIRClassificationResult(
            detected_resources=detected,
            sensitivity_level=max_sensitivity,
            data_categories=categories,
            is_fhir_data=len(detected) > 0,
            detection_confidence=confidence,
        )

    def _resolve_resource_type(self, type_str: str) -> FHIRResourceType:
        """Resolve a string to a FHIRResourceType enum."""
        normalized = type_str.strip()
        try:
            return FHIRResourceType(normalized)
        except ValueError:
            # Try case-insensitive match
            for member in FHIRResourceType:
                if member.value.lower() == normalized.lower():
                    return member
            return FHIRResourceType.UNKNOWN

    def _detect_from_field_names(
        self,
        data: dict[str, Any],
    ) -> list[FHIRResourceType]:
        """Detect FHIR resource types from field names."""
        detected: list[FHIRResourceType] = []

        for key in data.keys():
            normalized = key.lower().strip().replace(" ", "_").replace("-", "_")
            if normalized in FHIR_FIELD_HINTS:
                resource_type = FHIR_FIELD_HINTS[normalized]
                if resource_type not in detected:
                    detected.append(resource_type)

        return detected

    def _detect_from_structure(
        self,
        data: dict[str, Any],
    ) -> list[FHIRResourceType]:
        """
        Detect FHIR resource types from data structure patterns.

        LEARNING NOTE:
            FHIR resources have recognizable structures:
            - Observations have "code" + "value[x]" + "status"
            - Conditions have "code" + "clinicalStatus"
            - MedicationRequests have "medicationCodeableConcept" + "dosageInstruction"

            We look for these structural patterns even when the data
            doesn't explicitly declare itself as FHIR.
        """
        detected: list[FHIRResourceType] = []
        keys_lower = {k.lower() for k in data.keys()}

        # Observation pattern: code + value + status
        observation_hints = {"code", "value", "status", "effective", "valuestring",
                             "valuequantity", "valueinteger"}
        if len(keys_lower & observation_hints) >= 2:
            if FHIRResourceType.OBSERVATION not in detected:
                detected.append(FHIRResourceType.OBSERVATION)

        # Condition pattern: code + clinicalStatus/verificationStatus
        condition_hints = {"clinicalstatus", "verificationstatus",
                           "onsetdatetime", "abatementdatetime"}
        if keys_lower & condition_hints:
            if FHIRResourceType.CONDITION not in detected:
                detected.append(FHIRResourceType.CONDITION)

        # MedicationRequest pattern
        med_hints = {"medicationcodeableconcept", "dosageinstruction",
                     "dispenser", "authoreddon"}
        if keys_lower & med_hints:
            if FHIRResourceType.MEDICATION_REQUEST not in detected:
                detected.append(FHIRResourceType.MEDICATION_REQUEST)

        # Encounter pattern
        encounter_hints = {"class", "period", "hospitalization",
                           "serviceprovider", "reasoncode"}
        if len(keys_lower & encounter_hints) >= 2:
            if FHIRResourceType.ENCOUNTER not in detected:
                detected.append(FHIRResourceType.ENCOUNTER)

        return detected

    def get_sensitivity_for_resource(
        self,
        resource_type: FHIRResourceType,
    ) -> SensitivityLevel:
        """Get the sensitivity level for a specific FHIR resource type."""
        return FHIR_SENSITIVITY_MAP.get(resource_type, SensitivityLevel.MODERATE)

    def get_category_for_resource(
        self,
        resource_type: FHIRResourceType,
    ) -> str:
        """Get the data category for a specific FHIR resource type."""
        return FHIR_CATEGORY_MAP.get(resource_type, DataCategory.UNKNOWN)
