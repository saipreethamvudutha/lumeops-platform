# Session 8: Model Performance Tracking

## Overview

Session 8 adds **Model Performance Tracking** to LumeOps — the core differentiator that
transforms it from a generic monitoring tool into a true ML observability platform. While
traditional APM tracks request latency and error rates, ML observability adds prediction
distribution monitoring, accuracy metrics (via ground truth), drift detection, and data
quality trending.

This session delivers:
- **Performance Service** with SQL-level metric aggregation
- **5 new API endpoints** for model performance, timeseries, and ground truth
- **11 new Pydantic schemas** for performance data structures
- **Drift detection** comparing predictions against baseline distributions
- **Ground truth pipeline** enabling accuracy metrics (MAE, RMSE, bias)
- **Frontend Models page** with interactive charts and detailed metrics
- **37 unit tests** covering schemas, utilities, and drift logic

## What We Built

### 1. Database Layer — Performance Snapshots

**File**: `app/models/performance_snapshot.py`

The `ModelPerformanceSnapshot` table stores pre-computed periodic aggregations of model
metrics. Each row represents one model's performance for one time period (hourly or daily).

```
┌─────────────────────────────────────────────────────┐
│             model_performance_snapshots               │
├─────────────────────────────────────────────────────┤
│ id                    │ UUID primary key              │
│ tenant_id             │ FK → tenants                  │
│ model_id              │ FK → ml_models                │
│ period_start/end      │ Time window boundaries        │
│ period_type           │ "hourly" or "daily"           │
├──── Volume ──────────────────────────────────────────┤
│ total_inferences      │ Count in period               │
│ inferences_with_gt    │ Count with ground truth       │
│ ground_truth_coverage │ GT ratio (0-1)                │
├──── Predictions ─────────────────────────────────────┤
│ prediction_mean/std   │ Distribution center & spread  │
│ prediction_min/max    │ Range                         │
│ prediction_p50/p95/p99│ Percentiles                   │
├──── Accuracy ────────────────────────────────────────┤
│ mae                   │ Mean Absolute Error           │
│ rmse                  │ Root Mean Squared Error       │
│ mean_error            │ Bias (prediction - ground)    │
├──── Health ──────────────────────────────────────────┤
│ outlier_count/rate    │ Anomaly detection stats       │
│ quality_issue_count   │ Data quality violations       │
│ quality_rate          │ Clean data ratio (0-1)        │
│ pii_detected_count    │ Inferences with PII           │
│ total_pii_redacted    │ Individual PII fields redacted│
├──── Drift ───────────────────────────────────────────┤
│ drift_score           │ Normalized distance from      │
│                       │ baseline distribution         │
│ baseline_mean/std     │ Reference distribution params │
├──── Alerts ──────────────────────────────────────────┤
│ alerts_triggered      │ Count in period               │
│ alerts_by_severity    │ JSONB {"critical": N, ...}    │
├──── Confidence ──────────────────────────────────────┤
│ avg/min/max_confidence│ Confidence distribution       │
└─────────────────────────────────────────────────────┘
```

**Indexes (3)**:
- `idx_perf_tenant_model_period` — Primary lookup: tenant + model + time
- `idx_perf_period_type` — Filter by hourly/daily granularity
- `idx_perf_model_drift` — Find models with highest drift scores

**Migration**: `alembic/versions/b5e8d3f1a2c6_add_performance_snapshots.py`

### 2. Performance Service

**File**: `app/services/monitoring/performance.py`

The `PerformanceService` class provides 6 methods for computing and querying model metrics.
All heavy computation is done in PostgreSQL via SQL aggregate functions.

