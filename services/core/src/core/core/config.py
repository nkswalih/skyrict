"""Application configuration - pydantic-settings, env-driven, fail-fast on missing secrets.

Single source of truth for ALL configuration. Application code must never
call os.getenv() directly - everything routes through the ``settings`` object.
"""

from __future__ import annotations

import enum
import sys
from decimal import Decimal
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
    """All configuration loaded from environment variables.

    Prefix: CORE_ (set via .env or shell environment).
    CRITICAL vars (DATABASE_URL, JWT public key, JWKS issuer/audience) have NO
    defaults - the process refuses to start if they are missing.

    Core only VERIFIES identity-issued access tokens: it needs the public key
    and the issuer/audience the identity service signs for, never a private
    key, Redis, or an MFA key.
    """

    model_config = SettingsConfigDict(
        env_prefix="CORE_",
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
    DEFAULT_TENANT_ID: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description="default tenant ID for single-tenant or bootstrap",
    )
    BASE_DOMAIN: str = Field(
        default="",
        description=(
            "production tenant base domain, e.g. 'skyrict.com' - the first "
            "label of a Host like acme.skyrict.com is the tenant slug. Required "
            "in staging/production; ignored in dev/test which resolve tenants "
            "from the X-Tenant-Slug header injected by nginx."
        ),
    )

    # --- ERP settings ---
    DEFAULT_CURRENCY: str = Field(
        default="USD",
        description="default currency code for Money-typed amounts (ISO 4217)",
    )
    INVENTORY_ADJUST_APPROVE_THRESHOLD: Decimal = Field(
        default=Decimal("100.00"),
        description=(
            "inventory adjustments above this absolute value require approval "
            "before posting (in the tenant's default currency). Placeholder - "
            "consumed by the inventory module ticket."
        ),
    )

    # --- AI agent microservice (docs/modules/skyrict-ai/... §6.4) ---
    AI_AGENT_URL: str = Field(
        default="http://localhost:8002",
        description=(
            "base URL of the ai-agent service for /api/v1/ai/* proxying. In "
            "docker networks set CORE_AI_AGENT_URL=http://skyrict-ai-agent:8000."
        ),
    )
    AI_AGENT_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        gt=0,
        description="per-request timeout for proxied AI calls (LLMs are slow)",
    )
    AI_HR_REFRESH_INTERVAL_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "lazy-on-read TTL: when the HR attrition endpoint is read and the "
            "latest stored score's generated_at is older than this many days, the "
            "core re-scores by proxying anonymous feature vectors to ai-agent."
        ),
    )
    AI_HR_UTILIZATION_SCAN_INTERVAL_DAYS: int = Field(
        default=1,
        ge=1,
        description=(
            "lazy-on-read TTL for the leave-balance utilization scanner (8.1.4): "
            "the alert inbox is regenerated when it is read and the latest scan "
            "is older than this many days."
        ),
    )
    AI_HR_ANOMALY_SCAN_INTERVAL_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "lazy-on-read TTL for the leave-pattern anomaly detector (8.2.1): "
            "the anomaly inbox is regenerated when it is read and the latest "
            "scan is older than this many days."
        ),
    )
    AI_HR_SUGGESTION_SCAN_INTERVAL_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "lazy-on-read TTL for the smart leave-window suggestions (8.2.4): "
            "pending suggestions are regenerated when the surface is read and "
            "the latest scan is older than this many days."
        ),
    )
    AI_HR_PAYROLL_ANOMALY_SCAN_INTERVAL_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "lazy-on-read TTL for the payroll anomaly detector (HR-AI-001, Unit B): "
            "the payroll-anomaly inbox is regenerated from the latest non-void "
            "payroll run when it is read and the latest scan is older than this "
            "many days."
        ),
    )
    AI_HR_COMPLIANCE_SCAN_INTERVAL_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "lazy-on-read TTL for the compliance engine v1 (HR-AI-001, Unit C): "
            "the compliance inbox is regenerated from current people + documents "
            "when it is read and the latest scan is older than this many days."
        ),
    )
    AI_SYNC_TOKEN: str = Field(
        default="",
        description=(
            "bearer token ai-agent requires on POST /ai/inventory/embeddings/sync "
            "(SKY-70 product->embedding sync). Must match ai-agent's "
            "AI_INVENTORY_SYNC_TOKEN; empty disables the HTTP dispatch and keeps "
            "the feature fed only by the `ai-agent inventory reindex` CLI."
        ),
    )
    AI_INGEST_TOKEN: str = Field(
        default="",
        description=(
            "shared secret the ai-agent reindex/ingest CLIs present as a bearer "
            "on GET /inventory/products (SKY-70). Must match ai-agent's "
            "AI_INGEST_TOKEN; empty disables the machine-to-machine branch so "
            "only JWT + erp.inventory.read reads succeed. Never logged."
        ),
    )

    # --- Document management (SKY-87, docs/modules/documents.md) ---
    DOCS_STORAGE_BACKEND: str = Field(
        default="local",
        description=(
            "blob storage backend for uploaded documents: 'local' (dev/test "
            "default, files under DOCS_STORAGE_LOCAL_DIR) or 's3' (S3-compatible "
            "bucket). Mirrors the identity avatar storage split."
        ),
    )
    DOCS_STORAGE_LOCAL_DIR: str = Field(
        default="storage/documents",
        description="filesystem root for the local document storage backend",
    )
    DOCS_S3_BUCKET: str = Field(
        default="",
        description="S3 bucket for documents when DOCS_STORAGE_BACKEND=s3 (required)",
    )
    DOCS_S3_PREFIX: str = Field(
        default="documents",
        description="object-key prefix under which tenant document keys are stored",
    )
    DOCS_S3_REGION: str = Field(
        default="us-east-1",
        description="region for the S3-compatible bucket (endpoint_url overrides in dev)",
    )
    DOCS_S3_ENDPOINT_URL: str = Field(
        default="",
        description=(
            "optional S3-compatible endpoint (e.g. http://localhost:9000 for "
            "MinIO in dev); empty means the default AWS region endpoint."
        ),
    )
    DOCS_MAX_UPLOAD_BYTES: int = Field(
        default=26_214_400,
        ge=1,
        description="maximum accepted upload size per document version in bytes (25 MiB)",
    )
    DOCS_VIRUS_SCAN_HOOK_URL: str = Field(
        default="",
        description=(
            "optional virus-scan webhook URL invoked after an upload commits "
            "(SKY-87 stub: POSTed {document_id, tenant_id, checksum_sha256}); "
            "empty disables the hook."
        ),
    )

    # --- Payroll automation worker (HR-AUT-001, Commit 1) ---
    PAYROLL_AUTO_WORKER_ENABLED: bool = Field(
        default=True,
        description=(
            "run the in-process payroll batch worker (a background asyncio "
            "loop that claims and drains queued batches). Disabled under the "
            "test environment so integration tests drive process_once() directly."
        ),
    )
    PAYROLL_AUTO_POLL_SECONDS: float = Field(
        default=0.25,
        gt=0,
        description="interval between worker claim passes when the queue is idle",
    )
    PAYROLL_AUTO_ITEMS_PER_TICK: int = Field(
        default=10,
        ge=1,
        description="max payroll items one claim pass processes before committing/yielding",
    )
    PAYROLL_AUTO_MAX_RETRIES: int = Field(
        default=2,
        ge=1,
        description="per-item retry budget before an item is marked failed permanently",
    )

    # --- Reminder email delivery (SMTP -> Mailpit in dev) ---
    EMAIL_SMTP_HOST: str = Field(
        default="",
        description=(
            "SMTP relay host for payment-reminder email. Empty selects the "
            "log-only transport (dev/test default). Dev: 'mailpit' for the "
            "Mailpit container. Mirrors the ai-agent/identity SMTP blocks so "
            "compose can share one relay."
        ),
    )
    EMAIL_SMTP_PORT: int = Field(default=1025, description="SMTP relay port")
    EMAIL_FROM_ADDR: str = Field(
        default="Skyrict <no-reply@skyrict.dev>",
        description="From address for reminder email",
    )

    # --- Reporting endpoints (RPT-BE-001) ---
    REPORTING_QUERY_TIMEOUT_SECONDS: int = Field(
        default=30,
        ge=1,
        le=300,
        description=(
            "statement_timeout applied to every report execution (seconds). "
            "Guardrail against runaway report SQL: the timeout is set "
            "transaction-locally right before the definition query runs."
        ),
    )
    REPORTING_RESULT_CAP: int = Field(
        default=10_000,
        ge=1,
        description=(
            "max rows the UI run path returns (excess rows are truncated and "
            "flagged); CSV export streams the full result set without the cap."
        ),
    )
    REPORTING_RETENTION_ENABLED: bool = Field(
        default=True,
        description=(
            "run the in-process snapshot retention worker (a background asyncio "
            "loop that prunes snapshots beyond the per-definition limit). "
            "Disabled under the test environment so integration tests drive "
            "the retention pass directly."
        ),
    )
    REPORTING_RETENTION_LIMIT: int = Field(
        default=20,
        ge=1,
        description="number of most-recent snapshots kept per report definition",
    )
    REPORTING_RETENTION_POLL_SECONDS: float = Field(
        default=3600.0,
        gt=0,
        description="interval between retention passes while idle",
    )

    # --- Derived (loaded from files at validation time) ---
    jwt_public_key: str = ""

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
                "CORE_BASE_DOMAIN is required in staging/production so "
                "tenant subdomains (e.g. acme.skyrict.com) can be resolved "
                "from the Host header."
            )

        if errors:
            raise RuntimeError(
                "Production safety check failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return self


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings populates from env
