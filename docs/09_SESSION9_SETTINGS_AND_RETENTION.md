# Session 9: Tenant Settings & Data Retention Policies

## Overview

Session 9 transforms the Settings page from a simple API key input into a comprehensive
tenant management hub with configurable data retention policies. This is critical for
enterprise readiness — customers need self-service configuration and HIPAA-compliant
data lifecycle management.

This session delivers:
- **7 new database columns** on the tenant model for retention policies and settings
- **6 new API endpoints** for tenant settings, retention policy, and cleanup operations
- **DataRetentionService** with configurable TTL cleanup for 3 data types
- **Background scheduler** (APScheduler) for automated daily cleanup at 2 AM UTC
- **8 new Pydantic schemas** for settings and retention data structures
- **Complete Settings page redesign** with 5 sections (API key, organization, security, retention, about)
- **39 unit tests** covering schemas, utilities, and constraint validation

## What We Built

### 1. Database Migration — Retention & Settings Fields

**Migration**: `alembic/versions/c7d9e4f2a3b1_add_data_retention_and_tenant_settings.py`

Added 7 new columns to the `tenants` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `inference_retention_days` | Integer | NULL | Days to keep inference records |
| `alert_retention_days` | Integer | NULL | Days to keep resolved alerts |
| `webhook_delivery_retention_days` | Integer | 90 | Days to keep webhook delivery logs |
| `retention_policy_updated_at` | DateTime(tz) | NULL | When policy was last changed |
| `last_retention_cleanup_at` | DateTime(tz) | NULL | When cleanup last ran |
| `timezone` | String(50) | "UTC" | Preferred timezone for reports |
| `notification_preferences` | JSONB | NULL | Alert notification config |

**NULL means "keep forever"** — this is the safe default. No data is deleted unless the
admin explicitly configures a retention policy.

### 2. Data Retention Service

**File**: `app/services/data_retention.py`

The `DataRetentionService` provides 6 methods across two concerns:

#### Retention Policy Management
| Method | Purpose |
|--------|---------|
| `get_retention_policy()` | Get current TTL settings for a tenant |
| `update_retention_policy()` | Set TTL values with constraint validation |
| `get_tenant_settings()` | Full settings response for Settings page |
| `update_tenant_settings()` | Update contact info, timezone, notifications |

#### Data Cleanup
| Method | Purpose |
|--------|---------|
| `cleanup_tenant()` | Delete expired data for one tenant (supports dry_run) |
| `cleanup_all_tenants()` | Delete expired data for all tenants with policies |

#### Retention Constraints (HIPAA-Compliant)

| Data Type | Minimum Days | Reasoning |
|-----------|-------------|-----------|
| Inferences | 365 | HIPAA requires minimum 1-year retention for medical records |
| Alerts | 30 | Need at least 1 month for incident trend analysis |
| Webhook Deliveries | 7 | Need at least 1 week for debugging delivery issues |

**Critical safety rule**: Only **resolved** alerts are eligible for cleanup. Open and
acknowledged alerts are never deleted, regardless of age — they represent active
incidents that still need attention.

#### URL Masking Utility

```python
def _mask_url(url: str | None) -> str | None
```

Masks webhook URLs for display in the Settings page. Shows only the domain:
`https://hooks.slack.com/services/T00/B00/xxx` → `https://hooks.slack.com/****`

This prevents accidental exposure of webhook secrets in the UI.

### 3. API Endpoints (6 New)

