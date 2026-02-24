"""
Tests for security utilities.

COVERAGE:
    1. API key generation and verification
    2. System-wide field encryption/decryption
    3. Per-tenant key isolation (encrypt with tenant A, can't decrypt with tenant B)
    4. Dictionary encryption
    5. Tenant encryption key management
    6. Key rotation
    7. Unique ID generation

LEARNING NOTE:
    The most critical test here is TestPerTenantEncryption.
    If per-tenant isolation fails, a single key compromise could
    expose all healthcare data. These tests verify that:
    - Each tenant gets a unique encryption key
    - Data encrypted for one tenant CANNOT be decrypted by another
    - The same data encrypted for different tenants produces different ciphertext
"""

import pytest

from app.core.security import (
    decrypt_dict,
    decrypt_field,
    encrypt_dict,
    encrypt_field,
    generate_api_key,
    generate_inference_id,
    generate_request_id,
    generate_tenant_encryption_key,
    hash_api_key,
    rotate_encryption,
    verify_api_key,
)


class TestAPIKeyGeneration:
    """Test API key generation and hashing."""

    def test_generate_api_key(self):
        plaintext, key_hash = generate_api_key()
        assert plaintext.startswith("lum_sk_")
        assert len(plaintext) > 20
        assert len(key_hash) == 64  # SHA-256 hex digest

    def test_unique_keys(self):
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert key1 != key2

    def test_unique_hashes(self):
        _, hash1 = generate_api_key()
        _, hash2 = generate_api_key()
        assert hash1 != hash2


class TestAPIKeyVerification:
    """Test API key verification."""

    def test_verify_correct_key(self):
        plaintext, key_hash = generate_api_key()
        assert verify_api_key(plaintext, key_hash)

    def test_verify_wrong_key(self):
        _, key_hash = generate_api_key()
        wrong_key, _ = generate_api_key()
        assert not verify_api_key(wrong_key, key_hash)

    def test_verify_tampered_hash(self):
        plaintext, _ = generate_api_key()
        assert not verify_api_key(plaintext, "tampered_hash")


