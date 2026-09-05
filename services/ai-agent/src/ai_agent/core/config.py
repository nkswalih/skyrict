"""Application configuration - pydantic-settings, env-driven, fail-fast on missing secrets.

Single source of truth for ALL configuration. Application code must never
call os.getenv() directly - everything routes through the ``settings`` object.

Prefix: ``AI_`` (set via .env or shell environment). CRITICAL vars (DATABASE_URL,
REDIS_URL, JWT public key, JWKS issuer/audience) have NO defaults - the process
refuses to start if they are missing.

The service is provider-AGNOSTIC: provider credentials (AI_PROVIDER/AI_MODEL/
AI_BASE_URL/AI_API_KEY and the AI_FALLBACK_* quartet) are optional at boot.
With no providers configured, the service still starts and serves health -
AI requests then fail with a typed 503 ai_unavailable instead of crashing.
``INVENTORY_SERVICE_URL`` is accepted WITHOUT the prefix (compose contract
from the AI infrastructure spec §6.4) via a validation alias.
"""

from __future__ import annotations

import enum
import sys
from pathlib import Path  # noqa: TC003  # pydantic resolves annotations at runtime

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(enum.StrEnum):
    """Deployment environments - exactly four, no ad-hoc values."""

    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """All configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AI_",
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

    # --- Database (CRITICAL - no default) ---
    DATABASE_URL: str = Field(..., description="async PostgreSQL connection string - REQUIRED")

    # --- Redis (CRITICAL - required for distributed rate limiting) ---
    REDIS_URL: str = Field(
        ...,
        description="Redis connection URL used by the distributed rate limiter - REQUIRED",
    )

    # --- JWT verification (CRITICAL - all three required) ---
    JWT_PUBLIC_KEY_PATH: Path = Field(
        ..., description="path to RSA public key PEM for verifying identity tokens - REQUIRED"
    )
    JWKS_ISSUER: str = Field(
        ..., description="JWT issuer claim (iss) - REQUIRED, e.g. https://auth.skyrict.io"
    )
    JWKS_AUDIENCE: str = Field(
        ..., description="JWT audience claim (aud) - REQUIRED, e.g. api.skyrict.io"
    )

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(
        default=[],
        description="allowed CORS origins - must be explicit, never '*' in staging/production",
    )

    # --- Logging ---
    LOG_LEVEL: str = Field(default="INFO", description="log level")
    LOG_JSON: bool = Field(default=True, description="JSON log output")

    # --- Multi-tenancy ---
    BASE_DOMAIN: str = Field(
        default="",
        description=(
            "production tenant base domain, e.g. 'skyrict.com' - the first "
            "label of a Host like acme.skyrict.com is the tenant slug. Required "
            "in staging/production; ignored in dev/test which resolve tenants "
            "from the X-Tenant-Slug header injected by nginx."
        ),
    )

    # --- Core (inventory) service - data plane for AI features ---
    INVENTORY_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        validation_alias="INVENTORY_SERVICE_URL",
        description=(
            "base URL of the core monolith (inventory endpoints). Accepts the "
            "UNPREFIXED INVENTORY_SERVICE_URL per compose contract; in docker "
            "networks set INVENTORY_SERVICE_URL=http://skyrict-core:8001."
        ),
    )
    INVENTORY_SERVICE_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        gt=0,
        description="per-call timeout for core inventory reads",
    )

    # --- Provider configuration (ALL optional - see module docstring) ---
    PROVIDER: str | None = Field(
        default=None,
        description=(
            "primary provider key from the registry (openrouter, groq, openai, "
            "omniroute, agentrouter, generic). None = no provider configured; "
            "AI requests then return typed 503 ai_unavailable."
        ),
    )
    MODEL: str = Field(
        default="", description="primary model name, e.g. meta-llama/llama-3-8b-instruct"
    )
    BASE_URL: str = Field(
        default="",
        description=(
            "optional override of the provider's API base URL. Required for "
            "providers without a known preset (omniroute, agentrouter, generic)."
        ),
    )
    API_KEY: str = Field(default="", description="primary provider API key - never logged")
    PROVIDER_LOCAL_ONLY: bool = Field(
        default=False,
        description=(
            "data-residency clearance of the primary provider: True when it runs "
            "inside the trust boundary and may receive local-only data classes "
            "(cost/sell prices, customer/supplier names, user IDs). Cloud "
            "providers must keep this False."
        ),
    )
    PROVIDER_NATIVE: bool = Field(
        default=False,
        description=(
            "speak the provider's NATIVE (non OpenAI-compatible) chat API. "
            "Ollama is a known case: its /v1/chat/completions shim splits "
            "qwen3 reasoning into reasoning_content and returns empty content, "
            "while /api/chat works and supports think + json grammar. Only "
            "meaningful with a generic/local provider."
        ),
    )

    FALLBACK_PROVIDER: str | None = Field(
        default=None,
        description="fallback provider key from the registry (optional)",
    )
    FALLBACK_MODEL: str = Field(default="", description="fallback model name")
    FALLBACK_BASE_URL: str = Field(
        default="",
        description="optional override of the fallback provider's API base URL",
    )
    FALLBACK_API_KEY: str = Field(
        default="", description="fallback provider API key - never logged"
    )
    FALLBACK_LOCAL_ONLY: bool = Field(
        default=False,
        description="data-residency clearance of the fallback provider (see PROVIDER_LOCAL_ONLY)",
    )

    PROVIDER_TIMEOUT_SECONDS: float = Field(
        default=20.0,
        gt=0,
        description="per-provider total timeout for generation calls",
    )

    # --- Embedding configuration (SKY-58) ---
    EMBEDDING_PROVIDER: str | None = Field(
        default=None,
        description=(
            "embedding provider name: 'openai' (text-embedding-3-small via API), "
            "'ollama' (nomic-embed-text local), or None to disable embeddings"
        ),
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="embedding model identifier (OpenAI or Ollama)",
    )
    EMBEDDING_DIMENSIONS: int = Field(
        default=768,
        gt=0,
        description=(
            "output dimensions - must match the vector columns (768) for every "
            "supported provider: text-embedding-3-small via Matryoshka "
            "(768/1536 of native, ~1.5x storage of 512 at slightly better "
            "quality), gemini-embedding-2 via output_dimensionality, or "
            "ollama nomic-embed-text natively"
        ),
    )
    EMBEDDING_BASE_URL: str | None = Field(
        default=None,
        description=(
            "base URL for embedding API - Ollama: http://localhost:11434/v1, "
            "Gemini (free tier, OpenAI-compatible): "
            "https://generativelanguage.googleapis.com/v1beta/openai, "
            "OpenAI: None to use the default"
        ),
    )
    EMBEDDING_API_KEY: str | None = Field(
        default=None,
        description="API key for embedding provider (not needed for local Ollama)",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=100,
        gt=0,
        description="number of texts to embed per batch call",
    )
    EMBEDDING_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        gt=0,
        description="timeout for embedding API calls",
    )
    INGEST_TOKEN: str = Field(
        default="",
        description=(
            "bearer token used by the RAG ingestion CLI when pulling module "
            "data from the core service - never logged"
        ),
    )
    INVENTORY_SYNC_TOKEN: str = Field(
        default="",
        description=(
            "shared secret that core's post-commit product-change dispatch "
            "presents to POST /ai/inventory/embeddings/sync - must match core's "
            "CORE_AI_SYNC_TOKEN. Empty disables the sync endpoint (503). "
            "Machine-to-machine only; never logged."
        ),
    )

    # --- RAG configuration (SKY-58) ---
    RAG_CHUNK_CHILD_TOKENS: int = Field(
        default=400,
        gt=0,
        description="target token count for child chunks (embedded, searched)",
    )
    RAG_CHUNK_PARENT_TOKENS: int = Field(
        default=2000,
        gt=0,
        description="target token count for parent chunks (returned to LLM)",
    )
    RAG_CHUNK_OVERLAP_TOKENS: int = Field(
        default=60,
        ge=0,
        description="overlap tokens between adjacent child chunks (15% of 400)",
    )
    RAG_TOP_K_RETRIEVE: int = Field(
        default=20,
        gt=0,
        description="number of chunks to retrieve before reranking",
    )
    RAG_TOP_K_RETURN: int = Field(
        default=5,
        gt=0,
        description="number of chunks to return after reranking",
    )
    RAG_CACHE_TTL_SECONDS: int = Field(
        default=3600,
        gt=0,
        description="query cache TTL in seconds (1 hour)",
    )
    RAG_EPISODIC_TTL_DAYS: int = Field(
        default=90,
        gt=0,
        description="episodic memory retention in days",
    )

    # --- Inventory semantic search (SKY-70) ---
    INV_SEARCH_DEFAULT_LIMIT: int = Field(
        default=20,
        ge=1,
        le=50,
        description="max products returned by /ai/inventory/search",
    )
    INV_SEARCH_SEMANTIC_TOP_K: int = Field(
        default=50,
        gt=0,
        description="top-k products pulled from the vector index before exact/semantic merge",
    )
    INV_SEARCH_CACHE_TTL_SECONDS: int = Field(
        default=300,
        gt=0,
        description="hot-cache TTL for inventory search results (5 minutes)",
    )

    # --- AI behaviour thresholds ---
    CONFIDENCE_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description=(
            "abstention threshold - AI results below this confidence are returned "
            "as low-confidence abstentions instead of answers"
        ),
    )
    SUGGESTION_EXPIRY_DAYS: int = Field(
        default=7,
        ge=1,
        description="days before a pending restock suggestion auto-expires (spec §3.4)",
    )
    ANOMALY_AUTO_CLOSE_DAYS: int = Field(
        default=30,
        ge=1,
        description="days before an open anomaly auto-closes (spec §4.4)",
    )

    # --- Cross-module narrator (SKY-63) ---
    NARRATOR_SCHEDULER_ENABLED: bool = Field(
        default=False,
        description="start the daily narrator cron at boot (SKY-63)",
    )
    NARRATOR_SCHEDULER_TIMEZONE: str = Field(
        default="UTC",
        description="timezone for the daily narrator cron (tenant time)",
    )
    NARRATOR_ALLOW_LLM: bool = Field(
        default=True,
        description="whether the narrator may call the LLM (False forces abstentions)",
    )
    NARRATOR_DAILY_HOUR: int = Field(
        default=8, ge=0, le=23, description="hour of day for the daily narrator digest"
    )
    NARRATOR_DAILY_MINUTE: int = Field(
        default=0, ge=0, le=59, description="minute of hour for the daily narrator digest"
    )

    # --- Email delivery (SMTP) for critical anomaly alerts (spec §4.3) ---
    EMAIL_SMTP_HOST: str = Field(
        default="",
        description=(
            "SMTP relay host for critical-anomaly alerts. Empty selects the "
            "log-only transport (dev/test default). Dev: 'mailpit' or "
            "'localhost' for the Mailpit container. Mirrors identity's SMTP "
            "block so compose can share one relay."
        ),
    )
    EMAIL_SMTP_PORT: int = Field(default=1025, description="SMTP relay port")
    EMAIL_SMTP_USERNAME: str = Field(
        default="", description="SMTP auth username (optional, Mailpit needs none)"
    )
    EMAIL_SMTP_PASSWORD: str = Field(
        default="", description="SMTP auth password (optional, Mailpit needs none)"
    )
    EMAIL_SMTP_USE_TLS: bool = Field(
        default=False, description="enable STARTTLS when connecting to the relay"
    )
    EMAIL_FROM_ADDR: str = Field(
        default="Skyrict <no-reply@skyrict.dev>",
        description="From address for AI notification email",
    )

    # --- Critical-anomaly recipients ---
    ANOMALY_NOTIFY_EMAILS: str = Field(
        default="",
        description=(
            "admin recipients of critical-anomaly + escalation alerts, comma-"
            "separated (spec §4.3 'Email to admin (critical only)'). Empty "
            "disables dispatch even when SMTP is configured. Sent only for "
            "tenants with ai_restock_settings.email_alerts_enabled = true. "
            "Kept as a raw string: pydantic-settings tries to JSON-decode any "
            "list-typed env var, which would break plain comma syntax."
        ),
    )
    ANOMALY_REVIEW_BASE_URL: str = Field(
        default="",
        description=(
            "optional base URL for the 'Review anomaly' button, e.g. "
            "https://app.skyrict.io/anomalies. Empty omits the button."
        ),
    )
    ANOMALY_SCAN_SERVICE_TOKEN: str = Field(
        default="",
        description=(
            "bearer token the scheduled anomaly scan (spec §4.3) presents to "
            "core's inventory API. A background task has no user JWT, so it "
            "authenticates with this service token + per-tenant X-Tenant-Slug "
            "instead. Empty disables the scheduled pass (log-only), mirroring "
            "the log-only SMTP default."
        ),
    )

    # --- CRM follow-up scan (SKY-61) ---
    CRM_SCAN_SERVICE_TOKEN: str = Field(
        default="",
        description=(
            "bearer token the hourly CRM follow-up scan presents to core's "
            "CRM API. A background task has no user JWT, so it authenticates "
            "with this service token + per-tenant X-Tenant-Slug instead. Empty "
            "disables the scheduled scan (log-only)."
        ),
    )
    CRM_SCAN_STALE_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "number of days without activity before an entity is considered "
            "stale and eligible for a follow-up suggestion."
        ),
    )

    # --- Rate limits (spec §5.4) ---
    RATE_LIMIT_NL_QUERY_PER_MIN: int = Field(
        default=30, ge=1, description="NL queries per minute per user"
    )
    RATE_LIMIT_RAG_SEARCH_PER_MIN: int = Field(
        default=30, ge=1, description="RAG semantic searches per minute per user"
    )
    RATE_LIMIT_INV_SEARCH_PER_MIN: int = Field(
        default=30, ge=1, description="inventory product searches per minute per user"
    )
    RATE_LIMIT_APPROVAL_PER_MIN: int = Field(
        default=10, ge=1, description="suggestion approvals/rejections per minute per user"
    )
    RATE_LIMIT_ANOMALY_REVIEW_PER_MIN: int = Field(
        default=10, ge=1, description="anomaly resolve/dismiss/escalate per minute per user"
    )
    RATE_LIMIT_HR_COPILOT_PER_MIN: int = Field(
        default=20, ge=1, description="HR Copilot chat messages per minute per user"
    )
    RATE_LIMIT_CHAT_PER_MIN: int = Field(
        default=20, ge=1, description="supervisor chat turns per minute per user"
    )
    RATE_LIMIT_CRM_PER_MIN: int = Field(
        default=15, ge=1, description="CRM AI calls (score/health/list) per minute per user"
    )
    RATE_LIMIT_CRM_APPLY_PER_MIN: int = Field(
        default=10, ge=1, description="follow-up apply/dismiss actions per minute per user"
    )
    RATE_LIMIT_TENANT_PER_MIN: int = Field(
        default=100, ge=1, description="total AI calls per minute per tenant"
    )
    RATE_LIMIT_SCAN_PER_HOUR: int = Field(
        default=1, ge=1, description="background/manual suggestion scans per hour per tenant"
    )
    RATE_LIMIT_FAIL_CLOSED: bool = Field(
        default=False,
        description=(
            "when True, Redis unavailability blocks AI requests instead of "
            "failing open (platform posture is fail-open with a warning)"
        ),
    )

    # --- Derived (loaded from files at validation time) ---
    jwt_public_key: str = ""

    @property
    def anomaly_notify_emails(self) -> list[str]:
        """Parsed non-empty critical-alert recipients from the env string."""
        return [item.strip() for item in self.ANOMALY_NOTIFY_EMAILS.split(",") if item.strip()]

    # ------------------------------------------------------------------
    # Validators - run in definition order (pydantic v2)
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def load_public_key(self) -> Settings:
        """Load the JWT public key file and fail immediately if missing/unreadable."""
        path: Path = self.JWT_PUBLIC_KEY_PATH
        errors: list[str] = []

        if not path.exists():
            errors.append(f"JWT_PUBLIC_KEY_PATH: file not found at {path}")
        elif not path.is_file():
            errors.append(f"JWT_PUBLIC_KEY_PATH: path is not a file ({path})")
        else:
            try:
                content = path.read_text(encoding="utf-8")
                if "PUBLIC KEY" not in content:
                    errors.append("JWT_PUBLIC_KEY_PATH: file does not appear to contain a PEM key")
                else:
                    self.jwt_public_key = content
            except OSError as exc:
                errors.append(f"JWT_PUBLIC_KEY_PATH: cannot read {path}: {exc}")

        if errors:
            print(
                f"FATAL: {len(errors)} configuration error(s):\n"
                + "\n".join(f"  - {e}" for e in errors),
                file=sys.stderr,
            )
            sys.exit(1)

        return self

    @model_validator(mode="after")
    def validate_provider_pairing(self) -> Settings:
        """A named provider must always come with a model name."""
        errors: list[str] = []
        if self.PROVIDER is not None and not self.MODEL.strip():
            errors.append("MODEL is required when PROVIDER is set")
        if self.FALLBACK_PROVIDER is not None and not self.FALLBACK_MODEL.strip():
            errors.append("FALLBACK_MODEL is required when FALLBACK_PROVIDER is set")
        if self.PROVIDER is None and self.MODEL.strip():
            errors.append("PROVIDER is required when MODEL is set")
        if self.FALLBACK_PROVIDER is None and self.FALLBACK_MODEL.strip():
            errors.append("FALLBACK_PROVIDER is required when FALLBACK_MODEL is set")

        if errors:
            raise RuntimeError(
                "Invalid AI provider configuration:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        return self

    @model_validator(mode="after")
    def production_safety(self) -> Settings:
        """
        Fail-fast guards that apply ONLY in staging and production.

        Runs after load_public_key so all fields are populated.
        Checks:
          1. The public key must not point at committed test fixtures.
          2. DEBUG must be False.
          3. CORS_ORIGINS must not contain wildcard '*'.
          4. BASE_DOMAIN must be set (tenant subdomain resolution).
        """
        if self.ENVIRONMENT not in (Environment.STAGING, Environment.PRODUCTION):
            return self

        errors: list[str] = []

        if "tests/fixtures" in self.JWT_PUBLIC_KEY_PATH.as_posix():
            errors.append(
                "Refusing to start: JWT_PUBLIC_KEY_PATH points at a public test "
                "fixture. Production and staging must use a secret-manager-"
                "provisioned key, never the committed dev/test keypair."
            )

        if self.DEBUG:
            errors.append(
                "Refusing to start: DEBUG=true is not allowed in staging/production. "
                "Set DEBUG=false or omit it entirely."
            )

        if "*" in self.CORS_ORIGINS:
            errors.append(
                "Refusing to start: CORS_ORIGINS contains '*' which is not "
                "allowed in staging/production. List explicit origins instead."
            )

        if not self.BASE_DOMAIN.strip():
            errors.append(
                "AI_BASE_DOMAIN is required in staging/production so "
                "tenant subdomains (e.g. acme.skyrict.com) can be resolved "
                "from the Host header."
            )

        if errors:
            raise RuntimeError(
                "Production safety check failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return self


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings populates from env
