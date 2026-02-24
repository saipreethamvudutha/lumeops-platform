# LumeOps Data Flow: Every Step Explained

## How Healthcare Data Flows Through LumeOps

This document traces a single inference from the moment it arrives at
our API to the moment it's safely stored and the response is sent back.
Every transformation, check, and protection is documented.

---

## The Full Processing Pipeline

```
Hospital AI Model
    │
    │  POST /api/v1/ingest
    │  { model_id, prediction, input_features: { ... } }
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. SCHEMA VALIDATION (Pydantic)                            │
│     - Request body must match InferenceRequest schema       │
│     - input_features limited to 1MB (DoS protection)        │
│     - model_id required, prediction required                │
│     - Automatic 422 Unprocessable Entity on failure         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  2. AUTHENTICATION                                          │
│     - X-API-Key header extracted                            │
│     - HMAC-SHA256 hash computed                             │
│     - Hash compared to stored hashes (constant-time)        │
│     - Tenant ID resolved from API key                       │
│     - API key scope checked (must have "ingest" scope)      │
│     - IP whitelist enforced (if configured)                 │
│     - Automatic 401/403 on failure                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  3. RATE LIMITING                                           │
│     - Redis sliding window check                            │
│     - Limit based on tenant plan (starter/pro/enterprise)   │
│     - Automatic 429 Too Many Requests on failure            │
│     - Graceful degradation if Redis is down                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  4. DATA CLASSIFICATION                                     │
│     ┌───────────────────────────────────────────────────┐   │
│     │ For each field in input_features:                 │   │
│     │                                                   │   │
│     │ "patient_ssn"    → CRITICAL (direct identifier)   │   │
│     │ "diagnosis_code" → HIGH (clinical data)           │   │
│     │ "claim_amount"   → MODERATE (billing)             │   │
│     │ "prediction"     → LOW (model output)             │   │
│     │ "unknown_field"  → MODERATE (fail-safe default)   │   │
│     └───────────────────────────────────────────────────┘   │
│                                                             │
│  Classification methods (in order):                         │
│  1. Field name exact match (fastest, highest confidence)    │
│  2. Partial field name match (catches variants)             │
│  3. Default to MODERATE (fail-safe for unknown fields)      │
│                                                             │
│  Output: classification_summary + fields_to_redact          │
│          + fields_to_encrypt                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  5. PHI REDACTION (Three-Pass Detection)                    │
│                                                             │
│  IMPORTANT: Original data is DEEP COPIED first.             │
│  The original dict is NEVER modified.                       │
│                                                             │
│  ┌── Pass 1: CRITICAL Field Names ───────────────────┐     │
│  │ Field name "ssn" is in CRITICAL set?               │     │
│  │ YES → Replace value with [REDACTED_SSN]            │     │
│  │ NO  → Continue to Pass 2                           │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  ┌── Pass 2: HIGH Field Names ───────────────────────┐     │
│  │ Field name "diagnosis_code" is in HIGH set?        │     │
│  │ YES → Note for encryption (don't redact)           │     │
│  │       BUT scan value for embedded identifiers:     │     │
│  │       "Patient SSN 123-45-6789 has diabetes"       │     │
│  │       → "Patient SSN [REDACTED_SSN] has diabetes"  │     │
│  │ NO  → Continue to Pass 3                           │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  ┌── Pass 3: Value Pattern Matching ─────────────────┐     │
│  │ Does the value match any PHI regex pattern?        │     │
│  │ SSN: \d{3}-\d{2}-\d{4}                            │     │
│  │ EMAIL: [A-Za-z0-9._%+-]+@...                      │     │
│  │ MRN: MRN-\d{5,}                                   │     │
│  │ ... all 18 HIPAA identifier patterns               │     │
│  │ YES → Replace entire value with [REDACTED_TYPE]    │     │
│  │ NO  → Field is clean, keep as-is                   │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  Output: redacted_data + report (what was found/redacted)   │
│          + classification_summary                           │
│          + high_sensitivity_fields list                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  6. DATA QUALITY VALIDATION                                 │
│     - Missing required fields? (e.g., "age" expected)       │
│     - Null values in non-nullable fields?                   │
│     - Values outside expected ranges? (BP > 300?)           │
│     - Wrong data types? (string where number expected?)     │
│     - Severity classification (critical/warning/info)       │
│                                                             │
│  Output: is_valid + list of quality issues                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  7. OUTLIER DETECTION                                       │
│     - Load current baseline for this model                  │
│     - Compare prediction to baseline (3-sigma threshold)    │
│     - If no baseline yet: skip (will auto-initialize later) │
│                                                             │
│  Output: is_outlier + reason + bounds                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  8. ENCRYPTION (Per-Tenant Key Isolation)                   │
│                                                             │
│  The redacted input_features dict is encrypted using:       │
│                                                             │
│  Master Key (from env) + Tenant ID (from auth)              │
│       │                                                     │
│       ▼                                                     │
│  PBKDF2-SHA256 (480,000 iterations)                         │
│       │                                                     │
│       ▼                                                     │
│  Tenant-Specific Fernet Key                                 │
│       │                                                     │
│       ▼                                                     │
│  AES-128-CBC + HMAC-SHA256 (Fernet token)                   │
│       │                                                     │
│       ▼                                                     │
│  Base64-encoded ciphertext → stored in database             │
│                                                             │
│  IMPORTANT: Hospital A's key ≠ Hospital B's key             │
│  Compromising one tenant does NOT expose others.            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  9. DATABASE STORAGE                                        │
│                                                             │
│  Inference record created with:                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │ id                      : "inf_abc123..."        │       │
│  │ tenant_id               : "tenant_xyz"           │       │
│  │ model_id                : "diagnostic_v2"        │       │
│  │ prediction              : 0.87                   │       │
│  │ confidence              : 0.92                   │       │
│  │ input_features_encrypted: "gAAA..." (Fernet)     │       │
│  │ pii_detected            : true                   │       │
│  │ pii_redaction_count     : 3                      │       │
│  │ pii_types_found         : {"SSN":1,"EMAIL":1}    │       │
│  │ classification_summary  : {by_sensitivity:...}   │       │
│  │ max_sensitivity_level   : "CRITICAL"             │       │
│  │ contains_clinical_data  : true                   │       │
│  │ has_quality_issues      : false                  │       │
│  │ is_outlier              : false                  │       │
│  │ received_at             : "2024-01-15T10:30:00Z" │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Alerts created if: outlier detected or critical quality    │
│  issues found.                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  10. AUDIT LOGGING (Immutable)                              │
│      - "inference_received" event logged                    │
│      - "pii_redacted" event logged (if PHI found)           │
│      - Includes: tenant, inference_id, model, timestamp,    │
│        pii_types, source_ip                                 │
│      - NEVER includes raw PHI values                        │
│      - Append-only (cannot be modified or deleted)           │
│      - 7-year retention requirement                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  11. RESPONSE                                               │
│      {                                                      │
│        "status": "received",                                │
│        "inference_id": "inf_abc123...",                      │
│        "message": "Inference stored safely. 3 PHI item(s)   │
│                    redacted. 5 field(s) marked for           │
│                    encryption",                              │
│        "pii_redacted": 3,                                   │
│        "data_quality_issues": [],                           │
│        "alerts": null,                                      │
│        "timestamp": "2024-01-15T10:30:00Z"                  │
│      }                                                      │
│                                                             │
│  NEVER includes: raw data, encryption keys, other tenants'  │
│  data, internal error details, or stack traces.             │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Protection Summary

### What Happens to Each Data Type

| Field | Classification | Action | Stored As |
|---|---|---|---|
| `patient_ssn` | CRITICAL | Redacted | `[REDACTED_SSN]` (encrypted) |
| `patient_email` | CRITICAL | Redacted | `[REDACTED_EMAIL]` (encrypted) |
| `patient_name` | CRITICAL | Redacted | `[REDACTED_NAME]` (encrypted) |
| `diagnosis_code` | HIGH | Encrypted | Original value (per-tenant encrypted) |
| `medication` | HIGH | Encrypted | Original value (per-tenant encrypted) |
| `lab_glucose` | HIGH | Encrypted | Original value (per-tenant encrypted) |
| `clinical_note` | HIGH | Scanned + Encrypted | Embedded identifiers removed, rest encrypted |
| `claim_amount` | MODERATE | Standard encryption | Original value (encrypted) |
| `prediction` | LOW | Standard | Original value (encrypted with rest of payload) |
| `model_version` | LOW | Standard | Original value (encrypted with rest of payload) |

### The Five Protection Layers

```
Layer 1: TLS 1.3 ──────── Network encryption in transit
Layer 2: PHI Redaction ─── CRITICAL identifiers removed
Layer 3: Minimum Necessary ── Unnecessary fields stripped (per purpose)
Layer 4: Fernet Encryption ── Per-tenant AES-128-CBC + HMAC-SHA256
Layer 5: Disk Encryption ─── PostgreSQL + volume encryption at rest
```

### Access Control by Purpose

| Purpose | Can See | Cannot See |
|---|---|---|
| Dashboard | Predictions, quality metrics | Clinical data, identifiers |
| Model Monitoring | + Vitals, lab ranges | Diagnoses, medications, identifiers |
| Data Quality | + Diagnoses, medications | Direct identifiers |
| Compliance Reporting | + Billing metadata | Clinical details, identifiers |
| Audit Trail | Everything except identifiers | Raw PHI (always redacted) |
| Storage | All redacted data | Raw identifiers (redacted before storage) |

---

## Key Invariants (Things That MUST Always Be True)

1. **No raw PHI in responses.** API responses NEVER contain unredacted patient data.
2. **No raw PHI in logs.** Structured logging NEVER includes field values.
3. **No cross-tenant data leakage.** Every query includes `WHERE tenant_id = X`.
4. **No cross-tenant key access.** Each tenant has a unique encryption key.
5. **Original data never mutated.** The redaction engine works on a deep copy.
6. **Every action audited.** The audit log records every significant operation.
7. **Unknown fields default to encrypted.** New/unknown fields are treated as MODERATE.
8. **Behavioral health data extra-protected.** 42 CFR Part 2 compliance.
9. **Genetic data extra-protected.** GINA compliance.
