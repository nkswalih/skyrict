"""Full-chain migration round-trip for the AI agent (scratch database).

Applies identity's chain first (it creates ``tenants`` and owns the shared
RLS helper ``public.current_tenant_id()`` that ai-agent's 0001 references),
then core's chain (its ``erp_products`` key is the FK target of ai-agent's
0002 forecast/ABC tables), then the AI chain under ``alembic_version_ai`` -
real migrations against real Postgres, never ``create_all``. Then unwinds all
the way back to nothing and re-applies, proving the whole round-trip.

Sentinel assertions probe one representative artefact per concern: table
existence, version-table bookkeeping, RLS policies on exactly the seven
tenant-scoped tables (``agent_registry`` is global and must have NONE), the
partial unique pending index with its WHERE clause, named CHECK constraints,
the ``tenants`` FKs, the DESC ordering of the history index, and the SKY-60
supervisor seed (migration 0009). The version-table sentinel follows Alembic's
own head resolution so it survives future migrations.

The test owns a scratch database and never touches a shared test database -
it destroys the schema it builds. Event-loop discipline follows the repo
convention (tests/integration/conftest.py): each DB phase runs inside its own
``asyncio.run()`` and every connection closes before the loop exits. Skips
cleanly when no Postgres is reachable (local dev without Docker); CI provides
the service containers.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[3]  # services/ai-agent
_AI_ALEMBIC_INI = _ROOT / "alembic.ini"
_IDENTITY_ROOT = _ROOT.parent / "identity"
_IDENTITY_ALEMBIC_INI = _IDENTITY_ROOT / "alembic.ini"
_CORE_ROOT = _ROOT.parent / "core"
_CORE_ALEMBIC_INI = _CORE_ROOT / "alembic.ini"

_AI_TABLES = (
    "ai_query_log",
    "ai_suggestions",
    "ai_anomalies",
    "ai_audit_log",
    "agent_registry",
    "ai_restock_demand_stats",
    "ai_restock_settings",
    "ai_anomaly_rule_stats",
    # SKY-58 RAG tables (migration 0004)
    "ai_rag_parents",
    "ai_rag_chunks",
    "ai_episodic_memory",
    "ai_query_cache",
    "ai_eval_runs",
    # SKY-63 cached cross-module narrator digests (migration 0007)
    "ai_digest_snapshots",
    # SKY-59 LangGraph orchestration runtime (migration 0008)
    "graph_checkpoints",
    "graph_checkpoint_writes",
    "agent_interrupts",
    # SKY-61 CRM AI tables (migration 0010)
    "ai_lead_scores",
    "ai_deal_health",
    "ai_follow_up_suggestions",
    # HR-AI-003 L3 narrative snapshots (migration 0020)
    "ai_l3_narrative_snapshots",
)
_TENANT_SCOPED_TABLES = (
    "ai_query_log",
    "ai_suggestions",
    "ai_anomalies",
    "ai_audit_log",
    "ai_restock_demand_stats",
    "ai_restock_settings",
    "ai_anomaly_rule_stats",
    # SKY-59 orchestration tables carry RLS on current_tenant_id()
    "graph_checkpoints",
    "graph_checkpoint_writes",
    "agent_interrupts",
    # SKY-61 CRM AI tables carry RLS on current_tenant_id()
    "ai_lead_scores",
    "ai_deal_health",
    "ai_follow_up_suggestions",
)
# Demand stats carries composite FKs into core-owned erp_products/erp_warehouses
# and NO direct FK to tenants (cross-service idiom); only the tables below are
# direct children of ``tenants``.
_TENANT_FK_TABLES = (
    "ai_query_log",
    "ai_suggestions",
    "ai_anomalies",
    "ai_audit_log",
    "ai_restock_settings",
    "ai_anomaly_rule_stats",
    # SKY-58 tenant-scoped RAG tables (ai_eval_runs is global - no RLS)
    "ai_rag_parents",
    "ai_rag_chunks",
    "ai_episodic_memory",
    "ai_query_cache",
    # SKY-63 narrator digest snapshots are tenant-scoped (migration 0007)
    "ai_digest_snapshots",
    # SKY-59 orchestration tables are direct children of ``tenants``
    "graph_checkpoints",
    "graph_checkpoint_writes",
    "agent_interrupts",
    # SKY-61 CRM AI tables are direct children of ``tenants``
    "ai_lead_scores",
    "ai_deal_health",
    "ai_follow_up_suggestions",
    # HR-AI-003 L3 narrative snapshots are direct children of ``tenants``
    "ai_l3_narrative_snapshots",
)

_EXPECTED_CHECKS = {
    "ck_ai_suggestions_status",
    "ck_ai_suggestions_suggested_qty_positive",
    "ck_ai_suggestions_confidence_range",
    "ck_ai_anomalies_severity",
    "ck_ai_anomalies_status",
    "ck_ai_restock_settings_lead_time_positive",
    "ck_ai_restock_settings_safety_factor_positive",
    "ck_ai_restock_settings_sensitivity_range",
    "ck_ai_restock_settings_fp_threshold_range",
    "ck_ai_anomaly_rule_stats_counts_non_negative",
    "ck_agent_interrupts_status",
    # SKY-61 CRM AI constraints
    "ck_ai_lead_scores_score_range",
    "ck_ai_lead_scores_confidence_range",
    "ck_ai_deal_health_band",
    "ck_ai_deal_health_confidence_range",
    "ck_ai_follow_up_entity_type",
    "ck_ai_follow_up_type",
    "ck_ai_follow_up_status",
    "ck_ai_follow_up_confidence_range",
}


def _db_urls(base_url: str, dbname: str) -> tuple[str, str]:
    """Split ``base_url`` into an asyncpg maintenance DSN + scratch URL."""
    parts = urlsplit(base_url)
    maint_dsn = urlunsplit(("postgresql", parts.netloc, "/postgres", "", ""))
    scratch_url = urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", "", ""))
    return maint_dsn, scratch_url


def _to_dsn(sqlalchemy_url: str) -> str:
    """SQLAlchemy asyncpg URL -> plain asyncpg DSN."""
    return sqlalchemy_url.replace("+asyncpg", "")


async def _probe_database(maint_dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(maint_dsn, timeout=3)
    except (OSError, asyncpg.PostgresError):
        return False
    await conn.close()
    return True


async def _create_database(maint_dsn: str, dbname: str) -> None:
    conn = await asyncpg.connect(maint_dsn)
    try:
        # dbname is generated from uuid4().hex - no user input reaches here.
        await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


async def _drop_database(maint_dsn: str, dbname: str) -> None:
    conn = await asyncpg.connect(maint_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    finally:
        await conn.close()


async def _fetch_upgraded_artifacts(dsn: str) -> dict[str, Any]:
    """Collect every sentinel artifact in ONE connection pass."""
    artifacts: dict[str, Any] = {}
    conn = await asyncpg.connect(dsn)
    try:
        artifacts["tables"] = {
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename = ANY($1::text[])",
                list(_AI_TABLES),
            )
        }
        artifacts["version"] = await conn.fetchval("SELECT version_num FROM alembic_version_ai")

        artifacts["agent_names"] = {
            row["name"] for row in await conn.fetch("SELECT name FROM agent_registry")
        }

        artifacts["crm_assistant_enabled"] = await conn.fetchval(
            "SELECT enabled FROM agent_registry WHERE name = 'crm_assistant'"
        )

        artifacts["finance_assistant_enabled"] = await conn.fetchval(
            "SELECT enabled FROM agent_registry WHERE name = 'finance_assistant'"
        )

        artifacts["rls_tables"] = {
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND rowsecurity = true AND tablename = ANY($1::text[])",
                list(_TENANT_SCOPED_TABLES),
            )
        }
        artifacts["agent_registry_rowsecurity"] = await conn.fetchval(
            "SELECT rowsecurity FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'agent_registry'"
        )
        artifacts["policies"] = {
            row["policyname"]
            for row in await conn.fetch(
                "SELECT policyname FROM pg_policies WHERE schemaname = 'public' "
                "AND tablename = ANY($1::text[]) "
                "AND policyname LIKE 'tenant_isolation_%'",
                list(_TENANT_SCOPED_TABLES),
            )
        }

        pending_index = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_ai_suggestions_pending_unique'"
        )
        artifacts["pending_index"] = pending_index

        query_log_index = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_ai_query_log_tenant'"
        )
        artifacts["query_log_index"] = query_log_index

        artifacts["checks"] = {
            row["conname"]
            for row in await conn.fetch("SELECT conname FROM pg_constraint WHERE contype = 'c'")
        }
        artifacts["tenant_fks"] = int(
            str(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_constraint con "
                    "JOIN pg_class rel ON rel.oid = con.conrelid "
                    "WHERE con.contype = 'f' "
                    "AND confrelid = 'public.tenants'::regclass "
                    "AND rel.relname = ANY($1::text[])",
                    list(_TENANT_FK_TABLES),
                )
            )
        )
    finally:
        await conn.close()
    return artifacts


async def _collect_downgrade_state(dsn: str) -> tuple[set[str], int]:
    """Data tables still present after ``downgrade base`` + rows left in
    the AI version table (Alembic never drops its own version table)."""
    conn = await asyncpg.connect(dsn)
    try:
        tables = {
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename = ANY($1::text[])",
                list(_AI_TABLES),
            )
        }
        version_rows = int(await conn.fetchval("SELECT count(*) FROM alembic_version_ai"))
        return tables, version_rows
    finally:
        await conn.close()


async def _probe_active_tenant_enumeration(dsn: str) -> bool:
    """Insert one tenant and prove ``is_active`` rows are visible with NO GUC
    set - the premise of the scheduled anomaly scan, which enumerates active
    tenants before any request tenant context exists (permissive
    ``tenants_readable`` policy from identity 0001)."""
    slug = f"sched-probe-{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO public.tenants (name, slug) VALUES ($1, $2)",
            "Scheduled scan probe",
            slug,
        )
        visible = await conn.fetchval(
            "SELECT count(*) FROM public.tenants WHERE slug = $1 AND is_active = true", slug
        )
        return visible == 1
    finally:
        await conn.close()


class TestAiMigrationRoundTrip:
    def test_full_chain_identity_then_upgrade_downgrade_upgrade(self) -> None:
        base_url = os.environ.get("AI_DATABASE_URL", "")
        if not base_url:
            pytest.skip("AI_DATABASE_URL not set")
        maint_dsn, _ = _db_urls(base_url, "unused")
        if not asyncio.run(_probe_database(maint_dsn)):
            pytest.skip("Postgres not reachable - integration infra unavailable")

        dbname = f"skyrict_ai_test_{uuid.uuid4().hex[:8]}"
        _, scratch_url = _db_urls(base_url, dbname)

        # Ephemeral RSA keypair + Fernet key: identity's Settings fail-fasts
        # without them (same bootstrap idiom as core's integration conftest).
        key_dir = Path(tempfile.mkdtemp(prefix="skyrict-ai-mig-keys-"))
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        (key_dir / "public.pem").write_bytes(public_pem)
        (key_dir / "private.pem").write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        shared_env = os.environ.copy()
        shared_env.update(
            {
                "AI_ENVIRONMENT": "test",
                "IDENTITY_ENVIRONMENT": "test",
                "IDENTITY_DATABASE_URL": scratch_url,
                "IDENTITY_REDIS_URL": "redis://localhost:6379/0",
                "IDENTITY_JWT_PRIVATE_KEY_PATH": str(key_dir / "private.pem"),
                "IDENTITY_JWT_PUBLIC_KEY_PATH": str(key_dir / "public.pem"),
                "IDENTITY_JWKS_ISSUER": "https://auth.test.skyrict.io",
                "IDENTITY_JWKS_AUDIENCE": "api.test.skyrict.io",
                "IDENTITY_MFA_ENCRYPTION_KEY": Fernet.generate_key().decode("utf-8"),
                "CORE_ENVIRONMENT": "test",
                "CORE_DATABASE_URL": scratch_url,
                "CORE_JWT_PUBLIC_KEY_PATH": str(key_dir / "public.pem"),
                "CORE_JWKS_ISSUER": "https://auth.test.skyrict.io",
                "CORE_JWKS_AUDIENCE": "api.test.skyrict.io",
            }
        )
        ai_env = shared_env.copy()
        ai_env.update(
            {
                "AI_DATABASE_URL": scratch_url,
                "AI_JWT_PUBLIC_KEY_PATH": str(key_dir / "public.pem"),
                "AI_JWKS_ISSUER": "https://auth.test.skyrict.io",
                "AI_JWKS_AUDIENCE": "api.test.skyrict.io",
            }
        )

        def _alembic(ini: Path, cwd: Path, env: dict[str, str], *args: str) -> None:
            """Run alembic in a fresh interpreter (same idiom as core's
            test_migration_roundtrip). Revision arguments are REQUIRED -
            bare ``alembic upgrade`` is an argparse error (exit 2) before
            any database connection happens."""
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "-c", str(ini), *args],
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            assert result.returncode == 0, (
                f"alembic {' '.join(args)} failed ({ini.name}):\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        scratch_dsn = _to_dsn(scratch_url)
        asyncio.run(_drop_database(maint_dsn, dbname))
        asyncio.run(_create_database(maint_dsn, dbname))
        try:
            # Identity's chain FIRST - it owns tenants + current_tenant_id().
            _alembic(_IDENTITY_ALEMBIC_INI, _IDENTITY_ROOT, shared_env, "upgrade", "head")

            # Core's chain SECOND - erp_products is the FK target of 0002.
            _alembic(_CORE_ALEMBIC_INI, _CORE_ROOT, shared_env, "upgrade", "head")

            # AI chain up -> sentinel probes.
            _alembic(_AI_ALEMBIC_INI, _ROOT, ai_env, "upgrade", "head")

            artifacts = asyncio.run(_fetch_upgraded_artifacts(scratch_dsn))
            assert artifacts["tables"] == set(_AI_TABLES), "missing AI tables"
            # Track the real head so the sentinel survives future migrations
            # (same idiom as core's test_version_table_isolated).
            ai_head = ScriptDirectory(str(_ROOT / "alembic")).get_current_head()
            assert artifacts["version"] == ai_head
            assert "hr_copilot" in artifacts["agent_names"], "hr_copilot not seeded"
            assert "restock_advisor" in artifacts["agent_names"], "restock_advisor not seeded"
            # SKY-60 migration 0009: supervisor + delegated registry seed.
            assert "supervisor" in artifacts["agent_names"], "supervisor not seeded"
            assert "crm_assistant" in artifacts["agent_names"], "crm_assistant not seeded"
            assert "finance_assistant" in artifacts["agent_names"], "finance_assistant not seeded"
            # SKY-61 migration 0010: crm_assistant enabled (was disabled in 0009).
            assert artifacts["crm_assistant_enabled"] is True, "crm_assistant not enabled"
            # SKY-63 migration 0016: finance_assistant enabled (was disabled in 0009).
            assert artifacts["finance_assistant_enabled"] is True, "finance_assistant not enabled"

            expected_policies = {f"tenant_isolation_{t}" for t in _TENANT_SCOPED_TABLES}
            assert artifacts["rls_tables"] == set(_TENANT_SCOPED_TABLES)
            assert artifacts["policies"] == expected_policies
            assert artifacts["agent_registry_rowsecurity"] is False

            pending_index = artifacts["pending_index"]
            assert pending_index is not None
            assert "UNIQUE" in str(pending_index).upper()
            assert "pending" in str(pending_index).lower()

            query_log_index = artifacts["query_log_index"]
            assert query_log_index is not None
            assert "DESC" in str(query_log_index).upper()

            assert artifacts["checks"] >= _EXPECTED_CHECKS
            assert artifacts["tenant_fks"] == len(_TENANT_FK_TABLES)

            # Scheduled scan premise: active tenants are enumerable with no
            # request tenant context (permissive SELECT policy on tenants).
            assert asyncio.run(_probe_active_tenant_enumeration(scratch_dsn))

            # Full unwind -> nothing survives; the version table may remain
            # but must be empty (same contract as core's roundtrip test).
            _alembic(_AI_ALEMBIC_INI, _ROOT, ai_env, "downgrade", "base")
            remaining, version_rows = asyncio.run(_collect_downgrade_state(scratch_dsn))
            assert remaining == set(), f"artifacts survived downgrade: {remaining}"
            assert version_rows == 0, "alembic_version_ai still tracks revisions"

            # Re-apply proves the chain is repeatable after a full unwind.
            _alembic(_AI_ALEMBIC_INI, _ROOT, ai_env, "upgrade", "head")
        finally:
            asyncio.run(_drop_database(maint_dsn, dbname))