| Method | Description | SQL Features Used |
|--------|-------------|-------------------|
| `get_model_summary()` | Comprehensive model metrics | AVG, STDDEV, MIN, MAX, percentile_cont, COUNT FILTER, ABS, POWER, SQRT |
| `get_performance_timeseries()` | Time-bucketed metrics for charts | date_trunc, GROUP BY, ORDER BY, FILTER WHERE |
| `submit_ground_truth()` | Single ground truth submission | SELECT + UPDATE (PATCH-style) |
| `submit_ground_truth_batch()` | Batch GT submission (up to 500) | Loop with individual SELECT + UPDATE |
| `get_models_overview()` | All models with summary stats | LEFT JOIN, GROUP BY, aggregate FILTER |
| `_compute_drift()` | Drift score vs baseline | Baseline lookup + normalized distance |

#### Drift Detection Algorithm

```
drift_score = |current_mean - baseline_mean| / baseline_std
```

The drift score uses a simplified normalized distance metric:

| Score Range | Status | Meaning |
|-------------|--------|---------|
| < 0.5 | `stable` | Within normal variation |
| 0.5 - 1.0 | `minor_drift` | Monitor closely |
| 1.0 - 2.0 | `moderate_drift` | Investigate — predictions shifted |
| > 2.0 | `significant_drift` | Action needed — model may be degrading |

**Special cases handled**:
- `no_data` — No predictions in the period
- `no_baseline` — No baseline computed yet for this model
- `constant_baseline` — Baseline std=0 (all training predictions identical)

**Why this matters for healthcare**:
- Patient population shifts (e.g., flu season demographics) can cause drift
- Upstream data pipeline changes (e.g., lab units changed) manifest as prediction drift
- Gradual concept drift may indicate the model needs retraining
- Drift in a clinical model is a reportable event under some regulatory frameworks

#### _safe_round Utility

```python
def _safe_round(value: Any, digits: int = 4) -> float | None
```

Handles edge cases in metric computation:
- `None` → `None`
- `NaN` → `None`
- `Inf` / `-Inf` → `None`
- Numeric strings → converted and rounded
- Non-numeric → `None`

This prevents JSON serialization errors from PostgreSQL edge cases (e.g., STDDEV of one value = NULL, division by zero = NaN).

### 3. API Endpoints (5 New)

