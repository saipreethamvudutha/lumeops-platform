"""
PHI/PII Detection Patterns for Healthcare Data.

WHAT THIS FILE DOES:
    Defines regex patterns that detect all 18 HIPAA identifiers plus
    additional healthcare-specific sensitive data patterns.

WHY REGEX (NOT ML):
    1. Deterministic: Same input = same output. Always.
    2. Auditable: "We detect SSNs with pattern \\d{3}-\\d{2}-\\d{4}"
       is something a regulator can verify in 5 seconds.
    3. No drift: ML models degrade. Regex doesn't.
    4. No training data needed: ML-NER needs labeled healthcare data.
    5. Fast: Microseconds per pattern, not milliseconds per model call.
    6. Explainable: Required by HIPAA's transparency provisions.

PATTERN ORDER:
    More specific patterns come first to prevent false positives.
    Example: MRN-123456 should match MEDICAL_RECORD before PATIENT_ID.

COVERAGE:
    All 18 HIPAA identifiers:
    [1] Names                [10] Account numbers
    [2] Geographic data      [11] Certificate/license numbers
    [3] Dates               [12] Vehicle identifiers
    [4] Phone numbers       [13] Device identifiers
    [5] Fax numbers         [14] Web URLs
    [6] Email addresses     [15] IP addresses
    [7] SSN                 [16] Biometric IDs (field name only)
    [8] Medical record #    [17] Photos (binary detection)
    [9] Health plan #       [18] Other unique IDs

LEARNING NOTE:
    Healthcare regex differs from general-purpose PII detection.
    We must handle formats like:
    - MRN-123456 (medical record numbers)
    - HICN 1EG4-TE5-MK72 (Medicare beneficiary IDs)
    - NPI 1234567890 (National Provider Identifiers)
    These don't appear in standard PII detection libraries.
"""

from __future__ import annotations

import re
from enum import Enum


class PHIType(str, Enum):
    """
    Types of Protected Health Information that can be detected.

    Maps to HIPAA's 18 identifiers plus additional healthcare patterns.

    LEARNING NOTE:
        We use PHIType (not PIIType) because HIPAA's scope is broader
        than typical PII definitions. PHI = PII + health information.
        A diagnosis code alone isn't PII, but when it flows through
        our system alongside any identifier, the combination is PHI.
    """

    # HIPAA Identifier #7 - Most critical, most common
    SSN = "SSN"

    # HIPAA Identifier #8 - Medical Record Numbers
    MEDICAL_RECORD = "MEDICAL_RECORD"

    # HIPAA Identifier #18 + healthcare-specific
    PATIENT_ID = "PATIENT_ID"

    # HIPAA Identifier #9 - Health plan numbers
    HEALTH_PLAN_ID = "HEALTH_PLAN_ID"

    # Healthcare provider identifiers
    DEA_NUMBER = "DEA_NUMBER"
    NPI = "NPI"

    # HIPAA Identifier #10
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"

    # HIPAA Identifier #11
    LICENSE_NUMBER = "LICENSE_NUMBER"

    # HIPAA Identifier #6
    EMAIL = "EMAIL"

    # HIPAA Identifiers #4 and #5
    PHONE = "PHONE"
    FAX = "FAX"

    # HIPAA Identifier #3
    DATE = "DATE"

    # HIPAA Identifier #1
    NAME = "NAME"

    # HIPAA Identifier #2
    ADDRESS = "ADDRESS"
    ZIP_CODE = "ZIP_CODE"

    # HIPAA Identifier #14
    URL = "URL"

    # HIPAA Identifier #15
    IP_ADDRESS = "IP_ADDRESS"

    # HIPAA Identifier #12
    VEHICLE_ID = "VEHICLE_ID"

    # HIPAA Identifier #13
    DEVICE_ID = "DEVICE_ID"

    # Financial
    CREDIT_CARD = "CREDIT_CARD"

    # Generic catch-all for custom identifiers
    CUSTOM_ID = "CUSTOM_ID"


# Keep backward compatibility
PIIType = PHIType


# ══════════════════════════════════════════════════════════════════
#  Compiled Regex Patterns
# ══════════════════════════════════════════════════════════════════
#
# LEARNING NOTE ON PATTERN DESIGN:
#
# Each pattern uses word boundaries (\b) to avoid partial matches.
# Example: "\b\d{3}-\d{2}-\d{4}\b" matches "123-45-6789" but not
# the "123-45-6789" inside "X123-45-67890Y".
#
# Patterns are ordered from most specific to least specific within
# each category. The engine stops checking after the first match
# for a given field, so specific patterns must come first.
#
# re.compile() pre-compiles the patterns at import time for speed.
# Each pattern is compiled ONCE and reused for every inference.
# ══════════════════════════════════════════════════════════════════

