"""Full-chain migration round-trip against a scratch database (HR-BE-002 §9.3 #1).

Closes the DoD's "migration applies up and down" checkbox for the WHOLE chain,
not the newest link in isolation: identity base schema -> core ``upgrade head``
(all 7 revisions) -> core ``downgrade base`` (all the way back to nothing) ->
core ``upgrade head`` again — on a disposable scratch database created by the
test and dropped afterwards.

Why this exists: the thread that produced migration 0007 found a schema that
had silently diverged from what the migration files claimed (``ref_id`` uuid
drift), and the 0006 downgrade — dropping audit triggers, trigger functions,
RLS policies, seeded permission rows, and tenant tables in a six-step order —
had never been exercised as part of a longer chain unwind. A partial test
("upgrade head -> downgrade -1 -> upgrade head") would only prove the newest
link round-trips; this proves the whole chain does. If ``downgrade base`` ever
breaks, the fix is a new corrective migration or a documented accepted risk —
never an edit to an already-applied migration file.

Sentinel assertions probe one representative artefact of each migration:
``erp_leave_movements.ref_id`` varchar(64) (the 0007 drift regression guard),
the native enums (0002/0004/0005), RLS policies (0001..0006), the seeded ERP
permission keys (0006), ``erp_sequences`` (0006), the audit hash trigger (0006),
and ``current_tenant_id()`` (0001, shared with identity).

The test owns a scratch database and never touches the shared test database
(``migrated_schema``): it destroys the schema it builds. ``asyncio.run()`` wraps
each DB phase and disposes every engine before the loop closes (the fixture
discipline from tests/integration/conftest.py).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[3]  # services/core
_CORE_ALEMBIC_INI = _ROOT / "alembic.ini"
_IDENTITY_ALEMBIC_INI = _ROOT.parent / "identity" / "alembic.ini"

_ENUM_TYPES = (
    "erp_employment_status",
    "erp_leave_request_status",
    "erp_payroll_run_status",
    "erp_payroll_rounding",
    "erp_stock_movement_type",
    "erp_attendance_status",
)
_ERP_PERMISSION_KEYS = (
    "erp.hr.read",
    "erp.hr.write",
    "erp.hr.approve",
    "erp.payroll.read",
    "erp.payroll.write",
    "erp.payroll.approve",
    # 0021: HR & Payroll AI slice (docs/modules/skyrict-ai/hr-payroll-ai-features.md §3).
    "erp.hr.ai.read",
    "erp.hr.ai.individual",
    "erp.hr.ai.acknowledge",
    "erp.hr.ai.copilot",
    # 0023: ai-agent eval-harness record permission (HR-AI-002, SKY-72).
    "erp.hr.ai.eval",
    # 0025 (merged from dev: SKY-68 inventory advisors, renumbered past HR-AI-002).
    "erp.inventory.ai.approve",
)

# 0021: tenant-scoped tables created by the HR/Payroll AI migrations.
_HR_AI_TABLES = (
    "ai_hr_attrition_scores",
    "ai_payroll_anomaly_log",
    "ai_compliance_checks",
    "erp_employee_documents",
    # 0022: HR-AI-002 wave-2 tables (data quality, utilization alerts,
    # leave-pattern anomalies, leave suggestions, model eval harness).
    "ai_hr_quality_scores",
    "ai_hr_utilization_alerts",
    "ai_hr_leave_anomalies",
    "ai_hr_leave_suggestions",
    "hr_eval_runs",
    # 0024: HR-AI-002 pattern-engine input tables (holidays + blackouts).
    "ai_hr_public_holidays",
    "ai_hr_leave_blackout_periods",
)


def _db_urls(base_url: str, dbname: str) -> tuple[str, str]:
    """Split ``base_url`` into a maintenance DSN (asyncpg) and the scratch URL."""
    parts = urlsplit(base_url)
    netloc = parts.netloc
    maint_dsn = urlunsplit(("postgresql", netloc, "/postgres", "", ""))
    scratch_url = urlunsplit((parts.scheme, netloc, f"/{dbname}", "", ""))
    return maint_dsn, scratch_url


async def _probe_database(maint_dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(maint_dsn, timeout=5)
        await conn.close()
        return True
    except Exception:
        return False


async def _create_scratch_db(maint_dsn: str, dbname: str) -> None:
    conn = await asyncpg.connect(maint_dsn)
    try:
        await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


async def _drop_scratch_db(maint_dsn: str, dbname: str) -> None:
    conn = await asyncpg.connect(maint_dsn)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{dbname}' AND pid <> pg_backend_pid()"
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    finally:
        await conn.close()


def _run_alembic(ini: Path, cmd: list[str], overrides: dict[str, str], *, cwd: Path) -> None:
    """Run alembic in a fresh interpreter with env overrides (mirrors migrated_schema)."""
    env = {**os.environ, **overrides}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini), *cmd],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(cmd)} failed ({ini.name}):\n"
        f"{result.stderr.strip() or result.stdout.strip()}"
    )


async def _assert_upgraded_schema(url: str) -> None:
    """One probe per migration artefact after ``upgrade head``."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version_core"))
            ).scalar_one()
            assert version == "0025", f"head is {version}, expected 0025"

            # 0018: erp.leave.self is a first-class catalog permission.
            perm_row = (
                await conn.execute(
                    text("SELECT description FROM core_permissions WHERE key = 'erp.leave.self'")
                )
            ).scalar_one_or_none()
            assert perm_row is not None, "0018 must register erp.leave.self"

            # 0019: erp_leave_policies table exists with correct schema.
            policy_table = (
                await conn.execute(text("SELECT to_regclass('public.erp_leave_policies')"))
            ).scalar_one()
            assert policy_table is not None, "0019 must create erp_leave_policies table"

            policy_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'erp_leave_policies' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            expected_cols = {
                "tenant_id",
                "id",
                "casual_days_per_year",
                "sick_days_per_year",
                "effective_from",
                "last_accrual_year",
                "created_at",
                "updated_at",
            }
            assert expected_cols <= set(policy_cols), (
                f"erp_leave_policies missing columns: {expected_cols - set(policy_cols)}"
            )

            # 0025: erp.inventory.ai.approve is a first-class catalog permission
            # (SKY-68 advisors, merged from dev and renumbered after 0024).
            ai_approve_row = (
                await conn.execute(
                    text(
                        "SELECT description FROM core_permissions "
                        "WHERE key = 'erp.inventory.ai.approve'"
                    )
                )
            ).scalar_one_or_none()
            assert ai_approve_row is not None, "0025 must register erp.inventory.ai.approve"

            row = (
                await conn.execute(
                    text(
                        "SELECT data_type, character_maximum_length "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'erp_leave_movements' "
                        "AND column_name = 'ref_id'"
                    )
                )
            ).one()
            assert row[0] == "character varying", f"ref_id type is {row[0]}, expected varchar"
            assert row[1] == 64, f"ref_id length is {row[1]}, expected 64"

            enums = (
                (
                    await conn.execute(
                        text(
                            "SELECT typname FROM pg_type "
                            "WHERE typtype = 'e' AND typname = ANY(:names)"
                        ),
                        {"names": list(_ENUM_TYPES)},
                    )
                )
                .scalars()
                .all()
            )
            assert set(enums) == set(_ENUM_TYPES)

            policy_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_policies "
                        "WHERE schemaname = 'public' "
                        "AND policyname = 'tenant_isolation_erp_employees'"
                    )
                )
            ).scalar_one()
            assert policy_count == 1

            attendance_policy_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_policies "
                        "WHERE schemaname = 'public' "
                        "AND policyname = 'tenant_isolation_erp_attendance_records'"
                    )
                )
            ).scalar_one()
            assert attendance_policy_count == 1, "attendance RLS policy missing after upgrade head"

            attendance_unique_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_indexes "
                        "WHERE schemaname = 'public' "
                        "AND tablename = 'erp_attendance_records' "
                        "AND indexdef LIKE '%UNIQUE%'"
                        "AND indexdef LIKE '%employee_id%'"
                        "AND indexdef LIKE '%work_date%'"
                    )
                )
            ).scalar_one()
            assert attendance_unique_count >= 1, (
                "(tenant_id, employee_id, work_date) unique constraint missing"
            )

            key_count = (
                await conn.execute(
                    text("SELECT count(*) FROM core_permissions WHERE key = ANY(:keys)"),
                    {"keys": list(_ERP_PERMISSION_KEYS)},
                )
            ).scalar_one()
            assert key_count == len(_ERP_PERMISSION_KEYS)

            assert (
                await conn.execute(text("SELECT to_regclass('public.erp_sequences')"))
            ).scalar_one() is not None

            func_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_proc "
                        "WHERE proname = 'current_tenant_id' "
                        "AND pronamespace = 'public'::regnamespace"
                    )
                )
            ).scalar_one()
            assert func_count == 1

            trigger_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger "
                        "WHERE tgname = 'core_audit_logs_hash_chain' "
                        "AND NOT tgisinternal"
                    )
                )
            ).scalar_one()
            assert trigger_count == 1

            for tgname in (
                "erp_leave_movements_append_only",
                "erp_leave_movements_guard_negative",
            ):
                tg_count = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM pg_trigger "
                            "WHERE tgname = :name AND NOT tgisinternal"
                        ),
                        {"name": tgname},
                    )
                ).scalar_one()
                assert tg_count == 1, f"trigger {tgname} missing after upgrade head"

            neg_fn_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_proc "
                        "WHERE proname = 'erp_leave_movements_guard_negative' "
                        "AND prosecdef"
                    )
                )
            ).scalar_one()
            assert neg_fn_count == 1, "negative-guard function must be SECURITY DEFINER"

            # 0021: HR & Payroll AI tables exist, are tenant-scoped with RLS,
            # and the four erp.hr.ai.* permissions are registered.
            for table in _HR_AI_TABLES:
                regclass = (
                    await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})
                ).scalar_one()
                assert regclass is not None, f"0021 must create {table}"

            rls_tables = (
                (
                    await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname = 'public' AND rowsecurity = true "
                            "AND tablename = ANY(:names)"
                        ),
                        {"names": list(_HR_AI_TABLES)},
                    )
                )
                .scalars()
                .all()
            )
            assert set(rls_tables) == set(_HR_AI_TABLES), (
                f"HR-AI tables missing RLS: {set(_HR_AI_TABLES) - set(rls_tables)}"
            )
    finally:
        await engine.dispose()


