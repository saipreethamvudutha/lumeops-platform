"""
Test configuration and fixtures.

Provides test database, HTTP client, and authenticated test client.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:lumeops_dev_password@localhost:5432/lumeops_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

from app.core.security import generate_api_key
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_inference_payload():
    """Standard test inference payload."""
    return {
        "model_id": "diagnostic_v2",
        "prediction": 0.87,
        "confidence": 0.92,
        "input_features": {
            "age": 65,
            "systolic_bp": 145,
            "diastolic_bp": 92,
            "heart_rate": 78,
            "lab_glucose": 185.5,
            "patient_ssn": "123-45-6789",
            "patient_email": "john.doe@hospital.com",
        },
    }


@pytest.fixture
def sample_inference_no_pii():
    """Inference payload with no PII."""
    return {
        "model_id": "risk_model_v1",
        "prediction": 0.34,
        "input_features": {
            "age": 45,
            "weight": 82.5,
            "height": 175,
            "symptom_score": 3,
        },
    }


@pytest.fixture
def api_key_pair():
    """Generate a test API key pair."""
    return generate_api_key()
