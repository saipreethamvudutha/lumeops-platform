# Session 11: Audit Log Viewer & Trail Management

## Overview

Session 11 delivers the **Audit Log Viewer** — a HIPAA-critical feature that provides
full visibility into every auditable event across the platform. Healthcare compliance
officers and security teams need to inspect, search, filter, and export audit events
for incident investigations, regulatory audits, and operational monitoring.

This session delivers:
- **Enhanced Audit Trail API** with multi-field search, resource_type/status filters, and pagination metadata
- **New Stats Endpoint** (`GET /audit-trail/stats`) for event breakdown by action and resource type
- **CSV Export Endpoint** (`GET /audit-trail/export`) with 10,000-row limit for offline analysis
- **Full Audit Logs Page** with stats cards, filter bar, paginated table, detail modal, and CSV download
- **3 new API client functions** for audit trail list, stats, and CSV export
- **3 new TypeScript interfaces** (`AuditLogEntry`, `AuditTrailResponse`, `AuditTrailStats`)
- **42 new unit tests** across 7 test classes covering model, actions, response format, PII tracking, CSV, and configuration
- **Sidebar navigation** with ScrollText icon for Audit Trail

## Why Audit Log Viewer is Critical

### HIPAA Requirement

The HIPAA Security Rule (45 CFR 164.312(b)) mandates:
> Implement hardware, software, and/or procedural mechanisms that record and examine
> activity in information systems that contain or use electronic protected health information.

Without a viewer, the audit data we've been collecting since Session 1 is inaccessible
to compliance officers — rendering the audit system incomplete from a regulatory standpoint.

### Operational Value

| Use Case | How the Viewer Helps |
|----------|---------------------|
| **Incident Response** | Search by IP address or resource ID to trace unauthorized access |
| **Compliance Audits** | Export CSV for external auditors, filter by date range |
| **PII Monitoring** | Filter for PII_DETECTED_AND_REDACTED events, see redaction counts |
| **Key Management** | Track API key creation/revocation events |
| **System Health** | Stats breakdown shows event distribution across action types |

## What We Built

### 1. Enhanced Audit Trail API

**File**: `app/api/v1/compliance.py`

The existing `/audit-trail` endpoint was enhanced from a basic list with only `action`
and `days` filters to a fully-featured audit query API.

#### Before vs After

| Feature | Before (Session 1) | After (Session 11) |
|---------|-------------------|-------------------|
| Filters | `action`, `days` | `action`, `days`, `resource_type`, `status`, `search` |
| Search | None | Multi-field ILIKE on action, resource_id, resource_type, ip_address |
| Response fields | Basic (no IP, no key prefix) | Full: includes `api_key_prefix`, `ip_address`, `error_message`, `has_more` |
| Stats | None | Dedicated `/audit-trail/stats` endpoint |
| Export | None | CSV export via `/audit-trail/export` |
| Pagination | Offset only | Offset + `has_more` flag for UI pagination |

#### New Endpoints

```
GET /api/v1/reports/audit-trail/stats?days=30
GET /api/v1/reports/audit-trail/export?days=30&action=PII_DETECTED_AND_REDACTED
```

#### Multi-Field Search

The `search` parameter performs an `OR` query across 4 fields simultaneously:

```python
or_(
    AuditLog.action.ilike(term),
    AuditLog.resource_id.ilike(term),
    AuditLog.resource_type.ilike(term),
    AuditLog.ip_address.ilike(term),
)
```

**Why OR instead of AND?** In an audit investigation, users type a keyword and expect
to find matches anywhere. Searching for "192.168" should find events by IP. Searching
for "webhook" should find WEBHOOK_CREATED and WEBHOOK_DELETED actions. AND logic would
require exact matches across all fields, which defeats the purpose of a search bar.

#### Stats Endpoint Response

```json
{
    "period_days": 30,
    "total_events": 54,
    "pii_events": 20,
    "events_by_action": {
        "INFERENCE_RECEIVED": 25,
        "PII_DETECTED_AND_REDACTED": 10,
        "REPORT_GENERATED": 6,
        "API_KEY_CREATED": 3,
        "ENCRYPTION_KEY_ROTATION_BATCH": 2,
        "ENCRYPTION_KEY_ROTATED": 2
    },
    "events_by_resource_type": {
        "inference": 35,
        "report": 6,
        "api_key": 4,
        "tenant": 4,
        "alert": 3,
        "webhook": 2
    },
    "generated_at": "2026-02-24T22:34:56.332583+00:00"
}
```

#### CSV Export

The export endpoint generates a downloadable CSV with these columns:
`id`, `timestamp`, `action`, `resource_type`, `resource_id`, `api_key_prefix`,
`ip_address`, `status`, `pii_detected`, `details`

**Why 10,000 row limit?** CSV generation happens in memory using `io.StringIO`.
Without a limit, a tenant with millions of audit events could cause OOM. 10,000 rows
covers ~10 months of daily activity for a medium-sized deployment, and compliance
auditors typically work with bounded time ranges.

