"""
Healthcare Data Protection Engine.

This package handles ALL sensitive healthcare data, not just PII:
- PHI (Protected Health Information) redaction
- Data classification by sensitivity level
- HIPAA 18-identifier detection
- Clinical data encryption preparation

LEARNING NOTE:
    The package is still called "redaction" because that's the primary
    action, but its scope is broader: classify -> redact -> prepare for
    encryption. Think of it as the "data protection gateway."
"""

from app.services.redaction.classification import DataClassifier, SensitivityLevel
from app.services.redaction.engine import PIIRedactionEngine
from app.services.redaction.patterns import PHIType, PIIType

__all__ = [
    "PIIRedactionEngine",
    "DataClassifier",
    "SensitivityLevel",
    "PHIType",
    "PIIType",
]
