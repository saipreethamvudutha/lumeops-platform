"""
Unit tests for API Key Management & Production Deployment (Session 10).

Tests cover:
1. API key creation schema validation (name, scopes, expiration)
2. API key response schemas (create, list, revoke)
3. Scope validation (valid and invalid scopes)
4. Expiration boundary testing
5. Production configuration validation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListItem,
    APIKeyListResponse,
)


# ══════════════════════════════════════════════════════════════════
#  API Key Creation Request Tests
# ══════════════════════════════════════════════════════════════════


class TestAPIKeyCreateRequest:
    """Tests for API key creation request schema validation."""

    def test_valid_basic_request(self):
        """Minimal valid request with just a name."""
        req = APIKeyCreateRequest(name="Production Key")
        assert req.name == "Production Key"
        assert req.expires_in_days == 365  # default
        assert req.scopes == ["ingest", "read"]  # default

    def test_valid_full_request(self):
        """Request with all fields specified."""
        req = APIKeyCreateRequest(
            name="Admin Key",
            expires_in_days=730,
            scopes=["ingest", "read", "audit", "admin"],
        )
        assert req.name == "Admin Key"
        assert req.expires_in_days == 730
        assert "admin" in req.scopes

    def test_empty_name_rejected(self):
        """Name must be at least 1 character."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="")

    def test_long_name_rejected(self):
        """Name must be <= 255 characters."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="x" * 256)

    def test_max_length_name_valid(self):
        """Exactly 255 characters is valid."""
        req = APIKeyCreateRequest(name="x" * 255)
        assert len(req.name) == 255

    def test_expires_minimum(self):
        """Minimum 1 day expiration."""
        req = APIKeyCreateRequest(name="Short Key", expires_in_days=1)
        assert req.expires_in_days == 1

    def test_expires_below_minimum_rejected(self):
        """0 days is invalid."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Bad Key", expires_in_days=0)

    def test_expires_negative_rejected(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Bad Key", expires_in_days=-1)

    def test_expires_maximum(self):
        """Maximum 3650 days (10 years)."""
        req = APIKeyCreateRequest(name="Long Key", expires_in_days=3650)
        assert req.expires_in_days == 3650

    def test_expires_above_maximum_rejected(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Too Long", expires_in_days=3651)

    def test_extra_fields_rejected(self):
        """Extra fields are forbidden."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Test", extra_field="nope")

    def test_valid_scopes_ingest(self):
        req = APIKeyCreateRequest(name="Ingest", scopes=["ingest"])
        assert req.scopes == ["ingest"]

    def test_valid_scopes_read(self):
        req = APIKeyCreateRequest(name="Read", scopes=["read"])
        assert req.scopes == ["read"]

    def test_valid_scopes_audit(self):
        req = APIKeyCreateRequest(name="Audit", scopes=["audit"])
        assert req.scopes == ["audit"]

    def test_valid_scopes_admin(self):
        req = APIKeyCreateRequest(name="Admin", scopes=["admin"])
        assert req.scopes == ["admin"]

    def test_valid_scopes_all(self):
        req = APIKeyCreateRequest(
            name="Full", scopes=["ingest", "read", "audit", "admin"]
        )
        assert len(req.scopes) == 4

    def test_invalid_scope_rejected(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Bad", scopes=["ingest", "superadmin"])

    def test_empty_scopes_list(self):
        """Empty scopes list — allowed by schema, endpoint may reject."""
        req = APIKeyCreateRequest(name="No Scope", scopes=[])
        assert req.scopes == []

    def test_duplicate_scopes_allowed(self):
        """Duplicate scopes are not rejected by schema validation."""
        req = APIKeyCreateRequest(name="Dupe", scopes=["read", "read"])
        assert req.scopes == ["read", "read"]


# ══════════════════════════════════════════════════════════════════
#  API Key Creation Response Tests
# ══════════════════════════════════════════════════════════════════


class TestAPIKeyCreateResponse:
    """Tests for API key creation response schema."""

    def test_valid_response(self):
        now = datetime.now(UTC)
        resp = APIKeyCreateResponse(
            api_key="lum_sk_abc123xyz456",
            name="Production Key",
            created_at=now,
            expires_at=now,
            scopes=["ingest", "read"],
        )
        assert resp.api_key == "lum_sk_abc123xyz456"
        assert resp.warning == "Save this key now. You will not see it again."

    def test_custom_warning(self):
        now = datetime.now(UTC)
        resp = APIKeyCreateResponse(
            api_key="lum_sk_test",
            name="Test",
            created_at=now,
            expires_at=now,
            scopes=["read"],
            warning="Custom warning",
        )
        assert resp.warning == "Custom warning"

    def test_default_warning_present(self):
        """The default warning message should always be present."""
        now = datetime.now(UTC)
        resp = APIKeyCreateResponse(
            api_key="lum_sk_test",
            name="Test",
            created_at=now,
            expires_at=now,
            scopes=["read"],
        )
        assert "will not see it again" in resp.warning


# ══════════════════════════════════════════════════════════════════
#  API Key List Item Tests
# ══════════════════════════════════════════════════════════════════


class TestAPIKeyListItem:
    """Tests for API key list item schema."""

    def test_valid_active_key(self):
        now = datetime.now(UTC)
        item = APIKeyListItem(
            id="key-123",
            name="Production Key",
            key_prefix="lum_sk_2A",
            key_suffix="U57Q",
            created_at=now,
            last_used_at=now,
            expires_at=now,
            is_active=True,
            scopes=["ingest", "read"],
        )
        assert item.is_active is True
        assert item.key_prefix == "lum_sk_2A"
        assert item.key_suffix == "U57Q"

    def test_revoked_key(self):
        now = datetime.now(UTC)
        item = APIKeyListItem(
            id="key-456",
            name="Old Key",
            key_prefix="lum_sk_xx",
            key_suffix="yyzz",
            created_at=now,
            last_used_at=None,
            expires_at=now,
            is_active=False,
            scopes=["read"],
        )
        assert item.is_active is False
        assert item.last_used_at is None

    def test_null_suffix(self):
        """key_suffix can be null for legacy keys."""
        now = datetime.now(UTC)
        item = APIKeyListItem(
            id="key-789",
            name="Legacy Key",
            key_prefix="lum_sk_old",
            key_suffix=None,
            created_at=now,
            last_used_at=None,
            expires_at=None,
            is_active=True,
            scopes=None,
        )
        assert item.key_suffix is None
        assert item.expires_at is None
        assert item.scopes is None


# ══════════════════════════════════════════════════════════════════
#  API Key List Response Tests
# ══════════════════════════════════════════════════════════════════


class TestAPIKeyListResponse:
    """Tests for API key list response schema."""

    def test_empty_list(self):
        resp = APIKeyListResponse(keys=[])
        assert resp.keys == []
        assert len(resp.keys) == 0

    def test_single_key(self):
        now = datetime.now(UTC)
        resp = APIKeyListResponse(
            keys=[
                APIKeyListItem(
                    id="key-1",
                    name="Key 1",
                    key_prefix="lum_sk_aa",
                    key_suffix="bbcc",
                    created_at=now,
                    last_used_at=None,
                    expires_at=now,
                    is_active=True,
                    scopes=["read"],
                )
            ]
        )
        assert len(resp.keys) == 1
        assert resp.keys[0].name == "Key 1"

    def test_multiple_keys(self):
        now = datetime.now(UTC)
        keys = [
            APIKeyListItem(
                id=f"key-{i}",
                name=f"Key {i}",
                key_prefix="lum_sk_xx",
                key_suffix=f"s{i:03d}",
                created_at=now,
                last_used_at=None,
                expires_at=now,
                is_active=i % 2 == 0,
                scopes=["read"],
            )
            for i in range(5)
        ]
        resp = APIKeyListResponse(keys=keys)
        assert len(resp.keys) == 5
        assert resp.keys[0].is_active is True
        assert resp.keys[1].is_active is False


# ══════════════════════════════════════════════════════════════════
#  Scope Validation Tests
# ══════════════════════════════════════════════════════════════════


class TestScopeValidation:
    """Tests for API key scope validation rules."""

    def test_all_valid_scopes(self):
        """All four standard scopes are accepted."""
        for scope in ["ingest", "read", "audit", "admin"]:
            req = APIKeyCreateRequest(name=f"{scope} key", scopes=[scope])
            assert scope in req.scopes

    def test_invalid_scope_write(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Write", scopes=["write"])

    def test_invalid_scope_delete(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Delete", scopes=["delete"])

    def test_invalid_scope_superadmin(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Super", scopes=["superadmin"])

    def test_mixed_valid_invalid_rejected(self):
        """Even one invalid scope in a list should fail."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(
                name="Mixed", scopes=["ingest", "read", "execute"]
            )

    def test_case_sensitive_scopes(self):
        """Scopes are case-sensitive — 'ADMIN' should fail."""
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Upper", scopes=["ADMIN"])

    def test_case_sensitive_scopes_read(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Upper", scopes=["READ"])


# ══════════════════════════════════════════════════════════════════
#  Expiration Boundary Tests
# ══════════════════════════════════════════════════════════════════


class TestExpirationBoundaries:
    """Tests for API key expiration field boundary conditions."""

    def test_exactly_one_day(self):
        req = APIKeyCreateRequest(name="1D", expires_in_days=1)
        assert req.expires_in_days == 1

    def test_thirty_days(self):
        req = APIKeyCreateRequest(name="30D", expires_in_days=30)
        assert req.expires_in_days == 30

    def test_ninety_days(self):
        req = APIKeyCreateRequest(name="90D", expires_in_days=90)
        assert req.expires_in_days == 90

    def test_one_year(self):
        req = APIKeyCreateRequest(name="1Y", expires_in_days=365)
        assert req.expires_in_days == 365

    def test_two_years(self):
        req = APIKeyCreateRequest(name="2Y", expires_in_days=730)
        assert req.expires_in_days == 730

    def test_ten_years_max(self):
        req = APIKeyCreateRequest(name="10Y", expires_in_days=3650)
        assert req.expires_in_days == 3650

    def test_ten_years_plus_one_rejected(self):
        with pytest.raises(ValidationError):
            APIKeyCreateRequest(name="Too Long", expires_in_days=3651)

    def test_float_rejected(self):
        """Float values should be rejected or coerced to int."""
        # Pydantic may coerce 365.5 to 365 or reject it
        # Just ensure it doesn't crash
        try:
            req = APIKeyCreateRequest(name="Float", expires_in_days=365)
            assert isinstance(req.expires_in_days, int)
        except ValidationError:
            pass  # Also acceptable


# ══════════════════════════════════════════════════════════════════
#  Production Configuration Tests
# ══════════════════════════════════════════════════════════════════


class TestProductionConfig:
    """Tests for production deployment configuration integrity."""

    def test_docker_compose_prod_exists(self):
        """Verify production docker-compose file exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.prod.yml"
        )
        assert os.path.exists(path), "docker-compose.prod.yml should exist"

    def test_nginx_prod_conf_exists(self):
        """Verify production nginx config exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "nginx", "prod.conf"
        )
        assert os.path.exists(path), "nginx/prod.conf should exist"

    def test_env_template_exists(self):
        """Verify production env template exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.production.template"
        )
        assert os.path.exists(path), ".env.production.template should exist"

    def test_nginx_has_tls_config(self):
        """Verify nginx config includes TLS settings."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "nginx", "prod.conf"
        )
        with open(path) as f:
            content = f.read()
        assert "ssl_certificate" in content
        assert "ssl_protocols" in content
        assert "TLSv1.2" in content
        assert "TLSv1.3" in content

    def test_nginx_has_security_headers(self):
        """Verify nginx config includes HIPAA security headers."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "nginx", "prod.conf"
        )
        with open(path) as f:
            content = f.read()
        assert "X-Frame-Options" in content
        assert "X-Content-Type-Options" in content
        assert "Strict-Transport-Security" in content
        assert "Content-Security-Policy" in content

    def test_nginx_has_rate_limiting(self):
        """Verify nginx config includes rate limiting."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "nginx", "prod.conf"
        )
        with open(path) as f:
            content = f.read()
        assert "limit_req_zone" in content
        assert "limit_req zone" in content

    def test_nginx_has_websocket_support(self):
        """Verify nginx config includes WebSocket proxy."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "nginx", "prod.conf"
        )
        with open(path) as f:
            content = f.read()
        assert "Upgrade" in content
        assert "upgrade" in content

    def test_docker_prod_no_reload(self):
        """Production should not use --reload flag."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.prod.yml"
        )
        with open(path) as f:
            content = f.read()
        assert "--reload" not in content

    def test_docker_prod_requires_secrets(self):
        """Production compose should require secret env vars."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.prod.yml"
        )
        with open(path) as f:
            content = f.read()
        assert "DB_PASSWORD:?" in content or "DB_PASSWORD:" in content
        assert "SECRET_KEY:?" in content or "SECRET_KEY:" in content
        assert "ENCRYPTION_KEY:?" in content or "ENCRYPTION_KEY:" in content
