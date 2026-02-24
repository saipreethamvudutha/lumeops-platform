"""
Development seed script.

Creates a test tenant and API key for local development.
Run: python -m scripts.seed_dev
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import async_session_factory, init_db
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import APIKey
from app.models.tenant import Tenant


async def seed():
    """Create development test data."""
    print("Initializing database...")
    await init_db()

    async with async_session_factory() as session:
        # Check if already seeded
        from sqlalchemy import select
        existing = await session.execute(
            select(Tenant).where(Tenant.name == "Test Hospital")
        )
        if existing.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        # Create test tenant
        tenant = Tenant(
            name="Test Hospital",
            customer_type="hospital",
            contact_email="admin@testhospital.com",
            plan="professional",
            is_active=True,
            data_residency="us-east-1",
        )
        session.add(tenant)
        await session.flush()
        print(f"Created tenant: {tenant.name} (ID: {tenant.id})")

        # Create API key
        plaintext_key, key_hash = generate_api_key()

        api_key = APIKey(
            tenant_id=tenant.id,
            key_hash=key_hash,
            key_suffix=plaintext_key[-6:],
            name="Development Key",
            scopes=["ingest", "read", "audit", "admin"],
            expires_at=datetime.now(UTC) + timedelta(days=365),
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

        print(f"\nDevelopment API Key (save this):")
        print(f"  {plaintext_key}")
        print(f"\nKey suffix: ...{plaintext_key[-6:]}")
        print(f"Scopes: ingest, read, audit, admin")
        print(f"\nTest with:")
        print(f'  curl -X POST http://localhost:8000/api/v1/ingest \\')
        print(f'    -H "Authorization: Bearer {plaintext_key}" \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f'    -d \'{{"model_id": "test_model", "prediction": 0.87, '
              f'"input_features": {{"age": 65, "bp": 140, '
              f'"patient_ssn": "123-45-6789"}}}}\'')


if __name__ == "__main__":
    asyncio.run(seed())
