"""
Security utilities for LumeOps.

Handles:
- API key generation and hashing
- Field-level encryption (AES via Fernet) with per-tenant key isolation
- JWT token creation/validation
- Secure random generation
- Tenant encryption key management

LEARNING NOTE ON ENCRYPTION ARCHITECTURE:
    LumeOps uses a key hierarchy for encryption:

    Level 1: Master Key (ENCRYPTION_KEY from settings)
        - Used as the root key material
        - Never used directly for data encryption
        - Stored in environment variables / secrets manager

    Level 2: Per-Tenant Keys (derived from master + tenant_id)
        - Each tenant gets a unique encryption key
        - Derived using PBKDF2 with tenant_id as salt
        - If one tenant's data is somehow decrypted, other tenants
          are NOT compromised because each key is different

    Level 3: Per-Field Fernet Tokens
        - Each encryption operation creates a unique Fernet token
        - Includes timestamp (for replay attack detection)
        - HMAC for tamper detection

    WHY PER-TENANT KEYS:
        If we used a single encryption key for all tenants, a key compromise
        would expose ALL healthcare data. With per-tenant keys, the blast
        radius of a compromise is limited to one organization.

        In practice, this means:
        - Hospital A's data is encrypted with Key_A
        - Hospital B's data is encrypted with Key_B
        - Compromising Key_A does NOT reveal Hospital B's data
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings


# ── API Key Management ───────────────────────────────────────────


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key and its hash.

    Returns:
        Tuple of (plaintext_key, key_hash)

    The plaintext key is shown to the user ONCE.
    Only the hash is stored in the database.
    """
    settings = get_settings()
    # Generate 32 bytes of randomness = 43 chars base64
    random_part = secrets.token_urlsafe(32)
    plaintext_key = f"{settings.API_KEY_PREFIX}{random_part}"

    # Hash with SHA-256 + HMAC for storage
    key_hash = hash_api_key(plaintext_key)

    return plaintext_key, key_hash


