"""Tests for data quality validation service."""

import pytest

from app.services.monitoring.data_quality import DataQualityService


@pytest.fixture
def dq_service():
    return DataQualityService()


class TestMissingFields:
    """Test missing required field detection."""

    def test_all_fields_present(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65, "bp": 120},
            required_fields=["age", "bp"],
        )
        assert result.is_valid
        assert result.issue_count == 0

    def test_missing_field(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65},
            required_fields=["age", "bp"],
        )
        assert not result.is_valid
        assert result.issue_count == 1
        assert result.issues[0].issue_type == "missing_field"

    def test_multiple_missing(self, dq_service):
        result = dq_service.check(
            input_features={},
            required_fields=["age", "bp", "hr"],
        )
        assert result.issue_count == 3


class TestNullValues:
    """Test null value detection."""

    def test_no_nulls(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65, "bp": 120},
        )
        assert result.is_valid

    def test_null_value(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65, "bp": None},
        )
        assert not result.is_valid
        assert any(i.issue_type == "null_value" for i in result.issues)


class TestRangeValidation:
    """Test out-of-range value detection."""

    def test_within_range(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65},
            field_ranges={"age": {"min": 0, "max": 120}},
        )
        assert result.is_valid

    def test_below_minimum(self, dq_service):
        result = dq_service.check(
            input_features={"age": -5},
            field_ranges={"age": {"min": 0, "max": 120}},
        )
        assert not result.is_valid
        assert result.issues[0].issue_type == "out_of_range"

    def test_above_maximum(self, dq_service):
        result = dq_service.check(
            input_features={"age": 150},
            field_ranges={"age": {"min": 0, "max": 120}},
        )
        assert not result.is_valid


class TestTypeValidation:
    """Test type mismatch detection."""

    def test_correct_type(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65},
            field_types={"age": "float"},
        )
        assert result.is_valid

    def test_wrong_type(self, dq_service):
        result = dq_service.check(
            input_features={"age": "sixty-five"},
            field_types={"age": "float"},
        )
        assert not result.is_valid
        assert result.issues[0].issue_type == "type_mismatch"


class TestSeverity:
    """Test severity assignment."""

    def test_critical_for_missing_fields(self, dq_service):
        result = dq_service.check(
            input_features={},
            required_fields=["age"],
        )
        assert result.severity == "critical"

    def test_warning_for_out_of_range(self, dq_service):
        result = dq_service.check(
            input_features={"age": 150},
            field_ranges={"age": {"min": 0, "max": 120}},
        )
        assert result.severity == "warning"

    def test_no_severity_when_valid(self, dq_service):
        result = dq_service.check(
            input_features={"age": 65},
        )
        assert result.severity is None