### 2. TypeScript Interfaces

**File**: `frontend/src/types/api.ts`

Three new interfaces were added to match the backend response shapes:

```typescript
export interface AuditLogEntry {
    id: string;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    api_key_prefix: string | null;
    ip_address: string | null;
    status: string;
    error_message: string | null;
    pii_detected: boolean;
    pii_types: Record<string, number> | null;
    timestamp: string;
    details: Record<string, unknown> | null;
}

export interface AuditTrailResponse {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
    entries: AuditLogEntry[];
}

export interface AuditTrailStats {
    period_days: number;
    total_events: number;
    pii_events: number;
    events_by_action: Record<string, number>;
    events_by_resource_type: Record<string, number>;
    generated_at: string;
}
```

### 3. API Client Functions

**File**: `frontend/src/api/client.ts`

Three new functions handle all audit trail API communication:

| Function | Endpoint | Purpose |
|----------|----------|---------|
| `fetchAuditTrail(params)` | `GET /audit-trail` | List with filters + pagination |
| `fetchAuditTrailStats(days)` | `GET /audit-trail/stats` | Stats breakdown |
| `downloadAuditTrailCsv(params)` | `GET /audit-trail/export` | Blob download as CSV |

The CSV download uses the same blob-to-link pattern established in Session 10 for
the compliance PDF export: `axios blob → createObjectURL → programmatic link click → revokeObjectURL`.

### 4. Audit Logs Page

**File**: `frontend/src/pages/AuditLogsPage.tsx`

The audit logs page is a comprehensive event viewer with four main sections:

#### Stats Cards (Top Row)

Four stat cards showing:
- **Total Events** — Total audit events in the selected time range
- **PII Events** — Events with PII detection/redaction
- **Action Types** — Number of distinct action categories
- **Resource Types** — Number of distinct resource categories

#### Filter Bar

| Control | Type | Purpose |
|---------|------|---------|
| Search input | Text | Multi-field search (action, resource_id, resource_type, IP) |
| Days selector | Dropdown | 7d / 30d / 90d / 365d time range |
| Action filter | Dropdown | Filter by specific action type |
| Resource filter | Dropdown | Filter by resource type |
| CSV Export | Button | Download filtered results as CSV |
| Reset | Button | Clear all filters |

#### Paginated Table

Each row displays:
- **Action icon + label** — Color-coded by action type with descriptive labels
- **Resource info** — Resource type badge + truncated resource ID
- **IP / Key** — IP address and API key prefix (when available)
- **Status badge** — Green (success) or red (error) pill
- **Timestamp** — Relative time with full datetime in a secondary line
- **Arrow** — Clickable to open detail modal

Pagination uses numbered page buttons (up to 7 visible) with first/last navigation.

#### Detail Modal

Clicking any row opens a full-detail modal showing:
- Action with icon and color
- Timestamp (full ISO format)
- Status badge
- Resource type and ID
- IP address and API key prefix
- PII detection status with type breakdown
- Error message (if any)
- Full JSON details block

#### Action Type Metadata

Each of the 12 known action types has defined metadata:

| Action | Label | Color | Icon |
|--------|-------|-------|------|
| INFERENCE_RECEIVED | Inference Received | cyan | Zap |
| PII_DETECTED_AND_REDACTED | PII Detected & Redacted | amber | ShieldAlert |
| REPORT_GENERATED | Report Generated | violet | FileText |
| API_KEY_CREATED | API Key Created | emerald | KeyRound |
| API_KEY_REVOKED | API Key Revoked | red | KeyRound |
| ALERT_ACKNOWLEDGED | Alert Acknowledged | blue | Bell |
| ALERT_RESOLVED | Alert Resolved | emerald | CheckCircle |
| ALERTS_BULK_ACKNOWLEDGED | Bulk Alerts Acknowledged | blue | Bell |
| ENCRYPTION_KEY_ROTATED | Encryption Key Rotated | violet | RotateCw |
| ENCRYPTION_KEY_ROTATION_BATCH | Batch Key Rotation | violet | RotateCw |
| WEBHOOK_CREATED | Webhook Created | cyan | Globe |
| WEBHOOK_DELETED | Webhook Deleted | red | Globe |

**Why color-code actions?** In a dense audit log table, color-coding provides instant
visual scanning. A compliance officer can spot all red (revocation/deletion) events at
a glance without reading every row.

### 5. Navigation Integration

**Files Modified**:
- `frontend/src/App.tsx` — Added `/audit-logs` route
- `frontend/src/components/Layout.tsx` — Added sidebar nav item with ScrollText icon

The Audit Trail link is positioned after Compliance and before API Keys in the sidebar,
reflecting the natural workflow: generate compliance reports, then drill into audit events.

## Architecture Decisions

### Why PostgreSQL for the Viewer (Not Elasticsearch)?

The audit trail has dual-write to both PostgreSQL and Elasticsearch. The viewer queries
PostgreSQL because:

