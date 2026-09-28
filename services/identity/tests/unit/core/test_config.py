"""Unit tests for identity/core/config.py - production safety guards.

Covers all four staging/production fail-fast checks:
  1. JWT key paths pointing at committed test fixtures
  2. DEBUG=true
  3. CORS_ORIGINS contains '*'
  4. BASE_DOMAIN missing or not a plain domain (tenant subdomain resolution,
     and the CORS origin regex derived from it)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

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
    """Return a dict of Settings kwargs that pass load_rsa_keys (valid PEM files).

    ``_env_file=None`` keeps these tests hermetic: a developer's local
    ``.env`` (e.g. ``IDENTITY_DEBUG=true`` in dev) must never leak into the
    production-safety assertions, regardless of the working directory pytest
    is invoked from.
    """
    private_path, public_path = _write_keypair(tmp_path)
    return {
        "_env_file": None,
        "DATABASE_URL": "postgresql+asyncpg://x@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_PRIVATE_KEY_PATH": private_path,
        "JWT_PUBLIC_KEY_PATH": public_path,
        "JWKS_ISSUER": "https://api.skyrict.in",
        "JWKS_AUDIENCE": "api.skyrict.in",
        "BASE_DOMAIN": "skyrict.com",
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
        assert s.CORS_ORIGINS == ["https://app.skyrict.io"]

    # --- Check 4: BASE_DOMAIN required (tenant subdomain resolution) ---

    def test_raises_production_missing_base_domain(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="BASE_DOMAIN is required"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.PRODUCTION,
                    BASE_DOMAIN="",
                )
            )

    def test_raises_staging_blank_base_domain(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="BASE_DOMAIN is required"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.STAGING,
                    BASE_DOMAIN=" ",
                )
            )

    def test_passes_production_base_domain(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                ENVIRONMENT=Environment.PRODUCTION,
                BASE_DOMAIN="skyrict.com",
            )
        )
        assert s.BASE_DOMAIN == "skyrict.com"

    @pytest.mark.parametrize(
        "bad_domain",
        [
            "https://skyrict.in",  # scheme
            "skyrict.in:443",  # port
            "localhost:3000",  # host and port
            "*.skyrict.in",  # wildcard
            "skyrict.in/tenant",  # path
        ],
    )
    def test_raises_production_unusable_base_domain(self, tmp_path: Path, bad_domain: str):
        """A BASE_DOMAIN that is set but not a plain domain must refuse to boot.

        Worse than empty: an empty one is caught by the check above, whereas a
        malformed one resolves no tenant from a Host header *and* degrades the
        derived CORS regex to None, so tenant origins stop being allowed with
        no error logged anywhere.
        """
        with pytest.raises(RuntimeError, match="plain domain name"):
            Settings(
                **_make_valid_settings(
                    tmp_path,
                    ENVIRONMENT=Environment.PRODUCTION,
                    BASE_DOMAIN=bad_domain,
                )
            )

    def test_dev_allows_unusable_base_domain(self, tmp_path: Path):
        """The validity rule is production-only. Local development runs with an
        empty or host:port BASE_DOMAIN and must not fail to import."""
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                ENVIRONMENT=Environment.DEV,
                BASE_DOMAIN="localhost:3000",
            )
        )
        assert s.BASE_DOMAIN == "localhost:3000"


class TestMissingRequiredVars:
    """Omitting any required variable must fail fast and name the variable.

    The Definition of Done requires the missing-variable case in addition to
    the three production-safety validator cases.
    """

    REQUIRED_FIELDS = (
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_PRIVATE_KEY_PATH",
        "JWT_PUBLIC_KEY_PATH",
        "JWKS_ISSUER",
        "JWKS_AUDIENCE",
    )

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_field_names_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
    ):
        monkeypatch.delenv(f"IDENTITY_{field}", raising=False)
        kwargs = _make_valid_settings(tmp_path)
        kwargs.pop(field)
        with pytest.raises(ValidationError) as excinfo:
            Settings(**kwargs)  # _env_file=None already in _make_valid_settings
        assert field in str(excinfo.value)

    # An environment variable that is *set* to "" is present, so Field(...)
    # accepted it. That is not hypothetical: `redisUrlOverride` defaults to ''
    # in the IaC, and passing deployManagedRedis=false without setting it
    # handed identity REDIS_URL='' - which passed settings and then raised
    # "Redis URL must specify one of the following schemes" at import, minutes
    # after a green pipeline. DATABASE_URL has the identical defect against
    # SQLAlchemy. See skyrict_common.config_types and audit finding 10.
    @pytest.mark.parametrize("field", ["DATABASE_URL", "REDIS_URL"])
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_connection_url_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, blank: str
    ):
        monkeypatch.setenv(f"IDENTITY_{field}", blank)
        kwargs = _make_valid_settings(tmp_path)
        kwargs.pop(field, None)
        with pytest.raises(ValidationError) as excinfo:
            Settings(**kwargs)
        # The message must name the variable, or the operator is back to
        # grepping pod logs for a driver's error text.
        assert field in str(excinfo.value)

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_env_var_names_variable(self, monkeypatch: pytest.MonkeyPatch, field: str):
        monkeypatch.delenv(f"IDENTITY_{field}", raising=False)
        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)
        assert field in str(excinfo.value)


class TestTrustedProxies:
    """TRUSTED_PROXIES parsing/validation for the client-IP extraction."""

    def test_default_is_empty(self, tmp_path: Path):
        s = Settings(**_make_valid_settings(tmp_path))
        assert s.TRUSTED_PROXIES == []
        assert s.trusted_proxy_networks == ()

    def test_accepts_list_of_ips_and_cidrs(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                TRUSTED_PROXIES=["10.0.0.1", "192.168.0.0/16", "2001:db8::/32"],
            )
        )
        assert s.TRUSTED_PROXIES == ["10.0.0.1", "192.168.0.0/16", "2001:db8::/32"]
        assert len(s.trusted_proxy_networks) == 3

    def test_accepts_comma_separated_string(self, tmp_path: Path):
        s = Settings(
            **_make_valid_settings(
                tmp_path,
                TRUSTED_PROXIES="10.0.0.1, 192.168.0.0/16",
            )
        )
        assert s.TRUSTED_PROXIES == ["10.0.0.1", "192.168.0.0/16"]

    def test_bare_ip_expands_to_host_network(self, tmp_path: Path):
        import ipaddress

        s = Settings(**_make_valid_settings(tmp_path, TRUSTED_PROXIES=["10.0.0.1"]))
        network = s.trusted_proxy_networks[0]
        assert network == ipaddress.ip_network("10.0.0.1/32")

    def test_rejects_garbage_entry(self, tmp_path: Path):
        with pytest.raises(ValidationError, match="not a valid IP address or CIDR"):
            Settings(**_make_valid_settings(tmp_path, TRUSTED_PROXIES=["10.0.0.999"]))

    def test_rejects_non_string_entry(self, tmp_path: Path):
        with pytest.raises(ValidationError, match="must be a string"):
            Settings(**_make_valid_settings(tmp_path, TRUSTED_PROXIES=[42]))


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