def hash_api_key(plaintext_key: str) -> str:
    """
    Hash an API key for secure storage using HMAC-SHA256.

    Uses the app SECRET_KEY as the HMAC key to prevent
    rainbow table attacks even if the DB is compromised.
    """
    settings = get_settings()
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        plaintext_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(plaintext_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of API key against stored hash."""
    computed_hash = hash_api_key(plaintext_key)
    return hmac.compare_digest(computed_hash, stored_hash)


# ── Encryption Key Derivation ────────────────────────────────────
#
# LEARNING NOTE:
#   Key derivation is computationally expensive (480k iterations of
#   PBKDF2). We cache derived keys to avoid re-deriving on every
#   encryption/decryption operation. The cache is bounded to prevent
#   memory issues with many tenants.


@lru_cache(maxsize=128)
def _derive_fernet_key(encryption_key: str, salt: bytes) -> bytes:
    """
    Derive a Fernet-compatible key from the encryption key + salt.

    LEARNING NOTE:
        PBKDF2 (Password-Based Key Derivation Function 2) takes a
        password-like input and stretches it into a cryptographic key.
        The salt ensures that even if two tenants had the same
        encryption_key, they'd get different derived keys.

        480,000 iterations makes brute-force attacks impractical.
        This follows OWASP recommendations for PBKDF2-SHA256.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = kdf.derive(encryption_key.encode("utf-8"))
    return urlsafe_b64encode(key)


def _get_system_fernet_key() -> bytes:
    """Get the system-wide Fernet key (for non-tenant-specific encryption)."""
    settings = get_settings()
    return _derive_fernet_key(
        settings.ENCRYPTION_KEY,
        b"lumeops-field-encryption-v1",
    )


def _get_tenant_fernet_key(tenant_id: str, key_version: int = 1) -> bytes:
    """
    Get a tenant-specific Fernet key for a given key version.

    LEARNING NOTE:
        Each tenant gets a unique encryption key derived from:
        - The master ENCRYPTION_KEY (from environment)
        - The tenant_id (used as part of the salt)
        - The key_version (embedded in the salt)

        This means:
        - Different tenants = different encryption keys
        - Different key versions = different encryption keys
        - Same tenant + same version always gets the same key (deterministic)

    KEY ROTATION DESIGN:
        When we rotate a tenant's key, we increment the version.
        The salt changes from "lumeops-tenant-{id}-v1" to "...-v2",
        which causes PBKDF2 to derive a completely different key.

        This is elegant because:
        - No new key material needs to be generated or stored
        - The master key stays the same
        - Old versions are derivable (for decryption during migration)
        - New versions produce completely independent keys

    SECURITY NOTE:
        We combine a static prefix with the tenant_id and version
        to create the salt. The prefix prevents collision with the
        system-wide key derivation which uses a different salt.
    """
    settings = get_settings()
    salt = f"lumeops-tenant-{tenant_id}-v{key_version}".encode("utf-8")
    return _derive_fernet_key(settings.ENCRYPTION_KEY, salt)


# ── Field-Level Encryption ───────────────────────────────────────


def encrypt_field(
    plaintext: str,
    tenant_id: str | None = None,
    key_version: int = 1,
) -> str:
    """
    Encrypt a string field value using Fernet (AES-128-CBC).

    Args:
        plaintext: The string to encrypt.
        tenant_id: If provided, uses per-tenant key isolation.
                   If None, uses the system-wide key.
        key_version: Which key version to use (for rotation support).

    Returns:
        Base64-encoded ciphertext.

    LEARNING NOTE:
        When tenant_id is provided, the data is encrypted with a
        key unique to that tenant. This means even if an attacker
        gains access to one tenant's decryption key, they cannot
        read other tenants' data.
    """
    if tenant_id:
        fernet_key = _get_tenant_fernet_key(tenant_id, key_version)
    else:
        fernet_key = _get_system_fernet_key()

    f = Fernet(fernet_key)
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_field(
    ciphertext: str,
    tenant_id: str | None = None,
    key_version: int = 1,
) -> str:
    """
    Decrypt a Fernet-encrypted field value.

    Args:
        ciphertext: The encrypted string.
        tenant_id: Must match the tenant_id used during encryption.
        key_version: Must match the key_version used during encryption.

    Raises:
        ValueError: If decryption fails (tampered, wrong key, or wrong tenant).
    """
    if tenant_id:
        fernet_key = _get_tenant_fernet_key(tenant_id, key_version)
    else:
        fernet_key = _get_system_fernet_key()

    f = Fernet(fernet_key)
    try:
        decrypted = f.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt field: invalid token or wrong key") from e


def encrypt_dict(
    data: dict[str, Any],
    tenant_id: str | None = None,
    key_version: int = 1,
) -> str:
    """
    Encrypt an entire dict by serializing to JSON then encrypting.

    Args:
        data: The dictionary to encrypt.
        tenant_id: If provided, uses per-tenant key isolation.
        key_version: Which key version to use (for rotation support).

    LEARNING NOTE:
        This is used for encrypting the redacted inference features.
        Even after PHI redaction, the clinical data (HIGH sensitivity)
        is still present and needs encryption. Per-tenant encryption
        ensures that a database breach only exposes encrypted blobs
        that require per-tenant keys to decrypt.
    """
    import orjson

    json_bytes = orjson.dumps(data)

    if tenant_id:
        fernet_key = _get_tenant_fernet_key(tenant_id, key_version)
    else:
        fernet_key = _get_system_fernet_key()

    f = Fernet(fernet_key)
    encrypted = f.encrypt(json_bytes)
    return encrypted.decode("utf-8")


def decrypt_dict(
    ciphertext: str,
    tenant_id: str | None = None,
    key_version: int = 1,
) -> dict[str, Any]:
    """
    Decrypt an encrypted dict.

    Args:
        ciphertext: The encrypted string.
        tenant_id: Must match the tenant_id used during encryption.
        key_version: Must match the key_version used during encryption.
    """
    import orjson

    if tenant_id:
        fernet_key = _get_tenant_fernet_key(tenant_id, key_version)
    else:
        fernet_key = _get_system_fernet_key()

    f = Fernet(fernet_key)
    try:
        decrypted = f.decrypt(ciphertext.encode("utf-8"))
        return orjson.loads(decrypted)
    except InvalidToken as e:
        raise ValueError("Failed to decrypt dict: invalid token or wrong key") from e


# ── Tenant Encryption Key Management ─────────────────────────────


def generate_tenant_encryption_key() -> str:
    """
    Generate a new encryption key for a tenant.

    LEARNING NOTE:
        This generates a cryptographically strong random key that
        can be stored in the tenant's encryption_key_id field.
        In production, this would be a reference to an AWS KMS key
        or similar HSM-backed key. For now, it's a Fernet key that
        we store (encrypted with the master key) in the database.

    Returns:
        A base64-encoded Fernet key string.
    """
    return Fernet.generate_key().decode("utf-8")


def rotate_encryption(
    ciphertext: str,
    tenant_id: str,
    old_version: int,
    new_version: int,
) -> str:
    """
    Re-encrypt data from one key version to another.

    This is the core primitive for key rotation. It:
    1. Decrypts the data using the old key version
    2. Re-encrypts it with the new key version

    Args:
        ciphertext: Data encrypted with the old key version.
        tenant_id: The tenant whose data is being rotated.
        old_version: The key version the data was encrypted with.
        new_version: The key version to re-encrypt with.

    Returns:
        Data encrypted with the new key version.

    LEARNING NOTE ON KEY ROTATION:
        Key rotation is a compliance best practice. HIPAA requires
        organizations to implement "reasonable safeguards" (164.530(c)),
        and periodic key rotation is widely accepted as reasonable.

        Our rotation approach is version-based:
        - v1 salt: "lumeops-tenant-{id}-v1" → derives Key_v1
        - v2 salt: "lumeops-tenant-{id}-v2" → derives Key_v2
        - Key_v1 and Key_v2 are cryptographically independent

        This is preferable to storing separate key material because:
        1. No key material to secure or rotate in a secrets manager
        2. Any version is reproducible from the master key + tenant_id
        3. Old versions can always be derived for data recovery
        4. The LRU cache makes repeated derivations fast

        In production with AWS KMS, you'd use KMS key aliases and
        rotate the underlying CMK — same concept, hardware-backed.

    SECURITY NOTE:
        This function intentionally does NOT delete old key material.
        Old keys remain derivable because:
        - If rotation fails mid-way, we can still read old records
        - Audit requirements may need historical data access
        - The key_version on each inference record tells us which key to use
    """
    # Decrypt with old key version
    plaintext = decrypt_dict(ciphertext, tenant_id=tenant_id, key_version=old_version)

    # Re-encrypt with new key version
    return encrypt_dict(plaintext, tenant_id=tenant_id, key_version=new_version)


# ── JWT Tokens ──────────────────────────────────────────────────


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()

    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises jwt.InvalidTokenError on failure.
    """
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


# ── Utility ─────────────────────────────────────────────────────


def generate_request_id() -> str:
    """Generate a unique request ID for idempotency tracking."""
    return f"req_{secrets.token_urlsafe(16)}"


def generate_inference_id() -> str:
    """Generate a unique inference ID."""
    return f"inf_{secrets.token_urlsafe(16)}"
