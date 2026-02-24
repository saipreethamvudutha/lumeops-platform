# Session 7: Alert Management

## Overview

Session 7 adds a complete **Alert Management UI and API** to LumeOps, enabling
healthcare operations teams to triage, acknowledge, and resolve alerts generated
by the inference pipeline. This transforms alerts from passive database records
into an actionable incident management workflow — similar to PagerDuty, OpsGenie,
and Datadog's alerting systems.

## What We Built

### 1. Alert Lifecycle Model

Alerts follow a standard three-state lifecycle used across enterprise ops tooling:

```
   ┌─────────┐    acknowledge    ┌──────────────┐    resolve    ┌──────────┐
   │  OPEN   │ ─────────────────>│ ACKNOWLEDGED │ ──────────────>│ RESOLVED │
   └─────────┘                   └──────────────┘               └──────────┘
        │                                                             ▲
        │                         resolve (auto-ack)                  │
        └─────────────────────────────────────────────────────────────┘
```

**Why this matters for healthcare:**
- **MTTA (Mean Time to Acknowledge)**: Measures team responsiveness — critical
  in healthcare where delayed response to an outlier prediction (e.g., a cardiac
  risk model flagging an impossible value) could mask a system failure
- **MTTR (Mean Time to Resolve)**: Measures incident resolution speed — helps
  compliance teams report on operational effectiveness
- **Accountability**: `acknowledged_by` tracks who owns the alert, creating an
  audit trail for HIPAA incident response documentation

### 2. Backend API (7 Endpoints)

