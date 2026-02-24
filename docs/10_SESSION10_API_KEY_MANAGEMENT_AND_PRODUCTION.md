# Session 10: API Key Management UI, Compliance PDF Export & Production Deployment

## Overview

Session 10 completes the platform's operational readiness with three critical features:
self-service API key lifecycle management, a working compliance PDF export, and a
production-grade Docker deployment with Nginx reverse proxy and TLS termination.

This session delivers:
- **Full API Key Management UI** with create, revoke, copy, and scope selection
- **Compliance PDF Export** wired to the existing backend endpoint
- **Production Docker Compose** with Nginx reverse proxy, TLS, rate limiting
- **3 new API client functions** for key creation, revocation, and PDF download
- **3 new TypeScript interfaces** for API key create/revoke responses
- **52 new unit tests** covering schemas, validation, scope rules, and config integrity
- **Pre-existing TypeScript fixes** in ModelsPage (formatter types, unused imports)

## What We Built

### 1. API Key Management UI (Complete Redesign)

**File**: `frontend/src/pages/ApiKeysPage.tsx`

The API Keys page went from a read-only key list (117 lines) to a full management hub
(578 lines) with interactive key lifecycle operations.

#### Features

| Feature | Description |
|---------|-------------|
| **Create Key Modal** | Name input, scope selection grid, expiration presets (30d/90d/1y/2y) |
| **One-Time Key Display** | Green banner with copyable plaintext key + warning |
| **Revoke Confirmation** | Red modal with key name, "cannot be undone" warning |
| **Active/Revoked Sections** | Active keys shown first, revoked keys in collapsible section |
| **Status Badges** | Active (green), Expired (amber), Revoked (red) |
| **Copy to Clipboard** | Copy key ID with visual feedback (checkmark animation) |
| **Error Handling** | Red banner for failed operations with dismiss button |
| **Loading States** | Spinner on create/revoke buttons during API calls |

#### Scope Selection

The create modal shows all 4 RBAC scopes as selectable cards:

| Scope | Label | Description |
|-------|-------|-------------|
| `ingest` | Ingest | Submit inference data |
| `read` | Read | View dashboards and reports |
| `audit` | Audit | Access compliance reports |
| `admin` | Admin | Manage settings and keys |

Default selection: `ingest` + `read` (safe default for data pipeline keys).

#### Why a Modal for Key Creation?

- **Focus**: Key creation requires careful attention (name, scopes, expiry)
- **Security**: The one-time plaintext key display demands user focus
- **Consistency**: Matches the pattern used by AWS, GCP, and Stripe dashboards
- **Escape hatch**: Click outside or press Cancel to dismiss without creating

#### Why Separate Active/Revoked Sections?

- **Clarity**: Active keys are the primary concern for admins
- **Audit trail**: Revoked keys remain visible for compliance review
- **Space efficiency**: Revoked section is collapsed by default
- **HIPAA**: Retaining revocation records supports access control auditing

### 2. Compliance PDF Export

**File**: `frontend/src/pages/CompliancePage.tsx`

The "Export PDF" button was previously non-functional (no onClick handler). Now it:

1. Calls `GET /api/v1/reports/hipaa/pdf` with the report period
2. Receives the PDF as a blob (application/pdf)
3. Creates a temporary download link with timestamped filename
4. Triggers browser download: `lumeops-hipaa-compliance-2026-02-24.pdf`
5. Shows loading spinner during generation
6. Displays error banner if download fails

#### Why Blob Download Instead of Window.Open?

| Approach | Auth Support | Custom Filename | Error Handling |
|----------|-------------|-----------------|----------------|
| `window.open(url)` | No (no headers) | No | No |
| `<a href=url>` | No (no headers) | Limited | No |
| **Blob download** | Yes (via axios) | Yes | Yes |

The API requires Bearer token authentication, which rules out simple URL-based
approaches. The blob method sends proper auth headers and handles errors gracefully.

### 3. Production Docker Compose

**File**: `docker-compose.prod.yml`

A production-ready Docker Compose configuration with significant security hardening
over the development setup.

#### Development vs Production Comparison

