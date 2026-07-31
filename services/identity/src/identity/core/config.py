"""Application configuration — pydantic-settings, env-driven, fail-fast on missing secrets.

Single source of truth for ALL configuration. Application code must never
call os.getenv() directly — everything routes through the ``settings`` object.
"""

from __future__ import annotations

import enum
import sys
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, enum.Enum):
    """Deployment environments — exactly four, no ad-hoc values."""

    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """All configuration loaded from environment variables.

    Prefix: IDENTITY_ (set via .env or shell environment).
    CRITICAL vars (DATABASE_URL, JWT keys, REDIS_URL, JWKS) have NO defaults —
    the process refuses to start if they are missing.
    """

    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---
    ENVIRONMENT: Environment = Field(
        default=Environment.DEV,
        description="deployment environment: dev, test, staging, production",
    )
    DEBUG: bool = Field(default=False, description="enable debug mode")

    # --- Database (CRITICAL — no default) ---
    DATABASE_URL: str = Field(
        ..., description="async PostgreSQL connection string — REQUIRED"
    )

    # --- Redis (CRITICAL — no default) ---
    REDIS_URL: str = Field(..., description="Redis connection — REQUIRED")

    # --- JWT RS256 (CRITICAL — all four required) ---
    JWT_PRIVATE_KEY_PATH: Path = Field(
        ..., description="path to RSA private key PEM for signing — REQUIRED"
    )
    JWT_PUBLIC_KEY_PATH: Path = Field(
        ..., description="path to RSA public key PEM for verification — REQUIRED"
    )
    JWKS_ISSUER: str = Field(
        ..., description="JWT issuer claim (iss) — REQUIRED, e.g. https://auth.skyrict.io"
    )
    JWKS_AUDIENCE: str = Field(
        ..., description="JWT audience claim (aud) — REQUIRED, e.g. api.skyrict.io"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="access token TTL")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="refresh token TTL")

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(
        default=[],
        description="allowed CORS origins — must be explicit, never '*' in staging/production",
    )

    # --- Logging ---
    LOG_LEVEL: str = Field(default="INFO", description="log level")
    LOG_JSON: bool = Field(default=True, description="JSON log output")

    # --- Multi-tenancy ---
    DEFAULT_TENANT_ID: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description="default tenant ID for single-tenant or bootstrap",
    )

    # --- Password policy ---
    PASSWORD_MIN_LENGTH: int = Field(default=8, description="minimum password length")
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGIT: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True)

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN: int = Field(default=5, description="max login attempts per window")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, description="rate limit window")

    # --- Derived (loaded from files at validation time) ---
    jwt_private_key: str = ""
    jwt_public_key: str = ""

    # ------------------------------------------------------------------
    # Validators — run in definition order (pydantic v2)
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def load_rsa_keys(self) -> "Settings":
        """Load RSA key files and fail immediately if missing or unreadable."""
        errors: list[str] = []

        for label, path_attr, dest_attr in [
            ("JWT_PRIVATE_KEY_PATH", "JWT_PRIVATE_KEY_PATH", "jwt_private_key"),
            ("JWT_PUBLIC_KEY_PATH", "JWT_PUBLIC_KEY_PATH", "jwt_public_key"),
        ]:
            path: Path = getattr(self, path_attr)
            if not path.exists():
                errors.append(f"{label}: file not found at {path}")
            elif not path.is_file():
                errors.append(f"{label}: path is not a file ({path})")
            else:
                try:
                    content = path.read_text(encoding="utf-8")
                    if "PRIVATE KEY" not in content and "PUBLIC KEY" not in content:
                        errors.append(
                            f"{label}: file does not appear to contain a PEM key"
                        )
                    else:
                        setattr(self, dest_attr, content)
                except OSError as exc:
                    errors.append(f"{label}: cannot read {path}: {exc}")

        if errors:
            print(
                f"FATAL: {len(errors)} configuration error(s):\n"
                + "\n".join(f"  - {e}" for e in errors),
                file=sys.stderr,
            )
            sys.exit(1)

        return self

    @model_validator(mode="after")
    def production_safety(self) -> "Settings":
        """Fail-fast guards that apply ONLY in staging and production.

        Runs after load_rsa_keys so all fields are populated.
        Checks:
          1. JWT key paths must not point at committed test fixtures.
          2. DEBUG must be False.
          3. CORS_ORIGINS must not contain wildcard '*'.
        """
        if self.ENVIRONMENT not in (Environment.STAGING, Environment.PRODUCTION):
            return self

        errors: list[str] = []

        # Check 1: test fixture keys
        for label, path_attr in [
            ("JWT_PRIVATE_KEY_PATH", "JWT_PRIVATE_KEY_PATH"),
            ("JWT_PUBLIC_KEY_PATH", "JWT_PUBLIC_KEY_PATH"),
        ]:
            path: Path = getattr(self, path_attr)
            if "tests/fixtures" in path.as_posix():
                errors.append(
                    f"Refusing to start: {label} points at a public test "
                    f"fixture ({path}). Production and staging must use a "
                    f"secret-manager-provisioned key, never the committed "
                    f"dev/test keypair."
                )

        # Check 2: DEBUG must be off
        if self.DEBUG:
            errors.append(
                "Refusing to start: DEBUG=true is not allowed in staging/production. "
                "Set DEBUG=false or omit it entirely."
            )

        # Check 3: no wildcard CORS
        if "*" in self.CORS_ORIGINS:
            errors.append(
                "Refusing to start: CORS_ORIGINS contains '*' which is not "
                "allowed in staging/production. List explicit origins instead."
            )

        if errors:
            raise RuntimeError(
                "Production safety check failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        return self


settings = Settings()
