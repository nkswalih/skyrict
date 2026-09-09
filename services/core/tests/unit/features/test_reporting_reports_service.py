"""Unit tests for ReportService.run_report (RPT-BE-001) - fake repo, no database."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from core.features.reporting.seeds import find_seed_by_slug
from core.features.reporting.service import ReportService
from skyrict_common.exceptions import ConflictError, NotFoundError, ValidationError


class FakeRepo:
    """In-memory ReportRepository double recording calls."""

    def __init__(self) -> None:
        self.definitions: dict[str, Any] = {}
        self.snapshots: list[Any] = []
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    async def list_active_definitions(self, *, tenant_id: uuid.UUID) -> list[Any]:
        return [d for d in self.definitions.values() if d.tenant_id == tenant_id and d.is_active]

    async def get_definition(self, *, tenant_id: uuid.UUID, slug: str) -> Any | None:
        definition = self.definitions.get(slug)
        if definition is None:
            return None
        return definition if definition.tenant_id == tenant_id and definition.is_active else None

    async def get_definition_any(self, *, tenant_id: uuid.UUID, slug: str) -> Any | None:
        definition = self.definitions.get(slug)
        if definition is None:
            return None
        return definition if definition.tenant_id == tenant_id else None

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
    ) -> Any:
        definition = _definition(tenant_id=tenant_id, slug=slug, params=tuple(params))
        definition.title = title
        definition.module = module
        definition.description = description
        definition.sql = sql
        definition.permission_key = permission_key
        self.definitions[slug] = definition
        return definition

    async def run_query(
        self,
        *,
        sql: str,
        binds: dict[str, Any],
        statement_timeout_seconds: int = 30,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        self.run_calls.append((sql, binds))
        return (["bucket", "total"], [{"bucket": "current", "total": "150.00"}])

    async def upsert_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        period: date,
        payload: list[dict[str, Any]],
    ) -> Any:
        snapshot = type(
            "Snapshot",
            (),
            {
                "id": uuid.uuid4(),
                "generated_at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
            },
        )()
        self.snapshots.append((tenant_id, definition_id, period, payload))
        return snapshot

    async def list_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        limit: int,
    ) -> list[Any]:
        return self.snapshots[-limit:]

    async def list_definition_ids(self, *, tenant_id: uuid.UUID) -> list[Any]:
        return [
            definition.id
            for definition in self.definitions.values()
            if definition.tenant_id == tenant_id
        ]

    async def prune_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        keep_n: int,
    ) -> int:
        return 3


def _definition(*, tenant_id: uuid.UUID, slug: str, params: tuple[str, ...]) -> Any:
    definition = type("Definition", (), {})()
    definition.tenant_id = tenant_id
    definition.id = uuid.uuid4()
    definition.slug = slug
    definition.sql = "SELECT 1"
    definition.params = list(params)
    definition.params_tuple = params
    definition.is_active = True
    return definition


def _make_service(definitions: dict[str, Any]) -> ReportService:
    repo = FakeRepo()
    repo.definitions = definitions
    return ReportService(repository=repo)  # type: ignore[arg-type]


class TestRunReport:
    @pytest.mark.asyncio
    async def test_run_returns_columns_rows_and_snapshot(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        service = _make_service({definition.slug: definition})

        result = await service.run_report(
            tenant_id=tenant_id,
            slug="ar_aging",
            raw_params={"as_of_date": "2026-09-30"},
        )

        assert result["columns"] == ["bucket", "total"]
        assert result["rows"] == [{"bucket": "current", "total": "150.00"}]
        assert result["truncated"] is False
        assert result["period"] == date(2026, 9, 30)

    @pytest.mark.asyncio
    async def test_run_404_for_unknown_slug(self) -> None:
        service = _make_service({})

        with pytest.raises(NotFoundError):
            await service.run_report(
                tenant_id=uuid.uuid4(),
                slug="missing",
                raw_params={},
            )

    @pytest.mark.asyncio
    async def test_run_422_for_invalid_params(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        service = _make_service({definition.slug: definition})

        with pytest.raises(ValidationError):
            await service.run_report(
                tenant_id=tenant_id,
                slug="ar_aging",
                raw_params={"as_of_date": "2026-01-01'; DROP TABLE erp_report_snapshots; --"},
            )

    @pytest.mark.asyncio
    async def test_run_caps_rows_for_ui_path(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="pnl", params=("tenant_id",))
        service = _make_service({definition.slug: definition})
        service._repo.run_query = _run_query_with_rows(15)  # type: ignore[attr-defined]

        result = await service.run_report(
            tenant_id=tenant_id,
            slug="pnl",
            raw_params={},
            result_cap=10,
        )

        assert result["truncated"] is True
        assert len(result["rows"]) == 10


def _run_query_with_rows(count: int) -> Any:
    async def run_query(**kwargs: Any) -> tuple[list[str], list[dict[str, Any]]]:
        return ["n"], [{"n": i} for i in range(count)]

    return run_query


class TestListSnapshots:
    @pytest.mark.asyncio
    async def test_returns_snapshots_for_known_definition(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="ar_aging", params=("tenant_id",))
        service = _make_service({definition.slug: definition})

        result = await service.list_snapshots(tenant_id=tenant_id, slug="ar_aging", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_404_for_unknown_slug(self) -> None:
        service = _make_service({})

        with pytest.raises(NotFoundError):
            await service.list_snapshots(tenant_id=uuid.uuid4(), slug="missing", limit=5)


class TestExportReport:
    @pytest.mark.asyncio
    async def test_export_runs_full_and_writes_audit(self) -> None:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        fake_audit = FakeAudit()
        repo = FakeRepo()
        repo.definitions = {definition.slug: definition}
        service = ReportService(repository=repo, audit=fake_audit)  # type: ignore[arg-type]

        prepared = await service.export_report(
            tenant_id=tenant_id,
            user_id=user_id,
            actor_ip="203.0.113.9",
            actor_agent="pytest",
            slug="ar_aging",
            raw_params={"as_of_date": "2026-09-30"},
        )

        assert prepared["filename"] == "ar_aging-2026-09-30.csv"
        assert prepared["rows"] == 1
        assert "bucket,total" in prepared["csv"]
        assert "current,150.00" in prepared["csv"]
        assert len(fake_audit.entries) == 1
        entry = fake_audit.entries[0]
        assert entry["action"] == "report.exported"
        assert entry["target"] == "report:ar_aging"
        assert entry["tenant_id"] == tenant_id
        assert entry["user_id"] == user_id
        assert entry["ip_address"] == "203.0.113.9"
        assert entry["user_agent"] == "pytest"
        assert entry["details"]["rows"] == 1

    @pytest.mark.asyncio
    async def test_export_404_for_unknown_slug_without_audit(self) -> None:
        fake_audit = FakeAudit()
        repo = FakeRepo()
        service = ReportService(repository=repo, audit=fake_audit)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await service.export_report(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                actor_ip=None,
                actor_agent=None,
                slug="missing",
                raw_params={},
            )

        assert len(fake_audit.entries) == 0

    @pytest.mark.asyncio
    async def test_export_no_audit_service_is_optional(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="ar_aging", params=("tenant_id",))
        service = _make_service({definition.slug: definition})

        prepared = await service.export_report(
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            actor_ip=None,
            actor_agent=None,
            slug="ar_aging",
            raw_params={},
        )

        assert prepared["rows"] == 1
        assert prepared["csv"].startswith("bucket,total")


class FakeAudit:
    """Minimal AuditService double recording log() calls."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log(
        self,
        *,
        action: str,
        target: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> Any:
        self.entries.append(
            {
                "action": action,
                "target": target,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "details": details or {},
            }
        )
        return None


