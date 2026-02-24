# LumeOps Project Log
## A Living Record of Every Decision, Lesson, and Build Step

---

## What This Document Is

This is not a README. This is the **engineering journal** for LumeOps. Every
architectural decision, every security choice, every "why did we do it this
way?" is recorded here. If you're reading this six months from now wondering
why something works the way it does, this document has the answer.

---

## Session 1: Project Genesis

**Date:** 2026-02-23
**Goal:** Build LumeOps from scratch with enterprise-grade security

### What We Built

The initial skeleton of LumeOps -- FastAPI backend, database models,
PII redaction engine, authentication, monitoring, audit trail, compliance
reporting, and Docker infrastructure.

### Critical Correction Made

The initial build focused too narrowly on PII redaction. LumeOps handles
**all healthcare data**, not just personally identifiable information:

| Data Category | Examples | Why It Matters |
|---|---|---|
| PHI (Protected Health Information) | Diagnoses, lab results, medications | HIPAA-regulated, breach = federal violation |
| PII (Personally Identifiable Information) | SSN, name, DOB, address | Identity theft risk, HIPAA + state laws |
| EMR/EHR Data | Full medical records, clinical notes | Most sensitive data in healthcare |
| Clinical Decision Data | AI recommendations, risk scores | FDA-regulated if diagnostic |
| Insurance/Claims Data | CPT codes, claim amounts, denials | CMS-regulated, DOJ scrutiny |
| Operational Data | Bed counts, staffing, scheduling | Less sensitive but still protected |

### Lesson Learned

> **Never reduce a healthcare platform to "just PII." The entire data
> ecosystem is interconnected and regulated. A patient's lab result is
> not PII, but it is PHI. A diagnosis code is not a name, but it can
> identify a patient when combined with other data. Think in terms of
> data sensitivity levels, not categories.**

---

## Architecture Decisions Record (ADR)

### ADR-001: Why FastAPI (not Django, Flask, or Go)

**Decision:** Use FastAPI as the web framework.

**Why:**
- Async by default (critical for handling concurrent hospital data streams)
- Pydantic validation built-in (every byte of healthcare data must be validated)
- OpenAPI docs auto-generated (hospitals need API documentation for integration)
- Type hints throughout (catches bugs before they reach production)
- Performance close to Go/Node for I/O-bound work (which our API is)

**What we considered:**
- Django: Too opinionated, ORM doesn't support async well, heavier than needed
- Flask: No async, no built-in validation, would need many extensions
- Go: Faster raw performance, but slower development speed for a solo builder

**Trade-off accepted:** Python is slower than Go for CPU-bound work, but our
bottleneck is I/O (database, encryption, network), not CPU.

### ADR-002: Why PostgreSQL (not MongoDB, DynamoDB)

**Decision:** PostgreSQL as primary database.

**Why:**
- ACID transactions (healthcare data cannot be partially written)
- JSONB columns (flexible schema for varying inference formats)
- Encryption extensions (pgcrypto for additional protection)
- Multi-tenant proven at scale (row-level security available)
- Audit requirements need relational integrity
- 7-year data retention is a hard requirement -- Postgres handles this well

**What we considered:**
- MongoDB: Faster for unstructured data, but weaker consistency guarantees.
  In healthcare, "eventually consistent" is not acceptable for audit trails.
- DynamoDB: Good for scale, but expensive for 7-year retention and complex
  queries. Compliance reporting requires JOINs.

### ADR-003: Why Rule-Based Redaction (not ML)

**Decision:** Use regex patterns and field-name heuristics for PHI detection.

**Why:**
- **Deterministic:** Same input always produces same output. Regulators love this.
- **Auditable:** "We mask SSNs with pattern \d{3}-\d{2}-\d{4}" is explainable.
- **No false negatives from model drift:** ML models degrade over time. Regex doesn't.
- **No training data needed:** ML-based NER needs labeled healthcare data (expensive, slow).
- **Performance:** Regex is microseconds. ML inference adds 10-100ms per field.