**File**: `app/api/v1/tenant_settings.py`

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/api/v1/settings` | read | Get full tenant settings |
| PUT | `/api/v1/settings` | admin | Update tenant settings |
| GET | `/api/v1/settings/retention` | read | Get retention policy |
| PUT | `/api/v1/settings/retention` | admin | Update retention policy |
| POST | `/api/v1/settings/retention/preview` | admin | Dry run cleanup (count only) |
| POST | `/api/v1/settings/retention/cleanup` | admin | Execute cleanup (delete data) |

#### Why `/settings` and Not `/tenants/{id}`?

The authenticated user already "is" the tenant (via API key). There's no need for a
tenant ID in the URL — it comes from auth context. `/settings` is the natural REST
resource for self-service configuration. A `/tenants/{id}` endpoint would be for
super-admin multi-tenant management (not implemented yet).

#### Why POST for Cleanup (Not DELETE)?

- It's an **action**, not a resource deletion
- It supports **dry_run mode** (preview before delete)
- It returns a **summary** of what was deleted
- **Multiple resources** are affected (inferences, alerts, webhooks)

### 4. Pydantic Schemas (8 New)

**File**: `app/api/v1/schemas.py`

| Schema | Purpose |
|--------|---------|
| `TenantSettingsResponse` | Full tenant settings for the Settings page |
| `TenantSettingsUpdateRequest` | Update contact info, timezone, notifications |
| `RetentionPolicyResponse` | Current TTL settings |
| `RetentionPolicyUpdateRequest` | Set TTL values (with Pydantic `ge` constraints) |
| `RetentionCleanupResponse` | Result of cleanup operation |

#### Validation Features
- **Timezone validation**: Only standard timezone strings accepted
- **Customer type validation**: hospital, insurer, vendor, research, government
- **Extra fields forbidden**: Pydantic `extra="forbid"` prevents unknown fields
- **HIPAA minimum enforcement**: `ge=365` on inference_retention_days
- **Notification preferences**: Typed as `dict[str, bool]`

### 5. Background Scheduler

**File**: `app/core/scheduler.py`

Uses APScheduler's `AsyncIOScheduler` for periodic maintenance tasks.

#### Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `retention_cleanup` | Daily at 2:00 AM UTC | Delete expired data for all tenants |

#### Why APScheduler Instead of Celery?

| Factor | APScheduler | Celery |
|--------|-------------|--------|
| Extra process | No (runs in FastAPI) | Yes (separate worker) |
| Extra infra | None needed | Broker config needed |
| Debugging | Same process, same logs | Distributed, harder to debug |
| Async support | Native AsyncIO | Requires async Celery |
| Complexity | Minimal | Significant |
| Best for | I/O-bound tasks (DB queries) | CPU-bound tasks, horizontal scaling |

For retention cleanup (DELETE queries that complete in seconds), APScheduler is the
right choice. Celery would be appropriate for tasks that take > 30 seconds or need
horizontal scaling.

### 6. Frontend Settings Page (Complete Redesign)

**File**: `frontend/src/pages/SettingsPage.tsx`

The Settings page now has 5 sections:

#### 1. API Key Configuration
- Local browser storage (unchanged from before)
- Saves API key to localStorage for dashboard auth

#### 2. Organization (Server-Side)
- Editable fields: Name, Contact Email, Phone, Alert Email, Timezone
- Plan badge with color coding (starter/professional/enterprise)
- Data Residency display (read-only)
- Save button with loading/success states

#### 3. Security (Read-Only)
- Encryption key version
- Last key rotation timestamp
- Total rotation count
- Tenant active/inactive status

#### 4. Data Retention
- Three TTL inputs: Inferences (min 365), Alerts (min 30), Webhooks (min 7)
- Input validation with red border for invalid values
- "Forever" placeholder when empty
- Policy metadata (last updated, last cleanup)
- **Preview Cleanup** button (dry run — counts without deleting)
- **Delete N Records** button (appears only after preview shows > 0)
- Cleanup result panel with per-type counts
- Auto-cleanup schedule note (daily at 2 AM UTC)

#### 5. About LumeOps
- Platform info and version
- Feature grid (PII Redaction, Encryption, Audit Trail, Real-time)

#### Reusable Components
- `SectionHeader` — Icon + label + subtitle
- `InputField` — Label with icon + styled input
- `InfoBox` — Read-only metric display
- `RetentionField` — Number input with days suffix and min validation
- `CleanupSummary` — 4-column grid showing cleanup counts

### 7. Configuration Updates

**File**: `app/core/config.py`

Added 4 new settings:
```python
RETENTION_CLEANUP_HOUR: int = 2       # Hour (UTC) to run daily cleanup
RETENTION_MIN_INFERENCE_DAYS: int = 365  # HIPAA minimum
RETENTION_MIN_ALERT_DAYS: int = 30
RETENTION_MIN_WEBHOOK_DAYS: int = 7
```

## Design Decisions & Learning Notes

### Why Per-Tenant Retention Policies?

Different customers have different requirements:
- **Hospitals**: May need 7-year retention (HIPAA recommended)
- **Insurers**: May need 10-year retention (state regulations)
- **Research**: May want 2-year retention (study duration)
- **Vendors**: May want minimal retention (reduce liability)

A global setting wouldn't work. Each tenant configures their own policies.

### Why NULL = Keep Forever?

The safe default is to never delete data. A typo in retention configuration
(e.g., `30` instead of `3000`) could cause data loss. By requiring explicit
configuration and enforcing minimums, we protect against accidental deletion.

The workflow is:
1. Admin sets retention policy in Settings
2. Admin clicks "Preview Cleanup" to see impact
3. Admin clicks "Delete N Records" to confirm
4. Automated scheduler runs cleanup daily at 2 AM

### Why Only Resolved Alerts Are Deleted?

Open and acknowledged alerts represent active incidents. Deleting them would:
- Remove evidence of ongoing issues
- Break MTTA/MTTR calculation for current incidents
- Potentially violate incident response procedures

Only alerts that have been explicitly resolved (issue fixed, root cause addressed)
are eligible for cleanup. This ensures no active incident data is ever lost.

### Why Three Separate TTL Settings?

Different data types have different characteristics:
- **Inferences**: Primary clinical data — longest retention (HIPAA)
- **Alerts**: Operational data — medium retention for trend analysis
- **Webhook deliveries**: Debug logs — shortest retention (delivery receipts)

Bundling them into a single TTL would force customers to over-retain webhook logs
(waste storage) or under-retain inferences (compliance risk).

## Testing

### Unit Tests (39 Tests)

**File**: `tests/unit/test_tenant_settings_schemas.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestMaskUrl | 6 | None, empty, HTTPS, HTTP, port, invalid URL |
| TestTenantSettingsSchemas | 11 | Valid update, empty name, invalid timezone, valid timezones, invalid customer type, valid types, extra fields, all-none, notification prefs, response |
| TestRetentionPolicySchemas | 12 | Valid update, inference below min, at min, alert below min, at min, webhook below min, at min, null=forever, partial update, extra fields, large values, response |
| TestCleanupResponseSchemas | 3 | Dry run, actual, large numbers |
| TestRetentionConstraints | 7 | HIPAA minimum, boundary, 6-year, 7-year, negative, zero, alert minimum, webhook minimum |