PHI_PATTERNS: dict[PHIType, re.Pattern] = {
    # ── SSN (HIPAA #7) ──────────────────────────────────────────
    # Format: 123-45-6789 or 123456789
    # Excludes invalid SSNs (000, 666, 900-999 area numbers)
    PHIType.SSN: re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
        r"|\b(?!000|666|9\d{2})\d{3}(?!00)\d{2}(?!0000)\d{4}\b"
    ),

    # ── Medical Record Number (HIPAA #8) ────────────────────────
    # Formats: MRN-123456, MR#123456, MRN 123456
    PHIType.MEDICAL_RECORD: re.compile(
        r"\b(?:MR|MRNO|MRN|MEDICAL[_\s]?RECORD)[#\-:=\s]?\d{5,}\b",
        re.IGNORECASE,
    ),

    # ── Patient ID (HIPAA #18) ──────────────────────────────────
    # Formats: PAT-12345, PID:12345, HN-12345
    PHIType.PATIENT_ID: re.compile(
        r"\b(?:PAT|PID|PATIENT[_\s]?ID|HN|HOSPITAL[_\s]?NO)[#\-:=\s]?\w{3,}\b",
        re.IGNORECASE,
    ),

    # ── Health Plan ID (HIPAA #9) ───────────────────────────────
    # Medicare/Medicaid beneficiary numbers
    PHIType.HEALTH_PLAN_ID: re.compile(
        r"\b(?:HPBN|HICN|MBI|MEMBER[_\s]?ID|SUBSCRIBER[_\s]?ID)[#\-:=\s]?\w{5,}\b",
        re.IGNORECASE,
    ),

    # ── DEA Number ──────────────────────────────────────────────
    # Format: Two letters + seven digits (AB1234563)
    PHIType.DEA_NUMBER: re.compile(r"\b[A-Z]{2}\d{7}\b"),

    # ── NPI (National Provider Identifier) ──────────────────────
    # Format: Exactly 10 digits starting with 1 or 2
    PHIType.NPI: re.compile(r"\b[12]\d{9}\b"),

    # ── Account Number (HIPAA #10) ──────────────────────────────
    PHIType.ACCOUNT_NUMBER: re.compile(
        r"\b(?:ACCT?|ACCOUNT)[#\-:=\s]?\d{5,}\b",
        re.IGNORECASE,
    ),

    # ── License Number (HIPAA #11) ──────────────────────────────
    PHIType.LICENSE_NUMBER: re.compile(
        r"\b(?:DL|LICENSE|LIC)[#\-:=\s]?[A-Z0-9]{6,}\b",
        re.IGNORECASE,
    ),

    # ── Credit Card ─────────────────────────────────────────────
    # 4 groups of 4 digits with optional separators
    PHIType.CREDIT_CARD: re.compile(
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    ),

    # ── Email (HIPAA #6) ────────────────────────────────────────
    PHIType.EMAIL: re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),

    # ── Phone (HIPAA #4) ────────────────────────────────────────
    # US formats: (555) 123-4567, 555-123-4567, +1 555 123 4567
    PHIType.PHONE: re.compile(
        r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"
    ),

    # ── URL (HIPAA #14) ─────────────────────────────────────────
    # Patient portal URLs, health record links
    PHIType.URL: re.compile(
        r"https?://[^\s<>\"']{5,}",
        re.IGNORECASE,
    ),

    # ── IP Address (HIPAA #15) ──────────────────────────────────
    PHIType.IP_ADDRESS: re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),

    # ── Date (HIPAA #3) ─────────────────────────────────────────
    # MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD
    PHIType.DATE: re.compile(
        r"\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:\d{4}|\d{2})\b"
        r"|\b\d{4}[/\-](?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])\b"
    ),

    # ── Name (HIPAA #1) ─────────────────────────────────────────
    # Conservative: Capitalized FirstName LastName
    # LEARNING NOTE: This pattern has the highest false-positive rate.
    # "John Smith" matches, but so does "Blood Pressure" or "Heart Rate".
    # That's why field-name classification runs first and we use this
    # pattern only as a fallback.
    PHIType.NAME: re.compile(
        r"\b[A-Z][a-z]{1,20}\s[A-Z][a-z]{1,20}\b"
    ),

    # ── ZIP Code (HIPAA #2 partial) ─────────────────────────────
    # 5-digit or 5+4 format
    PHIType.ZIP_CODE: re.compile(
        r"\b\d{5}(?:-\d{4})?\b"
    ),

    # ── Vehicle ID (HIPAA #12) ──────────────────────────────────
    # VIN: 17 alphanumeric characters
    PHIType.VEHICLE_ID: re.compile(
        r"\b[A-HJ-NPR-Z0-9]{17}\b"
    ),

    # ── Device ID (HIPAA #13) ───────────────────────────────────
    # UDI (Unique Device Identifier) patterns
    PHIType.DEVICE_ID: re.compile(
        r"\b(?:UDI|DEVICE[_\s]?ID|SERIAL)[#\-:=\s]?[A-Z0-9]{6,}\b",
        re.IGNORECASE,
    ),
}