class TestFieldEncryption:
    """Test system-wide field-level encryption."""

    def test_encrypt_decrypt_string(self):
        original = "sensitive patient data"
        encrypted = encrypt_field(original)
        assert encrypted != original
        decrypted = decrypt_field(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_ciphertext(self):
        """Fernet uses random IV, so same plaintext gives different ciphertext."""
        original = "same data"
        enc1 = encrypt_field(original)
        enc2 = encrypt_field(original)
        assert enc1 != enc2  # Different IV each time

    def test_decrypt_tampered_data(self):
        """Tampered ciphertext must fail decryption (integrity check)."""
        encrypted = encrypt_field("data")
        # Corrupt the middle of the ciphertext (not just append)
        corrupted = encrypted[:10] + "XXXX" + encrypted[14:]
        with pytest.raises((ValueError, Exception)):
            decrypt_field(corrupted)


class TestPerTenantEncryption:
    """
    Test per-tenant encryption key isolation.

    LEARNING NOTE:
        This is the MOST IMPORTANT security test in LumeOps.
        Per-tenant key isolation ensures that:
        - Hospital A's data encrypted with Key_A
        - Hospital B's data encrypted with Key_B
        - Compromising Key_A does NOT reveal Hospital B's data

        If these tests fail, we have a critical security vulnerability
        where one tenant could potentially access another's data.
    """

    def test_tenant_encrypt_decrypt(self):
        """Data encrypted for a tenant can be decrypted with the same tenant ID."""
        tenant_id = "tenant_hospital_a"
        original = "patient diagnosis: hypertension"
        encrypted = encrypt_field(original, tenant_id=tenant_id)
        decrypted = decrypt_field(encrypted, tenant_id=tenant_id)
        assert decrypted == original

    def test_different_tenants_produce_different_ciphertext(self):
        """Same data encrypted for different tenants gives different ciphertext."""
        original = "same patient data"
        enc_a = encrypt_field(original, tenant_id="tenant_a")
        enc_b = encrypt_field(original, tenant_id="tenant_b")
        assert enc_a != enc_b  # Different keys -> different ciphertext

    def test_cross_tenant_decryption_fails(self):
        """
        CRITICAL: Data encrypted for tenant A CANNOT be decrypted by tenant B.

        This is the core isolation guarantee.
        """
        original = "sensitive clinical data"
        encrypted_for_a = encrypt_field(original, tenant_id="tenant_a")
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_field(encrypted_for_a, tenant_id="tenant_b")

    def test_system_key_cannot_decrypt_tenant_data(self):
        """Data encrypted with tenant key cannot be decrypted with system key."""
        original = "tenant-specific data"
        encrypted = encrypt_field(original, tenant_id="some_tenant")
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_field(encrypted)  # No tenant_id = system key

    def test_tenant_key_cannot_decrypt_system_data(self):
        """Data encrypted with system key cannot be decrypted with tenant key."""
        original = "system-wide data"
        encrypted = encrypt_field(original)  # System key
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_field(encrypted, tenant_id="some_tenant")

    def test_tenant_dict_encrypt_decrypt(self):
        """Dictionary encryption works with per-tenant keys."""
        tenant_id = "tenant_hospital_xyz"
        original = {
            "diagnosis_code": "E11.65",
            "medication": "metformin 500mg",
            "lab_glucose": 185.5,
        }
        encrypted = encrypt_dict(original, tenant_id=tenant_id)
        decrypted = decrypt_dict(encrypted, tenant_id=tenant_id)
        assert decrypted == original

    def test_tenant_dict_cross_tenant_fails(self):
        """Dict encrypted for tenant A CANNOT be decrypted by tenant B."""
        original = {"clinical_note": "Patient presents with chest pain"}
        encrypted = encrypt_dict(original, tenant_id="hospital_a")
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_dict(encrypted, tenant_id="hospital_b")


class TestDictEncryption:
    """Test dictionary encryption (system-wide key)."""

    def test_encrypt_decrypt_dict(self):
        original = {
            "age": 65,
            "diagnosis": "hypertension",
            "values": [1.0, 2.0, 3.0],
        }
        encrypted = encrypt_dict(original)
        assert isinstance(encrypted, str)
        decrypted = decrypt_dict(encrypted)
        assert decrypted == original

    def test_encrypt_empty_dict(self):
        original = {}
        encrypted = encrypt_dict(original)
        decrypted = decrypt_dict(encrypted)
        assert decrypted == original


class TestTenantKeyManagement:
    """Test tenant encryption key lifecycle."""

    def test_generate_tenant_key(self):
        """Generated keys should be valid Fernet keys."""
        key = generate_tenant_encryption_key()
        assert isinstance(key, str)
        assert len(key) > 20  # Fernet keys are 44 chars base64

    def test_generated_keys_are_unique(self):
        """Each generated key must be unique."""
        keys = {generate_tenant_encryption_key() for _ in range(50)}
        assert len(keys) == 50

    def test_key_rotation_version_based(self):
        """
        Key rotation: re-encrypt data from old key version to new key version.

        LEARNING NOTE:
            Version-based key rotation changes the PBKDF2 salt:
            - v1 salt: "lumeops-tenant-{id}-v1" → derives Key_v1
            - v2 salt: "lumeops-tenant-{id}-v2" → derives Key_v2
            These keys are cryptographically independent.

            The process:
            1. Data was encrypted with tenant's v1 key
            2. We rotate by decrypting with v1 and re-encrypting with v2
            3. The new ciphertext can only be decrypted with v2
        """
        original_data = {"patient_id": "[REDACTED_PATIENT_ID]", "glucose": 185.5}
        tenant_id = "test_tenant_rotation"

        # Encrypt with v1
        encrypted_v1 = encrypt_dict(original_data, tenant_id=tenant_id, key_version=1)

        # Rotate from v1 to v2
        encrypted_v2 = rotate_encryption(
            ciphertext=encrypted_v1,
            tenant_id=tenant_id,
            old_version=1,
            new_version=2,
        )

        # v2 ciphertext should decrypt with v2 key
        decrypted = decrypt_dict(encrypted_v2, tenant_id=tenant_id, key_version=2)
        assert decrypted == original_data

        # v1 ciphertext should still decrypt with v1 key
        decrypted_old = decrypt_dict(encrypted_v1, tenant_id=tenant_id, key_version=1)
        assert decrypted_old == original_data

        # v2 ciphertext should NOT decrypt with v1 key
        with pytest.raises(ValueError):
            decrypt_dict(encrypted_v2, tenant_id=tenant_id, key_version=1)

        # v1 ciphertext should NOT decrypt with v2 key
        with pytest.raises(ValueError):
            decrypt_dict(encrypted_v1, tenant_id=tenant_id, key_version=2)

    def test_key_rotation_multiple_versions(self):
        """Multiple rotations (v1 → v2 → v3) all produce independent keys."""
        original_data = {"test": "multi-rotation"}
        tenant_id = "multi_rotate_tenant"

        # Encrypt with v1
        enc_v1 = encrypt_dict(original_data, tenant_id=tenant_id, key_version=1)

        # Rotate v1 → v2
        enc_v2 = rotate_encryption(enc_v1, tenant_id, old_version=1, new_version=2)

        # Rotate v2 → v3
        enc_v3 = rotate_encryption(enc_v2, tenant_id, old_version=2, new_version=3)

        # All three ciphertexts are different
        assert enc_v1 != enc_v2 != enc_v3

        # Each can only be decrypted with its own version
        assert decrypt_dict(enc_v1, tenant_id=tenant_id, key_version=1) == original_data
        assert decrypt_dict(enc_v2, tenant_id=tenant_id, key_version=2) == original_data
        assert decrypt_dict(enc_v3, tenant_id=tenant_id, key_version=3) == original_data

        # Cross-version decryption fails
        with pytest.raises(ValueError):
            decrypt_dict(enc_v3, tenant_id=tenant_id, key_version=1)


class TestIDGeneration:
    """Test ID generation functions."""

    def test_request_id_format(self):
        rid = generate_request_id()
        assert rid.startswith("req_")

    def test_inference_id_format(self):
        iid = generate_inference_id()
        assert iid.startswith("inf_")

    def test_ids_are_unique(self):
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # All unique