| Feature | Development | Production |
|---------|------------|------------|
| **TLS** | None (HTTP only) | Nginx with TLS 1.2/1.3 |
| **Port binding** | All ports on 0.0.0.0 | DB/Redis/ES on 127.0.0.1 only |
| **Passwords** | Hardcoded defaults | Required via env vars |
| **Hot reload** | Yes (volume mounts) | No (baked into image) |
| **Workers** | 1 (with --reload) | 4 (configurable) |
| **Rate limiting** | Middleware only | Nginx + middleware (double layer) |
| **ES security** | Disabled | Enabled with password |
| **Redis auth** | None | Password required |
| **Resource limits** | None | CPU + memory limits per service |

#### Service Architecture

```
                    Internet
                       |
                       v
              ┌────────────────┐
              │     Nginx      │  :80 (redirect) + :443 (TLS)
              │  Reverse Proxy │  Rate limiting, security headers
              └───────┬────────┘
                      |
           ┌──────────┴──────────┐
           |                     |
    ┌──────v──────┐    ┌────────v────────┐
    │  Frontend   │    │   API Server    │
    │  (React)    │    │  (FastAPI x4)   │
    │  :80 int    │    │  :8000 internal │
    └─────────────┘    └───────┬─────────┘
                               |
              ┌────────────────┼────────────────┐
              |                |                |
       ┌──────v──────┐  ┌─────v─────┐  ┌──────v──────┐
       │ PostgreSQL  │  │   Redis   │  │Elasticsearch│
       │  :5432 lo   │  │ :6379 lo  │  │  :9200 lo   │
       └─────────────┘  └───────────┘  └─────────────┘
       (lo = localhost only, not exposed to host network)
```

#### Nginx Production Configuration

**File**: `nginx/prod.conf`

| Feature | Configuration |
|---------|--------------|
| **TLS** | TLS 1.2+ with ECDHE ciphers, OCSP stapling |
| **HSTS** | 2 years, includeSubDomains, preload |
| **CSP** | Strict Content-Security-Policy with wss: for WebSocket |
| **Rate limiting** | API: 30 req/s (burst 50), Login: 5 req/min |
| **HTTP/2** | Enabled for multiplexed connections |
| **WebSocket** | Proxy support for /ws/ endpoints |
| **Compression** | gzip level 6 for text, JS, CSS, JSON, SVG |
| **Request limits** | 10MB max body, 30s read timeout |

#### Why Nginx Instead of Direct TLS in Uvicorn?

| Factor | Uvicorn TLS | Nginx Reverse Proxy |
|--------|------------|---------------------|
| Performance | Python handles TLS | Native C handles TLS |
| Features | Basic TLS only | Rate limiting, caching, headers |
| Certificate renewal | App restart required | Reload only (0 downtime) |
| Static files | Through Python | Direct from disk (fast) |
| Security headers | In app code | In nginx config (simpler) |
| Load balancing | Not supported | Built-in upstream support |

Nginx is the industry standard for TLS termination in production. It handles
encryption at wire speed while the Python app focuses on business logic.

### 4. API Client Functions (3 New)

**File**: `frontend/src/api/client.ts`

| Function | Method | Endpoint | Description |
|----------|--------|----------|-------------|
| `createApiKey()` | POST | `/api/v1/apikeys` | Create key with name, scopes, expiry |
| `revokeApiKey()` | DELETE | `/api/v1/apikeys/{id}` | Soft-delete (revoke) a key |
| `downloadCompliancePdf()` | GET | `/api/v1/reports/hipaa/pdf` | Download PDF as blob |

### 5. TypeScript Interfaces (3 New)

**File**: `frontend/src/types/api.ts`

| Interface | Purpose |
|-----------|---------|
| `ApiKeyCreateRequest` | Request body for POST /apikeys |
| `ApiKeyCreateResponse` | Response with plaintext key + warning |
| `ApiKeyRevokeResponse` | Response with status, key_id, revoked_at |

### 6. Production Environment Template

**File**: `.env.production.template`