**File**: `app/api/v1/alerts.py`

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/api/v1/alerts` | read | List alerts with rich filtering |
| GET | `/api/v1/alerts/stats` | read | Aggregated statistics + MTTA/MTTR |
| GET | `/api/v1/alerts/{id}` | read | Get single alert details |
| POST | `/api/v1/alerts/{id}/ack` | admin | Acknowledge an alert |
| POST | `/api/v1/alerts/{id}/resolve` | admin | Resolve an alert |
| POST | `/api/v1/alerts/bulk-ack` | admin | Bulk acknowledge (up to 100) |
| POST | `/api/v1/alerts/bulk-resolve` | admin | Bulk resolve (up to 100) |

#### Filter Parameters (GET /alerts)

| Parameter | Type | Description |
|-----------|------|-------------|
| `alert_status` | enum | `open`, `acknowledged`, `resolved` |
| `severity` | enum | `critical`, `warning`, `info` |
| `alert_type` | enum | `outlier`, `data_quality`, `system` |
| `model_id` | string | Filter by specific model |
| `days` | int | Look-back window (default 7, max 365) |
| `sort_by` | enum | `triggered_at`, `severity`, `alert_type` |
| `sort_order` | enum | `desc` (default), `asc` |
| `limit` | int | Page size (default 25, max 100) |
| `offset` | int | Pagination offset |

### 3. Pydantic Schemas (8 New Schemas)

**File**: `app/api/v1/schemas.py`

#### Request Schemas
- **AlertAcknowledgeRequest**: `acknowledged_by` (1-255 chars, required), extra=forbid
- **AlertResolveRequest**: `resolution_note` (optional, max 2000 chars), extra=forbid
- **AlertBulkActionRequest**: `alert_ids` (1-100 items), `acknowledged_by` (optional)

#### Response Schemas
- **AlertDetailResponse**: Full alert record with all lifecycle timestamps
- **AlertListResponse**: Paginated list with `total`, `has_more`, `alerts[]`
- **AlertStatsResponse**: Aggregated counts + MTTA/MTTR + breakdown by severity/type
- **AlertBulkActionResponse**: `processed`, `skipped`, `alert_ids`

### 4. Frontend Alert Management Page

**File**: `frontend/src/pages/AlertsPage.tsx`

#### Features
- **Stat Cards**: Four KPI cards showing Open, Acknowledged, Resolved counts, and MTTA
- **Filter Bar**: Dropdowns for status, severity, type, and time range
- **Alert Table**: Selectable rows with severity badges, status indicators, timestamps
- **Individual Actions**: Acknowledge and Resolve buttons per alert row
- **Bulk Actions**: Checkbox selection with bulk acknowledge/resolve toolbar
- **Expandable Details**: Click to expand alert JSON details (bounds, issues, notes)
- **Pagination**: Previous/Next with offset tracking
- **Auto-refresh**: Data reloads after any state change

#### Navigation Integration
- Added "Alerts" to sidebar navigation with Bell icon
- Positioned between Inference Log and Compliance
- Route: `/alerts`

### 5. API Client Functions

**File**: `frontend/src/api/client.ts`

Seven new functions:
```typescript
fetchAlerts(params)        // GET /alerts with filter params
fetchAlertStats()          // GET /alerts/stats
acknowledgeAlert(id, by)   // POST /alerts/{id}/ack
resolveAlert(id, note?)    // POST /alerts/{id}/resolve
bulkAcknowledgeAlerts(...) // POST /alerts/bulk-ack
bulkResolveAlerts(...)     // POST /alerts/bulk-resolve
```

### 6. TypeScript Interfaces

**File**: `frontend/src/types/api.ts`

Four new interfaces:
- `AlertDetail` — Full alert record
- `AlertListResponse` — Paginated response with alerts array
- `AlertStats` — Statistics with MTTA/MTTR and breakdowns
- `AlertBulkResult` — Bulk operation result

## Design Decisions & Learning Notes

### Why Three-State Lifecycle?

The OPEN → ACKNOWLEDGED → RESOLVED pattern is the standard in incident management:

1. **OPEN**: Alert was triggered automatically by the ingest pipeline (outlier
   detected, data quality issue found). Nobody has seen it yet.

2. **ACKNOWLEDGED**: An operator has seen the alert and is working on it. This is
   important because it tells other team members "someone is handling this — don't
   duplicate effort." The `acknowledged_by` field provides accountability.

3. **RESOLVED**: Root cause addressed, alert closed. The optional `resolution_note`
   documents what was done — essential for post-incident reviews and compliance.

**Direct resolve** (skipping acknowledge) is supported because some alerts are
trivially resolved. When this happens, the system auto-sets `acknowledged_by` to
`"auto (resolved)"` so MTTA calculations still work.

### Why MTTA/MTTR?

These are the two most important operational metrics in any alerting system:

- **MTTA** = Average time between `triggered_at` and `acknowledged_at` across all
  acknowledged alerts. Tells you how quickly your team notices problems.

- **MTTR** = Average time between `triggered_at` and `resolved_at` across all
  resolved alerts. Tells you how quickly your team fixes problems.

Both are computed server-side using PostgreSQL's `EXTRACT(epoch FROM ...)` for
accuracy. They're nullable — when no alerts have been acknowledged/resolved yet,
the API returns `null` instead of misleading zeros.

### Why Scope-Based Authorization?

- **read** scope: Listing and viewing alerts (GET endpoints). Every API key with
  `read` scope can see the alert dashboard.

- **admin** scope: State-changing operations (POST endpoints for ack/resolve). Only
  keys with `admin` scope can modify alert state. This prevents read-only
  monitoring keys from accidentally acknowledging alerts.

### Why Idempotent Operations?

Acknowledging an already-acknowledged alert is a no-op (returns the current state).
This prevents race conditions where two operators click "Acknowledge" simultaneously.
However, acknowledging a **resolved** alert returns 409 Conflict — you can't
un-resolve by acknowledging.

### Why Bulk Operations with a 100-Item Limit?

Bulk operations process up to 100 alerts in a single request. This:
- Prevents accidentally bulk-operating on thousands of alerts
- Keeps request/response sizes manageable
- Maps well to paginated UI (one page = up to 100 alerts)

Bulk operations are non-atomic by design: each alert is processed individually,
and the response reports `processed` vs `skipped` counts. An already-acknowledged
alert in a bulk-ack request is simply skipped, not treated as an error.

## Testing

### Unit Tests (23 Tests)

**File**: `tests/unit/test_alert_schemas.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestAcknowledgeRequest | 5 | Valid, empty rejected, too long, extra fields |
| TestResolveRequest | 4 | With/without note, too long, extra fields |
| TestBulkActionRequest | 5 | Valid, empty list, too many, optional fields |
| TestResponseSchemas | 5 | Detail, list, stats, null MTTA/MTTR, bulk |
| TestAlertLifecycle | 3 | Open, acknowledged, resolved state validation |