### API Endpoint Verification

All 6 endpoints verified via curl:

1. **GET /settings** — Returns full tenant settings
2. **PUT /settings** — Updated phone and timezone
3. **GET /settings/retention** — Returns current retention policy
4. **PUT /settings/retention** — Set inference=730d, alert=90d, webhook=30d
5. **POST /settings/retention/preview** — Dry run returned 0 (all data recent)
6. **POST /settings/retention/cleanup** — Executed cleanup, 0 deleted

**Validation enforcement verified**:
- `inference_retention_days=30` → 422 "must be >= 365"
- `timezone="Mars/Olympus"` → 422 "Invalid timezone"

### Full Suite Results

```
283 unit tests passed (11.34s)
├── test_tenant_settings_schemas.py  — 39 tests (NEW)
├── test_performance_schemas.py      — 37 tests
├── test_alert_schemas.py            — 22 tests
├── test_data_quality.py             — 13 tests
├── test_fhir_classifier.py          — 20 tests
├── test_minimum_necessary.py        — 15 tests
├── test_redaction_engine.py         — 44 tests
├── test_security.py                 — 18 tests
├── test_webhook_service.py          — 21 tests
└── ... (remaining tests)

TypeScript: 0 errors
Vite build: 5.64s clean
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `alembic/versions/c7d9e4f2a3b1_...py` | NEW | Migration: 7 new tenant columns |
| `app/models/tenant.py` | MODIFIED | +7 retention/settings fields |
| `app/services/data_retention.py` | NEW | DataRetentionService (6 methods) + _mask_url |
| `app/api/v1/tenant_settings.py` | NEW | 6 settings/retention endpoints |
| `app/api/v1/schemas.py` | MODIFIED | +8 tenant/retention schemas |
| `app/core/scheduler.py` | NEW | APScheduler setup + retention_cleanup task |
| `app/core/config.py` | MODIFIED | +4 retention config settings |
| `app/main.py` | MODIFIED | Register settings router + scheduler lifecycle |
| `frontend/src/pages/SettingsPage.tsx` | REWRITTEN | 5-section settings hub (from API key only) |
| `frontend/src/api/client.ts` | MODIFIED | +5 settings/retention API functions |
| `frontend/src/types/api.ts` | MODIFIED | +3 settings/retention interfaces |
| `tests/unit/test_tenant_settings_schemas.py` | NEW | 39 schema/utility/constraint tests |
| `docs/09_SESSION9_SETTINGS_AND_RETENTION.md` | NEW | This documentation |

## Architecture After Session 9

```
┌──────────────────────────────────────────────────────────────────┐
│                      Frontend (React + Vite)                      │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│Dashboard │Inference │ Models   │ Alerts   │Webhooks  │Settings  │
│          │   Log    │          │          │          │ (NEW)    │
│          │          │          │          │          │ Org Info │
│          │          │          │          │          │ Security │
│          │          │          │          │          │ Retention│
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                              │
                    ┌─────────┴─────────┐
                    │   FastAPI (v1)     │
                    ├───────────────────┤
                    │ Ingest Pipeline   │──> PII Redaction + Outlier Detection
                    │ Performance Track │──> Drift + Accuracy + Health
                    │ Ground Truth      │──> MAE/RMSE computation
                    │ Alert Management  │──> Lifecycle + MTTA/MTTR
                    │ Webhook Delivery  │──> HTTP Callbacks
                    │ Tenant Settings   │──> Config + Retention (NEW)
                    │ Dashboard/Stats   │──> Aggregations
                    │ Compliance Reports│──> HIPAA Reports
                    └───────┬───────────┘
                            │
               ┌────────────┼────────────┐
               │            │            │
               ▼            ▼            ▼
          PostgreSQL     Redis      Elasticsearch
         (data+config)  (pub/sub)    (audit)
                            │
                   ┌────────┴────────┐
                   │  APScheduler     │ (NEW)
                   │  - Retention     │
                   │    cleanup @2AM  │
                   └─────────────────┘