Documents all required environment variables for production deployment:
- Database credentials (DB_USER, DB_PASSWORD)
- Redis password (REDIS_PASSWORD)
- Elasticsearch password (ELASTIC_PASSWORD)
- Application secrets (SECRET_KEY, ENCRYPTION_KEY)
- Configuration (LOG_LEVEL, API_WORKERS, ALLOWED_ORIGINS)
- TLS certificate instructions (Let's Encrypt / certbot)

### 7. Pre-Existing TypeScript Fixes

**File**: `frontend/src/pages/ModelsPage.tsx`

Fixed 3 TypeScript errors that existed before Session 10:
- Removed unused `AnimatePresence` import
- Fixed `loading` prop removed from `ModelDetailView` (was unused)
- Fixed Recharts `formatter` types (`number` → `number | undefined`)

## Design Decisions & Learning Notes

### Why Self-Service Key Management?

Without frontend key management, admins must use curl or Postman to create/revoke
keys. This creates:
- **Operational friction**: Non-technical admins can't manage access
- **Security risk**: Plaintext keys sent over insecure channels (Slack, email)
- **Audit gaps**: No visibility into key lifecycle from the dashboard

Self-service key management is table stakes for any enterprise API platform.

### Why Show Plaintext Key Only Once?

This follows the security model used by AWS, GCP, Stripe, and GitHub:

1. **Hash-only storage**: Only the PBKDF2-SHA256 hash is stored in the database
2. **No retrieval**: There's no way to reconstruct the plaintext from the hash
3. **Reduced exposure**: The key exists in plaintext only during the HTTP response
4. **User responsibility**: The warning banner makes it clear the key won't be shown again

### Why Revoke Instead of Delete?

Revocation (soft-delete) is preferred over hard deletion because:
- **Audit trail**: HIPAA requires tracking all access control changes
- **Forensics**: Revoked keys help investigate security incidents
- **Rollback**: In theory, a revoked key could be reactivated (not implemented yet)
- **Compliance**: Demonstrates access was explicitly revoked, not just lost

### Why Four Expiration Presets?

| Preset | Use Case |
|--------|----------|
| 30 days | Temporary access for contractors or testing |
| 90 days | Quarterly rotation for production keys |
| 1 year | Standard production key lifecycle |
| 2 years | Long-lived keys for stable integrations |

These match common enterprise security policies. The backend allows 1-3650 days
for custom requirements.

### Why Rate Limiting at Both Nginx and Application Layers?

| Layer | Purpose | Granularity |
|-------|---------|-------------|
| **Nginx** | Connection-level protection | Per IP address |
| **Application** | Business-logic protection | Per API key/tenant |

Nginx rate limiting protects against brute-force attacks before they reach the
application. Application rate limiting provides per-tenant fairness and prevents
abuse of specific endpoints.

## Testing

### Unit Tests (52 New Tests)

**File**: `tests/unit/test_api_key_management.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestAPIKeyCreateRequest | 19 | Name validation, expiry bounds, scope validation, extra fields |
| TestAPIKeyCreateResponse | 3 | Valid response, custom warning, default warning |
| TestAPIKeyListItem | 3 | Active key, revoked key, null fields |
| TestAPIKeyListResponse | 3 | Empty list, single key, multiple keys |
| TestScopeValidation | 7 | All valid scopes, invalid scopes, case sensitivity, mixed |
| TestExpirationBoundaries | 8 | 1d, 30d, 90d, 1y, 2y, 10y, 10y+1 rejected, float handling |
| TestProductionConfig | 9 | File existence, TLS config, security headers, rate limiting, WebSocket, no-reload, secrets required |

### API Endpoint Verification

All API key endpoints verified via curl:

1. **GET /apikeys** - Listed 4 keys (3 active + 1 revoked)
2. **POST /apikeys** - Created "Session 10 Test Key" with ingest+read scopes, 90d expiry
3. **DELETE /apikeys/{id}** - Revoked the test key, confirmed `is_active=false`
4. **GET /reports/hipaa/pdf** - Downloaded 4.5KB PDF with proper content-disposition header

**Validation enforcement verified**:
- `name=""` -> 422 "String should have at least 1 character"
- `scopes=["superadmin"]` -> 422 "Invalid scope: superadmin"

### Full Suite Results

```
335 unit tests passed (5.64s)
+-- test_api_key_management.py     -- 52 tests (NEW)
+-- test_tenant_settings_schemas.py -- 39 tests
+-- test_performance_schemas.py     -- 37 tests
+-- test_alert_schemas.py           -- 22 tests
+-- test_data_quality.py            -- 13 tests
+-- test_fhir_classifier.py         -- 20 tests
+-- test_minimum_necessary.py       -- 15 tests
+-- test_redaction_engine.py        -- 44 tests
+-- test_security.py                -- 18 tests
+-- test_webhook_service.py         -- 21 tests
+-- ... (remaining tests)

TypeScript: 0 errors
Vite build: 4.18s clean
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/pages/ApiKeysPage.tsx` | REWRITTEN | Full key management UI (117 -> 578 lines) |
| `frontend/src/pages/CompliancePage.tsx` | MODIFIED | Wired Export PDF button + error handling |
| `frontend/src/pages/ModelsPage.tsx` | MODIFIED | Fixed 3 pre-existing TypeScript errors |
| `frontend/src/api/client.ts` | MODIFIED | +3 functions (createApiKey, revokeApiKey, downloadCompliancePdf) |
| `frontend/src/types/api.ts` | MODIFIED | +3 interfaces (ApiKeyCreateRequest/Response, ApiKeyRevokeResponse) |
| `docker-compose.prod.yml` | NEW | Production Docker Compose with Nginx + TLS |
| `nginx/prod.conf` | NEW | Nginx reverse proxy with TLS, rate limiting, security headers |
| `nginx/generate-dev-certs.sh` | NEW | Self-signed cert generation for testing |
| `.env.production.template` | NEW | Production environment variable template |
| `.gitignore` | MODIFIED | Added nginx/certs/ exclusion |
| `tests/unit/test_api_key_management.py` | NEW | 52 tests for key schemas + production config |
| `docs/10_SESSION10_API_KEY_MANAGEMENT_AND_PRODUCTION.md` | NEW | This documentation |

## Architecture After Session 10

```
                        Internet
                           |
                    ┌──────v──────┐
                    │    Nginx    │  TLS termination
                    │  (prod.conf)│  Rate limiting
                    └──────┬──────┘  Security headers
                           |
              ┌────────────┴────────────┐
              |                         |
┌─────────────v──────────────┐   ┌─────v──────────────────┐
│    Frontend (React + Vite)  │   │  FastAPI (v1) x4 workers │
├──────┬──────┬──────┬───────┤   ├──────────────────────────┤
│Dash  │Infer │Models│Alerts │   │ Ingest Pipeline          │
│board │Log   │      │       │   │ Performance Tracking     │
│      │      │      │       │   │ Ground Truth Pipeline    │
├──────┼──────┼──────┼───────┤   │ Alert Management         │
│Web   │Comp  │API   │Sett   │   │ Webhook Delivery         │
│hooks │liance│Keys  │ings   │   │ Tenant Settings          │
│      │+ PDF │(NEW) │       │   │ API Key Management       │
│      │export│      │       │   │ Dashboard + Stats        │
└──────┴──────┴──────┴───────┘   │ Compliance Reports + PDF │
                                 └───────────┬──────────────┘
                                             |
                            ┌────────────────┼────────────────┐
                            |                |                |
                       PostgreSQL         Redis        Elasticsearch
                       (data+config)     (pub/sub)      (audit)
                                            |
                                   ┌────────┴────────┐
                                   │  APScheduler     │
                                   │  - Retention     │
                                   │    cleanup @2AM  │
                                   └─────────────────┘
```

## Deployment Guide

### Development (existing)

```bash
docker compose up -d
cd frontend && npm run dev
```

### Production

1. **Generate or obtain TLS certificates:**
   ```bash
   # For testing (self-signed):
   ./nginx/generate-dev-certs.sh

   # For production (Let's Encrypt):
   certbot certonly --standalone -d lumeops.example.com
   cp /etc/letsencrypt/live/lumeops.example.com/fullchain.pem ./nginx/certs/
   cp /etc/letsencrypt/live/lumeops.example.com/privkey.pem ./nginx/certs/
   ```

2. **Configure environment:**
   ```bash
   cp .env.production.template .env.production
   # Edit .env.production with strong passwords and secrets
   ```

3. **Deploy:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d
   ```

4. **Verify:**
   ```bash
   curl -k https://localhost/health
   curl -k https://localhost/api/v1/dashboard/stats -H "Authorization: Bearer <key>"
   ```

## What's Next

The platform is now feature-complete for an MVP. Potential future sessions:

1. **Tenant Onboarding Flow** - Self-registration with email verification
2. **Horizontal Scaling** - Kubernetes manifests, Celery for heavy tasks
3. **Monitoring Stack** - Prometheus + Grafana for infrastructure metrics
4. **Audit Log Viewer** - Frontend page to browse Elasticsearch audit trail
5. **Role-Based UI** - Hide admin features for non-admin API keys