### API Endpoint Verification

All 7 endpoints verified via curl:

1. **List alerts**: Returns paginated results with all filter combinations
2. **Alert stats**: Computes MTTA (17.5 min), MTTR (120 min) from test data
3. **Get alert**: Returns full detail with JSON bounds/issues
4. **Acknowledge**: Sets `acknowledged_at` and `acknowledged_by`
5. **Resolve**: Sets `resolved_at`, auto-acknowledges if needed, stores resolution note
6. **Bulk acknowledge**: Processes batch, reports processed/skipped
7. **Bulk resolve**: Processes batch with resolution note

### Full Suite Results

```
207 tests passed (4.98s)
├── test_alert_schemas.py       — 22 tests (NEW)
├── test_data_quality.py        — 13 tests
├── test_fhir_classifier.py     — 20 tests
├── test_minimum_necessary.py   — 15 tests
├── test_redaction_engine.py    — 44 tests
├── test_security.py            — 18 tests
└── test_webhook_service.py     — 21 tests

TypeScript: 0 errors
Vite build: 4.63s clean
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `app/api/v1/alerts.py` | NEW | 7 alert management endpoints |
| `app/api/v1/schemas.py` | MODIFIED | +8 alert schemas |
| `app/main.py` | MODIFIED | Register alerts router |
| `frontend/src/pages/AlertsPage.tsx` | NEW | Alert management UI |
| `frontend/src/App.tsx` | MODIFIED | Add /alerts route |
| `frontend/src/components/Layout.tsx` | MODIFIED | Add Alerts nav item |
| `frontend/src/api/client.ts` | MODIFIED | +7 alert API functions |
| `frontend/src/types/api.ts` | MODIFIED | +4 alert interfaces |
| `tests/unit/test_alert_schemas.py` | NEW | 22 schema validation tests |
| `docs/07_SESSION7_ALERT_MANAGEMENT.md` | NEW | This documentation |

## Architecture After Session 7

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend (React + Vite)                   │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│Dashboard │Inference │ Alerts   │Webhooks  │ Compliance      │
│          │   Log    │ (NEW)    │          │                 │
└──────────┴──────────┴──────────┴──────────┴─────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   FastAPI (v1)     │
                    ├───────────────────┤
                    │ Ingest Pipeline   │──> Alerts (auto-create)
                    │ Alert Management  │──> Acknowledge/Resolve
                    │ Webhook Delivery  │──> HTTP Callbacks
                    │ Dashboard/Stats   │──> Aggregations
                    │ Compliance Reports│──> HIPAA Reports
                    └───────────────────┘
                              │
          ┌───────────┬───────┴───────┬──────────────┐
          │PostgreSQL │    Redis      │Elasticsearch │
          │(data+alerts)│ (pub/sub)   │  (audit)     │
          └───────────┴───────────────┴──────────────┘
```

## What's Next

Potential Session 8 features:
1. **Model Performance Tracking** — Track accuracy, drift, and degradation over time
2. **Tenant Onboarding** — Self-service tenant creation and API key management UI
3. **Data Retention Policies** — Configurable TTL for inferences and alerts per tenant
4. **Production Deployment** — Docker Compose for production, Nginx reverse proxy, SSL
