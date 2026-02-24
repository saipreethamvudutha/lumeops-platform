"""
Data quality validation service.

Checks incoming inference data for:
1. Missing required fields
2. Null values
3. Out-of-range values
4. Type mismatches
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger("data_quality")


class DataQualityIssue:
    """A single data quality problem."""

    __slots__ = ("issue_type", "field_name", "message", "value")

    def __init__(
        self,
        issue_type: str,
        field_name: str,
        message: str,
        value: Any = None,
    ):
        self.issue_type = issue_type
        self.field_name = field_name
        self.message = message
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.issue_type,
            "field": self.field_name,
            "message": self.message,
        }


class DataQualityResult:
    """Result of data quality validation."""

    __slots__ = ("is_valid", "issues", "severity")

    def __init__(
        self,
        is_valid: bool,
        issues: list[DataQualityIssue],
        severity: str | None,
    ):
        self.is_valid = is_valid
        self.issues = issues
        self.severity = severity

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "severity": self.severity,
            "issue_count": self.issue_count,
        }


class DataQualityService:
    """
    Validate inference data quality.

    Uses model configuration to know which fields are required,
    what ranges are valid, and what types are expected.
    """

    def check(
        self,
        input_features: dict[str, Any],
        required_fields: list[str] | None = None,
        field_ranges: dict[str, dict[str, float]] | None = None,
        field_types: dict[str, str] | None = None,
    ) -> DataQualityResult:
        """
        Run all data quality checks on input features.

        Args:
            input_features: The inference input data (already redacted).
            required_fields: List of field names that must be present.
            field_ranges: Dict of field_name -> {"min": x, "max": y}.
            field_types: Dict of field_name -> expected_type ("float", "string", etc).

        Returns:
            DataQualityResult with validation status and issues.
        """
        issues: list[DataQualityIssue] = []

        # 1. Missing required fields
        if required_fields:
            for field in required_fields:
                if field not in input_features:
                    issues.append(
                        DataQualityIssue(
                            issue_type="missing_field",
                            field_name=field,
                            message=f"Required field missing: {field}",
                        )
                    )

        # 2. Null values
        for field, value in input_features.items():
            if value is None:
                issues.append(
                    DataQualityIssue(
                        issue_type="null_value",
                        field_name=field,
                        message=f"Null value in field: {field}",
                    )
                )

        # 3. Out-of-range values
        if field_ranges:
            for field, value in input_features.items():
                if field in field_ranges and isinstance(value, (int, float)):
                    range_config = field_ranges[field]
                    min_val = range_config.get("min")
                    max_val = range_config.get("max")

                    if min_val is not None and value < min_val:
                        issues.append(
                            DataQualityIssue(
                                issue_type="out_of_range",
                                field_name=field,
                                message=f"{field}={value} below minimum {min_val}",
                                value=value,
                            )
                        )

                    if max_val is not None and value > max_val:
                        issues.append(
                            DataQualityIssue(
                                issue_type="out_of_range",
                                field_name=field,
                                message=f"{field}={value} above maximum {max_val}",
                                value=value,
                            )
                        )

        # 4. Type mismatches
        if field_types:
            type_map = {
                "float": (int, float),
                "int": (int,),
                "string": (str,),
                "bool": (bool,),
            }
            for field, expected_type in field_types.items():
                if field in input_features and input_features[field] is not None:
                    value = input_features[field]
                    expected_python_types = type_map.get(expected_type)
                    if expected_python_types and not isinstance(
                        value, expected_python_types
                    ):
                        issues.append(
                            DataQualityIssue(
                                issue_type="type_mismatch",
                                field_name=field,
                                message=(
                                    f"{field} should be {expected_type}, "
                                    f"got {type(value).__name__}"
                                ),
                                value=value,
                            )
                        )

        # Determine severity
        severity = None
        if issues:
            if any(i.issue_type == "missing_field" for i in issues):
                severity = "critical"
            elif any(i.issue_type == "out_of_range" for i in issues):
                severity = "warning"
            else:
                severity = "info"

        return DataQualityResult(
            is_valid=len(issues) == 0,
            issues=issues,
            severity=severity,
        )
