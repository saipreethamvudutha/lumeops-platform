# Session 5: WebSocket Real-Time Updates + RBAC

## What We Built

This session added two major enterprise-grade capabilities to LumeOps:

1. **WebSocket Real-Time Event Streaming** - Live dashboard updates via Redis pub/sub
2. **RBAC (Role-Based Access Control)** - Scope-enforced permissions on every API endpoint

---

## Part 1: WebSocket Real-Time Updates

### The Problem

Before this change, the dashboard polled the REST API every 30-60 seconds to check for new data. This creates two issues:

- **Latency**: Up to 60 seconds before a new inference appears on the dashboard
- **Waste**: Most polls return the same data (nothing changed)

### The Solution: Redis Pub/Sub + WebSocket

When an inference is ingested, the server publishes an event to a tenant-scoped Redis channel. WebSocket connections subscribe to their tenant's channel and forward events to the browser instantly.

```
POST /ingest  -->  Store in DB  -->  Publish to Redis channel
                                          |
WebSocket clients <-- Subscribe to channel
```

### Architecture Decisions

**Why Redis Pub/Sub (not a dedicated message broker)?**

We already have Redis running for rate limiting. Redis pub/sub is:
- Zero additional infrastructure
- Ephemeral (fire-and-forget) which matches our use case
- Sub-millisecond latency
- Naturally supports multi-instance deployments (all API servers share the same Redis)

If a client disconnects and reconnects, they fetch fresh data from the REST API. There's no need for message persistence (which would justify Kafka or RabbitMQ).

**Why native WebSocket (not Socket.IO)?**

- FastAPI has first-class WebSocket support
- All modern browsers support the WebSocket API natively
- Socket.IO's polling fallback adds complexity we don't need
- Smaller frontend bundle (zero dependencies vs socket.io-client)

**Why query param authentication (not headers)?**

The browser's `WebSocket` constructor doesn't support custom headers. The standard workaround is passing the token as a query parameter:

```javascript
new WebSocket('ws://host/api/v1/ws?token=lum_sk_xxx')
```

This is safe because WebSocket connections upgrade from HTTPS, so the token is encrypted in transit.

### Files Created/Modified

#### `app/core/pubsub.py` (NEW)

The Redis pub/sub manager. Two classes:

- **`EventPublisher`** (singleton): Publishes events to tenant-scoped channels. Used by the ingest endpoint. Lazy-connects to Redis on first publish. Fails silently if Redis is unavailable (graceful degradation).

- **`EventSubscriber`** (per-connection): Subscribes to a tenant's channel and yields messages as an async generator. Each WebSocket connection creates its own subscriber (required by Redis - a subscribed connection can't execute other commands).

Channel naming: `lumeops:events:{tenant_id}` ensures tenant isolation.

#### `app/api/v1/ws.py` (NEW)

The WebSocket endpoint handler. Connection lifecycle:

1. Extract token from query params
2. Validate API key (same auth as REST, requires `read` scope)
3. Check connection limit (max 50 per tenant, prevents resource exhaustion)
4. Accept connection, send welcome message
5. Subscribe to tenant's Redis channel
6. Run two concurrent tasks:
   - Forward Redis events to WebSocket client
   - Listen for client pings (keepalive)
7. On disconnect: unsubscribe, decrement connection counter

Security features:
- Authentication on handshake (rejected before connection is established)
- Per-tenant connection limits prevent abuse
- Scope validation (requires `read` scope)
- No PHI in event payloads (only metadata)

#### `app/api/v1/ingest.py` (MODIFIED)

Added event publishing after audit logging (step 9 in the pipeline):

```python
await event_publisher.publish(
    tenant_id=str(tenant_id),
    event_type="inference_received",
    payload={
        "inference_id": inference_id,
        "model_name": model.model_name,
        "prediction": payload.prediction,
        "pii_redacted": redaction_result.report["total_pii_found"],
        "is_outlier": outlier_result.is_outlier,
        ...
    },
)
```

