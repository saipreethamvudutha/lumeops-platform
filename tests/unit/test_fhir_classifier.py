"""
Tests for HL7 FHIR Resource Classification.

COVERAGE:
    1. Explicit resourceType detection
    2. Field name hint detection
    3. Structure-based detection
    4. Sensitivity level mapping
    5. Data category mapping
    6. Mixed resource payloads
    7. Non-FHIR data handling

LEARNING NOTE:
    These tests verify that the FHIR classifier correctly identifies
    healthcare data patterns -- even when the data doesn't follow
    formal FHIR specification. This is important because hospital AI
    systems often send flattened or partial FHIR data.
"""

import pytest

from app.services.emr.fhir_classifier import (
    FHIRClassifier,
    FHIRResourceType,
    FHIR_SENSITIVITY_MAP,
)
from app.services.redaction.classification import SensitivityLevel


@pytest.fixture
def classifier():
    return FHIRClassifier()


class TestExplicitResourceType:
    """Test detection via explicit resourceType field."""

    def test_patient_resource(self, classifier):
        data = {"resourceType": "Patient", "name": "John Doe", "id": "12345"}
        result = classifier.classify_payload(data)
        assert result.is_fhir_data is True
        assert FHIRResourceType.PATIENT in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.CRITICAL
        assert result.detection_confidence == "high"

    def test_observation_resource(self, classifier):
        data = {"resourceType": "Observation", "code": "85354-9", "value": 120}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.OBSERVATION in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.HIGH

    def test_condition_resource(self, classifier):
        data = {"resourceType": "Condition", "code": "E11.65"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.CONDITION in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.HIGH

    def test_claim_resource(self, classifier):
        data = {"resourceType": "Claim", "total": 5000.00}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.CLAIM in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.MODERATE

    def test_organization_resource(self, classifier):
        data = {"resourceType": "Organization", "name": "City Hospital"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.ORGANIZATION in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.LOW

    def test_case_insensitive_resource_type(self, classifier):
        data = {"resourceType": "patient"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.PATIENT in result.detected_resources

    def test_underscore_resource_type_field(self, classifier):
        """Some systems use resource_type instead of resourceType."""
        data = {"resource_type": "Observation", "value": 120}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.OBSERVATION in result.detected_resources


class TestFieldNameHints:
    """Test detection via field name patterns."""

    def test_loinc_code_hints_observation(self, classifier):
        data = {"loinc_code": "85354-9", "patient_age": 65}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.OBSERVATION in result.detected_resources

    def test_dosage_instruction_hints_medication(self, classifier):
        data = {"dosage_instruction": "500mg BID", "medication_code": "metformin"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.MEDICATION_REQUEST in result.detected_resources

    def test_encounter_class_hints_encounter(self, classifier):
        data = {"encounter_class": "inpatient", "length_of_stay": 3}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.ENCOUNTER in result.detected_resources

    def test_conclusion_hints_diagnostic_report(self, classifier):
        data = {"conclusion": "Normal sinus rhythm", "diagnostic_code": "ECG"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.DIAGNOSTIC_REPORT in result.detected_resources

    def test_gene_studied_hints_genomics(self, classifier):
        data = {"gene_studied": "BRCA1", "variant_found": "pathogenic"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.GENOMICS_REPORT in result.detected_resources

    def test_coverage_hints(self, classifier):
        data = {"coverage_type": "Medicare", "beneficiary": "PAT-12345"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.COVERAGE in result.detected_resources

    def test_medium_confidence_for_hints(self, classifier):
        """Field hint detection should be medium confidence."""
        data = {"loinc_code": "85354-9"}
        result = classifier.classify_payload(data)
        assert result.detection_confidence == "medium"


class TestStructureDetection:
    """Test detection via FHIR-like data structures."""

    def test_observation_structure(self, classifier):
        """code + value + status = Observation pattern."""
        data = {"code": "8480-6", "value": 120, "status": "final"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.OBSERVATION in result.detected_resources

    def test_condition_structure(self, classifier):
        """clinicalStatus field suggests Condition resource."""
        data = {"clinicalStatus": "active", "code": "E11.65"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.CONDITION in result.detected_resources

    def test_medication_request_structure(self, classifier):
        data = {"medicationCodeableConcept": "metformin", "dosageInstruction": "BID"}
        result = classifier.classify_payload(data)
        assert FHIRResourceType.MEDICATION_REQUEST in result.detected_resources


class TestNonFHIRData:
    """Test handling of non-FHIR data."""

    def test_plain_inference_data(self, classifier):
        data = {"age": 65, "bmi": 28.5, "prediction": 0.87}
        result = classifier.classify_payload(data)
        assert result.is_fhir_data is False
        assert len(result.detected_resources) == 0
        assert result.detection_confidence == "none"

    def test_non_fhir_defaults_to_moderate(self, classifier):
        """Non-FHIR data should default to MODERATE sensitivity."""
        data = {"some_field": "some_value"}
        result = classifier.classify_payload(data)
        assert result.sensitivity_level == SensitivityLevel.MODERATE


class TestMixedPayloads:
    """Test payloads with multiple FHIR resource patterns."""

    def test_patient_plus_observation(self, classifier):
        """If both Patient and Observation detected, sensitivity is CRITICAL."""
        data = {
            "patient_reference": "Patient/12345",
            "observation_code": "85354-9",
            "observation_value": 120,
        }
        result = classifier.classify_payload(data)
        assert FHIRResourceType.PATIENT in result.detected_resources
        assert FHIRResourceType.OBSERVATION in result.detected_resources
        assert result.sensitivity_level == SensitivityLevel.CRITICAL

    def test_classification_result_to_dict(self, classifier):
        data = {"resourceType": "Observation", "code": "85354-9"}
        result = classifier.classify_payload(data)
        d = result.to_dict()
        assert "Observation" in d["detected_resources"]
        assert d["is_fhir_data"] is True
        assert d["sensitivity_level"] == "HIGH"


class TestSensitivityMapping:
    """Verify all resource types have correct sensitivity levels."""

    def test_all_critical_resources(self):
        critical_types = [
            FHIRResourceType.PATIENT,
            FHIRResourceType.RELATED_PERSON,
            FHIRResourceType.PRACTITIONER,
            FHIRResourceType.PERSON,
        ]
        for rt in critical_types:
            assert FHIR_SENSITIVITY_MAP[rt] == SensitivityLevel.CRITICAL, (
                f"{rt.value} should be CRITICAL"
            )

    def test_all_high_resources(self):
        high_types = [
            FHIRResourceType.CONDITION,
            FHIRResourceType.OBSERVATION,
            FHIRResourceType.MEDICATION_REQUEST,
            FHIRResourceType.PROCEDURE,
            FHIRResourceType.DIAGNOSTIC_REPORT,
            FHIRResourceType.ALLERGY_INTOLERANCE,
            FHIRResourceType.IMMUNIZATION,
            FHIRResourceType.GENOMICS_REPORT,
        ]
        for rt in high_types:
            assert FHIR_SENSITIVITY_MAP[rt] == SensitivityLevel.HIGH, (
                f"{rt.value} should be HIGH"
            )

    def test_genomics_is_high(self):
        """Genetic data has special protection under GINA."""
        assert FHIR_SENSITIVITY_MAP[FHIRResourceType.GENOMICS_REPORT] == SensitivityLevel.HIGH


class TestHelperMethods:
    """Test individual helper methods."""

    def test_get_sensitivity_for_resource(self, classifier):
        assert classifier.get_sensitivity_for_resource(
            FHIRResourceType.PATIENT
        ) == SensitivityLevel.CRITICAL

    def test_get_category_for_resource(self, classifier):
        category = classifier.get_category_for_resource(FHIRResourceType.CONDITION)
        assert category == "diagnosis"

    def test_unknown_resource_defaults_moderate(self, classifier):
        assert classifier.get_sensitivity_for_resource(
            FHIRResourceType.UNKNOWN
        ) == SensitivityLevel.MODERATE