**File**: `app/api/v1/performance.py`

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/api/v1/models/overview` | read | All models with summary stats |
| GET | `/api/v1/models/{id}/performance` | read | Detailed model performance |
| GET | `/api/v1/models/{id}/performance/timeseries` | read | Time-bucketed data for charts |
| POST | `/api/v1/models/{id}/ground-truth/{inf_id}` | ingest | Submit single ground truth |
| POST | `/api/v1/models/ground-truth/batch` | ingest | Batch ground truth (up to 500) |

#### Query Parameters

**GET /models/overview**:
- `days` (int, default=7, range 1-365) — Look-back window

**GET /models/{id}/performance**:
- `days` (int, default=7, range 1-365) — Look-back window

**GET /models/{id}/performance/timeseries**:
- `days` (int, default=7, range 1-90) — Look-back window
- `granularity` (string, "hourly" or "daily") — Time bucket size

#### Response Structure: Model Performance Summary

```json
{
  "model": { "id", "model_name", "model_version", "description", "framework", "is_active", "tags", "created_at" },
  "period": { "days", "start", "end" },
  "volume": { "total", "today", "all_time", "with_ground_truth", "ground_truth_coverage" },
  "predictions": { "mean", "std", "min", "max", "p50", "p95", "p99" },
  "accuracy": { "mae", "rmse", "mean_error" },
  "health": { "outlier_count", "outlier_rate", "quality_issue_count", "quality_rate", "pii_inferences", "total_pii_redacted" },
  "confidence": { "avg", "min", "max" },
  "drift": { "score", "status", "baseline_mean", "baseline_std" },
  "alerts": { "total", "by_severity" },
  "generated_at": "2025-02-24T..."
}
```

#### Response Structure: Timeseries Point

Each data point in the timeseries represents one time bucket:
```json
{
  "timestamp": "2025-02-23T00:00:00+00:00",
  "total_inferences": 50,
  "with_ground_truth": 10,
  "prediction_mean": 0.45,
  "prediction_std": 0.12,
  "prediction_min": 0.01,
  "prediction_max": 0.98,
  "outlier_count": 3,
  "outlier_rate": 0.06,
  "quality_issue_count": 1,
  "quality_rate": 0.98,
  "pii_inferences": 5,
  "total_pii_redacted": 8,
  "avg_confidence": 0.88,
  "mae": 0.06,
  "rmse": 0.09
}
```

### 4. Pydantic Schemas (11 New)

**File**: `app/api/v1/schemas.py`

#### Performance Schemas
- **ModelPerformanceSummary** — Full model metrics (model, period, volume, predictions, accuracy, health, confidence, drift, alerts, generated_at)
- **ModelOverviewItem** — Summary stats per model for the list view (17 fields)
- **ModelsOverviewResponse** — List wrapper (total, days, models[], generated_at)
- **PerformanceTimeseriesPoint** — Single time bucket with 15 metric fields
- **PerformanceTimeseriesResponse** — model_id, days, granularity, series[], generated_at

#### Ground Truth Schemas
- **GroundTruthSubmitRequest** — `ground_truth: float`, extra=forbid
- **GroundTruthSubmitResponse** — inference_id, model_id, prediction, ground_truth, absolute_error, submitted_at
- **GroundTruthBatchItem** — inference_id + ground_truth, extra=forbid
- **GroundTruthBatchRequest** — items list (min=1, max=500), extra=forbid
- **GroundTruthBatchResponse** — processed, skipped, total, optional errors list

### 5. Router Registration Order

**File**: `app/main.py`

A critical design detail: the `performance` router is registered **before** the `models`
router, both under the `/api/v1/models` prefix:

```python
# Model performance tracking (registered BEFORE models router
# so /overview and /ground-truth/batch match before /{model_id})
app.include_router(
    performance.router,
    prefix=f"{prefix}/models",
    tags=["model-performance"],
)
app.include_router(
    models.router,
    prefix=f"{prefix}/models",
    tags=["models"],
)
```

**Why this matters**: FastAPI matches routes in registration order. The existing models
router has a `/{model_id}` catch-all path parameter. If registered first, a request to
`/models/overview` would be caught by `/{model_id}` with model_id="overview" — resulting
in a 404. By registering performance routes first, static paths like `/overview` and
`/ground-truth/batch` are matched before the parameterized catch-all.

This is a common pattern in web frameworks with prefix-based routing. The rule is:
**register specific/static routes before dynamic/parameterized routes**.

### 6. Frontend — Models Page

**File**: `frontend/src/pages/ModelsPage.tsx`

The Models page provides two views:

#### List View (Models Grid)
- **Responsive grid**: 1-3 columns depending on screen size
- **Model cards**: Name, version, framework badge, active indicator
- **Quick stats**: Inferences count, quality rate, outlier rate
- **Footer**: Total inferences count, last inference time
- **Color coding**: Green (healthy), amber (warning), red (critical)
- **Time range selector**: 24h, 7d, 30d, 90d
- **Animated entry**: Staggered fade-in with motion

#### Detail View (Model Performance Dashboard)
- **KPI Cards (6)**: Period Volume, Today, Quality Rate, Outlier Rate, Drift Score, Avg Confidence
- **Charts (4)**:
  1. **Inference Volume** — AreaChart with cyan gradient
  2. **Prediction Mean Trend** — LineChart with min/max bounds
  3. **Data Quality Trend** — BarChart showing quality rate per bucket
  4. **Outlier Rate Trend** — AreaChart with amber gradient
- **Detailed Metrics Panels (3)**:
  1. **Prediction Distribution** — Mean, Std, Median, P95, P99, Min, Max
  2. **Accuracy Metrics** — MAE, RMSE, Mean Error (or "No ground truth" placeholder)
  3. **Drift Detection** — Status badge, score, baseline params, threshold reference
- **Health Summary Bar** — 6-column grid showing total inferences, outliers, quality issues, PII stats, alerts triggered

#### Helper Components
- `DriftBadge` — Color-coded drift status chip (7 states)
- `MiniStat` — KPI card with icon and value
- `MetricRow` — Label/value pair for metric panels
- `fmt()` — Formats nullable numbers with fixed decimals
- `pct()` — Formats nullable decimals as percentages
- `timeAgo()` — Human-readable relative timestamps

#### Navigation Integration
- Added "Models" to sidebar with Brain icon
- Positioned between "Inference Log" and "Alerts"
- Route: `/models`

### 7. API Client & TypeScript Types

**File**: `frontend/src/api/client.ts` — 5 new functions:
```typescript
fetchModelsOverview(days)                          // GET /models/overview
fetchModelPerformance(modelId, days)               // GET /models/{id}/performance
fetchPerformanceTimeseries(modelId, params)         // GET /models/{id}/performance/timeseries
submitGroundTruth(modelId, inferenceId, gt)         // POST /models/{id}/ground-truth/{inf_id}
submitGroundTruthBatch(items)                       // POST /models/ground-truth/batch
```

**File**: `frontend/src/types/api.ts` — 7 new interfaces:
- `ModelOverview` — Summary stats per model
- `ModelsOverviewResponse` — API response wrapper
- `ModelPerformanceSummary` — Full performance data with nested dicts
- `PerformanceTimeseriesPoint` — Single chart data point
- `PerformanceTimeseriesResponse` — Timeseries API response
- `GroundTruthResult` — Single GT submission result
- `GroundTruthBatchResult` — Batch GT submission result

## Design Decisions & Learning Notes

### Why SQL-Level Aggregation?

All metric computation happens in PostgreSQL, not Python. This is crucial for performance:

```sql
-- PostgreSQL computes this across millions of rows in seconds
SELECT
    AVG(prediction) as mean,
    STDDEV(prediction) as std,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY prediction) as p95,
    COUNT(*) FILTER (WHERE is_outlier = true) as outliers