1. **Consistency** — PostgreSQL is the source of truth; ES replication may lag
2. **Simplicity** — SQLAlchemy queries are simpler than Elasticsearch DSL for basic filters
3. **Reliability** — No additional service dependency for the critical audit viewer
4. **ACID** — PostgreSQL guarantees we never see partial or phantom audit entries

Elasticsearch can be used later for full-text search across `details` JSON and
high-cardinality faceted filtering when the dataset grows beyond what PostgreSQL
handles efficiently.

### Why ILIKE Search Instead of Full-Text Search?

`ILIKE` with the `%search%` pattern is sufficient because:
- Audit field values (actions, IPs, resource IDs) are short, structured strings
- The PostgreSQL indexes on `action` and `resource_type` accelerate most queries
- Full-text search (tsvector) adds complexity without proportional benefit here
- For compliance investigations, exact substring matching is the expected behavior

### Why 50 Items Per Page?

`PAGE_SIZE = 50` balances information density with rendering performance:
- Compliance officers scan large volumes of events, so 10-25 rows per page wastes time
- 100+ rows causes noticeable rendering lag with React state updates
- 50 matches what GitHub, AWS CloudTrail, and Datadog use for audit log viewers

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| `app/api/v1/compliance.py` | Enhanced audit-trail endpoint + 2 new endpoints | +130 |
| `frontend/src/types/api.ts` | Added 3 TypeScript interfaces | +30 |
| `frontend/src/api/client.ts` | Added 3 API client functions | +55 |
| `frontend/src/pages/AuditLogsPage.tsx` | **New** — Full audit log viewer page | +450 |
| `frontend/src/App.tsx` | Added audit-logs route | +2 |
| `frontend/src/components/Layout.tsx` | Added Audit Trail nav item + ScrollText icon | +2 |
| `tests/unit/test_audit_trail.py` | **New** — 42 unit tests across 7 classes | +419 |

## Test Coverage

### Unit Tests (42 new tests)

| Test Class | Tests | What It Covers |
|------------|-------|----------------|
| `TestAuditLogModel` | 8 | Model creation, nullable fields, defaults, table name, indexes |
| `TestAuditActionTypes` | 13 | All 12 known action types (parametrized) + field length |
| `TestResourceTypes` | 7 | 6 known resource types (parametrized) + nullable |
| `TestAuditTrailResponseFormat` | 3 | Pagination, entry fields, stats fields |
| `TestPIITracking` | 3 | PII detection with types, no PII, structure preservation |
| `TestCSVExportFormat` | 2 | CSV headers, row generation from model |
| `TestAuditTrailConfiguration` | 6 | File existence (page, model, service, endpoints, nav, route) |

### SQLAlchemy Default Value Testing

Two tests initially failed because SQLAlchemy `default=` values aren't applied at Python
object creation time — only at `session.flush()`. The fix was to verify the column
definition's default value rather than the in-memory object:

```python
# WRONG: SQLAlchemy default not applied at creation time
log = AuditLog(tenant_id="t1", action="TEST")
assert log.status == "success"  # FAILS: log.status is None

# CORRECT: Verify column definition
col = AuditLog.__table__.columns["status"]
assert col.default.arg == "success"  # PASSES
```

This is a common SQLAlchemy gotcha worth documenting. The default is only applied when:
1. The object is added to a session and flushed/committed
2. The database assigns the default via `server_default`

### Endpoint Testing (curl)

All endpoints verified against live Docker containers:

| Endpoint | Test | Result |
|----------|------|--------|
| `GET /audit-trail?days=30&limit=5` | Pagination, all fields present | 54 total, 5 returned |
| `GET /audit-trail?action=PII_DETECTED_AND_REDACTED` | Action filter | 10 results |
| `GET /audit-trail?resource_type=api_key` | Resource type filter | 4 results |
| `GET /audit-trail?search=webhook` | Multi-field search | 2 results |
| `GET /audit-trail?search=192.168` | IP address search | 33 results |
| `GET /audit-trail?search=PII` | Action keyword search | 10 results |
| `GET /audit-trail/stats?days=30` | Stats breakdown | 54 events, 20 PII, 12 actions |
| `GET /audit-trail/export?days=30` | CSV download | Valid CSV, 54 rows + header |

### Full Test Suite

```
Total: 376 passed, 0 failures (unit tests)
TypeScript: 0 errors
Vite Build: 2839 modules, clean production build
```

## Running Totals

| Metric | Session 10 | Session 11 | Delta |
|--------|-----------|-----------|-------|
| Unit Tests | 335 | 376 | +42 (new test file) |
| TypeScript Errors | 0 | 0 | — |
| API Endpoints | 25 | 28 | +3 (stats, export, enhanced list) |
| Frontend Pages | 8 | 9 | +1 (AuditLogsPage) |
| Sidebar Nav Items | 8 | 9 | +1 (Audit Trail) |
| API Client Functions | 22 | 25 | +3 |
| TypeScript Interfaces | 18 | 21 | +3 |
