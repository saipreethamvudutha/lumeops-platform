"""
EMR/EHR Data Handling with HL7 FHIR Awareness.

This package provides:
- FHIR resource type detection and classification
- EMR-aware sensitivity mapping
- Clinical data structure recognition
- EHR integration safeguards

LEARNING NOTE:
    HL7 FHIR (Fast Healthcare Interoperability Resources) is THE standard
    for exchanging electronic health records. When a hospital's AI system
    sends us data, it often follows FHIR conventions -- even if they don't
    send raw FHIR JSON.

    Understanding FHIR resource types lets us:
    1. Classify data more accurately (a "Patient" resource is CRITICAL)
    2. Apply the right protection (a "MedicationRequest" is HIGH)
    3. Validate data structure (an "Observation" should have a code + value)
    4. Generate better compliance reports (we know what kind of clinical
       data flowed through our system)

    We don't REQUIRE FHIR format -- we just understand it.
    This is a recognition layer, not a validation layer.
"""

from app.services.emr.fhir_classifier import FHIRClassifier, FHIRResourceType

__all__ = [
    "FHIRClassifier",
    "FHIRResourceType",
]
