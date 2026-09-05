"""Full-chain migration round-trip against a scratch database (HR-BE-002 §9.3 #1).

Closes the DoD's "migration applies up and down" checkbox for the WHOLE chain,
not the newest link in isolation: identity base schema -> core ``upgrade head``
(all 7 revisions) -> core ``downgrade base`` (all the way back to nothing) ->
core ``upgrade head`` again - on a disposable scratch database created by the
test and dropped afterwards.

Why this exists: the thread that produced migration 0007 found a schema that
had silently diverged from what the migration files claimed (``ref_id`` uuid
drift), and the 0006 downgrade - dropping audit triggers, trigger functions,
RLS policies, seeded permission rows, and tenant tables in a six-step order -
had never been exercised as part of a longer chain unwind. A partial test
("upgrade head -> downgrade -1 -> upgrade head") would only prove the newest
link round-trips; this proves the whole chain does. If ``downgrade base`` ever
breaks, the fix is a new corrective migration or a documented accepted risk -
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
    # 0025: inventory AI approve permission (SKY-68, renumbered on HR-AI-002).
    "erp.inventory.ai.approve",
    # 0031: payroll automation permissions (HR-AUT-001).
    "erp.payroll.ai.read",
    "erp.payroll.ai.run",
    "erp.payroll.ai.notify",
    "erp.payroll.ai.approve",
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
    # 0031: payroll automation engine tables (HR-AUT-001, Commit 1).
    "ai_payroll_batch_runs",
    "ai_payroll_batch_items",
    # 0032: benefit plans + elections (HR-AUT-001, pre-flight finish-up).
    "erp_benefit_plans",
    "erp_benefit_elections",
    # 0033: payroll notifications + schedules (HR-AUT-001, Commit 3).
    "ai_payroll_notifications",
    "ai_payroll_notification_prefs",
    "ai_payroll_schedules",
    # 0035: payslip review queue (HR-AUT-001, Commit 2).
    "erp_payslip_reviews",
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


async def _insert_tenants(url: str) -> list[str]:
    """Insert two tenants BEFORE the core chain runs (RPT-DATA-001 seeding probe).

    Identity's chain creates ``tenants`` but no rows; 0036 seeds the Phase-1
    report pack into tenants that already exist at migration time. Two rows
    here let the round-trip assert each of them gets exactly the 12-definition
    pack - once, idempotently, on both the first and the re-run upgrade.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, plan_tier, is_active) "
                    "VALUES (:id, :name, :slug, 'free', true)"
                ),
                [
                    {"id": uuid.UUID(tenant_a), "name": "Tenant A", "slug": f"rt-a-{tenant_a[:8]}"},
                    {"id": uuid.UUID(tenant_b), "name": "Tenant B", "slug": f"rt-b-{tenant_b[:8]}"},
                ],
            )
            await conn.commit()
        return [tenant_a, tenant_b]
    finally:
        await engine.dispose()


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