The payload intentionally contains only metadata - no encrypted features or PHI. This maintains HIPAA compliance even over the pub/sub channel.

Alert events are published separately so the frontend can display distinct alert banners.

#### `app/main.py` (MODIFIED)

- Added pub/sub publisher initialization in startup lifecycle
- Added publisher cleanup in shutdown lifecycle
- Registered WebSocket router under `/api/v1/ws`

#### `frontend/src/hooks/useWebSocket.ts` (NEW)

React hook managing the WebSocket connection:

- **Auto-reconnect with exponential backoff**: 1s, 2s, 4s, 8s, ... up to 30s. Prevents thundering herd when the server restarts.
- **Ping keepalive**: Sends ping every 25 seconds to detect dead connections
- **Event buffer**: Stores last 50 events in memory (newest first)
- **Auth error detection**: Stops reconnecting on 4001/4003 (auth failures)
- **Cleanup on unmount**: Closes connection and cancels timers

#### `frontend/src/pages/DashboardPage.tsx` (MODIFIED)

Added three UI elements:

1. **Connection status indicator** (top-right): Green pulsing dot = live, yellow = connecting, gray = offline
2. **Auto-refresh on events**: When a `inference_received` event arrives, stats and charts automatically refresh
3. **Live Event Feed panel** (bottom-right): Scrollable list of recent events with color-coded entries:
   - Blue = new inference
   - Amber = alert triggered
   - Green = connection established

### Testing Results

```
# WebSocket connection test
Welcome message: {"type": "connected", "data": {"tenant": "Test Hospital", ...}}
Pong response verified

# End-to-end real-time test
1. Connected WebSocket
2. Ingested inference via REST API
3. Received real-time event on WebSocket within milliseconds

# Security tests
No token: Rejected (HTTP 403)
Invalid token: Rejected (HTTP 403)
Non-prefixed token: Rejected (HTTP 403)
```

---

## Part 2: RBAC (Role-Based Access Control)

### The Problem

Before this change, API key scopes were defined (`ingest`, `read`, `audit`, `admin`) but only `admin` was actually enforced on 3 endpoints. A key with only `ingest` scope could freely read dashboard data, compliance reports, and audit trails.

### The Solution: Scope-Enforced Dependency

Created a combined dependency `require_scope_rate_limited(scope)` that checks both the required scope AND rate limits in a single function. Every endpoint now declares its required scope.

### Scope Mapping

| Scope    | What It Allows                                              |
|----------|-------------------------------------------------------------|
| `ingest` | POST /ingest (write inference data)                         |
| `read`   | GET endpoints: dashboard, inferences, models, encryption status, API key list |
| `audit`  | Compliance reports (HIPAA JSON/PDF) and audit trail access  |
| `admin`  | API key create/revoke, encryption rotation, model registration |

### Design Decisions

**Why not separate roles (admin, operator, viewer)?**

Scopes are more flexible than roles. A single API key can have any combination:
- `["ingest"]` - for automated ML pipelines that only write data
- `["read"]` - for dashboard viewers
- `["ingest", "read"]` - default for most users
- `["ingest", "read", "audit", "admin"]` - full admin access

This composability means you don't need predefined role hierarchies.

**Why enforce at the dependency level (not middleware)?**

FastAPI's dependency injection system naturally supports this. The `require_scope_rate_limited("read")` dependency:
1. Validates the API key (authentication)
2. Checks the required scope (authorization)
3. Enforces rate limits (protection)

All in a single `Depends()` call. The scope is declared directly on the endpoint, making it self-documenting.

### Files Modified

#### `app/middleware/rate_limit.py`

Added `require_scope_rate_limited(scope)` - a factory function that returns a FastAPI dependency combining scope checking with rate limiting:

```python
def require_scope_rate_limited(scope: str):
    async def _check(request, auth=Depends(get_current_tenant)):
        if scope not in auth.scopes:
            raise HTTPException(403, f"Missing scope: {scope}")
        # ... rate limit check ...
        return auth
    return _check
```

#### `app/middleware/auth.py`