async def _assert_downgraded_to_base(url: str) -> None:
    """After ``downgrade base`` every core table is gone; the version table
    may survive but must be empty (Alembic never drops its version table)."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            version_rows = (
                await conn.execute(text("SELECT count(*) FROM alembic_version_core"))
            ).scalar_one()
            assert version_rows == 0, "alembic_version_core still tracks revisions"

            for table in (
                "public.erp_leave_movements",
                "public.erp_employees",
                "public.core_permissions",
                "public.erp_sequences",
            ):
                regclass = (await conn.execute(text(f"SELECT to_regclass('{table}')"))).scalar_one()
                assert regclass is None, f"{table} still exists after downgrade base"

            for table in _HR_AI_TABLES:
                regclass = (
                    await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})
                ).scalar_one()
                assert regclass is None, f"{table} still exists after downgrade base"

            func_count = (
                await conn.execute(
                    text("SELECT count(*) FROM pg_proc WHERE proname LIKE 'erp_leave_movements_%'")
                )
            ).scalar_one()
            assert func_count == 0, "leave-movement trigger functions survive downgrade"
    finally:
        await engine.dispose()


def test_core_migration_chain_round_trips_up_down_up() -> None:
    """upgrade head -> downgrade base -> upgrade head must reproduce the schema."""
    base_url = os.environ["CORE_DATABASE_URL"]
    dbname = f"skyrict_core_rt_{uuid.uuid4().hex[:12]}"
    maint_dsn, scratch_url = _db_urls(base_url, dbname)

    if not asyncio.run(_probe_database(maint_dsn)):
        pytest.skip(f"database unavailable: {maint_dsn}")

    try:
        asyncio.run(_create_scratch_db(maint_dsn, dbname))

        # Identity base schema first: core's 0001 FKs tenants(id) and shares
        # current_tenant_id(), so identity's chain must exist (as in production).
        _run_alembic(
            _IDENTITY_ALEMBIC_INI,
            ["upgrade", "head"],
            {"IDENTITY_DATABASE_URL": scratch_url},
            cwd=_IDENTITY_ALEMBIC_INI.parent,
        )

        _run_alembic(
            _CORE_ALEMBIC_INI,
            ["upgrade", "head"],
            {"CORE_DATABASE_URL": scratch_url},
            cwd=_CORE_ALEMBIC_INI.parent,
        )
        asyncio.run(_assert_upgraded_schema(scratch_url))

        _run_alembic(
            _CORE_ALEMBIC_INI,
            ["downgrade", "base"],
            {"CORE_DATABASE_URL": scratch_url},
            cwd=_CORE_ALEMBIC_INI.parent,
        )
        asyncio.run(_assert_downgraded_to_base(scratch_url))

        _run_alembic(
            _CORE_ALEMBIC_INI,
            ["upgrade", "head"],
            {"CORE_DATABASE_URL": scratch_url},
            cwd=_CORE_ALEMBIC_INI.parent,
        )
        asyncio.run(_assert_upgraded_schema(scratch_url))
    finally:
        asyncio.run(_drop_scratch_db(maint_dsn, dbname))
