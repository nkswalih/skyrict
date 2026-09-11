"""Unit tests for memory compaction service and budget manager (SKY-90).

Compaction tests use a fake repository - no DB, no LLM, no network. Budget
tests are pure utility checks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_agent.features.memory_compaction.budget import ContextBudgetManager
from ai_agent.features.memory_compaction.service import MemoryCompactionService

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class _FakeRow:
    def __init__(
        self, *, row_id: uuid.UUID, query: str, response: str, created_at: datetime
    ) -> None:
        self.id = row_id
        self.query_text = query
        self.response_summary = response
        self.created_at = created_at


class _FakeMemoryRepo:
    """Records compaction interactions; lets tests control batches and facts."""

    def __init__(
        self,
        *,
        rows: list[_FakeRow] | None = None,
        llm_facts: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows = rows or []
        self.llm_facts = llm_facts
        self.list_calls: list[dict[str, Any]] = []
        self.stored_facts: list[dict[str, Any]] = []
        self.marked_ids: list[uuid.UUID] = []
        self.store_fail = False

    async def list_uncompacted_episodic(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        before: datetime,
        limit: int = 100,
    ) -> list[_FakeRow]:
        self.list_calls.append({"tenant_id": tenant_id, "user_id": user_id, "before": before})
        return self.rows

    async def store_semantic_facts(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        facts: list[dict[str, Any]],
    ) -> None:
        if self.store_fail:
            raise RuntimeError("store backend down")
        self.stored_facts.extend(facts)

    async def mark_episodic_compacted(
        self,
        *,
        tenant_id: uuid.UUID,
        ids: list[uuid.UUID],
    ) -> int:
        self.marked_ids = ids
        return len(ids)


class _FakeLlm:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.has_providers = True
        self._texts = texts or ['[{"fact": "Prefers weekly check-ins", "category": "preference"}]']
        self.complete = AsyncMock(side_effect=[_Completion(text) for text in self._texts])


class _Completion:
    def __init__(self, text: str) -> None:
        self.text = text


def _row(*, age_days: int, query: str = "Query", response: str = "Response") -> _FakeRow:
    return _FakeRow(
        row_id=uuid.uuid4(),
        query=query,
        response=response,
        created_at=NOW - timedelta(days=age_days),
    )


class TestMemoryCompactionService:
    async def test_no_rows_returns_zero_summary(self) -> None:
        repo = _FakeMemoryRepo(rows=[])
        service = MemoryCompactionService(repo=repo)

        result = await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        assert result.rows_processed == 0
        assert result.facts_stored == 0
        assert result.llm_used is False
        assert repo.stored_facts == []
        assert repo.marked_ids == []

    async def test_deterministic_fallback_without_provider(self) -> None:
        rows = [_row(age_days=10, query="What is on hand?", response="42 units on hand")]
        repo = _FakeMemoryRepo(rows=rows)
        service = MemoryCompactionService(repo=repo)

        result = await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        assert result.rows_processed == 1
        assert result.facts_stored == 1
        assert result.llm_used is False
        assert repo.stored_facts[0]["source"] == "compaction"
        assert repo.stored_facts[0]["confidence"] == 0.5
        assert repo.marked_ids == [rows[0].id]

    async def test_llm_facts_stored_when_provider_exists(self) -> None:
        rows = [
            _row(
                age_days=14,
                query="What products do we carry?",
                response="We carry SKU-A and SKU-B.",
            )
        ]
        repo = _FakeMemoryRepo(rows=rows)
        llm = _FakeLlm(
            [
                '[{"fact": "Tenant carries SKU-A and SKU-B", "category": "entity", '
                '"entity_type": "customer", "entity_id": null, "confidence": 0.9}]'
            ]
        )
        service = MemoryCompactionService(repo=repo, llm_router=llm)

        result = await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        assert result.rows_processed == 1
        assert result.facts_stored == 1
        assert result.llm_used is True
        assert repo.stored_facts[0]["source"] == "compaction"
        assert repo.stored_facts[0]["category"] == "entity"
        assert repo.marked_ids == [rows[0].id]

    async def test_llm_failure_falls_back_to_deterministic(self) -> None:
        rows = [_row(age_days=10)]

        class _BoomLlm:
            has_providers = True

            async def complete(self, request: Any) -> _Completion:
                raise RuntimeError("provider down")

        repo = _FakeMemoryRepo(rows=rows)
        service = MemoryCompactionService(repo=repo, llm_router=_BoomLlm())  # type: ignore[arg-type]

        result = await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        assert result.rows_processed == 1
        assert result.facts_stored == 1
        assert repo.stored_facts[0]["confidence"] == 0.5

    async def test_llm_garbage_ignored(self) -> None:
        rows = [_row(age_days=10)]
        repo = _FakeMemoryRepo(rows=rows)
        llm = _FakeLlm(["this is not json"])
        service = MemoryCompactionService(repo=repo, llm_router=llm)

        result = await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        # json_mode guarantees validity in production; a broken parse falls
        # back so the pass always progresses.
        assert result.facts_stored == 1
        assert repo.stored_facts[0]["confidence"] == 0.5

    async def test_store_failure_does_not_mark_rows(self) -> None:
        rows = [_row(age_days=10)]
        repo = _FakeMemoryRepo(rows=rows)
        repo.store_fail = True
        service = MemoryCompactionService(repo=repo)

        with pytest.raises(RuntimeError):
            await service.compact_user(tenant_id=TENANT_ID, user_id=USER_ID)

        # The exception propagates - marking must not happen on a failed fold
        # (data would be lost).
        assert repo.marked_ids == []


# ---------------------------------------------------------------------------
# Budget manager
# ---------------------------------------------------------------------------


class TestContextBudgetManager:
    def test_default_budget_for_known_agent(self) -> None:
        manager = ContextBudgetManager()
        assert manager.budget_for("crm_assistant") == 4000

    def test_unknown_agent_falls_back_to_default(self) -> None:
        manager = ContextBudgetManager()
        assert manager.budget_for("unknown_agent") == 6000

    def test_fits_small_context(self) -> None:
        manager = ContextBudgetManager()
        assert manager.fits(agent="crm_assistant", text="short context")

    def test_trim_keeps_parts_whole_and_truncates_tail(self) -> None:
        manager = ContextBudgetManager(budgets={"crm_assistant": 40})
        parts = ["A" * 100, "B" * 100]
        trimmed = manager.trim_to_budget(agent="crm_assistant", parts=parts)
        assert "… (context trimmed to fit budget)" in trimmed
        assert manager.estimate_tokens(trimmed) <= 40 + 2  # marker overhead

    def test_trim_drops_parts_beyond_budget(self) -> None:
        manager = ContextBudgetManager(budgets={"crm_assistant": 10})
        parts = ["AAAA AAAA", "B" * 400]
        trimmed = manager.trim_to_budget(agent="crm_assistant", parts=parts)
        assert "BBBB" not in trimmed

    def test_trim_empty_parts(self) -> None:
        manager = ContextBudgetManager()
        assert manager.trim_to_budget(agent="crm_assistant", parts=[]) == ""
