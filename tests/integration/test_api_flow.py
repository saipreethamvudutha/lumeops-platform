"""
Integration tests for the full API flow.

Tests the complete lifecycle: health check -> seed tenant -> ingest inference ->
query dashboard -> generate compliance report.

Requires PostgreSQL and Redis running (use Docker Compose).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session_factory, init_db
from app.core.security import generate_api_key, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.tenant import Tenant

from datetime import UTC, datetime, timedelta


@pytest_asyncio.fixture
async def integration_client():
    """HTTP client that hits the real ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def seeded_db():
    """Initialize DB and create a test tenant with API key."""
    await init_db()

    async with async_session_factory() as session:
        # Create tenant
        tenant = Tenant(
            name="Integration Test Hospital",
            customer_type="hospital",
            contact_email="test@integration.com",
            plan="professional",
            is_active=True,
            data_residency="us-east-1",
        )
        session.add(tenant)
        await session.flush()

        # Create API key
        plaintext_key, key_hash = generate_api_key()
        api_key = APIKey(
            tenant_id=tenant.id,
            key_hash=key_hash,
            key_suffix=plaintext_key[-6:],
            name="Integration Test Key",
            scopes=["ingest", "read", "audit", "admin"],
            expires_at=datetime.now(UTC) + timedelta(days=1),
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

        yield {"tenant_id": str(tenant.id), "api_key": plaintext_key}


@pytest.mark.integration
class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    async def test_health_endpoint(self, integration_client: AsyncClient):
        response = await integration_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "version" in data

    async def test_readiness_endpoint(self, integration_client: AsyncClient):
        response = await integration_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["services"]["database"] == "ok"
        assert data["services"]["redis"] == "ok"


@pytest.mark.integration
class TestIngestFlow:
    """Test the full inference ingestion flow."""

    async def test_ingest_with_pii_redaction(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Verify that PII is detected and redacted during ingestion."""
        response = await integration_client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
            json={
                "model_id": "test_diagnostic",
                "prediction": 0.87,
                "confidence": 0.92,
                "input_features": {
                    "age": 65,
                    "bp": 140,
                    "patient_ssn": "123-45-6789",
                    "patient_email": "patient@hospital.com",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["pii_redacted"] >= 2  # SSN + email

    async def test_ingest_without_pii(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Clean data should ingest without redaction."""
        response = await integration_client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
            json={
                "model_id": "test_risk_model",
                "prediction": 0.34,
                "input_features": {
                    "age": 45,
                    "weight": 82.5,
                    "symptom_score": 3,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["pii_redacted"] == 0

    async def test_ingest_unauthorized(self, integration_client: AsyncClient):
        """Requests without API key should be rejected."""
        response = await integration_client.post(
            "/api/v1/ingest",
            json={"model_id": "test", "prediction": 0.5, "input_features": {}},
        )
        assert response.status_code in (401, 403)

    async def test_ingest_invalid_payload(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Invalid payloads should return 422."""
        response = await integration_client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
            json={"model_id": "test"},  # Missing required fields
        )
        assert response.status_code == 422


@pytest.mark.integration
class TestDashboardFlow:
    """Test dashboard stats after ingestion."""

    async def test_dashboard_stats(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Dashboard should reflect ingested data."""
        # First ingest some data
        await integration_client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
            json={
                "model_id": "dashboard_test",
                "prediction": 0.75,
                "input_features": {"age": 50, "bp": 130},
            },
        )

        # Then check dashboard
        response = await integration_client.get(
            "/api/v1/dashboard/stats",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inferences"]["today"] >= 1
        assert "data_quality" in data
        assert "system" in data
        assert data["system"]["status"] == "healthy"


@pytest.mark.integration
class TestComplianceFlow:
    """Test HIPAA compliance report generation."""

    async def test_compliance_report(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Compliance report should generate with correct structure."""
        response = await integration_client.get(
            "/api/v1/reports/hipaa",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "executive_summary" in data
        assert "compliance_checklist" in data
        assert data["executive_summary"]["compliance_status"] == "COMPLIANT"

        # All checklist items should PASS
        for item in data["compliance_checklist"]:
            assert item["status"] == "PASS", f"Failed: {item['requirement']}"


@pytest.mark.integration
class TestApiKeyFlow:
    """Test API key management."""

    async def test_list_api_keys(
        self, integration_client: AsyncClient, seeded_db: dict
    ):
        """Should list API keys for the tenant."""
        response = await integration_client.get(
            "/api/v1/apikeys",
            headers={"Authorization": f"Bearer {seeded_db['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) >= 1
        key = data["keys"][0]
        assert key["is_active"] is True
        assert "ingest" in key["scopes"]


@pytest.mark.integration
class TestSecurityHeaders:
    """Test that security headers are present on all responses."""

    async def test_security_headers_present(self, integration_client: AsyncClient):
        response = await integration_client.get("/health")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-xss-protection") == "1; mode=block"
        assert "strict-transport-security" in response.headers
        assert response.headers.get("cache-control") == "no-store"

    async def test_request_id_present(self, integration_client: AsyncClient):
        response = await integration_client.get("/health")
        assert "x-request-id" in response.headers
        assert response.headers["x-request-id"].startswith("req_")