Added `require_scopes(*scopes)` for endpoints requiring multiple scopes simultaneously.

#### All endpoint files

Replaced `Depends(check_rate_limit)` with `Depends(require_scope_rate_limited("scope"))`:

- `ingest.py`: `require_scope_rate_limited("ingest")`
- `inference_list.py`: `require_scope_rate_limited("read")`
- `dashboard.py`: `require_scope_rate_limited("read")`
- `timeseries.py`: `require_scope_rate_limited("read")`
- `models.py`: POST = `"admin"`, GET = `"read"`
- `api_keys.py`: POST/DELETE = `"admin"`, GET = `"read"`
- `compliance.py`: All endpoints = `"audit"`
- `encryption.py`: POST rotate = `"admin"`, GET status = `"read"`

Removed duplicate inline scope checks from `api_keys.py` and `encryption.py` (now handled by the dependency).

### Testing Results

```
=== INGEST-ONLY key ===
POST /ingest:          200 (allowed)
GET /dashboard/stats:  403 (blocked - needs 'read')
GET /inferences:       403 (blocked - needs 'read')
POST /apikeys:         403 (blocked - needs 'admin')
GET /reports/hipaa:    403 (blocked - needs 'audit')

=== READ-ONLY key ===
GET /dashboard/stats:  200 (allowed)
GET /inferences:       200 (allowed)
GET /models:           200 (allowed)
POST /ingest:          403 (blocked - needs 'ingest')
POST /encryption/rotate: 403 (blocked - needs 'admin')
GET /reports/hipaa:    403 (blocked - needs 'audit')

=== ADMIN key (all scopes) ===
GET /dashboard/stats:  200 (full access)
GET /reports/hipaa:    200 (full access)
GET /encryption/status: 200 (full access)
```

---

## Session Summary

### What Passed

- **164 unit tests**: All passing (4.62s)
- **Frontend build**: Zero TypeScript errors (3.42s)
- **WebSocket E2E**: Connection, auth, ping/pong, real-time events verified
- **RBAC E2E**: All scope combinations tested - correct allow/deny on every endpoint

### New Files

| File | Purpose |
|------|---------|
| `app/core/pubsub.py` | Redis pub/sub publisher + subscriber |
| `app/api/v1/ws.py` | WebSocket endpoint with tenant isolation |
| `frontend/src/hooks/useWebSocket.ts` | React hook with auto-reconnect |

### Modified Files

| File | Change |
|------|--------|
| `app/api/v1/ingest.py` | Added real-time event publishing |
| `app/main.py` | Added WebSocket route + pub/sub lifecycle |
| `app/middleware/rate_limit.py` | Added `require_scope_rate_limited()` |
| `app/middleware/auth.py` | Added `require_scopes()` |
| `app/api/v1/dashboard.py` | Scope enforcement (`read`) |
| `app/api/v1/timeseries.py` | Scope enforcement (`read`) |
| `app/api/v1/inference_list.py` | Scope enforcement (`read`) |
| `app/api/v1/compliance.py` | Scope enforcement (`audit`) |
| `app/api/v1/encryption.py` | Scope enforcement (`admin`/`read`) |
| `app/api/v1/models.py` | Scope enforcement (`admin`/`read`) |
| `app/api/v1/api_keys.py` | Scope enforcement (`admin`/`read`) |
| `frontend/src/pages/DashboardPage.tsx` | Live feed + connection status |

### Current Feature Status

| Feature | Status |
|---------|--------|
| PII Redaction Engine | Complete |
| Field-Level Encryption | Complete |
| Data Quality Monitoring | Complete |
| Outlier Detection | Complete |
| HIPAA Compliance Reports (JSON + PDF) | Complete |
| Audit Trail (DB + Elasticsearch) | Complete |
| Rate Limiting (Redis sliding window) | Complete |
| Encryption Key Rotation | Complete |
| Real-time Dashboard Charts | Complete |
| Inference Log Viewer | Complete |
| WebSocket Real-Time Updates | Complete |
| RBAC Scope Enforcement | Complete |
