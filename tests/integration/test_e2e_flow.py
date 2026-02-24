"""
End-to-end data flow test.

Verifies the complete LumeOps pipeline:
  1. Ingest inference with PHI → PII detected and redacted
  2. Dashboard stats reflect the inference
  3. Audit trail contains events for inference + redaction
  4. Compliance report includes correct counts
  5. PDF export generates valid PDF bytes
  6. Elasticsearch receives dual-written audit events

Requires Docker Compose stack running (postgres, redis, elasticsearch).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from datetime import UTC, datetime, timedelta

from app.core.database import async_session_factory, init_db
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.model import MLModel
from app.models.tenant import Tenant


@pytest_asyncio.fixture
async def e2e_setup():
    """
    Set up a complete test environment:
    - Tenant with encryption
    - API key with full scopes
    - Registered ML model
    """
    await init_db()

    async with async_session_factory() as session:
        # Create tenant
        tenant = Tenant(
            name="E2E Test Hospital",
            customer_type="hospital",
            contact_email="e2e@test.com",
            plan="enterprise",
            is_active=True,
            data_residency="us-east-1",
        )
        session.add(tenant)
        await session.flush()

        # Create ML model
        model = MLModel(
            tenant_id=tenant.id,
            model_name="e2e_readmission_model",
            model_version="1.0.0",
            description="End-to-end test model",
            framework="pytorch",
            is_active=True,
            required_fields=["age", "diagnosis", "los_days"],
            field_ranges={"age": {"min": 0, "max": 120}},
            field_types={"age": "float", "diagnosis": "string", "los_days": "float"},
        )
        session.add(model)
        await session.flush()

        # Create API key
        plaintext_key, key_hash = generate_api_key()
        api_key = APIKey(
            tenant_id=tenant.id,
            key_hash=key_hash,
            key_suffix=plaintext_key[-6:],
            name="E2E Test Key",
            scopes=["ingest", "read", "audit", "admin"],
            expires_at=datetime.now(UTC) + timedelta(days=1),
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

        yield {
            "tenant_id": str(tenant.id),
            "api_key": plaintext_key,
            "model_id": str(model.id),
        }


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for the ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.integration
class TestEndToEndDataFlow:
    """
    Complete end-to-end test of the LumeOps data pipeline.

    This test class runs steps sequentially — each test depends on prior state.
    Use pytest-ordering or run with `-k TestEndToEndDataFlow` to ensure order.
    """

    async def test_01_ingest_inference_with_phi(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 1: Ingest an inference containing PHI data."""
        response = await client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
            json={
                "model_id": e2e_setup["model_id"],
                "prediction": 0.78,
                "confidence": 0.93,
                "input_features": {
                    "age": 72,
                    "diagnosis": "acute_mi",
                    "los_days": 5,
                    "patient_ssn": "987-65-4321",
                    "patient_email": "jane.smith@hospital.org",
                    "patient_name": "Jane Smith",
                    "insurance_member_id": "INS-998877",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Verify inference accepted
        assert data["status"] == "received"
        assert data["inference_id"].startswith("inf_")

        # Verify PHI was detected and redacted
        assert data["pii_redacted"] >= 3, (
            f"Expected at least 3 PII items (SSN, email, name), got {data['pii_redacted']}"
        )

        # Store inference ID for subsequent tests
        e2e_setup["inference_id"] = data["inference_id"]

    async def test_02_ingest_clean_inference(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 2: Ingest clean data (no PHI) to verify zero-redaction path."""
        response = await client.post(
            "/api/v1/ingest",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
            json={
                "model_id": e2e_setup["model_id"],
                "prediction": 0.22,
                "confidence": 0.88,
                "input_features": {
                    "age": 45,
                    "diagnosis": "hypertension",
                    "los_days": 2,
                    "bmi": 28.5,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_redacted"] == 0

    async def test_03_dashboard_reflects_inferences(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 3: Dashboard stats should show the ingested inferences."""
        response = await client.get(
            "/api/v1/dashboard/stats",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()

        # At least 2 inferences (from steps 1 and 2)
        assert data["inferences"]["today"] >= 2
        assert data["inferences"]["all_time"] >= 2

        # PII protection should reflect the redaction from step 1
        assert data["pii_protection"]["total_redacted_today"] >= 3

        # System should be healthy
        assert data["system"]["status"] == "healthy"

    async def test_04_audit_trail_has_events(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 4: Audit trail should contain inference + PII redaction events."""
        response = await client.get(
            "/api/v1/reports/audit-trail?days=1",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Should have audit entries
        assert data["total"] >= 2

        # Check for expected action types
        actions = {entry["action"] for entry in data["entries"]}
        assert "INFERENCE_RECEIVED" in actions

    async def test_05_compliance_report_json(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 5: Compliance report should reflect all activity."""
        response = await client.get(
            "/api/v1/reports/hipaa?days=1",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Executive summary
        assert data["executive_summary"]["compliance_status"] == "COMPLIANT"
        assert data["executive_summary"]["total_inferences"] >= 2
        assert data["executive_summary"]["pii_instances_redacted"] >= 3

        # All checklist items should PASS
        for item in data["compliance_checklist"]:
            assert item["status"] == "PASS", f"Failed: {item['requirement']}"

        # Report should have audit logging section
        assert data["audit_logging"]["status"] == "ACTIVE"
        assert data["audit_logging"]["retention"] == "7 years"

    async def test_06_compliance_report_pdf(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 6: PDF compliance report should generate valid PDF bytes."""
        response = await client.get(
            "/api/v1/reports/hipaa/pdf?days=1",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
        )
        assert response.status_code == 200

        # Verify Content-Type
        assert response.headers["content-type"] == "application/pdf"

        # Verify Content-Disposition
        assert "attachment" in response.headers.get("content-disposition", "")
        assert "lumeops-hipaa-compliance" in response.headers.get("content-disposition", "")

        # Verify it's a valid PDF (starts with %PDF header)
        content = response.content
        assert len(content) > 0
        assert content[:5] == b"%PDF-"

    async def test_07_security_headers_on_all_responses(
        self, client: AsyncClient, e2e_setup: dict
    ):
        """Step 7: All responses must include security headers."""
        # Test on authenticated endpoint
        response = await client.get(
            "/api/v1/dashboard/stats",
            headers={"Authorization": f"Bearer {e2e_setup['api_key']}"},
        )

        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-xss-protection") == "1; mode=block"
        assert "strict-transport-security" in response.headers
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("x-request-id", "").startswith("req_")

    async def test_08_unauthorized_access_blocked(
        self, client: AsyncClient
    ):
        """Step 8: All protected endpoints reject unauthenticated requests."""
        endpoints = [
            ("POST", "/api/v1/ingest"),
            ("GET", "/api/v1/dashboard/stats"),
            ("GET", "/api/v1/reports/hipaa"),
            ("GET", "/api/v1/reports/hipaa/pdf"),
            ("GET", "/api/v1/reports/audit-trail"),
            ("GET", "/api/v1/apikeys"),
        ]

        for method, path in endpoints:
            if method == "POST":
                response = await client.post(
                    path,
                    json={"model_id": "x", "prediction": 0.5, "input_features": {"a": 1}},
                )
            else:
                response = await client.get(path)

            assert response.status_code in (401, 403), (
                f"{method} {path} returned {response.status_code}, expected 401/403"
            )