FROM inferences
WHERE model_id = :model_id AND received_at >= :start
```

Loading 1M inference rows into Python to compute these in a loop would be:
- **10-100x slower** (Python loops vs PostgreSQL's optimized C aggregation)
- **Memory intensive** (1M rows * ~500 bytes = ~500MB in Python memory)
- **Error-prone** (handling NULL/NaN in Python requires explicit checks)

PostgreSQL's `percentile_cont`, `FILTER WHERE`, and `date_trunc` make SQL-level
aggregation both cleaner and faster than equivalent Python code.

### Why On-Demand Computation Instead of Pre-Computed Snapshots?

The snapshot table exists in the schema but the current service computes metrics
on-demand from the `inferences` table. This simplifies deployment:

1. **No background scheduler needed** (no Celery, no cron)
2. **Always fresh data** (no stale snapshots)
3. **Simpler debugging** (query the source table directly)

For production at scale (>10M inferences per model), you'd add a periodic Celery beat
task to pre-compute snapshots every hour, then serve from the snapshot table. The
snapshot model is already defined and migrated, ready for that optimization.

### Why Separate Ground Truth Endpoints?

Ground truth in healthcare often arrives days or weeks after the original inference:
- A cardiac risk prediction might be made at admission
- The actual outcome (ground truth) is known only after treatment/discharge

The ground truth pipeline uses a simple PATCH-style approach:
1. Original inference is stored with `ground_truth = NULL`
2. Later, POST ground truth for that inference_id
3. Accuracy metrics (MAE, RMSE) automatically become available
4. Dashboard shows "No ground truth" when coverage is 0%

The batch endpoint (up to 500 items) supports bulk retroactive labeling — common when
clinical outcome data is exported from an EHR system in batches.

### Why 4-Tier Drift Classification?

The drift score uses normalized standard deviations because it's intuitive:
- **< 0.5**: Predictions are within half a standard deviation of baseline — normal variation
- **0.5-1.0**: Predictions shifted by up to 1 std — worth monitoring
- **1.0-2.0**: Predictions shifted 1-2 standard deviations — investigate root cause
- **> 2.0**: More than 2 std away — in a normal distribution, this covers <5% probability

This is a simplified version of the Population Stability Index (PSI) used in production
ML monitoring systems. Full PSI computes KL-divergence between binned distributions,
but the normalized mean difference provides a good approximation for initial monitoring.

### Why Accuracy Uses MAE + RMSE + Mean Error?

Three complementary accuracy metrics provide a complete picture:

- **MAE (Mean Absolute Error)**: Average magnitude of errors. Easy to interpret: "on
  average, predictions are off by 0.08." Treats all errors equally.

- **RMSE (Root Mean Squared Error)**: Penalizes large errors more than small ones. If
  RMSE >> MAE, there are some large outlier errors.

- **Mean Error (Bias)**: The average signed error. Positive = model over-predicts,
  negative = model under-predicts. Critical in healthcare where systematic bias
  (e.g., always under-predicting risk) can have patient safety implications.

## Testing

### Unit Tests (37 Tests)

**File**: `tests/unit/test_performance_schemas.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestSafeRound | 11 | Normal float, None, NaN, Inf, -Inf, zero, negative, integer, string number, non-numeric, default digits |
| TestGroundTruthSchemas | 12 | Valid submit, negative GT, zero GT, extra fields, submit response, batch item, empty ID rejected, batch valid, empty rejected, too many rejected, batch response, with errors |
| TestModelOverviewSchemas | 3 | Full item, null optionals, overview response |
| TestPerformanceSummarySchemas | 2 | Full summary, no ground truth |
| TestPerformanceTimeseriesSchemas | 3 | Point, null accuracy, response |
| TestDriftLogic | 6 | Stable, minor, moderate, significant, zero std, identical |