**What we considered:**
- SpaCy NER: Better at catching names in free text, but non-deterministic,
  needs GPU, and harder to explain to auditors.
- AWS Comprehend Medical: Good but adds external dependency, costs per call,
  and data leaves our boundary (PHI going to AWS API = compliance question).

**Future plan:** Phase 2 may add ML-based detection as a SECOND layer on top
of rule-based, never as a replacement.

### ADR-004: Why Field-Level Encryption (not just TLS + disk encryption)

**Decision:** Encrypt sensitive fields individually using Fernet (AES), on top
of TLS in transit and disk encryption at rest.

**Why this is defense-in-depth:**

```
Layer 1: TLS 1.3 in transit (network → API)
Layer 2: PHI redaction before storage (API → database)
Layer 3: Field-level Fernet encryption (application → database)
Layer 4: PostgreSQL disk encryption (database → disk)
Layer 5: AWS EBS/S3 encryption (disk → storage)
```

If any single layer fails, the others still protect the data.

**Why Fernet specifically:**
- Built on AES-128-CBC + HMAC-SHA256 (authenticated encryption)
- Includes timestamp (can detect replay attacks)
- Python cryptography library (well-audited, FIPS-compatible)
- Simple API (less chance of implementation bugs)

### ADR-005: Why Multi-Tenant at Application Layer (not Database Level)

**Decision:** Enforce tenant isolation in application code, not PostgreSQL
row-level security (RLS).

