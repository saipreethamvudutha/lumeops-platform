# Session 4: Frontend Dashboard + Charts + Rate Limiting + Key Rotation

## What We Built

This session added the user-facing layer and additional security features:

1. **React Frontend Dashboard** - Real-time monitoring UI with charts
2. **Inference Log Viewer** - Paginated table with compliance filters
3. **Dashboard API Endpoints** - Stats, time-series, quality trends
4. **Redis Sliding-Window Rate Limiting** - Per-key, plan-tiered
5. **Encryption Key Rotation** - Batch re-encryption with zero downtime

---

## Part 1: Frontend Dashboard

### Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19.2 | UI framework |
| TypeScript | strict | Type safety |
| Vite | 7.3 | Build tool (dev proxy on port 3000 → 8000) |
| Tailwind CSS | 4.2 | Utility-first styling |
| Recharts | 3.7 | Composable chart components |
| React Router DOM | 7.13 | Client-side routing |
| Axios | 1.13 | HTTP client with interceptors |
| Lucide React | 0.575 | SVG icon library |

### Architecture Decisions

**Why Vite (not CRA or Next.js)?**
- Lightning-fast HMR for development
- Native ESM support
- Simple proxy configuration for API forwarding
- No SSR complexity (this is an internal dashboard, not a public site)

**Why Recharts (not D3 or Chart.js)?**
- Composable React components (not imperative canvas API)
- Lightweight, excellent defaults
- Easy to customize with Tailwind-compatible colors
- Built-in responsive container support

**Why localStorage for API Key (not cookies)?**
- Simple for MVP dashboard
- API key is injected via Axios interceptor on every request
- WebSocket also reads from localStorage for `?token=` param
- No server-side session management needed

### Frontend Structure

```
frontend/src/
├── pages/
│   ├── DashboardPage.tsx        # Main monitoring dashboard
│   ├── InferencesPage.tsx       # Inference log viewer
│   ├── CompliancePage.tsx       # HIPAA compliance report
│   ├── ApiKeysPage.tsx          # API key management
│   └── SettingsPage.tsx         # API key configuration
├── components/
│   ├── Layout.tsx               # Sidebar navigation wrapper
│   ├── StatCard.tsx             # Reusable stat card
│   ├── SystemStatus.tsx         # Health check indicator
│   └── ComplianceChecklist.tsx  # Requirement checklist
├── hooks/
│   ├── useDashboard.ts          # Dashboard stats hook (30s refresh)
│   └── useWebSocket.ts          # Real-time event hook
├── api/
│   └── client.ts                # Axios service layer
├── types/
│   └── api.ts                   # TypeScript interfaces
├── App.tsx                      # Root router
└── main.tsx                     # Entry point
```

### Dashboard Page

Four stat cards across the top:
- **Inferences Today** (with all-time comparison)
- **PHI Redacted** (sensitive data protection count)
- **Data Quality Rate** (percentage with issue count)
- **Active Alerts** (severity indicator)

Two chart panels:
1. **Inference Volume** (Area Chart, 24-hour, hourly granularity)
   - Dual areas: total inferences + PHI redacted
   - Custom gradients for visual hierarchy
2. **Data Quality Rate** (Bar Chart, 7-day, daily granularity)
   - Daily quality percentages
   - Dynamic Y-axis scaling

System status panel and live event feed in right column.

### Inference Log Viewer

- Paginated table (25 records per page)
- Filters: time range, PII detection, outlier status
- Expandable detail panel with full metadata
- Color-coded sensitivity badges (CRITICAL=red, HIGH=orange, MODERATE=yellow, LOW=green)
- No decrypted features shown (HIPAA minimum necessary principle)

### API Service Layer

```typescript
// Axios interceptor auto-injects API key
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('lumeops_api_key');
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});
```

---

## Part 2: Dashboard API Endpoints

### `GET /api/v1/dashboard/stats`

Returns aggregated dashboard metrics for a tenant:

```json
{
  "inferences": { "today": 1250, "this_week": 8500, "this_month": 35000, "all_time": 150000 },
  "data_quality": { "quality_rate": 0.992, "issues_today": 10 },
  "predictions": { "outliers_today": 3 },
  "pii_protection": { "total_redacted_today": 45 },
  "alerts": { "active": 2, "recent": [...] },
  "system": { "status": "healthy", "version": "0.1.0" }
}
```

### `GET /api/v1/dashboard/timeseries`

Pre-aggregated time-series data using PostgreSQL `date_trunc()`:

**Why PostgreSQL (not TimescaleDB/InfluxDB)?**
- For SaaS scale (thousands of inferences/day per tenant), PostgreSQL with indexes is sufficient
- Adding a dedicated TSDB would increase operational complexity without current need
- Can migrate later if scale demands it

Supports periods: `24h` (hourly), `7d` (daily), `30d` (daily). Fills empty time slots with zeroes.

### `GET /api/v1/dashboard/quality-trend`

Daily quality rate over configurable window. Calculation: `(total - issues) / total * 100`.

### `GET /api/v1/inferences`

Paginated inference list with filters. Returns metadata only (no decrypted features). Supports filtering by:
- Time range (1-365 days)
- PII detection (has_pii)
- Outlier status (is_outlier)
- Quality issues (has_quality_issues)
- Sensitivity level (max_sensitivity)

---

## Part 3: Rate Limiting

### Architecture: Redis Sliding Window

**Why sliding window (not fixed window)?**
- Fixed window allows burst at window boundaries (e.g., 100 requests at 11:59 + 100 at 12:00)
- Sliding window smooths this by tracking actual request timestamps

**Implementation:**
```python
# Redis sorted set: score = timestamp, member = request ID
pipe.zremrangebyscore(key, 0, window_start)  # Remove expired
pipe.zadd(key, {str(now): now})              # Add current
pipe.zcard(key)                               # Count in window
pipe.expire(key, window_seconds + 1)          # Auto-cleanup
```

### Plan Tiers

| Plan          | Requests/Minute |
|---------------|-----------------|
| `starter`     | Lower tier      |
| `professional`| Mid tier        |
| `enterprise`  | High tier       |

### Graceful Degradation

If Redis is unavailable, requests are allowed through (fail-open). This prevents Redis outages from taking down the entire API. Rate limit headers are returned on 429 responses:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
```

---

## Part 4: Encryption Key Rotation

### The Problem

Even without a breach, periodic key rotation limits the exposure window of a compromised key. HIPAA and enterprise security policies require key rotation capabilities.

### Zero-Downtime Design

During rotation, the system handles both old and new key versions simultaneously:
- New writes use the new version
- Old reads use the version stored on the inference record
- Background re-encryption progressively migrates old records

### Batch Re-encryption

`POST /api/v1/encryption/rotate` processes records in configurable batches (default 500):

1. First call: Increment tenant's `encryption_key_version`, start re-encryption
2. Subsequent calls: Continue re-encrypting remaining records
3. Final call: Returns `migration_complete: true`

Each inference record tracks its `encryption_key_version`, making the process idempotent and resumable.

### Status Endpoint

`GET /api/v1/encryption/status` returns:
- Current key version and rotation count
- Records by version (shows migration progress)
- Encryption method: Fernet (AES-128-CBC + HMAC-SHA256)
- Key derivation: PBKDF2-SHA256 (480,000 iterations)

---

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `app/api/v1/dashboard.py` | Dashboard stats endpoint |
| `app/api/v1/timeseries.py` | Time-series data (2 endpoints) |
| `app/api/v1/inference_list.py` | Inference log viewer (list + detail) |
| `app/api/v1/encryption.py` | Key rotation + status endpoints |
| `app/middleware/rate_limit.py` | Redis sliding-window rate limiter |
| `frontend/src/pages/DashboardPage.tsx` | Main dashboard with charts |
| `frontend/src/pages/InferencesPage.tsx` | Inference log viewer |
| `frontend/src/pages/CompliancePage.tsx` | HIPAA compliance report |
| `frontend/src/pages/ApiKeysPage.tsx` | API key management |
| `frontend/src/pages/SettingsPage.tsx` | Settings page |
| `frontend/src/components/Layout.tsx` | Sidebar navigation |
| `frontend/src/components/StatCard.tsx` | Reusable stat card |
| `frontend/src/components/SystemStatus.tsx` | Health check |
| `frontend/src/components/ComplianceChecklist.tsx` | Compliance checklist |
| `frontend/src/hooks/useDashboard.ts` | Dashboard stats hook |
| `frontend/src/api/client.ts` | Axios API service |
| `frontend/src/types/api.ts` | TypeScript interfaces |

### Modified Files

| File | Change |
|------|--------|
| `app/main.py` | Added dashboard, timeseries, inference, encryption routes |
| `app/api/v1/schemas.py` | Added dashboard and compliance Pydantic models |

---

## Session Summary

### What Passed

- Frontend builds with zero TypeScript errors
- All API endpoints return correct data shapes
- Rate limiting correctly enforces plan tiers
- Key rotation processes batches and resumes correctly
- Charts render with real data from the API

### Current Feature Status After Session 4

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