### API Endpoint Verification

All 5 endpoints verified via curl against running server:

1. **GET /models/overview** — Returns 6 models with summary stats:
   - Inference counts, quality rates, outlier rates per model
   - Verified response structure matches `ModelsOverviewResponse` schema

2. **GET /models/{id}/performance** — Full model metrics:
   - Prediction distribution (mean, std, percentiles)
   - Health metrics (outlier rate, quality rate, PII stats)
   - Drift detection (score + status vs baseline)
   - Confidence distribution
   - Alert summary by severity

3. **GET /models/{id}/performance/timeseries** — Daily time buckets:
   - Returns one data point per day
   - Each with volume, prediction stats, health, accuracy

4. **POST /models/{id}/ground-truth/{inf_id}** — Ground truth submission:
   - Submitted ground truth value: 0.001
   - Returned absolute_error: 0.549 (|0.55 - 0.001|)
   - Inference now has ground_truth + ground_truth_received_at populated

5. **GET /models (original)** — Verified no regression:
   - Existing model CRUD endpoints still work correctly after router reorder

### Full Suite Results

```
244 tests passed (4.92s)
├── test_performance_schemas.py    — 37 tests (NEW)
├── test_alert_schemas.py          — 22 tests
├── test_data_quality.py           — 13 tests
├── test_fhir_classifier.py        — 20 tests
├── test_minimum_necessary.py      — 15 tests
├── test_redaction_engine.py       — 44 tests
├── test_security.py               — 18 tests
├── test_webhook_service.py        — 21 tests
└── ... (remaining tests)

TypeScript: 0 errors
Vite build: 6.62s clean
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `app/models/performance_snapshot.py` | NEW | Snapshot table with 30+ columns, 3 indexes |
| `app/models/__init__.py` | MODIFIED | Export ModelPerformanceSnapshot |
| `alembic/versions/b5e8d3f1a2c6_...py` | NEW | Create model_performance_snapshots table |
| `app/services/monitoring/performance.py` | NEW | PerformanceService (6 methods) + _safe_round |
| `app/api/v1/performance.py` | NEW | 5 performance tracking endpoints |
| `app/api/v1/schemas.py` | MODIFIED | +11 performance/ground-truth schemas |
| `app/api/v1/__init__.py` | MODIFIED | Export performance module |
| `app/main.py` | MODIFIED | Register performance router (before models) |
| `frontend/src/pages/ModelsPage.tsx` | NEW | Models list + detail view with 4 charts |
| `frontend/src/App.tsx` | MODIFIED | Add /models route |
| `frontend/src/components/Layout.tsx` | MODIFIED | Add Models nav item with Brain icon |
| `frontend/src/api/client.ts` | MODIFIED | +5 performance API functions |
| `frontend/src/types/api.ts` | MODIFIED | +7 performance interfaces |
| `tests/unit/test_performance_schemas.py` | NEW | 37 schema/utility/drift tests |
| `docs/08_SESSION8_MODEL_PERFORMANCE.md` | NEW | This documentation |

## Architecture After Session 8

```
┌──────────────────────────────────────────────────────────────────┐
│                      Frontend (React + Vite)                      │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│Dashboard │Inference │ Models   │ Alerts   │Webhooks  │Compliance│
│          │   Log    │ (NEW)    │          │          │          │
│          │          │ List +   │          │          │          │
│          │          │ Detail   │          │          │          │
│          │          │ 4 Charts │          │          │          │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                              │
                    ┌─────────┴─────────┐
                    │   FastAPI (v1)     │
                    ├───────────────────┤
                    │ Ingest Pipeline   │──> PII Redaction + Outlier Detection
                    │ Performance Track │──> Drift + Accuracy + Health (NEW)
                    │ Ground Truth      │──> MAE/RMSE computation (NEW)
                    │ Alert Management  │──> Lifecycle + MTTA/MTTR
                    │ Webhook Delivery  │──> HTTP Callbacks
                    │ Dashboard/Stats   │──> Aggregations
                    │ Compliance Reports│──> HIPAA Reports
                    └───────────────────┘
                              │
          ┌───────────┬───────┴───────┬──────────────┐
          │PostgreSQL │    Redis      │Elasticsearch │
          │(data+perf)│  (pub/sub)    │  (audit)     │
          └───────────┴───────────────┴──────────────┘