async def _assert_upgraded_schema(url: str, tenant_ids: list[str] | None = None) -> None:
    """One probe per migration artefact after ``upgrade head``.

    ``tenant_ids`` (when given) are tenants that already existed when the core
    chain ran - 0036 must have seeded the Phase-1 report pack into each.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version_core"))
            ).scalar_one()
            assert version == "0037", f"head is {version}, expected 0037"

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

            # 0025: erp.inventory.ai.approve is a first-class catalog permission.
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

            # 0031: payroll automation columns on settings + employees.
            settings_col = (
                await conn.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'erp_payroll_settings' "
                        "AND column_name = 'ai_automation_enabled'"
                    )
                )
            ).one_or_none()
            assert settings_col is not None, (
                "0031 must add erp_payroll_settings.ai_automation_enabled"
            )
            assert settings_col[0] == "boolean"

            for col_name in ("bank_account", "bank_name"):
                bank_col = (
                    await conn.execute(
                        text(
                            "SELECT data_type FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'erp_employees' "
                            "AND column_name = :name"
                        ),
                        {"name": col_name},
                    )
                ).one_or_none()
                assert bank_col is not None, f"0031 must add erp_employees.{col_name}"
                assert bank_col[0] == "character varying"

            # 0032: benefit catalogue — columns + status/type constraints.
            plan_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'erp_benefit_plans' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "tenant_id",
                "id",
                "plan_code",
                "name",
                "plan_type",
                "monthly_cost_cents",
                "is_active",
                "effective_from",
            }.issubset(set(plan_cols)), plan_cols

            election_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'erp_benefit_elections' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "tenant_id",
                "id",
                "employee_id",
                "plan_id",
                "status",
                "effective_from",
            }.issubset(set(election_cols)), election_cols

            plan_type_check = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.erp_benefit_plans'::regclass "
                        "AND conname = 'ck_erp_benefit_plans_type'"
                    )
                )
            ).scalar_one()
            assert plan_type_check == 1, "0032 must add the plan_type check constraint"

            election_status_check = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.erp_benefit_elections'::regclass "
                        "AND conname = 'ck_erp_benefit_elections_status'"
                    )
                )
            ).scalar_one()
            assert election_status_check == 1, "0032 must add the election status check constraint"

            # 0033: notifications + schedules — tables, dedupe constraint, checks.
            notif_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'ai_payroll_notifications' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "tenant_id",
                "id",
                "recipient_user_id",
                "event_type",
                "dedupe_key",
                "in_app",
                "email_stub",
                "subject",
                "body",
                "batch_id",
                "run_id",
                "employee_id",
                "created_at",
            }.issubset(set(notif_cols)), notif_cols
            notif_dedupe = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.ai_payroll_notifications'::regclass "
                        "AND conname = 'uq_ai_payroll_notifications_dedupe'"
                    )
                )
            ).scalar_one()
            assert notif_dedupe == 1, "0033 must add the notification dedupe constraint"

            pref_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'ai_payroll_notification_prefs' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "tenant_id",
                "user_id",
                "in_app_on",
                "email_on",
                "updated_at",
            }.issubset(set(pref_cols)), pref_cols

            schedule_cols = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' "
                            "AND table_name = 'ai_payroll_schedules' "
                            "ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "tenant_id",
                "id",
                "name",
                "cron_expression",
                "enabled",
                "last_fired_at",
                "next_run_at",
                "created_at",
                "updated_at",
            }.issubset(set(schedule_cols)), schedule_cols

            # 0034: payroll accrual JE bridge (HR-AUT-001, Commit 4).
            je_status_col = (
                await conn.execute(
                    text(
                        "SELECT data_type, character_maximum_length "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'erp_payroll_runs' "
                        "AND column_name = 'je_bridge_status'"
                    )
                )
            ).one_or_none()
            assert je_status_col is not None, "0034 must add erp_payroll_runs.je_bridge_status"
            assert je_status_col[0] == "character varying", je_status_col
            assert je_status_col[1] == 16, je_status_col

            je_status_check = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.erp_payroll_runs'::regclass "
                        "AND conname = 'ck_erp_payroll_runs_je_bridge_status'"
                    )
                )
            ).scalar_one()
            assert je_status_check == 1, "0034 must add the je_bridge_status check constraint"

            je_bridge_col = (
                await conn.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'erp_payroll_settings' "
                        "AND column_name = 'je_bridge_enabled'"
                    )
                )
            ).one_or_none()
            assert je_bridge_col is not None, "0034 must add erp_payroll_settings.je_bridge_enabled"
            assert je_bridge_col[0] == "boolean", je_bridge_col

            # 0035: payslip review queue (HR-AUT-001, Commit 2).
            review_table = (
                await conn.execute(text("SELECT to_regclass('public.erp_payslip_reviews')"))
            ).scalar_one()
            assert review_table is not None, "0035 must create erp_payslip_reviews table"

            review_cols = {
                row[0]
                for row in await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'erp_payslip_reviews'"
                    )
                )
            }
            assert {
                "tenant_id",
                "id",
                "run_id",
                "employee_id",
                "employee_number",
                "employee_name",
                "gross",
                "deductions",
                "net",
                "status",
                "version",
                "rejected_reason",
                "reviewed_by",
                "reviewed_at",
                "rejected_by",
                "rejected_at",
                "created_at",
                "updated_at",
            }.issubset(set(review_cols)), review_cols

            review_status_check = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.erp_payslip_reviews'::regclass "
                        "AND conname = 'ck_erp_payslip_reviews_status'"
                    )
                )
            ).scalar_one()
            assert review_status_check == 1, (
                "0035 must add the payslip review status check constraint"
            )

            # 0036: reporting data layer (RPT-DATA-001).
            for table in ("erp_report_definitions", "erp_report_snapshots"):
                regclass = (
                    await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})
                ).scalar_one()
                assert regclass is not None, f"0036 must create {table}"

            for policy_name in (
                "tenant_isolation_erp_report_definitions",
                "tenant_isolation_erp_report_snapshots",
            ):
                policy_count = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM pg_policies "
                            "WHERE schemaname = 'public' AND policyname = :name"
                        ),
                        {"name": policy_name},
                    )
                ).scalar_one()
                assert policy_count == 1, f"0036 must create RLS policy {policy_name}"

            reports_perm = (
                await conn.execute(
                    text("SELECT description FROM core_permissions WHERE key = 'erp.reports.read'")
                )
            ).scalar_one_or_none()
            assert reports_perm is not None, "0036 must register erp.reports.read"

            for constraint in (
                "uq_erp_report_definitions_tenant_slug",
                "uq_erp_report_snapshots_tenant_definition_period",
                "fk_erp_report_snapshots_definition",
            ):
                snip_constraint = (
                    await conn.execute(
                        text("SELECT count(*) FROM pg_constraint WHERE conname = :name"),
                        {"name": constraint},
                    )
                ).scalar_one()
                assert snip_constraint == 1, f"0036 must add {constraint}"

            if tenant_ids is not None:
                # 0036 seeds the Phase-1 pack into tenants that existed at
                # migration time - 12 definitions each, gated by erp.reports.read.
                rows = (
                    await conn.execute(
                        text(
                            "SELECT tenant_id, count(*), min(permission_key), max(permission_key) "
                            "FROM erp_report_definitions "
                            "GROUP BY tenant_id ORDER BY tenant_id"
                        )
                    )
                ).all()
                assert {str(r[0]) for r in rows} == set(tenant_ids)
                for r in rows:
                    assert r[1] == 12, f"tenant {r[0]} has {r[1]} report definitions"
                    assert r[2] == "erp.reports.read", r
                    assert r[3] == "erp.reports.read", r

            # 0037: stock-health analytics (SKY-71) - the movement-trend index
            # and the erp.inventory.cost permission gate. (Renumbered from
            # 0031/0032 after merging the reporting data layer in 0036; the
            # snapshot persistence previously shipped here was dropped because
            # dev's 0036 owns the erp_report_snapshots table.)
            mv_index_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_indexes "
                        "WHERE schemaname = 'public' "
                        "AND tablename = 'erp_stock_movements' "
                        "AND indexname = 'ix_erp_stock_movements_tenant_wh_type_created'"
                    )
                )
            ).scalar_one()
            assert mv_index_count == 1, "0037 must create the movement analytics index"

            cost_perm = (
                await conn.execute(
                    text(
                        "SELECT description FROM core_permissions WHERE key = 'erp.inventory.cost'"
                    )
                )
            ).scalar_one_or_none()
            assert cost_perm is not None, "0037 must register erp.inventory.cost"
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
                "public.erp_report_definitions",
                "public.erp_report_snapshots",
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

        # Two tenants pre-date 0036, so the migration's per-tenant report
        # seeding is exercised (RPT-DATA-001).
        tenant_ids = asyncio.run(_insert_tenants(scratch_url))

        _run_alembic(
            _CORE_ALEMBIC_INI,
            ["upgrade", "head"],
            {"CORE_DATABASE_URL": scratch_url},
            cwd=_CORE_ALEMBIC_INI.parent,
        )
        asyncio.run(_assert_upgraded_schema(scratch_url, tenant_ids))

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
        asyncio.run(_assert_upgraded_schema(scratch_url, tenant_ids))
    finally:
        asyncio.run(_drop_scratch_db(maint_dsn, dbname))
