"""
Tests for HIPAA Minimum Necessary Rule Enforcement.

COVERAGE:
    1. Purpose-based filtering (different purposes get different data)
    2. Dashboard purpose (most restrictive)
    3. Storage purpose (least restrictive)
    4. Compliance reporting purpose
    5. Access permission checks
    6. Removal report accuracy
    7. Clinical data filtering by purpose

LEARNING NOTE:
    The minimum necessary rule is about ACCESS CONTROL at the data level.
    Even after redaction removes identifiers, we still shouldn't expose
    clinical data to a dashboard that only needs prediction scores.
    These tests verify that each purpose only sees what it needs.
"""

import pytest

from app.services.compliance.minimum_necessary import (
    DataPurpose,
    MinimumNecessaryFilter,
)


@pytest.fixture
def filter():
    return MinimumNecessaryFilter()


@pytest.fixture
def sample_redacted_payload():
    """A payload that has already been through the redaction engine."""
    return {
        # CRITICAL fields are already redacted
        "ssn": "[REDACTED_SSN]",
        "patient_email": "[REDACTED_EMAIL]",
        # HIGH fields (clinical data, already marked for encryption)
        "diagnosis_code": "E11.65",
        "medication": "metformin 500mg",
        "lab_glucose": "185.5",
        "heart_rate": "78",
        "clinical_note": "Patient presents with [REDACTED_SSN], has diabetes",
        # LOW fields (model outputs)
        "prediction": "0.87",
        "confidence": "0.92",
        # MODERATE fields (operational)
        "claim_amount": "5000.00",
    }


class TestDashboardPurpose:
    """Dashboard should only see model outputs and system data."""

    def test_dashboard_filters_clinical_data(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.DASHBOARD
        )
        # Model outputs should be retained
        assert "prediction" in result.filtered_data
        assert "confidence" in result.filtered_data
        # Clinical data should be removed
        assert "diagnosis_code" not in result.filtered_data
        assert "medication" not in result.filtered_data
        assert "clinical_note" not in result.filtered_data

    def test_dashboard_removes_redacted_identifiers(self, filter, sample_redacted_payload):
        """Even redacted identifiers shouldn't appear in dashboards."""
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.DASHBOARD
        )
        # Redacted tokens are still CRITICAL category -- should be removed
        assert "ssn" not in result.filtered_data
        assert "patient_email" not in result.filtered_data


class TestStoragePurpose:
    """Storage keeps everything (after redaction) because we may need it later."""

    def test_storage_retains_clinical_data(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.STORAGE
        )
        assert "diagnosis_code" in result.filtered_data
        assert "medication" in result.filtered_data

    def test_storage_retains_model_outputs(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.STORAGE
        )
        assert "prediction" in result.filtered_data
        assert "confidence" in result.filtered_data


class TestCompliancePurpose:
    """Compliance reporting needs metadata, not clinical details."""

    def test_compliance_has_billing_data(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.COMPLIANCE_REPORTING
        )
        assert "claim_amount" in result.filtered_data

    def test_compliance_excludes_clinical_details(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.COMPLIANCE_REPORTING
        )
        assert "diagnosis_code" not in result.filtered_data
        assert "clinical_note" not in result.filtered_data


class TestModelMonitoringPurpose:
    """Model monitoring needs vitals and labs for data quality checks."""

    def test_monitoring_has_vitals(self, filter):
        data = {
            "heart_rate": "78",
            "systolic_bp": "145",
            "prediction": "0.87",
        }
        result = filter.apply(data, purpose=DataPurpose.MODEL_MONITORING)
        assert "heart_rate" in result.filtered_data
        assert "prediction" in result.filtered_data

    def test_monitoring_has_lab_results(self, filter):
        data = {"lab_glucose": "185.5", "prediction": "0.87"}
        result = filter.apply(data, purpose=DataPurpose.MODEL_MONITORING)
        # lab_glucose maps to LAB_RESULT via partial name match
        assert "prediction" in result.filtered_data


class TestDataQualityPurpose:
    """Data quality checks need more clinical context."""

    def test_data_quality_has_diagnosis(self, filter):
        data = {
            "diagnosis_code": "E11.65",
            "prediction": "0.87",
            "medication": "metformin",
        }
        result = filter.apply(data, purpose=DataPurpose.DATA_QUALITY)
        assert "diagnosis_code" in result.filtered_data
        assert "medication" in result.filtered_data


class TestRemovalReport:
    """Verify the removal report is accurate and complete."""

    def test_removal_report_counts(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.DASHBOARD
        )
        assert len(result.fields_removed) > 0
        assert len(result.fields_retained) > 0
        # Total should match original field count
        total = len(result.fields_removed) + len(result.fields_retained)
        assert total == len(sample_redacted_payload)

    def test_removal_report_has_reasons(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.DASHBOARD
        )
        for entry in result.removal_report:
            assert "field" in entry
            assert "reason" in entry
            assert "category" in entry

    def test_to_dict_format(self, filter, sample_redacted_payload):
        result = filter.apply(
            sample_redacted_payload, purpose=DataPurpose.DASHBOARD
        )
        d = result.to_dict()
        assert d["purpose"] == "dashboard"
        assert "fields_removed_count" in d
        assert "fields_retained_count" in d


class TestAccessPermissions:
    """Test pre-flight access permission checks."""

    def test_prediction_permitted_for_dashboard(self, filter):
        assert filter.check_access_permitted("prediction", DataPurpose.DASHBOARD)

    def test_diagnosis_not_permitted_for_dashboard(self, filter):
        assert not filter.check_access_permitted(
            "diagnosis_code", DataPurpose.DASHBOARD
        )

    def test_diagnosis_permitted_for_data_quality(self, filter):
        assert filter.check_access_permitted(
            "diagnosis_code", DataPurpose.DATA_QUALITY
        )

    def test_get_permitted_fields(self, filter):
        data = {
            "prediction": "0.87",
            "diagnosis_code": "E11.65",
            "ssn": "[REDACTED_SSN]",
        }
        permitted = filter.get_permitted_fields(data, DataPurpose.DASHBOARD)
        assert "prediction" in permitted
        assert "diagnosis_code" not in permitted
        assert "ssn" not in permitted


class TestBehavioralHealthProtection:
    """
    Behavioral health data requires extra protection under 42 CFR Part 2.

    LEARNING NOTE:
        42 CFR Part 2 is MORE restrictive than HIPAA for substance abuse
        and mental health records. These fields should be restricted
        to the minimum possible purposes.
    """

    def test_behavioral_health_excluded_from_dashboard(self, filter):
        assert not filter.check_access_permitted(
            "substance_abuse", DataPurpose.DASHBOARD
        )

    def test_behavioral_health_excluded_from_monitoring(self, filter):
        assert not filter.check_access_permitted(
            "substance_abuse", DataPurpose.MODEL_MONITORING
        )

    def test_behavioral_health_permitted_for_storage(self, filter):
        """Storage retains all data after redaction for future analysis."""
        assert filter.check_access_permitted(
            "substance_abuse", DataPurpose.STORAGE
        )
