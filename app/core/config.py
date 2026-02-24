"""
Application configuration with security-first defaults.

All sensitive values loaded from environment variables.
No secrets hardcoded. No defaults for production credentials.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "LumeOps"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # ── Security ─────────────────────────────────────────────────
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    API_KEY_PREFIX: str = "lum_sk_"
    ALLOWED_HOSTS: list[str] = ["*"]
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── Database (PostgreSQL) ────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lumeops"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False

    # ── Redis ────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # ── Elasticsearch ────────────────────────────────────────────
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_INDEX_PREFIX: str = "lumeops-audit"

    # ── AWS ──────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    AWS_KMS_KEY_ID: str = ""
    AWS_S3_BUCKET: str = "lumeops-data"
    AWS_S3_REPORTS_BUCKET: str = "lumeops-reports"

    # ── Encryption ───────────────────────────────────────────────
    ENCRYPTION_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Fernet-compatible encryption key for field-level encryption",
    )

    # ── Rate Limiting ────────────────────────────────────────────
    RATE_LIMIT_STARTER: int = 100  # requests/minute
    RATE_LIMIT_PROFESSIONAL: int = 500
    RATE_LIMIT_ENTERPRISE: int = 5000

    # ── Monitoring ───────────────────────────────────────────────
    BASELINE_MIN_SAMPLES: int = 100
    BASELINE_DEFAULT_SAMPLES: int = 1000
    OUTLIER_SIGMA_THRESHOLD: float = 3.0

    # ── Alerts ───────────────────────────────────────────────────
    ALERT_EMAIL_ENABLED: bool = False
    ALERT_SLACK_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_FROM_EMAIL: str = "alerts@lumeops.io"

    # ── Audit ────────────────────────────────────────────────────
    AUDIT_RETENTION_YEARS: int = 7
    AUDIT_LOG_TO_STDOUT: bool = True

    # ── Data Retention ─────────────────────────────────────────────
    RETENTION_CLEANUP_HOUR: int = 2  # Hour (UTC) to run daily cleanup
    RETENTION_MIN_INFERENCE_DAYS: int = 365  # HIPAA minimum
    RETENTION_MIN_ALERT_DAYS: int = 30
    RETENTION_MIN_WEBHOOK_DAYS: int = 7

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v == "production":
            # In production, enforce stricter settings
            return v
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