class TestPruneSnapshots:
    @pytest.mark.asyncio
    async def test_prunes_each_definition_of_the_tenant(self) -> None:
        tenant_id = uuid.uuid4()
        definition_a = _definition(tenant_id=tenant_id, slug="a", params=("tenant_id",))
        definition_b = _definition(tenant_id=tenant_id, slug="b", params=("tenant_id",))
        service = _make_service({definition_a.slug: definition_a, definition_b.slug: definition_b})

        total = await service.prune_snapshots(tenant_id=tenant_id, keep_n=3)

        assert total == 6  # 3 pruned per definition, two definitions


class TestCreateDefinition:
    """RPT-AI-001 (SKY-80): the create path accepts ONLY whitelisted template SQL.

    Every security property of the NL report builder lives in these tests: the
    template lookup, the exact-match SQL gate, param allow-list equality, the
    defense-in-depth read-only revalidation, slug uniqueness, and the audit
    event.
    """

    def _persist_kwargs(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        slug: str = "ar_aging_90plus",
        source_slug: str = "ar_aging",
        sql: str | None = None,
        params: list[str] | None = None,
        default_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seed = find_seed_by_slug(source_slug)
        resolved_sql = seed.sql if seed is not None and sql is None else (sql or "SELECT 1")
        resolved_params = (
            list(seed.params) if seed is not None and params is None else (params or [])
        )
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "actor_ip": "203.0.113.9",
            "actor_agent": "pytest",
            "slug": slug,
            "title": "AR aging 90+ focus",
            "module": "finance",
            "description": "Generated from the canonical AR aging template.",
            "sql": resolved_sql,
            "params": resolved_params,
            "source_slug": source_slug,
            "default_params": default_params
            if default_params is not None
            else {"as_of_date": "2026-09-30"},
        }

    @pytest.mark.asyncio
    async def test_create_persists_definition_with_template_sql_and_audits(self) -> None:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        fake_audit = FakeAudit()
        repo = FakeRepo()
        service = ReportService(repository=repo, audit=fake_audit)  # type: ignore[arg-type]

        result = await service.create_definition(
            **self._persist_kwargs(tenant_id=tenant_id, user_id=user_id)
        )

        definition = repo.definitions["ar_aging_90plus"]
        assert definition.slug == "ar_aging_90plus"
        assert definition.module == "finance"
        assert definition.permission_key == "erp.reports.read"
        assert definition.is_active is True

        assert result["default_params"] == {"as_of_date": "2026-09-30"}
        assert len(fake_audit.entries) == 1
        entry = fake_audit.entries[0]
        assert entry["action"] == "report.created"
        assert entry["target"] == "report:ar_aging_90plus"
        assert entry["tenant_id"] == tenant_id
        assert entry["user_id"] == user_id
        assert entry["details"]["source_slug"] == "ar_aging"

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_template(self) -> None:
        service = _make_service({})

        with pytest.raises(ValidationError):
            await service.create_definition(
                **self._persist_kwargs(
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    source_slug="not_a_whitelisted_report",
                )
            )

    @pytest.mark.asyncio
    async def test_create_rejects_arbitrary_sql_even_with_valid_source(self) -> None:
        tenant_id = uuid.uuid4()
        service = _make_service({})

        with pytest.raises(ValidationError):
            await service.create_definition(
                **self._persist_kwargs(
                    tenant_id=tenant_id,
                    user_id=uuid.uuid4(),
                    sql="SELECT pg_sleep(999); DROP TABLE erp_report_definitions; --",
                )
            )

    @pytest.mark.asyncio
    async def test_create_rejects_non_matching_sql_whitespace_insensitive(self) -> None:
        tenant_id = uuid.uuid4()
        seed = find_seed_by_slug("ar_aging")
        assert seed is not None
        service = _make_service({})

        # A semantically-different template SQL (different WHERE) must be
        # rejected even though it is still structurally "read-only".
        doctored = seed.sql.replace("i.status IN ('issued', 'approved')", "1 = 1")
        with pytest.raises(ValidationError):
            await service.create_definition(
                **self._persist_kwargs(tenant_id=tenant_id, user_id=uuid.uuid4(), sql=doctored)
            )

    @pytest.mark.asyncio
    async def test_create_accepts_whitespace_only_variance_of_template(self) -> None:
        tenant_id = uuid.uuid4()
        seed = find_seed_by_slug("ar_aging")
        assert seed is not None
        repo = FakeRepo()
        service = ReportService(repository=repo)  # type: ignore[arg-type]

        reflowed = "   ".join(seed.sql.splitlines())
        await service.create_definition(
            **self._persist_kwargs(tenant_id=tenant_id, user_id=uuid.uuid4(), sql=reflowed)
        )

        assert "ar_aging_90plus" in repo.definitions
        assert repo.definitions["ar_aging_90plus"].sql == seed.sql

    @pytest.mark.asyncio
    async def test_create_resolves_template_sql_when_sql_omitted(self) -> None:
        """The NL builder never has the SQL: omitting it must resolve the
        template SQL from source_slug and persist it byte-for-byte."""
        tenant_id = uuid.uuid4()
        seed = find_seed_by_slug("ar_aging")
        assert seed is not None
        repo = FakeRepo()
        service = ReportService(repository=repo)  # type: ignore[arg-type]

        await service.create_definition(
            **self._persist_kwargs(
                tenant_id=tenant_id,
                user_id=uuid.uuid4(),
                sql=None,
            )
        )

        persisted = repo.definitions["ar_aging_90plus"]
        assert persisted.sql == seed.sql
        assert persisted.params == list(seed.params)
        assert persisted.permission_key == "erp.reports.read"

    @pytest.mark.asyncio
    async def test_create_with_omitted_sql_on_user_defined_slug(self) -> None:
        """Even with a brand-new user slug, omitting sql persists exactly the
        template SQL of the named source - never anything the builder crafted."""
        tenant_id = uuid.uuid4()
        seed = find_seed_by_slug("cash_received")
        assert seed is not None
        repo = FakeRepo()
        service = ReportService(repository=repo)  # type: ignore[arg-type]

        await service.create_definition(
            **self._persist_kwargs(
                tenant_id=tenant_id,
                user_id=uuid.uuid4(),
                slug="my_cash_focus",
                source_slug="cash_received",
                sql=None,
            )
        )

        persisted = repo.definitions["my_cash_focus"]
        assert persisted.sql == seed.sql
        assert persisted.params == list(seed.params)

    @pytest.mark.asyncio
    async def test_create_rejects_mismatched_param_allowlist(self) -> None:
        tenant_id = uuid.uuid4()
        service = _make_service({})

        with pytest.raises(ValidationError):
            await service.create_definition(
                **self._persist_kwargs(
                    tenant_id=tenant_id,
                    user_id=uuid.uuid4(),
                    params=["tenant_id", "as_of_date", "evil_param"],
                )
            )

    @pytest.mark.asyncio
    async def test_create_conflicts_when_slug_already_exists(self) -> None:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        repo = FakeRepo()
        repo.definitions["ar_aging_90plus"] = _definition(
            tenant_id=tenant_id, slug="ar_aging_90plus", params=("tenant_id",)
        )
        service = ReportService(repository=repo, audit=FakeAudit())  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await service.create_definition(
                **self._persist_kwargs(tenant_id=tenant_id, user_id=user_id)
            )

    @pytest.mark.asyncio
    async def test_create_conflicts_on_soft_deleted_slug(self) -> None:
        tenant_id = uuid.uuid4()
        repo = FakeRepo()
        stale = _definition(tenant_id=tenant_id, slug="ar_aging_90plus", params=("tenant_id",))
        stale.is_active = False
        repo.definitions["ar_aging_90plus"] = stale
        service = ReportService(repository=repo)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await service.create_definition(
                **self._persist_kwargs(tenant_id=tenant_id, user_id=uuid.uuid4())
            )

    @pytest.mark.asyncio
    async def test_create_never_persists_default_params(self) -> None:
        tenant_id = uuid.uuid4()
        repo = FakeRepo()
        service = ReportService(repository=repo)  # type: ignore[arg-type]

        result = await service.create_definition(
            **self._persist_kwargs(
                tenant_id=tenant_id,
                user_id=uuid.uuid4(),
                default_params={"as_of_date": "2026-09-30", "extra": "x"},
            )
        )

        assert result["default_params"] == {"as_of_date": "2026-09-30", "extra": "x"}
        assert repo.definitions["ar_aging_90plus"].description is not None
        # No default_params attribute on the persisted model: the schema has no
        # column for it by design.
        assert not hasattr(repo.definitions["ar_aging_90plus"], "default_params")