**Why:**
- Every query includes `WHERE tenant_id = X` (explicit, auditable)
- Easier to reason about (developer sees the filter, can't miss it)
- Portable (not tied to PostgreSQL-specific features)
- Testable (unit tests can verify isolation)

**Risk accepted:** A bug in application code could leak cross-tenant data.
Mitigated by: code review, integration tests that verify isolation, and
the authentication middleware always sets tenant_id from the API key.

---

## Security Model

### The Data Trust Boundary

```
UNTRUSTED ZONE                    TRUST BOUNDARY              TRUSTED ZONE
(Hospital's network)              (LumeOps API)               (LumeOps storage)

  Hospital AI Model                                           PostgreSQL
  sends inference     ──────►  [Validate]                     (encrypted)
  with PHI                     [Authenticate]
                               [Rate Limit]                   Redis
                               [Classify Data]                (ephemeral only)
                               [Redact PHI]
                               [Check Quality]                Audit Log
                               [Detect Outliers]              (immutable)
                               [Encrypt]
                               [Store]
                               [Audit Log]     ──────►        All data is:
                               [Respond]                      - PHI-free (redacted)
                                                              - Encrypted (Fernet)
                                                              - Audited (every access)
                                                              - Isolated (per-tenant)
```

### What Never Crosses the Trust Boundary Outward

- Raw PHI (always redacted before any response)
- Encryption keys (never in logs, never in responses)
- Other tenants' data (isolation enforced at every layer)
- Internal error details (generic error messages only)

---

## Session 2: Full Healthcare Data Protection

**Date:** 2026-02-23 (continued)
**Goal:** Expand beyond PII to handle ALL healthcare data types

### What We Built

After the critical correction from Session 1, we completely redesigned the
data protection engine to handle the full spectrum of healthcare data:

| Component | What Changed | Why |
|---|---|---|
| Classification Engine | NEW: 4-level sensitivity classification | Different data types need different protection |
| Redaction Engine | REWRITTEN: Three-pass detection | Need to distinguish CRITICAL (redact) from HIGH (encrypt) |
| FHIR Classifier | NEW: HL7 FHIR resource type detection | Hospitals send FHIR-formatted data |
| Per-Tenant Encryption | NEW: Each tenant gets unique encryption key | Limits blast radius of key compromise |
| Minimum Necessary Filter | NEW: Purpose-based data filtering | HIPAA requires minimum necessary access |
| Database Models | UPDATED: Classification metadata storage | Need to track what data types flow through the system |
| Test Suite | EXPANDED: 100+ tests covering clinical scenarios | Every HIPAA identifier and clinical data type tested |

### Architecture Decisions (continued)

### ADR-006: Why Four Sensitivity Levels (not just "sensitive" / "not sensitive")

**Decision:** Classify data into CRITICAL/HIGH/MODERATE/LOW levels.

**Why:**
- **CRITICAL (Level 4):** Direct identifiers that MUST be redacted. SSN, name,
  MRN, email. No legitimate reason to store these for AI monitoring.
- **HIGH (Level 3):** Clinical data that must be ENCRYPTED but preserved.
  Diagnoses, lab results, medications. We need these for monitoring but must
  protect them heavily.
- **MODERATE (Level 2):** Operational data with standard encryption. Billing
  codes, administrative metadata. Protected but not as tightly controlled.
- **LOW (Level 1):** System/model data. Predictions, confidence scores,
  timestamps. Standard handling.

**What we considered:**
- Binary classification (sensitive/not): Too crude. A diagnosis code and an SSN
  both need protection, but they need DIFFERENT protection.
- Six levels: Over-engineering. Four levels map cleanly to four protection actions
  (redact/encrypt-strict/encrypt-standard/standard).

### ADR-007: Why Per-Tenant Encryption Key Isolation

**Decision:** Derive a unique Fernet key for each tenant using PBKDF2 with
tenant_id as the salt.

**Why:**
- If one tenant's key is compromised, other tenants are NOT affected
- Each tenant's data is cryptographically isolated in the database
- Key rotation can be done per-tenant without affecting others
- Defense-in-depth: even if application-level tenant isolation fails,
  encryption keys prevent cross-tenant data access

**Key hierarchy:**
```
Master Key (env variable)
  ├── System Key (salt: "lumeops-field-encryption-v1")
  │     └── Used for non-tenant-specific data
  ├── Tenant A Key (salt: "lumeops-tenant-{tenant_a_id}-v1")
  │     └── Used for all of Tenant A's inference data
  └── Tenant B Key (salt: "lumeops-tenant-{tenant_b_id}-v1")
        └── Used for all of Tenant B's inference data
```

**Performance note:** PBKDF2 with 480k iterations is expensive (~100ms per derivation).
We use `@lru_cache(maxsize=128)` to cache derived keys so the cost is paid once per
tenant per application lifetime.

### ADR-008: Why FHIR Awareness (not just generic field detection)

**Decision:** Add HL7 FHIR resource type detection alongside generic field classification.

**Why:**
- Many hospital AI systems use FHIR conventions in their data
- FHIR resource types map directly to sensitivity levels
  (Patient = CRITICAL, Observation = HIGH, Organization = LOW)
- FHIR awareness enables better compliance reporting
  ("we processed 50,000 Observation resources last month")
- It's a recognition layer, not a requirement -- non-FHIR data
  still works fine through the generic classifier

**Detection methods (in priority order):**
1. Explicit `resourceType` field (formal FHIR)
2. Field name hints (e.g., `loinc_code` suggests Observation)
3. Structure patterns (e.g., code + value + status = Observation)

### ADR-009: Why HIPAA Minimum Necessary at Application Layer

**Decision:** Implement purpose-based data filtering that restricts what
data each API consumer can see.

**Why:**
- HIPAA 45 CFR 164.502(b) REQUIRES minimum necessary access
- A dashboard showing model performance doesn't need diagnosis codes
- Compliance reports need metadata, not raw clinical data
- Audit views need more access but still no raw identifiers

**Purpose profiles:**
```
DASHBOARD:        prediction, confidence, system metadata
MODEL_MONITORING: + vitals, lab results (for data quality)
DATA_QUALITY:     + diagnoses, medications (for accuracy checks)
COMPLIANCE:       + billing, insurance metadata
AUDIT:            Everything except direct identifiers
STORAGE:          All data after redaction (most permissive)
```

### Lessons Learned in Session 2

> **Lesson 1: Classification must come before protection.**
> You can't protect data correctly if you don't know what it is.
> The classification engine runs first, then the redaction engine
> and encryption layer know exactly what to do with each field.

> **Lesson 2: "Encrypt everything" is not a strategy.**
> Different data types need different treatment. Encrypting an SSN
> is pointless -- it should be removed entirely. Encrypting a
> diagnosis code makes sense -- we need it but must protect it.
> Encrypting a prediction score is unnecessary overhead.

> **Lesson 3: Per-tenant isolation is non-negotiable in healthcare.**
> A single encryption key for all tenants means a single point of
> failure for ALL patients across ALL hospitals. The key hierarchy
> limits the blast radius to one organization.

---

---

## Session 3: Docker Integration, CI/CD, and Frontend Dashboard

**Date:** 2026-02-24
**Goal:** Get the full stack running, add CI/CD, build the frontend dashboard

### What We Built

After Session 2 ended with a system crash (Docker + app unresponsive, required
Mac restart), Session 3 focused on recovery, Docker integration, and the
frontend dashboard.

### Infrastructure Fixes

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Dockerfile build failure | `COPY ... 2>/dev/null \|\| true` is invalid Docker syntax | Replaced with standard `COPY` instructions |
| 330MB Docker build context | No `.dockerignore`, `.venv/` included | Created `.dockerignore` excluding venv, cache, docs |
| Port 5432 conflict | Local PostgreSQL already running | Remapped Docker postgres to port 5434 |
| `version` deprecation warning | docker-compose.yml used obsolete `version: "3.8"` | Removed the version key |
| Seed script not in container | `scripts/` not copied in Dockerfile | Used `docker compose cp` to inject, then `exec` to run |

### Docker Compose Stack (4 Services)

```
lumeops-postgres-1        postgres:16-alpine                  Healthy   5434:5432
lumeops-redis-1           redis:7-alpine                      Healthy   6379:6379
lumeops-elasticsearch-1   elasticsearch:8.13.0                Healthy   9200:9200
lumeops-api-1             lumeops-api (custom)                Healthy   8000:8000
```

All services healthy with dependency-based startup ordering
(API waits for postgres + redis + elasticsearch to be healthy).

### API Endpoint Verification

All endpoints tested and working:

```
GET  /health               -> {"status": "alive"}
GET  /ready                -> {"status": "ready", "services": {"database": "ok", "redis": "ok"}}
POST /api/v1/ingest        -> PII detected and redacted, inference stored
GET  /api/v1/dashboard/stats -> Real-time metrics (inferences, PHI redacted, quality)
GET  /api/v1/reports/hipaa  -> Full compliance report with checklist (all PASS)
GET  /api/v1/apikeys       -> API key listing with scopes and expiration
```

Performance: ~12-17ms per inference ingestion (including PII redaction + encryption + audit logging).

### CI/CD Pipeline (GitHub Actions)

Created `.github/workflows/ci.yml` with 4 jobs:

1. **Lint & Type Check** - Ruff linter, Ruff formatter, Bandit security scan
2. **Tests** - Unit tests with PostgreSQL + Redis service containers, coverage report
3. **Security Scan** - Bandit analysis with JSON report artifact
4. **Docker Build** - Image build + smoke test (depends on lint + test passing)

### Frontend Dashboard (React + TypeScript + Tailwind)

Built a complete single-page application:

**Tech Stack:**
- React 19 + TypeScript (Vite bundler)
- Tailwind CSS v4 (via @tailwindcss/vite plugin)
- Recharts (charts and data visualization)
- React Router v7 (client-side routing)
- Axios (API client with auth interceptor)
- Lucide React (icons)

**Pages:**
1. **Dashboard** - Stat cards (inferences, PHI redacted, data quality, alerts),
   24-hour inference volume chart, 7-day quality bar chart, system status panel
2. **Compliance** - HIPAA compliance status banner, executive summary cards,
   data protection details, access controls, full compliance checklist
3. **API Keys** - List active keys with scopes, expiration, last used
4. **Settings** - API key configuration (stored in localStorage), about info

**Architecture Decisions:**

### ADR-010: Why Vite (not Create React App)

**Decision:** Use Vite as the frontend build tool.

**Why:**
- CRA is deprecated and unmaintained
- Vite is 10-100x faster for development (native ESM, no bundling in dev)
- First-class TypeScript support
- Tailwind CSS v4 plugin support
- Built-in proxy for API development (avoids CORS issues)
- Production builds use Rollup (optimized, tree-shaken)

### ADR-011: Why Tailwind CSS (not Material UI, Ant Design)

**Decision:** Use Tailwind CSS for styling.

**Why:**
- No component library lock-in (we own every pixel)
- Smaller bundle size (only generates used CSS)
- Consistent design language across the entire dashboard
- Healthcare dashboards need custom, professional appearance
- Enterprise customers judge products by visual quality
- Faster to iterate than CSS-in-JS or component libraries

### ADR-012: Why API Key in localStorage (for MVP)

**Decision:** Store the API key in browser localStorage for dashboard auth.

**Why (MVP trade-off):**
- Simple implementation (no session management needed)
- Dashboard is an internal tool (not public-facing)
- API key is already the auth mechanism for the backend
- Phase 2 will add proper session-based auth with JWT + refresh tokens

**Risk accepted:** localStorage is vulnerable to XSS. Mitigated by:
- CSP headers prevent script injection
- No user-generated content on the dashboard
- API key scoped to read-only operations from dashboard

### Test Results

```
163 unit tests: ALL PASSING
- test_data_quality.py: 13 tests
- test_fhir_classifier.py: 27 tests
- test_minimum_necessary.py: 19 tests
- test_redaction_engine.py: 85 tests
- test_security.py: 19 tests

Integration test suite: WRITTEN (tests/integration/test_api_flow.py)
- Health endpoint tests
- Full ingestion flow with PII redaction
- Dashboard stats verification
- Compliance report generation
- API key management
- Security header verification
```

### Lessons Learned in Session 3

> **Lesson 4: Docker COPY does not support shell syntax.**
> The `COPY file 2>/dev/null || true` pattern is a shell construct.
> Docker's COPY instruction is not a shell command. If you need
> conditional copying, use multi-stage builds or ensure the source exists.

> **Lesson 5: Always create a .dockerignore.**
> Without it, Docker sends the entire project directory as build context.
> Our `.venv/` was 330MB. With `.dockerignore`, context dropped to ~6KB.
> This is a 50,000x reduction in build context size.

> **Lesson 6: Port conflicts are environment-specific.**
> Local PostgreSQL installations often claim port 5432.
> Always map Docker ports to non-default host ports in development.
> Internal Docker networking (container-to-container) is unaffected.

---

## Session 4: Production Hardening — Migrations, Elasticsearch, PDF Export

**Date:** 2026-02-24
**Goal:** Production-grade migrations, Elasticsearch audit integration, PDF reports, frontend Docker

### What We Built

| Component | Status | What It Does |
|---|---|---|
| Alembic Initial Migration | COMPLETE | Full DDL for all 8 tables with indexes, JSONB columns, FK constraints |
| Frontend Dockerfile | COMPLETE | Multi-stage build: Node 20 → nginx 1.27 with security headers |
| Frontend nginx.conf | COMPLETE | SPA routing, API proxy, OWASP security headers, gzip, cache control |
| Frontend in docker-compose | COMPLETE | `frontend` service on port 3000, depends on API |
| Elasticsearch Audit Integration | COMPLETE | Dual-write audit service: PostgreSQL (primary) + ES (secondary) |
| ES Index Lifecycle Management | COMPLETE | Hot → Warm → Cold → Delete after 7 years (HIPAA retention) |
| PDF Compliance Report | COMPLETE | ReportLab-generated PDF with executive summary, checklist, evidence |
| End-to-End Data Flow Test | COMPLETE | 8-step integration test covering full pipeline |

### Alembic Migration

The autogenerate command produced an empty migration because tables already existed
(created by `init_db` during seeding). We wrote the migration manually to capture
the complete schema — 8 tables, 30+ indexes, JSONB columns, foreign keys.

**Key command:** `alembic stamp head` marks the existing database as "at this revision"
without running CREATE TABLE statements. Fresh deployments use `alembic upgrade head`.

### Elasticsearch Dual-Write Architecture

```
Inference Request
      │
      ├── PostgreSQL (primary, always)
      │     └── audit_logs table (indexed, SQL-queryable)
      │
      └── Elasticsearch (secondary, best-effort)
            └── lumeops-audit-000001 index
                  ├── Write alias: lumeops-audit-write
                  ├── Read alias: lumeops-audit-read
                  └── ILM Policy: hot(30d) → warm(90d) → cold(365d) → delete(2555d/7yr)
```

**Design principle:** ES failures never break requests. If Elasticsearch is down,
audit events still land in PostgreSQL. ES is for fast search; Postgres is for durability.

**On startup, the app automatically:**
1. Connects to Elasticsearch
2. Creates/updates the ILM policy (7-year retention)
3. Creates/updates the index template (typed mappings)
4. Creates the initial index with write + read aliases

### Frontend Production Build

Multi-stage Docker build:
```
Stage 1: node:20-alpine
  - npm ci (exact lockfile versions)
  - npm run build (TypeScript → optimized JS/CSS)

Stage 2: nginx:1.27-alpine
  - Copies dist/ from Stage 1
  - Custom nginx.conf with:
    - OWASP security headers (CSP, HSTS, X-Frame-Options, etc.)
    - SPA fallback routing (try_files → index.html)
    - API reverse proxy (/api/ → backend:8000)
    - Static asset caching (1 year, immutable — Vite content hashes)
    - Blocked sensitive paths (.env, .git)
  - Non-root user (uid 1001)
  - Health check
```

### PDF Compliance Report

New endpoint: `GET /api/v1/reports/hipaa/pdf`

Generates a professional 2-page PDF using ReportLab:
- LumeOps header with report metadata
- Executive summary (compliance status, inference count, PII redacted)
- Personal information safeguarding table (encryption, redaction)
- Access control summary
- Audit logging statistics
- 8-item HIPAA compliance checklist with PASS/FAIL indicators
- Color-coded status (green for PASS, red for FAIL)
- Legal disclaimer footer

The JSON and PDF endpoints share the same data-building function (`_build_hipaa_report`)
to ensure consistency.

### Architecture Decisions (continued)

### ADR-013: Why Dual-Write to PostgreSQL + Elasticsearch (not ES-only)

**Decision:** Write audit events to both PostgreSQL and Elasticsearch.

**Why:**
- PostgreSQL is ACID-compliant; Elasticsearch is not. Audit trail integrity matters.
- ES is for search performance (full-text, aggregations, time-series)
- PG is for durability (transactions, foreign keys, backup/restore)
- If ES goes down, we lose search but not data
- If PG goes down, we lose writes (app is down anyway — PG is primary DB)

**ES write pattern:** Fire-and-forget with error logging. Never blocks the request.

### ADR-014: Why ILM for 7-Year Retention (not manual index management)

**Decision:** Use Elasticsearch Index Lifecycle Management for automated retention.

**Why:**
- HIPAA requires 7-year audit log retention
- ILM automatically manages index lifecycle (rollover, merge, delete)
- Hot phase: new data, fast writes (30 days or 10GB)
- Warm phase: read-mostly, force-merged (90 days)
- Cold phase: read-only, infrequent access (1 year)
- Delete phase: safely removed after 7 years (2555 days)
- No cron jobs, no manual intervention

### ADR-015: Why ReportLab for PDF (not wkhtmltopdf, Puppeteer, or WeasyPrint)

**Decision:** Use ReportLab for PDF generation.

**Why:**
- Pure Python (no browser/WebKit dependency, no system packages)
- Works in Alpine Docker containers without additional setup
- Professional output with precise layout control
- Already in dependencies (`reportlab>=4.1.0`)
- No HTML→PDF conversion step (direct PDF construction)
- Lightweight (~3MB, no headless browser overhead)

**What we considered:**
- wkhtmltopdf: Requires Qt/WebKit system libraries (huge Docker image)
- Puppeteer/Playwright: Node.js dependency, headless Chrome (800MB+)
- WeasyPrint: Requires cairo/pango system libraries

### Docker Compose Stack (5 Services)

```
lumeops-postgres-1        postgres:16-alpine                  Healthy   5434:5432
lumeops-redis-1           redis:7-alpine                      Healthy   6379:6379
lumeops-elasticsearch-1   elasticsearch:8.13.0                Healthy   9200:9200
lumeops-api-1             lumeops-api (custom)                Healthy   8000:8000
lumeops-frontend-1        lumeops-frontend (custom)           Healthy   3000:80
```

### Test Results

```
163 unit tests: ALL PASSING (3.62s)

New E2E tests (tests/integration/test_e2e_flow.py):
  1. Ingest inference with PHI → 3+ items redacted
  2. Ingest clean inference → 0 redactions
  3. Dashboard reflects both inferences
  4. Audit trail contains inference + redaction events
  5. Compliance report JSON → COMPLIANT, correct counts
  6. Compliance report PDF → valid %PDF- header, correct Content-Type
  7. Security headers on all responses
  8. Unauthorized access blocked on all protected endpoints
```

### Verified Elasticsearch Integration

```bash
# Audit events dual-written to ES:
curl -s 'http://localhost:9200/lumeops-audit-read/_search' | python3 -m json.tool

# Result: 2 events per inference with PHI:
#   1. INFERENCE_RECEIVED (with ip_address, model_id, pii_types)
#   2. PII_DETECTED_AND_REDACTED (with pii_types, total_redacted)
```

### Lessons Learned in Session 4

> **Lesson 7: Alembic autogenerate compares models to the database.**
> If tables already exist (created by `init_db`), autogenerate sees no difference
> and generates empty migrations. Use `alembic stamp head` to sync the revision
> tracker with an existing database. Write the initial migration manually.

> **Lesson 8: Elasticsearch writes should never block the happy path.**
> Healthcare data ingestion must be fast and reliable. ES is a secondary index
> for search and compliance. If ES is slow or down, the inference still gets
> processed and stored in PostgreSQL.

> **Lesson 9: Security headers belong on BOTH backend and frontend.**
> The API adds headers via FastAPI middleware. The frontend nginx config adds
> them too. This is defense-in-depth — if one layer is bypassed (e.g., direct
> API access), the other still protects.

---

## Session 11: Audit Log Viewer & Trail Management

**Date:** 2026-02-24
**Goal:** Make audit trail data accessible through a full-featured viewer UI

### What We Built

| Component | Status | What It Does |
|---|---|---|
| Enhanced Audit Trail API | COMPLETE | Added resource_type, status, multi-field search filters |
| Stats Endpoint | COMPLETE | `GET /audit-trail/stats` — event breakdown by action and resource |
| CSV Export Endpoint | COMPLETE | `GET /audit-trail/export` — downloadable CSV, 10,000 row limit |
| AuditLogsPage | COMPLETE | Full page with stats cards, filter bar, paginated table, detail modal |
| API Client Functions | COMPLETE | 3 new functions: fetchAuditTrail, fetchAuditTrailStats, downloadAuditTrailCsv |
| TypeScript Interfaces | COMPLETE | AuditLogEntry, AuditTrailResponse, AuditTrailStats |
| Unit Tests | COMPLETE | 42 new tests across 7 test classes |
| Navigation | COMPLETE | Sidebar link with ScrollText icon |

### Architecture Decisions

### ADR-020: Why Multi-Field OR Search (not single-field ILIKE)

**Decision:** The `search` parameter queries action, resource_id, resource_type,
and ip_address simultaneously using OR.

**Why:**
- Audit investigation workflows are exploratory — users type a keyword and expect
  matches anywhere relevant
- Searching "192.168" should find events by IP address
- Searching "webhook" should find WEBHOOK_CREATED and WEBHOOK_DELETED actions
- AND logic would require exact matches across all fields, defeating the purpose
- ILIKE (not full-text search) because audit field values are short, structured strings

### ADR-021: Why PostgreSQL for the Audit Viewer (not Elasticsearch)

**Decision:** The audit log viewer queries PostgreSQL, not Elasticsearch.

**Why:**
- PostgreSQL is the source of truth; ES replication may lag
- SQLAlchemy queries are simpler for basic filters and pagination
- No additional service dependency for the critical audit viewer
- ACID guarantees — no partial or phantom audit entries
- ES can be used later for full-text search across the `details` JSONB field

### ADR-022: Why 50 Items Per Page

**Decision:** `PAGE_SIZE = 50` for the audit table.

**Why:**
- Compliance officers scan large volumes of events (10-25 rows wastes time)
- 100+ rows causes noticeable rendering lag with React state updates
- 50 matches industry standard (AWS CloudTrail, GitHub, Datadog)

### Lessons Learned in Session 11

> **Lesson 16: SQLAlchemy `default=` is not Python `__init__` default.**
> `mapped_column(default="success")` only applies the default at `session.flush()`,
> not when you create the object in Python. This is a common gotcha that caused
> test failures: `AuditLog(tenant_id="t1", action="TEST").status` is `None`,
> not `"success"`. Tests must verify `AuditLog.__table__.columns["status"].default.arg`
> instead.

> **Lesson 17: Search UX beats search precision in audit tools.**
> The first implementation searched only `resource_id`, which returned 0 results
> for "webhook". After expanding to OR search across action, resource_type,
> resource_id, and ip_address, the same query found both webhook events.
> In investigation tools, recall matters more than precision.

### Test Results

```
376 unit tests: ALL PASSING (4.92s)
TypeScript: 0 errors
Vite Build: 2839 modules, clean production build

New tests (tests/unit/test_audit_trail.py):
  - TestAuditLogModel: 8 tests (create, nullable, defaults, indexes)
  - TestAuditActionTypes: 13 tests (12 action types + field length)
  - TestResourceTypes: 7 tests (6 types + nullable)
  - TestAuditTrailResponseFormat: 3 tests (pagination, entry, stats)
  - TestPIITracking: 3 tests (detected, not detected, structure)
  - TestCSVExportFormat: 2 tests (headers, row generation)
  - TestAuditTrailConfiguration: 6 tests (file existence, nav, route)
```

### Endpoint Verification

```
GET /audit-trail?days=30&limit=5          → 54 total, 5 returned, has_more=true
GET /audit-trail?action=PII_DETECTED      → 10 PII redaction events
GET /audit-trail?resource_type=api_key    → 4 API key events
GET /audit-trail?search=webhook           → 2 webhook events (multi-field OR)
GET /audit-trail?search=192.168           → 33 events by IP address
GET /audit-trail/stats?days=30            → 54 events, 20 PII, 12 action types
GET /audit-trail/export?days=30           → Valid CSV, 54 rows + header
```

---

## What's Next

- Alert Rule Builder (custom alert conditions and thresholds)
- Onboarding Wizard (guided first-time setup flow)
- E2E Integration Tests (Playwright browser automation)
- Real-Time Live Monitoring (WebSocket-based event stream)
- Production deployment to cloud (ECS, ALB, CloudFront)
