"""Unit tests for identity/core/config.py — production safety guards.

Covers all three staging/production fail-fast checks:
  1. JWT key paths pointing at committed test fixtures
  2. DEBUG=true
  3. CORS_ORIGINS contains '*'
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from identity.core.config import Environment, Settings

if TYPE_CHECKING:
    from pathlib import Path


def _write_keypair(tmp_path: Path) -> tuple[Path, Path]:
    """Generate a fresh RSA key pair and write PEM files to tmp_path.

    Returns (private_key_path, public_key_path). Real keys are used so the
    Settings.load_rsa_keys validator is satisfied.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def _make_valid_settings(tmp_path: Path, **overrides) -> dict:
    """Return a dict of Settings kwargs that pass load_rsa_keys (valid PEM files)."""
    private_path, public_path = _write_keypair(tmp_path)
    return {
        "DATABASE_URL": "postgresql+asyncpg://x@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_PRIVATE_KEY_PATH": private_path,
        "JWT_PUBLIC_KEY_PATH": public_path,
        "JWKS_ISSUER": "https://auth.skyrict.io",
        "JWKS_AUDIENCE": "api.skyrict.io",
        **overrides,
    }


class TestProductionSafety:
    """All three production_safety validator checks."""

    # --- Check 1: test fixture keys ---

    def test_raises_production_fixture_private_key(self, tmp_path: Path):
        fixture_dir = tmp_path / "tests" / "fixtures" / "rsa"
        fixture_dir.mkdir(parents=True)
        private_path, _ = _write_keypair(fixture_dir)
        with pytest.raises(RuntimeError, match=r"tests[\\/]fixtures"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.PRODUCTION,
                    JWT_PRIVATE_KEY_PATH=private_path,
                )
            )

    def test_raises_staging_fixture_public_key(self, tmp_path: Path):
        fixture_dir = tmp_path / "tests" / "fixtures" / "rsa"
        fixture_dir.mkdir(parents=True)
        _, public_path = _write_keypair(fixture_dir)
        with pytest.raises(RuntimeError, match=r"tests[\\/]fixtures"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.STAGING,
                    JWT_PUBLIC_KEY_PATH=public_path,
                )
            )

    def test_passes_dev_fixture_path(self, tmp_path: Path):
        s = Settings(**_make_valid_settings(tmp_path, ENVIRONMENT=Environment.DEV))
        assert s.ENVIRONMENT == Environment.DEV

    def test_passes_production_real_key_path(self, tmp_path: Path):
        s = Settings(**_make_valid_settings(tmp_path, ENVIRONMENT=Environment.PRODUCTION))
        assert s.ENVIRONMENT == Environment.PRODUCTION

    # --- Check 2: DEBUG=true ---

    def test_raises_production_debug_true(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="DEBUG=true is not allowed"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.PRODUCTION,
                    DEBUG=True,
                )
            )

    def test_raises_staging_debug_true(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="DEBUG=true is not allowed"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.STAGING,
                    DEBUG=True,
                )
            )

    def test_passes_dev_debug_true(self, tmp_path: Path):
        s = Settings(**_make_valid_settings(tmp_path, ENVIRONMENT=Environment.DEV, DEBUG=True))
        assert s.DEBUG is True

    def test_passes_production_debug_false(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                ENVIRONMENT=Environment.PRODUCTION,
                DEBUG=False,
            )
        )
        assert s.DEBUG is False

    # --- Check 3: wildcard CORS ---

    def test_raises_production_wildcard_cors(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="CORS_ORIGINS contains"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.PRODUCTION,
                    CORS_ORIGINS=["*"],
                )
            )

    def test_raises_staging_wildcard_cors(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="CORS_ORIGINS contains"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.STAGING,
                    CORS_ORIGINS=["*"],
                )
            )

    def test_passes_dev_wildcard_cors(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(tmp_path, ENVIRONMENT=Environment.DEV, CORS_ORIGINS=["*"])
        )
        assert "*" in s.CORS_ORIGINS

    def test_passes_production_explicit_cors(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                ENVIRONMENT=Environment.PRODUCTION,
                CORS_ORIGINS=["https://app.skyrict.io"],
            )
        )
        assert "https://app.skyrict.io" in s.CORS_ORIGINS


class TestEnvironmentEnum:
    """Verify Environment StrEnum works correctly."""

    def test_enum_values(self):
        assert Environment.DEV.value == "dev"
        assert Environment.TEST.value == "test"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"

    def test_string_comparison(self):
        assert Environment.DEV == "dev"
        assert Environment.PRODUCTION == "production"

    def test_settings_default_is_dev(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("IDENTITY_ENVIRONMENT", raising=False)
        s = Settings(**_make_valid_settings(tmp_path))
        assert s.ENVIRONMENT == Environment.DEV
