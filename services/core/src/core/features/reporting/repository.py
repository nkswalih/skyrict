"""Repository for dashboard layout CRUD and report definitions/snapshots (RPT-DATA-001)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.reporting.models.dashboard import ErpDashboardModel
from core.features.reporting.models.report_definition import ErpReportDefinitionModel
from core.features.reporting.models.report_snapshot import ErpReportSnapshotModel
from core.features.reporting.models.user_layout import UserDashboardLayoutModel
from core.features.reporting.models.widget_event import WidgetEventModel
from core.features.reporting.runner import json_safe_value

logger = structlog.get_logger("core.reporting.repository")


class DashboardRepository:
    """Data-access layer for dashboard layouts and widget telemetry."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Tenant default dashboard --------------------------------------------

    async def get_tenant_default(self, *, tenant_id: uuid.UUID) -> ErpDashboardModel | None:
        """Return the tenant's default dashboard, or None."""
        result = await self._session.execute(
            select(ErpDashboardModel).where(
                ErpDashboardModel.tenant_id == tenant_id,
                ErpDashboardModel.tenant_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_tenant_default(
        self,
        *,
        tenant_id: uuid.UUID,
        title: str,
        layout: list[dict[str, Any]],
    ) -> ErpDashboardModel:
        """Create or update the tenant's default dashboard."""
        existing = await self.get_tenant_default(tenant_id=tenant_id)
        if existing is not None:
            existing.title = title
            existing.layout = layout
            dashboard = existing
        else:
            dashboard = ErpDashboardModel(
                tenant_id=tenant_id,
                title=title,
                layout=layout,
                tenant_default=True,
            )
            self._session.add(dashboard)
        await self._session.flush()
        # updated_at is server-side (ON UPDATE now()); refresh it inside the
        # awaited context so a post-flush read by the caller cannot trigger a
        # lazy refresh (MissingGreenlet in the async engine).
        await self._session.refresh(dashboard, attribute_names=["updated_at"])
        return dashboard

    # --- User layout ---------------------------------------------------------

    async def get_user_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserDashboardLayoutModel | None:
        """Return the user's personal layout override, or None."""
        result = await self._session.execute(
            select(UserDashboardLayoutModel).where(
                UserDashboardLayoutModel.tenant_id == tenant_id,
                UserDashboardLayoutModel.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_user_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        layout: list[dict[str, Any]],
    ) -> UserDashboardLayoutModel:
        """Create or update the user's personal layout."""
        existing = await self.get_user_layout(tenant_id=tenant_id, user_id=user_id)
        if existing is not None:
            existing.layout = layout
            record = existing
        else:
            record = UserDashboardLayoutModel(
                tenant_id=tenant_id,
                user_id=user_id,
                layout=layout,
            )
            self._session.add(record)
        await self._session.flush()
        # updated_at is server-side (ON UPDATE now()); refresh it inside the
        # awaited context so a post-flush read by the caller cannot trigger a
        # lazy refresh (MissingGreenlet in the async engine).
        await self._session.refresh(record, attribute_names=["updated_at"])
        return record

    async def delete_user_layout(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete the user's personal layout (reset to default). Returns True if deleted."""
        existing = await self.get_user_layout(tenant_id=tenant_id, user_id=user_id)
        if existing is None:
            return False
        await self._session.delete(existing)
        await self._session.flush()
        return True

    # --- Widget events -------------------------------------------------------

    async def record_widget_events(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        events: list[dict[str, Any]],
    ) -> int:
        """Insert widget interaction events. Returns the count of inserted rows."""
        if not events:
            return 0

        rows = [
            WidgetEventModel(
                tenant_id=tenant_id,
                user_id=user_id,
                widget_id=ev["widget_id"],
                event=ev["event"],
            )
            for ev in events
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return len(rows)

    async def count_widget_events(
        self,
        *,
        tenant_id: uuid.UUID,
        widget_id: str,
    ) -> int:
        """Count total events for a widget in a tenant (for AI gating)."""
        from sqlalchemy import func as sqlfunc

        result = await self._session.execute(
            select(sqlfunc.count())
            .select_from(WidgetEventModel)
            .where(
                WidgetEventModel.tenant_id == tenant_id,
                WidgetEventModel.widget_id == widget_id,
            )
        )
        return result.scalar_one() or 0

    async def get_widget_event_summary(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Return per-widget event counts for the AI suggestion engine.

        Only returns widgets with >= 1 event.  The AI suggestion endpoint
        uses the 50-event threshold separately.
        """
        from sqlalchemy import func as sqlfunc

        result = await self._session.execute(
            select(
                WidgetEventModel.widget_id,
                sqlfunc.count().label("total_events"),
                sqlfunc.count(WidgetEventModel.event.distinct()).label("distinct_events"),
            )
            .where(WidgetEventModel.tenant_id == tenant_id)
            .group_by(WidgetEventModel.widget_id)
            .order_by(sqlfunc.count().desc())
        )
        return [
            {
                "widget_id": row.widget_id,
                "total_events": row.total_events,
                "distinct_events": row.distinct_events,
            }
            for row in result
        ]


class ReportRepository:
    """Data-access layer for report definitions and snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_definitions(
        self, *, tenant_id: uuid.UUID
    ) -> list[ErpReportDefinitionModel]:
        """Return the tenant's active definitions ordered by module then slug."""
        result = await self._session.execute(
            select(ErpReportDefinitionModel)
            .where(
                ErpReportDefinitionModel.tenant_id == tenant_id,
                ErpReportDefinitionModel.is_active.is_(True),
            )
            .order_by(ErpReportDefinitionModel.module, ErpReportDefinitionModel.slug)
        )
        return list(result.scalars().all())

    async def get_definition(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
    ) -> ErpReportDefinitionModel | None:
        """Return one active definition by slug, or None."""
        result = await self._session.execute(
            select(ErpReportDefinitionModel).where(
                ErpReportDefinitionModel.tenant_id == tenant_id,
                ErpReportDefinitionModel.slug == slug,
                ErpReportDefinitionModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_definition_any(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
    ) -> ErpReportDefinitionModel | None:
        """Return a definition by slug regardless of active state, or None.

        Used by the create path so a soft-deleted definition with the same slug
        still blocks reuse (a slug is unique per tenant forever - the tenant's
        run history stays meaningful if it were ever re-run).
        """
        result = await self._session.execute(
            select(ErpReportDefinitionModel).where(
                ErpReportDefinitionModel.tenant_id == tenant_id,
                ErpReportDefinitionModel.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def create_definition(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        title: str,
        module: str,
        description: str | None,
        sql: str,
        params: list[str],
        permission_key: str,
    ) -> ErpReportDefinitionModel:
        """Persist a new (user-created) report definition for the tenant.

        The create path is authoritative here: unlike the seed catalog helper
        (which returns the row object), the repository inserts the row and
        returns the freshly-created model so the service can audit and return
        a runnable definition in one unit of work. ``id`` and the audit
        columns take server defaults.
        """
        definition = ErpReportDefinitionModel(
            tenant_id=tenant_id,
            slug=slug,
            title=title,
            module=module,
            description=description,
            sql=sql,
            params=params,
            permission_key=permission_key,
        )
        self._session.add(definition)
        await self._session.flush()
        # ``updated_at`` is server-side (default now()); refresh it inside the
        # awaited context so a post-flush read by the caller (the router
        # serialising ReportDefinitionRead) cannot trigger a lazy refresh
        # (MissingGreenlet in the async engine).
        await self._session.refresh(definition, attribute_names=["updated_at"])
        return definition

    async def run_query(
        self,
        *,
        sql: str,
        binds: dict[str, Any],
        statement_timeout_seconds: int = 30,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Execute one read-only report statement and return ``(columns, rows)``.

        The statement timeout is applied transaction-locally via
        ``set_config('statement_timeout', ..., true)`` in the same transaction
        as the query, so a runaway report can never hold the request open past
        the configured guardrail (``REPORTING_QUERY_TIMEOUT_SECONDS``).

        No interpolation happens here: ``binds`` arrive from
        :func:`core.features.reporting.params.build_report_binds`, which
        rejects unknown/typed incorrectly values before this is reached. Every
        returned value is coerced through ``json_safe_value`` so the rows are
        ready for JSONB snapshot payloads and CSV export.
        """
        timeout_value = f"{statement_timeout_seconds}s"
        await self._session.execute(
            text("SELECT set_config('statement_timeout', :value, true)"),
            {"value": timeout_value},
        )
        result = await self._session.execute(text(sql), binds)
        rows: list[dict[str, Any]] = [
            {key: json_safe_value(value) for key, value in row._mapping.items()} for row in result
        ]
        columns = list(result.keys())
        return columns, rows

    async def upsert_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        period: date,
        payload: list[dict[str, Any]],
    ) -> ErpReportSnapshotModel:
        """Idempotently store a snapshot for (tenant, definition, period).

        Re-running the same period replaces the payload (and refreshes
        ``generated_at``) instead of inserting a second row - erp-phase1.md
        §M-RPT snapshot-refresh acceptance.
        """
        existing = await self.get_snapshot(
            tenant_id=tenant_id,
            definition_id=definition_id,
            period=period,
        )
        if existing is not None:
            existing.payload = payload
            snapshot = existing
        else:
            snapshot = ErpReportSnapshotModel(
                tenant_id=tenant_id,
                definition_id=definition_id,
                period=period,
                payload=payload,
            )
            self._session.add(snapshot)
        await self._session.flush()
        # ``generated_at`` is server-side (default + ON UPDATE now()), so the
        # flush leaves it expired; reading it synchronously right after the
        # flush (ReportService.run_report returns it) would trigger a lazy
        # refresh, which cannot run in the async session and raises
        # MissingGreenlet -> HTTP 500. Eagerly refresh the server-generated
        # columns inside the awaited context so the returned snapshot is fully
        # readable by the caller.
        await self._session.refresh(snapshot, attribute_names=["generated_at"])
        return snapshot

    async def get_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        period: date,
    ) -> ErpReportSnapshotModel | None:
        """Return the snapshot for (tenant, definition, period), or None."""
        result = await self._session.execute(
            select(ErpReportSnapshotModel).where(
                ErpReportSnapshotModel.tenant_id == tenant_id,
                ErpReportSnapshotModel.definition_id == definition_id,
                ErpReportSnapshotModel.period == period,
            )
        )
        return result.scalar_one_or_none()

    async def list_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        limit: int,
    ) -> list[ErpReportSnapshotModel]:
        """Return the newest ``limit`` snapshots, newest first (stable tie-break)."""
        result = await self._session.execute(
            select(ErpReportSnapshotModel)
            .where(
                ErpReportSnapshotModel.tenant_id == tenant_id,
                ErpReportSnapshotModel.definition_id == definition_id,
            )
            .order_by(
                ErpReportSnapshotModel.generated_at.desc(),
                ErpReportSnapshotModel.id.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_definition_ids(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Return every definition id for a tenant (active or not - snapshots of
        retired definitions still consume retention budget)."""
        result = await self._session.execute(
            select(ErpReportDefinitionModel.id).where(
                ErpReportDefinitionModel.tenant_id == tenant_id
            )
        )
        return list(result.scalars().all())

    async def list_all_definition_pairs(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return ``(tenant_id, definition_id)`` for every definition in the DB.

        Used by the background retention worker, which walks every tenant's
        definitions with each tenant's RLS context set. Never tenant-scoped
        itself: the owner role bypasses RLS and this method must enumerate
        rows across all tenants.
        """
        result = await self._session.execute(
            select(ErpReportDefinitionModel.tenant_id, ErpReportDefinitionModel.id)
        )
        return [(row[0], row[1]) for row in result]

    async def prune_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        keep_n: int,
    ) -> int:
        """Delete a definition's snapshots beyond the newest ``keep_n``.

        Newest is ordered by ``generated_at`` then ``id`` (a deterministic
        tie-break for same-timestamp refreshes). Returns the deleted count.
        """
        keep_ids = (
            select(ErpReportSnapshotModel.id)
            .where(
                ErpReportSnapshotModel.tenant_id == tenant_id,
                ErpReportSnapshotModel.definition_id == definition_id,
            )
            .order_by(
                ErpReportSnapshotModel.generated_at.desc(),
                ErpReportSnapshotModel.id.desc(),
            )
            .limit(keep_n)
        )
        stmt = delete(ErpReportSnapshotModel).where(
            ErpReportSnapshotModel.tenant_id == tenant_id,
            ErpReportSnapshotModel.definition_id == definition_id,
            ErpReportSnapshotModel.id.not_in(keep_ids),
        )
        result = await self._session.execute(stmt)
        # ``rowcount`` is present on ``CursorResult`` (the runtime type) but the
        # ``Result[Any]`` stubs used by ``AsyncSession`` omit it; this is safe
        # because DELETE statements always produce a ``CursorResult``.
        return getattr(result, "rowcount", 0) or 0