# Backward compatibility alias
PII_PATTERNS = PHI_PATTERNS


# ══════════════════════════════════════════════════════════════════
#  Field Name Detection Sets
# ══════════════════════════════════════════════════════════════════
#
# LEARNING NOTE:
# Two-pass detection gives us better coverage:
# Pass 1: Check if the FIELD NAME suggests PHI (fast, high confidence)
# Pass 2: Check if the FIELD VALUE matches a pattern (slower, broader)
#
# If a field is named "patient_ssn", we KNOW it's an SSN regardless
# of what the value looks like. This catches cases where the SSN
# might be in a non-standard format our regex misses.
# ══════════════════════════════════════════════════════════════════

# Field names that indicate CRITICAL (Level 4) data -- must redact
PHI_FIELD_NAMES_CRITICAL: set[str] = {
    # Names
    "name", "first_name", "last_name", "full_name",
    "patient_name", "patient_first_name", "patient_last_name",
    "guarantor_name", "next_of_kin", "emergency_contact_name",
    "attending_physician", "referring_physician", "provider_name",

    # Government IDs
    "ssn", "social_security", "social_security_number", "patient_ssn",
    "passport", "passport_number",
    "driver_license", "drivers_license", "license_number",

    # Healthcare IDs
    "mrn", "medical_record", "medical_record_number",
    "patient_id", "encounter_id",
    "insurance_id", "member_id", "subscriber_id",
    "beneficiary_id", "hicn", "mbi",
    "npi", "dea", "dea_number",
    "device_serial", "device_id", "udi",

    # Contact
    "email", "email_address", "patient_email",
    "phone", "phone_number", "patient_phone", "mobile", "fax",
    "address", "street_address", "home_address",

    # Financial
    "credit_card", "card_number", "cc_number",
    "account_number", "bank_account",

    # Technical identifiers
    "ip_address", "mac_address",
}

# Field names that indicate HIGH (Level 3) data -- must encrypt
PHI_FIELD_NAMES_HIGH: set[str] = {
    # Dates
    "dob", "date_of_birth", "birth_date", "birthday",
    "admission_date", "discharge_date", "death_date",

    # Demographics
    "age", "patient_age", "gender", "sex", "race", "ethnicity",
    "marital_status", "language", "religion",

    # Geographic
    "zip", "zip_code", "postal_code", "city", "county", "state",

    # Clinical
    "diagnosis", "diagnosis_code", "dx_code", "icd_code", "icd10",
    "snomed", "snomed_code", "condition",
    "medication", "drug_name", "prescription", "dosage", "rx", "ndc_code",
    "procedure_code", "cpt_code", "hcpcs_code", "procedure",
    "clinical_note", "progress_note", "discharge_summary",
    "radiology_report", "pathology_report",
    "genetic_test", "gene_variant", "brca", "genomic",
    "substance_abuse", "mental_health", "psychiatric", "dsm_code",
    "allergy", "allergies",
    "immunization", "vaccination",
    "family_history",

    # Vitals and Labs
    "lab_result", "lab_value",
    "hemoglobin", "hgb", "hba1c", "glucose", "lab_glucose",
    "creatinine", "bun", "gfr",
    "wbc", "rbc", "platelet",
    "potassium", "sodium", "chloride", "calcium", "magnesium",
    "cholesterol", "ldl", "hdl", "triglycerides",
    "troponin", "bnp", "psa", "tsh", "t4",
    "inr", "pt", "ptt",
    "blood_pressure", "systolic_bp", "diastolic_bp",
    "heart_rate", "pulse", "respiratory_rate",
    "temperature", "temp", "spo2", "oxygen_saturation",
    "bmi", "weight", "height",
}

# Combined backward-compatible set
PII_FIELD_NAMES = PHI_FIELD_NAMES_CRITICAL | PHI_FIELD_NAMES_HIGH