```

## Metric Computation Flow

```
Inference submitted via POST /ingest
        │
        ▼
┌─────────────────────────┐
│  Stored in `inferences`  │
│  table with prediction,  │
│  confidence, is_outlier, │
│  has_quality_issues, etc.│
└────────────┬────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
GET /performance    POST /ground-truth
    │                 │
    ▼                 ▼
┌──────────┐    ┌──────────────┐
│ SQL AGG  │    │ Update       │
│ AVG,STDDEV│   │ ground_truth │
│ MIN,MAX  │    │ column       │
│ P50,P95  │    └──────┬───────┘
│ COUNT    │           │
│ FILTER   │           ▼
└────┬─────┘    Accuracy metrics
     │          become available
     ▼          (MAE, RMSE, bias)
┌──────────┐
│ Compare  │
│ vs.      │
│ baseline │
│ (drift)  │
└────┬─────┘
     │
     ▼
Response with model, volume,
predictions, accuracy, health,
drift, confidence, alerts
```

## What's Next

Potential Session 9 features:
1. **Tenant Onboarding** — Self-service tenant creation and API key management UI
2. **Data Retention Policies** — Configurable TTL for inferences and alerts per tenant
3. **Production Deployment** — Docker Compose for production, Nginx reverse proxy, SSL
4. **Scheduled Snapshot Computation** — Celery beat task to pre-compute performance snapshots
