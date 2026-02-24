# Session 6: Webhook Notifications

## Overview

Session 6 transforms LumeOps from a passive observability platform into an
**actionable notification system**. Tenants can now configure HTTP webhook
endpoints to receive real-time callbacks when events occur in their inference
pipelines — alerts, outliers, PII detections, data quality issues, and more.

## What We Built

### 1. Database Layer

**Two new tables** (migration `a3f7c9d2e1b4`):

#### `webhook_configs`
Per-tenant webhook endpoint configuration:
- **Endpoint**: name, URL, description, custom headers
- **Event subscriptions**: JSONB array of event types to receive
- **Security**: HMAC-SHA256 signing secret (generated at creation)
- **Lifecycle**: is_active flag, auto-disable after consecutive failures
- **Delivery tracking**: last_triggered_at, last_success/failure, HTTP status,
  consecutive failure count, total deliveries/failures
- **Indexes**: by tenant, by (tenant + is_active)

#### `webhook_deliveries`
Immutable audit trail of every delivery attempt:
- **References**: webhook_id, tenant_id, event_type, event_id
- **Payload**: The sent JSON (never contains PHI)
- **Response**: HTTP status, response body (truncated 1KB), response time
- **Status**: success boolean, error message, attempt number
- **Index**: by webhook, by tenant, by delivery time

### 2. Webhook Delivery Service (`app/services/webhooks/`)

#### Core Features

**HMAC-SHA256 Signing**
Every payload is cryptographically signed:
```
X-LumeOps-Signature: sha256=<hex-encoded HMAC>
```
Receivers verify authenticity by computing the same HMAC with their secret.
This prevents spoofed deliveries and tampered payloads — same pattern used by
GitHub, Stripe, and other enterprise webhook providers.

**Fire-and-Forget Pattern**
Webhook delivery does NOT block the inference pipeline. If a delivery fails,
the inference is still stored successfully. This follows the same architecture
as Elasticsearch writes and Redis pub/sub — secondary systems are best-effort.

**Auto-Disable After Failures**
After 10 consecutive delivery failures, the webhook automatically disables to
prevent resource waste on dead endpoints. The failure counter resets on any
successful delivery. Re-enabling via the API resets the counter.

**Delivery Audit Trail**
Every delivery attempt is recorded in `webhook_deliveries` with HTTP status,
response time, and error details. Retained for debugging and compliance.

#### Event Types

| Event Type | Description | Triggered By |
|---|---|---|
| `alert_created` | Any alert fires | All alert-generating conditions |
| `outlier_detected` | Prediction anomaly | Outlier detection in ingest |
| `pii_detected` | PHI found in data | PII redaction in ingest |
| `data_quality_issue` | Quality check fails | Data quality validation |
| `key_rotated` | Encryption key change | Key rotation endpoint |
| `compliance_report` | Report generated | Compliance report endpoint |

#### Security: No PHI in Payloads

Webhook payloads **never contain raw patient data**, input features, or any
PHI. Only metadata is transmitted:
- Alert type and severity
- Inference ID (not the inference content)
- Model name
- Counts and timestamps
- PII type names (e.g., "SSN detected"), not the actual PII values

This ensures HIPAA compliance even if the receiving endpoint is outside the
covered entity's boundary.

### 3. API Endpoints

All webhook endpoints require the `admin` scope.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/webhooks` | Create webhook (returns secret once) |
| `GET` | `/api/v1/webhooks` | List all webhooks for tenant |
| `GET` | `/api/v1/webhooks/{id}` | Get single webhook details |
| `PATCH` | `/api/v1/webhooks/{id}` | Update webhook config |
| `DELETE` | `/api/v1/webhooks/{id}` | Delete webhook + delivery history |
| `POST` | `/api/v1/webhooks/{id}/test` | Send test delivery |
| `GET` | `/api/v1/webhooks/{id}/deliveries` | Get delivery history (paginated) |

#### Create Webhook Response
```json
{
  "id": "uuid",
  "name": "Slack #ops-alerts",
  "url": "https://hooks.slack.com/services/...",
  "events": ["alert_created", "pii_detected"],
  "secret": "whsec_...",
  "is_active": true,
  "created_at": "2026-02-24T...",
  "warning": "Save the signing secret now. You will not be able to see it again."
}
```

The signing secret follows the `whsec_` prefix convention and is shown
**only once** at creation time — same pattern as API keys.

### 4. Ingest Pipeline Integration

Webhooks are dispatched from the inference ingest endpoint after alerts and
PII detection:

```
POST /api/v1/ingest
  1. Validate request
  2. PII redaction
  3. Data quality check
  4. Outlier detection
  5. Encrypt and store
  6. Create alerts (if needed)
  7. Audit log
  8. Redis pub/sub (real-time WebSocket)
  9. Webhook notifications (NEW)    <-- fire-and-forget
 10. Baseline initialization check
 11. Return response
