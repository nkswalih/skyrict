"""Service layer for dashboard layout and report operations."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from core.core.audit_events import REPORT_CREATED, REPORT_EXPORTED
from core.features.reporting.params import build_report_binds, resolve_period
from core.features.reporting.repository import DashboardRepository, ReportRepository
from core.features.reporting.runner import csv_buffer
from core.features.reporting.seeds import find_seed_by_slug, normalize_sql
from core.features.reporting.validation import require_tenant_filter, validate_read_only_sql
from skyrict_common.exceptions import ConflictError, NotFoundError, ValidationError

logger = structlog.get_logger("core.reporting.service")

# Minimum telemetry events required before the AI suggestion engine
# will produce a layout recommendation.
_MIN_EVENTS_FOR_SUGGESTION = 50


class DashboardService:
    """Orchestrates layout reads/writes and telemetry recording."""

    def __init__(self, repository: DashboardRepository) -> None:
        self._repo = repository

    # --- Layout resolution ---------------------------------------------------

    async def resolve_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Return the effective layout for a user.

        Priority: user override > tenant default > empty layout.
        """
        user_layout = await self._repo.get_user_layout(tenant_id=tenant_id, user_id=user_id)
        if user_layout is not None:
            return {
                "source": "user",
                "layout": user_layout.layout,
                "updated_at": user_layout.updated_at.isoformat(),
            }

        tenant_default = await self._repo.get_tenant_default(tenant_id=tenant_id)
        if tenant_default is not None:
            return {
                "source": "tenant_default",
                "layout": tenant_default.layout,
                "updated_at": tenant_default.updated_at.isoformat(),
            }

        return {"source": "empty", "layout": [], "updated_at": None}

    # --- User layout CRUD ----------------------------------------------------

    async def save_user_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        layout: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Save the user's personal layout."""
        record = await self._repo.upsert_user_layout(
            tenant_id=tenant_id, user_id=user_id, layout=layout
        )
        logger.info(
            "user_layout_saved",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            widget_count=len(layout),
        )
        return {
            "layout": record.layout,
            "updated_at": record.updated_at.isoformat(),
        }

    async def reset_user_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete the user's personal layout, reverting to the tenant default."""
        deleted = await self._repo.delete_user_layout(tenant_id=tenant_id, user_id=user_id)
        logger.info(
            "user_layout_reset",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            deleted=deleted,
        )
        return deleted

    # --- Telemetry -----------------------------------------------------------

    async def record_events(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        events: list[dict[str, Any]],
    ) -> int:
        """Record widget interaction events."""
        count = await self._repo.record_widget_events(
            tenant_id=tenant_id, user_id=user_id, events=events
        )
        if count > 0:
            logger.info(
                "widget_events_recorded",
                tenant_id=str(tenant_id),
                user_id=str(user_id),
                count=count,
            )
        return count

    async def has_enough_events(self, *, tenant_id: uuid.UUID) -> bool:
        """Check whether the tenant has enough telemetry for an AI suggestion."""
        # Check across all widgets - if any widget hits the threshold, we suggest.
        summary = await self._repo.get_widget_event_summary(tenant_id=tenant_id)
        return any(item["total_events"] >= _MIN_EVENTS_FOR_SUGGESTION for item in summary)

    async def get_event_summary(self, *, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return per-widget event counts."""
        return await self._repo.get_widget_event_summary(tenant_id=tenant_id)


class ReportService:
    """Orchestrates report listing, parametrized execution, and snapshots.

    The service owns the business rules (param typing, period resolution, UI
    row cap) and delegates every query to the repository - the report SQL is
    executed only through ``ReportRepository.run_query``, so the database
    layer stays the sole place raw SQL is issued (import-linter rule).
    """

    def __init__(
        self,
        repository: ReportRepository,
        audit: Any | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit

    async def list_reports(
        self,
        *,
        tenant_id: uuid.UUID,
        module: str | None = None,
    ) -> list[Any]:
        """Return the tenant's active definitions, optionally filtered by module."""
        definitions = await self._repo.list_active_definitions(tenant_id=tenant_id)
        if module is None:
            return definitions
        return [definition for definition in definitions if definition.module == module]

    async def get_report(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
    ) -> Any:
        """Return one active definition by slug (404 when unknown)."""
        definition = await self._repo.get_definition(tenant_id=tenant_id, slug=slug)
        if definition is None:
            raise NotFoundError(f"Report {slug!r} was not found")
        return definition

    async def create_definition(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_ip: str | None,
        actor_agent: str | None,
        slug: str,
        title: str,
        module: str,
        description: str | None,
        params: list[str],
        source_slug: str,
        default_params: dict[str, Any] | None = None,
        sql: str | None = None,
    ) -> Any:
        """Persist a new report definition whose SQL is a whitelisted template.

        The NL report builder (RPT-AI-001, SKY-80) hands us a spec that names
        the canonical template it matched (``source_slug``) but never the SQL.
        This method is the security boundary that guarantees NO arbitrary or
        AI-generated SQL can reach the database:

        1. Resolve the canonical seed by ``source_slug`` - unknown template is
           422 (we only ever accept known whitelisted reports).
        2. Require the ``sql`` (when supplied) to normalize-match the template
           EXACTLY (whitespace-insensitive). When omitted - the normal NL
           builder path - the template SQL is resolved server-side, so the
           stored definition is byte-for-byte the reviewed read-only template.
        3. Defense-in-depth re-validation: the resolved template SQL must still
           pass ``validate_read_only_sql`` + ``require_tenant_filter`` (fail
           closed at create time, not just at run time).
        4. The declared ``params`` allow-list must equal the template's declared
           params - no new/optional/unknown bind parameters.
        5. Enforce slug uniqueness tenant-wide (active OR soft-deleted), 409.
        6. Create the row with the template's own ``permission_key``, then write
           an immutable ``REPORT_CREATED`` audit event.

        ``default_params`` (the resolved values the builder produced) are NOT
        persisted - the schema has no default-params column and this ticket
        deliberately adds none. They are returned so the web client can
        pre-fill the run form for the just-created report.
        """
        seed = find_seed_by_slug(source_slug)
        if seed is None:
            raise ValidationError(f"Report template {source_slug!r} is not whitelisted")
        resolved_sql = seed.sql if sql is None else sql
        if normalize_sql(resolved_sql) != normalize_sql(seed.sql):
            raise ValidationError(
                "Report SQL must exactly match the whitelisted template "
                f"{source_slug!r}; custom SQL is not allowed"
            )
        if sorted(params) != sorted(seed.params):
            raise ValidationError(
                "Declared parameters must match the whitelisted template's parameters"
            )

        # Fail closed: never persist a definition that could not be run safely.
        validate_read_only_sql(seed.sql, seed.params)
        require_tenant_filter(seed.sql)

        existing = await self._repo.get_definition_any(tenant_id=tenant_id, slug=slug)
        if existing is not None:
            raise ConflictError(f"Report {slug!r} already exists")

        definition = await self._repo.create_definition(
            tenant_id=tenant_id,
            slug=slug,
            title=title,
            module=module,
            description=description,
            sql=seed.sql,
            params=list(seed.params),
            permission_key=seed.permission_key,
        )
        if self._audit is not None:
            await self._audit.log(
                action=REPORT_CREATED,
                target=f"report:{slug}",
                tenant_id=tenant_id,
                user_id=user_id,
                ip_address=actor_ip,
                user_agent=actor_agent,
                details={
                    "report": slug,
                    "source_slug": source_slug,
                    "module": module,
                    "permission_key": seed.permission_key,
                },
            )
        logger.info(
            "report.created",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            slug=slug,
            source_slug=source_slug,
            module=module,
            definition_id=str(definition.id),
        )
        return {
            "definition": definition,
            "default_params": default_params or {},
        }

    async def run_report(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        raw_params: dict[str, Any],
        statement_timeout_seconds: int = 30,
        result_cap: int = 10_000,
    ) -> dict[str, Any]:
        """Execute a report, store its snapshot, and return the run result.

        Steps (in order):
        1. Resolve the active definition - 404 before any validation.
        2. Type the user params into bind values - 422 on any unknown/mismatched
           value BEFORE any SQL executes (injection fails here).
        3. Execute the definition SQL with the statement-timeout guardrail.
        4. Cap rows for the UI path (never for export).
        5. Store/refresh the ``(definition, period)`` snapshot idempotently.
        """
        definition = await self.get_report(tenant_id=tenant_id, slug=slug)
        binds = build_report_binds(
            declared=definition.params_tuple,
            raw_params=raw_params,
            tenant_id=tenant_id,
        )
        period = resolve_period(raw_params)
        columns, rows = await self._repo.run_query(
            sql=definition.sql,
            binds=binds,
            statement_timeout_seconds=statement_timeout_seconds,
        )
        truncated = len(rows) > result_cap
        if truncated:
            rows = rows[:result_cap]
        snapshot = await self._repo.upsert_snapshot(
            tenant_id=tenant_id,
            definition_id=definition.id,
            period=period,
            payload=rows,
        )
        logger.info(
            "report.run.completed",
            tenant_id=str(tenant_id),
            slug=slug,
            columns=len(columns),
            rows=len(rows),
            truncated=truncated,
            period=period.isoformat(),
            snapshot_id=str(snapshot.id),
        )
        return {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "period": period,
            "snapshot_id": snapshot.id,
            "generated_at": snapshot.generated_at,
        }

    async def export_report(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_ip: str | None,
        actor_agent: str | None,
        slug: str,
        raw_params: dict[str, Any],
        statement_timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Run a report FULL (no UI cap) and build its CSV for streaming/audit.

        The CSV is built from the same coerced values as snapshots, and an
        immutable ``REPORT_EXPORTED`` audit row is written BEFORE the file is
        returned so an export is always on record even if the stream later
        fails. Returns a prepared export (columns, csv, row count, filename)
        for the route to stream.
        """
        definition = await self.get_report(tenant_id=tenant_id, slug=slug)
        binds = build_report_binds(
            declared=definition.params_tuple,
            raw_params=raw_params,
            tenant_id=tenant_id,
        )
        period = resolve_period(raw_params)
        columns, rows = await self._repo.run_query(
            sql=definition.sql,
            binds=binds,
            statement_timeout_seconds=statement_timeout_seconds,
        )
        csv_text = csv_buffer(columns=columns, rows=rows)
        if self._audit is not None:
            await self._audit.log(
                action=REPORT_EXPORTED,
                target=f"report:{slug}",
                tenant_id=tenant_id,
                user_id=user_id,
                ip_address=actor_ip,
                user_agent=actor_agent,
                details={
                    "report": slug,
                    "period": period.isoformat(),
                    "rows": len(rows),
                    "bytes": len(csv_text.encode("utf-8")),
                },
            )
        logger.info(
            "report.export.completed",
            tenant_id=str(tenant_id),
            slug=slug,
            rows=len(rows),
        )
        return {
            "columns": columns,
            "csv": csv_text,
            "rows": len(rows),
            "period": period,
            "filename": f"{slug}-{period.isoformat()}.csv",
        }

    async def list_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        limit: int = 20,
    ) -> list[Any]:
        """Return the newest snapshots for a definition (404 when unknown)."""
        definition = await self.get_report(tenant_id=tenant_id, slug=slug)
        return await self._repo.list_snapshots(
            tenant_id=tenant_id,
            definition_id=definition.id,
            limit=limit,
        )

    async def prune_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        keep_n: int,
    ) -> int:
        """Prune every definition of a tenant to its newest ``keep_n`` snapshots.

        Runs per definition so the retention limit applies per definition
        (never to the tenant as a whole). Returns the total deleted count.
        """
        definition_ids = await self._repo.list_definition_ids(tenant_id=tenant_id)
        total = 0
        for definition_id in definition_ids:
            total += await self._repo.prune_snapshots(
                tenant_id=tenant_id,
                definition_id=definition_id,
                keep_n=keep_n,
            )
        if total:
            logger.info(
                "report.snapshots.pruned",
                tenant_id=str(tenant_id),
                pruned=total,
                keep_n=keep_n,
            )
        return total
