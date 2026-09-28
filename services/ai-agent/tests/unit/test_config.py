"""Unit tests for configuration validation (provider-agnostic boot contract)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_agent.core.config import Environment, Settings


def _base_env() -> dict[str, str]:
    return {
        "AI_ENVIRONMENT": "test",
        "AI_DATABASE_URL": "postgresql+asyncpg://skyrict:skyrict@localhost:5433/skyrict_identity",
        "AI_REDIS_URL": "redis://localhost:6379/0",
    }


def test_settings_load_with_minimal_env(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.ENVIRONMENT is Environment.TEST
    # Provider-agnostic boot: no providers configured, no crash.
    assert settings.PROVIDER is None
    assert settings.FALLBACK_PROVIDER is None
    # 0.75 is exactly representable as a float - plain equality is safe.
    assert settings.CONFIDENCE_THRESHOLD == 0.75
    assert settings.RATE_LIMIT_NL_QUERY_PER_MIN == 30
    assert settings.RATE_LIMIT_TENANT_PER_MIN == 100


def test_inventory_service_url_accepted_without_prefix(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    # Compose contract (spec §6.4): the unprefixed variable name.
    monkeypatch.setenv("INVENTORY_SERVICE_URL", "http://skyrict-core:8001")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.INVENTORY_SERVICE_URL == "http://skyrict-core:8001"


def test_report_service_url_accepted_without_prefix(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    # Compose contract (spec §6.4 / SKY-80): the unprefixed variable name.
    monkeypatch.setenv("REPORT_SERVICE_URL", "http://skyrict-core:8001")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.REPORT_SERVICE_URL == "http://skyrict-core:8001"
    assert settings.REPORT_SERVICE_TIMEOUT_SECONDS == 10.0


def test_provider_without_model_rejected(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    monkeypatch.setenv("AI_PROVIDER", "openrouter")

    with pytest.raises(RuntimeError, match="MODEL is required when PROVIDER is set"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_model_without_provider_rejected(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    monkeypatch.setenv("AI_MODEL", "llama-3")

    with pytest.raises(RuntimeError, match="PROVIDER is required when MODEL is set"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_fallback_pairing_validated(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))

    with pytest.raises(RuntimeError, match="FALLBACK_MODEL is required"):
        Settings(
            PROVIDER="groq",  # type: ignore[typeddict-item]
            MODEL="llama-3",  # type: ignore[typeddict-item]
            FALLBACK_PROVIDER="openrouter",  # type: ignore[typeddict-item]
            _env_file=None,  # type: ignore[call-arg]
        )


def test_production_safety_requires_base_domain(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    env = _base_env()
    env["AI_ENVIRONMENT"] = "production"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))

    with pytest.raises(RuntimeError, match="AI_BASE_DOMAIN is required"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_anomaly_notify_emails_comma_list(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
    # Spec §4.3 "Email to admin (critical only)": comma-separated recipients
    # arrive through a plain env string, whitespace tolerant.
    monkeypatch.setenv("AI_ANOMALY_NOTIFY_EMAILS", "ops@skyrict.dev, admin@skyrict.dev ")
    monkeypatch.setenv("AI_EMAIL_SMTP_HOST", "mailpit")
    monkeypatch.setenv("AI_EMAIL_FROM_ADDR", "Skyrict <no-reply@skyrict.dev>")
    monkeypatch.setenv("AI_ANOMALY_REVIEW_BASE_URL", "https://app.skyrict.io/anomalies")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.anomaly_notify_emails == ["ops@skyrict.dev", "admin@skyrict.dev"]
    assert s.EMAIL_SMTP_HOST == "mailpit"
    assert s.EMAIL_FROM_ADDR == "Skyrict <no-reply@skyrict.dev>"
    assert s.ANOMALY_REVIEW_BASE_URL == "https://app.skyrict.io/anomalies"


def test_email_alerts_default_to_disabled(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "public.pem"
    key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    # Conservative defaults: no relay, no recipients, no button → dispatch
    # is fully off until an operator opts in.
    assert s.anomaly_notify_emails == []
    assert s.EMAIL_SMTP_HOST == ""
    assert s.ANOMALY_REVIEW_BASE_URL == ""


class TestBlankConnectionUrlsRejected:
    """A *set-but-empty* connection URL must fail in settings, not in a driver.

    `Field(...)` enforces presence, and an env var set to "" is present. That
    is not hypothetical: the IaC's `redisUrlOverride` defaults to '', so
    `deployManagedRedis=false` with the override left alone handed this service
    `AI_REDIS_URL=''` - which validated, then raised "Redis URL must specify
    one of the following schemes" at import, minutes after a green pipeline.
    DATABASE_URL fails the same way against SQLAlchemy.

    See skyrict_common.config_types and audit finding 10.
    """

    @pytest.mark.parametrize("field", ["AI_DATABASE_URL", "AI_REDIS_URL"])
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_is_rejected_and_names_the_variable(
        self, monkeypatch, tmp_path, field: str, blank: str
    ) -> None:
        key_file = tmp_path / "public.pem"
        key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
        monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
        for key, value in _base_env().items():
            if key != field:
                monkeypatch.setenv(key, value)
        # Set, but empty - the shape that defeated Field(...).
        monkeypatch.setenv(field, blank)

        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert field.removeprefix("AI_").lower() in str(excinfo.value).lower()

    def test_a_real_url_is_accepted(self, monkeypatch, tmp_path) -> None:
        # Orthogonal control: the constraint must not reject working values, or
        # this "fix" would just trade one outage for another.
        key_file = tmp_path / "public.pem"
        key_file.write_text("-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
        monkeypatch.setenv("AI_JWT_PUBLIC_KEY_PATH", str(key_file))
        for key, value in _base_env().items():
            monkeypatch.setenv(key, value)

        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.REDIS_URL == "redis://localhost:6379/0"