```

Events dispatched:
- **Outlier detected** → `outlier_detected` + `alert_created`
- **Data quality issue** → `data_quality_issue` + `alert_created`
- **PII found** → `pii_detected`

The entire webhook dispatch is wrapped in a try/except to ensure webhook
failures never impact inference processing.

### 5. Frontend: Webhooks Management Page

New page at `/webhooks` with full CRUD:

- **Create form**: Name, URL, description, event type checkboxes
- **Webhook list**: Cards with status badges, delivery stats, event tags
- **Actions per webhook**: Test delivery, enable/disable toggle, expand
  delivery history, delete
- **Secret modal**: One-time display of signing secret with copy button
- **Delivery history**: Expandable panel showing recent delivery attempts
  with status, HTTP code, response time, and errors
- **Empty state**: Guided onboarding when no webhooks configured

The page follows the existing design system:
- Dark glassmorphism theme
- Framer Motion animations (staggered entrance, expand/collapse)
- Cyan/violet accent colors
- Responsive layout with mobile-friendly action buttons

### 6. Testing

**21 new unit tests** covering:
- Secret generation (prefix, length, uniqueness, URL-safety)
- HMAC signature computation (format, determinism, cross-verification)
- Event type validation
- Delivery logic (success, failure, timeout, HTTP status tracking)
- Auto-disable after max consecutive failures
- Failure counter reset on success
- Delivery audit record creation
- Payload security (no PHI)

Total test count: **185 tests (164 existing + 21 new), all passing**.

## Architecture Decisions

### Why HMAC-SHA256 for Signing?
Industry standard (GitHub, Stripe, Twilio). Receivers can verify payload
authenticity without exposing the secret. The `sha256=` prefix in the
signature allows future algorithm migration.

### Why Fire-and-Forget?
The inference pipeline is the critical path. Webhook delivery is valuable
but not essential — if Slack is down, the alert is still stored, still
visible in the dashboard, and still pushed via WebSocket. Making webhooks
blocking would add latency and create a dependency on external systems.

### Why Auto-Disable?
A dead webhook endpoint that gets hit on every inference wastes HTTP
connections and adds latency (timeout waits). Auto-disabling after 10
failures is a common pattern (Stripe uses 5, GitHub uses circuit breakers).
The tenant can re-enable via the API when their endpoint is fixed.

### Why Separate webhook_deliveries Table?
Individual delivery records provide:
1. **Debugging**: "Why didn't my Slack channel get notified?"
2. **Compliance**: Immutable proof of notification attempt
3. **Metrics**: Delivery success rates, response times
4. **Retention**: Can be cleaned up independently of webhook configs

## Files Created/Modified

### New Files
| File | Purpose |
|---|---|
| `app/models/webhook.py` | WebhookConfig + WebhookDelivery models |
| `app/services/webhooks/__init__.py` | Service package |
| `app/services/webhooks/service.py` | Delivery service with retry logic |
| `app/api/v1/webhooks.py` | CRUD + test + delivery history endpoints |
| `alembic/versions/a3f7c9d2e1b4_add_webhook_tables.py` | Migration |
| `frontend/src/pages/WebhooksPage.tsx` | Full webhook management UI |
| `tests/unit/test_webhook_service.py` | 21 unit tests |
| `docs/06_SESSION6_WEBHOOK_NOTIFICATIONS.md` | This documentation |

### Modified Files
| File | Change |
|---|---|
| `app/models/__init__.py` | Added WebhookConfig, WebhookDelivery exports |
| `app/api/v1/schemas.py` | Added 8 webhook Pydantic schemas |
| `app/api/v1/ingest.py` | Integrated webhook dispatch after alerts |
| `app/main.py` | Registered webhook router |
| `frontend/src/App.tsx` | Added /webhooks route |
| `frontend/src/components/Layout.tsx` | Added Webhooks nav item |
| `frontend/src/api/client.ts` | Added 6 webhook API functions |
| `frontend/src/types/api.ts` | Added 6 webhook TypeScript interfaces |

## Verification Checklist

- [x] Alembic migration runs cleanly (a3f7c9d2e1b4)
- [x] Backend compiles without errors
- [x] All 185 unit tests pass (164 existing + 21 new)
- [x] Frontend TypeScript check: zero errors
- [x] Frontend Vite build: succeeds in ~4s
- [x] API health check returns healthy after restart
- [x] Webhook CRUD endpoints tested via curl
- [x] Create returns signing secret with whsec_ prefix
- [x] List returns webhook with delivery tracking fields
- [x] Delete removes webhook and delivery history

## Database State

- Alembic revision: `a3f7c9d2e1b4` (head)
- New tables: `webhook_configs`, `webhook_deliveries`
- New indexes: `idx_webhook_tenant`, `idx_webhook_active`,
  `idx_delivery_webhook`, `idx_delivery_tenant`, `idx_delivery_time`
