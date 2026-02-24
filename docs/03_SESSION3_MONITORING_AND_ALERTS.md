# Session 3: Data Quality Monitoring + Outlier Detection + Alerts

## What We Built

This session added the monitoring and alerting layer to LumeOps:

1. **Data Quality Validation Engine** - 4-category check system per inference
2. **Statistical Outlier Detection** - 3-sigma baseline-based detection
3. **Alert System** - Tiered severity alerts created during ingest

---

## Part 1: Data Quality Validation

### The Problem

Raw ML inference data from hospitals can contain missing fields, out-of-range values, null entries, and type mismatches. Without validation, bad data silently degrades model monitoring accuracy.

### The Solution: DataQualityService

A synchronous validation engine that runs on every ingested inference, checking against per-model configuration.

### Validation Categories

| Issue Type       | Detection                                | Severity    |
|------------------|------------------------------------------|-------------|
| `missing_field`  | Required field not present in payload    | **CRITICAL** |
| `null_value`     | Field present but value is `None`        | **INFO**     |
| `out_of_range`   | Value outside configured min/max bounds  | **WARNING**  |
| `type_mismatch`  | Value type doesn't match expected type   | **INFO**     |

### Per-Model Configuration

Each registered model stores its validation rules as JSONB:

```python
required_fields: ["age", "symptom_1", "lab_value"]
field_ranges:    {"age": {"min": 0, "max": 120}, "bp": {"min": 60, "max": 200}}
field_types:     {"age": "float", "symptom": "string", "id": "int"}
```

This allows different validation rules per specialty (radiology vs cardiology).

### Severity Assignment Logic

- **CRITICAL**: Any `missing_field` issues (blocks inference processing)
- **WARNING**: Any `out_of_range` issues (degraded data quality)
- **INFO**: Only null/type issues (minor concerns)
- **None**: All valid

### Design Decision: Validate After PII Redaction

Data quality checks run on redacted data, not raw input. This ensures:
- No PHI appears in error messages or quality reports
- Validation operates on the data that actually gets stored
- Classification metadata is preserved for compliance

---

## Part 2: Outlier Detection

### The Problem

A single anomalous prediction (e.g., a patient risk score of 95 when the model typically outputs 40-70) could indicate a data pipeline issue, model drift, or a genuine edge case. Without outlier detection, these go unnoticed.

### The Solution: 3-Sigma Statistical Detection

```
lower_bound = mean - (sigma_threshold * std)
upper_bound = mean + (sigma_threshold * std)
is_outlier = prediction < lower_bound OR prediction > upper_bound
```

### Why 3-Sigma (Not ML-Based Anomaly Detection)?

- Simple, auditable, and statistically sound
- Doesn't require complex ML models to monitor ML models
- Easy to explain to healthcare compliance teams
- Configurable per-model via `outlier_sigma` field
- Sufficient for initial production deployment

### Baseline Lifecycle

**Initialization Threshold:**
- `BASELINE_MIN_SAMPLES = 100` (minimum before computing)
- `BASELINE_DEFAULT_SAMPLES = 1000` (default historical window)
- Configurable per model via `baseline_required_samples`

**Computation:**
1. Collect last N predictions for the model
2. Calculate: mean, standard deviation, median, min, max
3. Store as a `Baseline` record with `is_current=True`
4. Mark previous baseline with `valid_until` timestamp

**Edge Cases:**
- No baseline yet: Returns `is_outlier=False` with reason "No baseline available yet"
- Zero standard deviation (constant predictions): Any different value is an outlier
- Each model can override `outlier_sigma` threshold (default 3.0)

### Bounds Reporting

Every outlier check returns detailed context for debugging:

```python
OutlierResult(
    is_outlier=True,
    reason="Prediction 95.4 above upper bound 72.3 (mean=60.0, std=4.1, threshold=3sigma)",
    bounds={"lower": 47.7, "upper": 72.3},
    baseline_id="baseline_uuid",
)
```

---

## Part 3: Alert System

### Design Decisions

**Severity-Based Alert Triggering:**
- Outliers: Always create WARNING-level alerts
- Data Quality: Only CRITICAL severity triggers alerts
- This prevents alert fatigue from minor issues (e.g., null values)

**Alert Types:**

| Type           | Trigger                                      | Default Severity |
|----------------|----------------------------------------------|------------------|
| `outlier`      | `outlier_result.is_outlier == True`          | WARNING          |
| `data_quality` | `dq_result.severity == "critical"`           | CRITICAL         |
| `system_error` | Reserved for future use                      | varies           |

**Alert Lifecycle Fields:**
- `triggered_at` - When the alert was created
- `acknowledged_at / acknowledged_by` - Human workflow tracking
- `resolved_at` - When the issue was resolved
- `notified_email / notified_slack` - Notification tracking (future)

### Database Indexes

Optimized for common query patterns:
- `idx_alert_tenant` - Multi-tenant isolation
- `idx_alert_unresolved` - Active alert dashboard (`WHERE resolved_at IS NULL`)
- `idx_alert_triggered` - Timeline-based queries
- `idx_alert_model` - Model-specific alert filtering

---

## Ingest Pipeline Integration

The monitoring checks are integrated synchronously into the ingest flow:

```
POST /ingest
  1. Model lookup / auto-registration
  2. PII Redaction
  3. Data Quality Checks (DataQualityService)
  4. Baseline / Outlier Detection (BaselineService)
  5. Classification metadata extraction
  6. Encryption of redacted data
  7. Alert creation (if outlier or critical DQ issue)
  8. Audit logging
  9. Real-time event publishing
 10. Baseline initialization check (if sample threshold reached)
```

Alerts are created during ingest (not asynchronously) to provide immediate feedback in the API response:

```json
{
  "status": "received",
  "inference_id": "...",
  "data_quality_issues": ["Missing required field: lab_value"],
  "alerts": [{"type": "data_quality", "message": "..."}]
}
```

---

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `app/services/monitoring/data_quality.py` | Data quality validation engine |
| `app/services/monitoring/baselines.py` | Outlier detection with baseline management |
| `app/models/alert.py` | Alert database model with lifecycle fields |
| `app/models/baseline.py` | Statistical baseline model (mean, std, etc.) |
| `app/models/data_quality_metric.py` | Aggregated DQ metrics (hourly/daily) |

### Modified Files

| File | Change |
|------|--------|
| `app/api/v1/ingest.py` | Integrated DQ checks, outlier detection, and alert creation |
| `app/core/config.py` | Added baseline and alert configuration constants |

---

## Session Summary

### Key Constants

```python
BASELINE_MIN_SAMPLES = 100          # Minimum for baseline computation
BASELINE_DEFAULT_SAMPLES = 1000     # Default historical window
OUTLIER_SIGMA_THRESHOLD = 3.0       # Standard deviations for outlier flag
```

### What Passed

- Unit tests for data quality validation (missing fields, ranges, types, severity)
- Outlier detection with and without baselines
- Alert creation for outliers and critical DQ issues
- End-to-end ingest with monitoring pipeline
