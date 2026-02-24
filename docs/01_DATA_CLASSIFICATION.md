# LumeOps Data Classification Guide
## Understanding What Data We Handle and Why It Matters

---

## Why This Matters to You

Before writing a single line of code for data handling, you must understand
what you're protecting. In healthcare, getting this wrong means:

- **HIPAA violation:** $100 - $50,000 per record exposed, up to $1.5M/year
- **FDA action:** Warning letters, product recalls, market withdrawal
- **DOJ investigation:** $50M+ settlements for algorithmic discrimination
- **Loss of trust:** Hospitals will never use your product again

This document defines every type of data LumeOps touches, how sensitive
it is, and what protections it requires.

---

## HIPAA's 18 Identifiers (The Legal Foundation)

HIPAA defines exactly 18 types of information that make health data
"individually identifiable." If ANY of these are present alongside
health information, the entire record is PHI (Protected Health Information).

| # | Identifier | Examples | Our Detection Method |
|---|---|---|---|
| 1 | Names | John Smith, Mary Johnson | Regex + field name |
| 2 | Geographic data (smaller than state) | 123 Main St, ZIP 10001 | Regex + field name |
| 3 | Dates (except year) related to individual | DOB, admission date, discharge date | Regex + field name |
| 4 | Phone numbers | (555) 123-4567 | Regex |
| 5 | Fax numbers | (555) 123-4568 | Regex |
| 6 | Email addresses | patient@email.com | Regex |
| 7 | Social Security Numbers | 123-45-6789 | Regex |
| 8 | Medical Record Numbers | MRN-123456 | Regex + field name |
| 9 | Health plan beneficiary numbers | HPBN-789012 | Regex + field name |
| 10 | Account numbers | ACC-345678 | Field name heuristic |
| 11 | Certificate/license numbers | DL, nursing license | Regex + field name |
| 12 | Vehicle identifiers & serial numbers | VIN, plate numbers | Regex |
| 13 | Device identifiers & serial numbers | Pacemaker serial, pump ID | Field name heuristic |
| 14 | Web URLs | patient portal links | Regex |
| 15 | IP addresses | 192.168.1.100 | Regex |
| 16 | Biometric identifiers | Fingerprints, retinal scans | Field name heuristic |
| 17 | Full-face photographs | Image data | Binary detection |
| 18 | Any other unique identifying number | Custom hospital IDs | Field name heuristic |

**Key insight:** Our redaction engine must cover ALL 18, not just the
obvious ones (SSN, email, phone).

---

## LumeOps Data Sensitivity Levels

We classify all data into four sensitivity levels. Each level has
specific handling requirements.

### Level 4: CRITICAL (Direct Identifiers)
**What:** Data that directly identifies a patient on its own.
**Examples:** SSN, full name, medical record number, email
**Handling:**
- MUST be redacted before storage (no exceptions)
- Replaced with `[REDACTED_TYPE]` token
- Original value NEVER stored, NEVER logged, NEVER cached
- Redaction event logged to immutable audit trail

### Level 3: HIGH (Indirect Identifiers / Clinical Data)
**What:** Data that can identify a patient when combined with other data,
OR sensitive clinical information.
**Examples:** Date of birth, ZIP code, diagnosis codes, lab results,
medications, treatment plans, genetic data
**Handling:**
- Redact direct identifiers within this data
- Encrypt before storage (field-level Fernet encryption)
- Access logged to audit trail
- Minimum necessary rule applies (only store what's needed)

### Level 2: MODERATE (Operational Healthcare Data)
**What:** Healthcare operational data that is sensitive but not directly
identifying.
**Examples:** Aggregated statistics, model performance metrics, inference
counts, quality scores, alert summaries
**Handling:**
- Encrypt at rest (database-level encryption)
- Access controlled (API key + scope)
- Standard audit logging

### Level 1: LOW (System Data)
**What:** Technical operational data with no patient information.
**Examples:** System health metrics, API latency, error rates, server logs
**Handling:**
- Standard security practices
- No encryption beyond TLS
- Retained per standard policy

---

## The "Minimum Necessary" Rule

HIPAA requires that we only access, use, or disclose the **minimum amount
of PHI necessary** to accomplish the intended purpose.

For LumeOps, this means:

1. **We don't need raw PHI.** Our job is to monitor the AI model's
   predictions and data quality -- not to read patient records.

2. **We redact first, then process.** The redacted data is sufficient
   for computing baselines, detecting outliers, and generating reports.

3. **We never reconstruct.** Even though we could theoretically reverse
   some redactions (e.g., if ZIP code is the only redacted field), we
   never attempt this and our code has no mechanism to do so.

4. **Access is scoped.** API keys have specific scopes (ingest, read,
   audit, admin). A key with "ingest" scope cannot read reports.

---

## Clinical Data We Handle (Beyond PII)

This is what the initial build missed. Healthcare AI inferences contain
much more than names and SSNs:

### Diagnosis Data
- **ICD-10 codes:** E11.65 (Type 2 diabetes with hyperglycemia)
- **SNOMED CT codes:** Clinical terminology codes
- **DSM-5 codes:** Mental health diagnoses
- **Sensitivity:** HIGH -- a diagnosis can be stigmatizing (HIV, mental
  health, substance abuse). Special protections under 42 CFR Part 2.

### Laboratory Data
- **Lab values:** Glucose, HbA1c, cholesterol, CBC, metabolic panels
- **Reference ranges:** Normal vs. abnormal flags
- **Sensitivity:** HIGH when combined with other data

### Medication Data
- **Drug names:** Metformin, lisinopril, insulin
- **Dosages:** 500mg, 10mg, 20 units
- **Prescriber info:** May contain provider names (identifier #1)
- **Sensitivity:** HIGH -- certain medications reveal conditions
  (e.g., AZT suggests HIV, lithium suggests bipolar)

### Procedure Data
- **CPT codes:** Medical procedure codes
- **HCPCS codes:** Healthcare Common Procedure Coding System
- **Surgical notes references:** May contain identifiers
- **Sensitivity:** HIGH

### Imaging Data References
- **DICOM metadata:** Patient name, ID, study date embedded in headers
- **Radiology reports:** Free text with PHI
- **Sensitivity:** CRITICAL -- DICOM headers contain multiple identifiers

### Genomic/Genetic Data
- **Genetic test results:** BRCA mutations, pharmacogenomics
- **Sensitivity:** CRITICAL -- uniquely identifies individuals,
  covered by GINA (Genetic Information Nondiscrimination Act)

---

## How This Changes Our Architecture

### Before (PII-only thinking):
```
Inference comes in → Scan for SSN/email/phone → Mask those → Store the rest
```

### After (Full healthcare data handling):
```
Inference comes in
  → Classify every field by sensitivity level (4/3/2/1)
  → Level 4 (identifiers): REDACT completely
  → Level 3 (clinical): REDACT identifiers within, ENCRYPT the data
  → Level 2 (operational): ENCRYPT at rest
  → Level 1 (system): Standard handling
  → Log classification decision to audit trail
  → Enforce minimum necessary rule
  → Store with appropriate protection per level
```

This is a fundamental shift from "find and mask PII" to
"classify and protect ALL healthcare data appropriately."