```

## Data Retention Flow

```
Admin configures retention policy in Settings page
    │
    ▼
PUT /api/v1/settings/retention
    │ Validates: inference >= 365, alert >= 30, webhook >= 7
    │ Saves to tenants table
    ▼
POST /api/v1/settings/retention/preview  (optional)
    │ Counts records that would be deleted
    │ Returns summary without deleting
    ▼
POST /api/v1/settings/retention/cleanup  (on-demand)
    │                              OR
    │ APScheduler daily at 2 AM UTC (automatic)
    ▼
DataRetentionService.cleanup_tenant()
    │
    ├─ Inferences older than inference_retention_days → DELETE
    ├─ RESOLVED alerts older than alert_retention_days → DELETE
    │  (open/acknowledged alerts are NEVER deleted)
    └─ Webhook deliveries older than webhook_delivery_retention_days → DELETE
    │
    ▼
Updates last_retention_cleanup_at on tenant
Logs summary to structured logging
```

## What's Next

Potential Session 10 features:
1. **Production Deployment** — Docker Compose for production, Nginx reverse proxy, SSL/TLS
2. **Tenant Onboarding** — Self-service tenant registration with initial API key generation
3. **Scheduled Performance Snapshots** — Use APScheduler to pre-compute model metrics hourly
4. **API Key Management UI** — Create/revoke keys from the frontend
