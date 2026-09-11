"""CLI entrypoint for the Core service."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import typer

# services/core - the alembic.ini lives here; the CLI is invoked via
# `uv run --directory services/core core ...`, so never resolve relative to
# the process CWD (which is already services/core, making a nested path).
# cli.py lives at services/core/src/core/, so parents[2] is services/core.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

app = typer.Typer(name="core", help="Skyrict Core Service CLI")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8001, help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    log_level: str = typer.Option("info", help="Log level"),
) -> None:
    """Start the Core service."""
    import uvicorn

    uvicorn.run(
        "core.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


@app.command()
def migrate(head: str = typer.Option("head", help="Alembic target revision")) -> None:
    """Run database migrations (version table: alembic_version_core)."""
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", head],
        cwd=_PACKAGE_ROOT,
        check=True,
    )


@app.command()
def seed(
    tenant_id: str = typer.Option(
        None,
        "--tenant-id",
        help="UUID of a tenant to seed HR/Payroll defaults + reporting pack + core RBAC roles",
    ),
) -> None:
    """Seed reference + per-tenant defaults and core RBAC roles.

    Reference data (erp_currencies, core_permissions) is seeded by migration
    0001 itself, so this command always verifies those rows are present. With
    ``--tenant-id`` it additionally seeds that tenant's leave-type catalogue
    defaults, the single payroll-settings row, the Phase-1 reporting pack in
    ``erp_report_definitions``, and the five system roles in ``core_roles``
    (core.seed) - idempotent.
    """
    import asyncio

    from sqlalchemy import func, select

    from core.db.session import async_session_factory
    from core.models.core_permission import CorePermissionModel
    from core.models.erp_currency import ErpCurrencyModel

    async def _verify() -> None:
        async with async_session_factory() as session:
            currency_count = (
                await session.execute(select(func.count()).select_from(ErpCurrencyModel))
            ).scalar_one()
            permission_count = (
                await session.execute(select(func.count()).select_from(CorePermissionModel))
            ).scalar_one()
            typer.echo(f"erp_currencies: {currency_count} rows")
            typer.echo(f"core_permissions: {permission_count} rows")

    async def _seed_tenant() -> None:
        from core.seed import (
            seed_core_roles_for_tenant,
            seed_reporting_defaults,
            seed_tenant_hr_defaults,
        )

        await seed_tenant_hr_defaults(uuid.UUID(tenant_id))
        await seed_reporting_defaults(uuid.UUID(tenant_id))
        await seed_core_roles_for_tenant(uuid.UUID(tenant_id))
        typer.echo(
            f"seeded HR/Payroll defaults + reporting pack + core RBAC roles for tenant {tenant_id}"
        )

    async def _run() -> None:
        await _verify()
        if tenant_id:
            await _seed_tenant()

    asyncio.run(_run())


@app.command()
def seed_crm(
    tenant_id: str = typer.Option(
        None,
        "--tenant-id",
        help="UUID of a tenant to seed CRM demo data (defaults to the first active tenant)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Clear existing CRM data for the tenant, then reseed",
    ),
) -> None:
    """Seed 10+ demo records per CRM entity (leads/opportunities/customers/...).

    Idempotent: without ``--force`` a tenant that already has CRM customers is
    left untouched. Timestamps are staggered over the past ~90 days so the
    workspace timeline reads as real history.
    """
    import asyncio

    from sqlalchemy import select

    from core.db.session import async_session_factory
    from core.models.tenant import TenantModel

    async def _run() -> None:
        async with async_session_factory() as session:
            if tenant_id:
                target = uuid.UUID(tenant_id)
            else:
                found = (
                    await session.execute(
                        select(TenantModel)
                        .where(TenantModel.is_active.is_(True))
                        .order_by(TenantModel.created_at.asc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if found is None:
                    typer.echo("No active tenant found; pass --tenant-id explicitly.")
                    raise typer.Exit(code=1)
                target = found.id
                typer.echo(f"Using tenant {target} ({found.slug})")

        from core.seed_crm import seed_crm_demo_data

        counts = await seed_crm_demo_data(target, force=force)
        typer.echo(f"seeded CRM demo data for tenant {target}:")
        for key, value in counts.items():
            typer.echo(f"  {key}: {value}")

    asyncio.run(_run())


@app.command()
def seed_demo(
    tenant_id: str = typer.Option(
        None,
        "--tenant-id",
        help="UUID of a tenant to seed demo data (defaults to the first active tenant)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Clear existing demo data for the tenant, then reseed",
    ),
    employees: int = typer.Option(
        15,
        "--employees",
        min=1,
        help="Number of employees to seed (15 default; 50 for the payroll automation acceptance scrub)",
    ),
) -> None:
    """Seed 10+ demo records per ERP module (Finance, HR, Payroll, Sales).

    Idempotent: without --force a tenant that already has departments is
    left untouched.
    """
    import asyncio

    from sqlalchemy import select

    from core.db.session import async_session_factory
    from core.models.tenant import TenantModel

    async def _run() -> None:
        async with async_session_factory() as session:
            if tenant_id:
                target = uuid.UUID(tenant_id)
            else:
                found = (
                    await session.execute(
                        select(TenantModel)
                        .where(TenantModel.is_active.is_(True))
                        .order_by(TenantModel.created_at.asc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if found is None:
                    typer.echo("No active tenant found; pass --tenant-id explicitly.")
                    raise typer.Exit(code=1)
                target = found.id
                typer.echo(f"Using tenant {target} ({found.slug})")

        from core.seed_demo import seed_demo_data

        counts = await seed_demo_data(target, force=force, employees=employees)
        typer.echo(f"seeded demo data for tenant {target}:")
        for key, value in counts.items():
            typer.echo(f"  {key}: {value}")

    asyncio.run(_run())


@app.command()
def seed_overdue_invoices(
    tenant_id: str = typer.Option(
        ...,
        "--tenant-id",
        help="UUID of a tenant to seed overdue invoices for",
    ),
) -> None:
    """Seed overdue invoices so the A8 payment-reminder flow can be tested.

    Non-destructive and idempotent: inserts a few APPROVED/ISSUED invoices
    (``INV-OVR-*``) whose due date is in the past; existing rows are untouched.
    """
    import asyncio

    from core.seed_overdue_invoices import seed_overdue_invoices as _seed

    async def _run() -> None:
        counts = await _seed(uuid.UUID(tenant_id))
        typer.echo(f"seeded overdue invoices for tenant {tenant_id}:")
        for key, value in counts.items():
            typer.echo(f"  {key}: {value}")

    asyncio.run(_run())


@app.command()
def seed_revenue_history(
    tenant_id: str = typer.Option(
        ...,
        "--tenant-id",
        help="UUID of a tenant to seed approved invoice history for",
    ),
) -> None:
    """Seed 8 months of APPROVED invoices so the A3/A4 finance demo can test.

    Non-destructive and idempotent: backfills ``INV-HIST-*`` invoices for the
    tenant (skipping existing numbers), and does nothing when the tenant
    already has >= 3 distinct approved months (the FIN-AI-003 floor).
    """
    import asyncio

    from core.seed_revenue_history import seed_revenue_history as _seed

    async def _run() -> None:
        counts = await _seed(uuid.UUID(tenant_id))
        typer.echo(f"seeded approved invoice history for tenant {tenant_id}:")
        for key, value in counts.items():
            typer.echo(f"  {key}: {value}")

    asyncio.run(_run())


@app.command()
def provision_rbac(
    tenant_id: str = typer.Option(
        ...,
        "--tenant-id",
        help="UUID of the tenant to provision core RBAC rows for",
    ),
    payload: str = typer.Option(
        ...,
        "--payload",
        help=(
            "Path to a JSON file (or inline JSON) with the role_grants snapshot "
            "carried by the identity.tenant.provisioned / rbac.role_granted events"
        ),
    ),
) -> None:
    """Mirror identity roles + grants into core_roles / core_user_roles.

    Applies the same idempotent handler the Kafka consumer will run once the
    platform bus lands; the payload shape matches ``skyrict_events.schemas``
    (``role_grants``: role_id, role_name, permissions, is_system_role,
    user_id, scope_id).
    """
    import asyncio

    from core.events.consumers.rbac import provision_tenant_rbac

    raw = Path(payload).read_text() if Path(payload).exists() else payload
    data = json.loads(raw)
    role_grants = data["role_grants"] if isinstance(data, dict) else data

    async def _run() -> None:
        result = await provision_tenant_rbac(uuid.UUID(tenant_id), role_grants)
        counts = result.as_dict()
        typer.echo(f"provisioned tenant {tenant_id}: {counts}")

    asyncio.run(_run())


@app.command()
def retention(
    keep: int = typer.Option(
        None,
        "--keep",
        min=1,
        help="Per-definition snapshot cap (default: REPORTING_RETENTION_LIMIT, 20)",
    ),
) -> None:
    """Run one report-snapshot retention pass (manual/CI equivalent of the worker).

    Walks every tenant's definitions and prunes snapshots beyond the newest
    ``keep`` per definition (the ticket's "keeping N per definition" contract).
    """
    import asyncio

    from core.core.config import settings
    from core.db.session import async_session_factory
    from core.features.reporting.retention_worker import SnapshotRetentionWorker

    async def _run() -> None:
        keep_n = keep if keep is not None else settings.REPORTING_RETENTION_LIMIT
        outcome = await SnapshotRetentionWorker(
            async_session_factory,
            keep_n=keep_n,
        ).process_all()
        typer.echo(
            f"retention pass complete: {outcome.tenants_processed} tenants, "
            f"{outcome.snapshots_pruned} snapshots pruned (keep={keep_n})"
        )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
