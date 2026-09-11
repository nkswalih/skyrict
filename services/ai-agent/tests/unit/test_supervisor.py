"""Supervisor feature tests - classification + delegation + event streaming.

Covers: LLM classification (happy path, low confidence, unparseable, provider
outage → keyword fallback), event ordering per segment, multi-agent fan-out,
unprovisioned module abstention, deterministic provider-free inventory answer,
and delegate failure degrading instead of killing the stream.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.core.providers import LlmCompletion, LlmRequest
from ai_agent.core.providers.base import LlmStreamChunk
from ai_agent.features.nl_query.gateway import ProductRef, StockLevelRow
from ai_agent.features.rag.retrieval.service import RetrievalItem, RetrievalResult
from ai_agent.features.supervisor.schemas import (
    AgentStartEvent,
    CitationsEvent,
    ClassificationEvent,
    DoneEvent,
    SupervisorEvent,
    TokenEvent,
)
from ai_agent.features.supervisor.service import SupervisorService

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeLlmRouter:
    """Scripted router: completion text / stream tokens / outage modes."""

    def __init__(
        self,
        *,
        has_providers: bool = True,
        completion_text: str | Exception | list[str] = "",
        stream_tokens: list[str] | None = None,
    ) -> None:
        self.has_providers = has_providers
        self._completion_text = completion_text
        self._completion_pool = list(completion_text) if isinstance(completion_text, list) else None
        self._stream_tokens = stream_tokens or ["hello ", "world "]
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        self.complete_calls += 1
        if self._completion_pool is not None:
            text = self._completion_pool.pop(0) if self._completion_pool else self._completion_text
            if isinstance(text, Exception):
                raise text
            return LlmCompletion(text=text, model_used="fake-model", latency_ms=1)
        if isinstance(self._completion_text, Exception):
            raise self._completion_text
        return LlmCompletion(text=self._completion_text, model_used="fake-model", latency_ms=1)

    async def stream(self, request: LlmRequest):
        self.stream_calls += 1
        for token in self._stream_tokens:
            yield LlmStreamChunk(token_delta=token, model_used="fake-model")


class FakeGateway:
    def __init__(
        self,
        *,
        levels: list[StockLevelRow] | None = None,
        products: list[ProductRef] | None = None,
    ) -> None:
        self._levels = levels or []
        self._products = products or []

    async def list_products(self) -> list[ProductRef]:
        return self._products

    async def list_warehouses(self) -> list[object]:
        return []

    async def get_stock_levels(
        self,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> list[StockLevelRow]:
        return self._levels

    async def list_movements(
        self,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: str | None = None,
    ) -> list[object]:
        return []


class FakeRag:
    async def search(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        module: str | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            data=[
                RetrievalItem(
                    parent_id=uuid.uuid4(),
                    source_ref="docs/inventory-ops.md",
                    module="inventory",
                    chunk_text="Items below reorder point should be restocked within 48 hours.",
                    score=0.91,
                    child_hits=2,
                    metadata_={},
                )
            ],
            model_used="fake-embed",
            latency_ms=1,
            cached=False,
            query_hash="h",
        )


class FakeHrCopilot:
    def __init__(
        self, *, answer: str = "Two weeks of paid leave.", error: Exception | None = None
    ) -> None:
        self._answer = answer
        self._error = error

    async def ask(
        self,
        *,
        message: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SimpleNamespace:
        if self._error is not None:
            raise self._error
        return SimpleNamespace(answer=self._answer)


class FakeForecast:
    async def get_forecast(self, *, product_id: uuid.UUID) -> list[dict[str, object]]:
        return [{"horizon_weeks": 4, "avg_demand": "12.0"}]


class FakeCoachSuggestions:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    async def list_pending_for_rep(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
    ) -> list[dict[str, object]]:
        return self._rows


class FakeGuardianReports:
    def __init__(
        self,
        reports: list[dict[str, object]] | None = None,
        events: list[dict[str, object]] | None = None,
    ) -> None:
        self._reports = reports or []
        self._events = events or []

    async def list_reports(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int = 1,
    ) -> list[dict[str, object]]:
        return self._reports[:limit]

    async def list_events_for_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> list[dict[str, object]]:
        return self._events


def make_service(
    *,
    router: FakeLlmRouter | None = None,
    gateway: FakeGateway | None = None,
    rag: FakeRag | None = None,
    hr_copilot: FakeHrCopilot | None = None,
    forecast: FakeForecast | None = None,
    coach_suggestions: FakeCoachSuggestions | None = None,
    guardian_reports: FakeGuardianReports | None = None,
    provisioned: dict[str, bool] | None = None,
    threshold: float = 0.75,
) -> SupervisorService:
    resolved_gateway = gateway or FakeGateway()

    async def gateway_factory() -> FakeGateway:
        return resolved_gateway

    return SupervisorService(
        llm_router=router or FakeLlmRouter(has_providers=True),
        gateway_factory=gateway_factory,
        rag=rag,
        hr_copilot=hr_copilot,
        forecast=forecast,
        coach_suggestions=coach_suggestions,
        guardian_reports=guardian_reports,
        provisioned=provisioned
        or {
            "inventory_monitor": True,
            "hr_copilot": True,
            "crm_assistant": True,
            "finance_assistant": True,
            "sales_coach": True,
            "audit_guardian": True,
        },
        confidence_threshold=threshold,
    )


async def collect(
    service: SupervisorService, query: str = "What stock is low?"
) -> list[SupervisorEvent]:
    return [
        event
        async for event in service.stream_answer(query=query, tenant_id=TENANT_ID, user_id=USER_ID)
    ]


def classification_events(events: list[SupervisorEvent]) -> list[ClassificationEvent]:
    return [e for e in events if isinstance(e, ClassificationEvent)]


def tokens_text(events: list[SupervisorEvent], agent: str) -> str:
    return "".join(e.delta for e in events if isinstance(e, TokenEvent) and e.agent == agent)


# --- classification ----------------------------------------------------------


async def test_classify_routes_high_confidence() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["inventory_monitor"], "confidence": 0.9}),
    )
    service = make_service(router=router)

    decision = await service.classify("What stock is below reorder point?")

    assert decision.agents == ("inventory_monitor",)
    assert decision.abstain is False
    assert decision.reason == "routed"
    assert router.complete_calls == 1


async def test_classify_abstains_low_confidence() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["hr_copilot"], "confidence": 0.4}),
    )
    service = make_service(router=router)

    decision = await service.classify("something vague")

    assert decision.abstain is True
    assert decision.reason == "low_confidence"


async def test_classify_abstains_unparseable_output() -> None:
    router = FakeLlmRouter(has_providers=True, completion_text="sorry, I can't")
    service = make_service(router=router)

    decision = await service.classify("blah blah")

    assert decision.abstain is True
    assert decision.reason == "unparseable_classifier_output"
    assert router.complete_calls == 2


async def test_classify_keyword_fallback_after_unparseable_output() -> None:
    router = FakeLlmRouter(has_providers=True, completion_text="sorry, I can't")
    service = make_service(router=router)

    decision = await service.classify("What stock is below reorder point?")

    assert decision.agents == ("inventory_monitor",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"
    assert router.complete_calls == 2


async def test_classify_recovers_after_truncated_completion() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=[
            '{"',
            json.dumps({"agents": ["finance_assistant"], "confidence": 0.9}),
        ],
    )
    service = make_service(router=router)

    decision = await service.classify("What is our net income this quarter?")

    assert decision.agents == ("finance_assistant",)
    assert decision.abstain is False
    assert decision.reason == "routed"
    assert router.complete_calls == 2


async def test_classify_keyword_fallback_without_providers() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(router=router)

    decision = await service.classify("How much stock is reserved?")

    assert decision.agents == ("inventory_monitor",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"
    assert router.complete_calls == 0


async def test_classify_keyword_fallback_when_provider_unavailable() -> None:
    router = FakeLlmRouter(has_providers=True, completion_text=AiUnavailableError("down"))
    service = make_service(router=router)

    decision = await service.classify("Summarize our leave policy")

    assert decision.agents == ("hr_copilot",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"


async def test_classify_strips_markdown_fences() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text="```json\n"
        + json.dumps({"agents": ["finance_assistant"], "confidence": 0.9})
        + "\n```",
    )
    service = make_service(router=router)

    decision = await service.classify("How was revenue last quarter?")

    assert decision.agents == ("finance_assistant",)
    assert decision.abstain is False


async def test_classify_recovers_fence_and_prose_wrapped_json() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text="\n```json\n"
        + json.dumps({"agents": ["finance_assistant"], "confidence": 0.9})
        + "\n```\nnothing else",
    )
    service = make_service(router=router)

    decision = await service.classify("What is our net income this quarter?")

    assert decision.agents == ("finance_assistant",)
    assert decision.abstain is False
    assert decision.reason == "routed"


async def test_classify_finance_keyword_fallback_covers_net_income() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(router=router)

    decision = await service.classify("What is our net income this quarter?")

    assert decision.agents == ("finance_assistant",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"
    assert router.complete_calls == 0


# --- streaming ---------------------------------------------------------------


async def test_stream_abstention_is_supervisor_segment() -> None:
    router = FakeLlmRouter(has_providers=True, completion_text="garbage")
    service = make_service(router=router)

    events = await collect(service, query="whatever")

    assert classification_events(events)[0].abstain is True
    assert [e.agent for e in events if isinstance(e, AgentStartEvent)] == ["supervisor"]
    assert tokens_text(events, "supervisor")  # non-empty text
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.agents == ("supervisor",)


async def test_stream_inventory_segment_with_citations() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["inventory_monitor"], "confidence": 0.95}),
        stream_tokens=["25 ", "units ", "on ", "hand."],
    )
    gateway = FakeGateway(
        levels=[
            StockLevelRow(
                product_id=uuid.uuid4(),
                warehouse_id=uuid.uuid4(),
                qty_on_hand=Decimal("25"),
                qty_reserved=Decimal("3"),
            )
        ]
    )
    service = make_service(router=router, gateway=gateway, rag=FakeRag())

    events = await collect(service, query="How much stock on hand?")

    classification = classification_events(events)[0]
    assert classification.agents == ("inventory_monitor",)
    assert tokens_text(events, "inventory_monitor") == "25 units on hand."
    citations = [
        e for e in events if isinstance(e, CitationsEvent) and e.agent == "inventory_monitor"
    ]
    assert len(citations) == 1
    assert citations[0].citations[0].source_ref == "docs/inventory-ops.md"
    # RAG context reached the prompt (single stream call happened).
    assert router.stream_calls == 1


async def test_stream_hr_copilot_segment() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["hr_copilot"], "confidence": 0.9}),
    )
    service = make_service(router=router, hr_copilot=FakeHrCopilot())

    events = await collect(service, query="How much leave do I get?")

    assert tokens_text(events, "hr_copilot") == "Two weeks of paid leave."
    citations = [e for e in events if isinstance(e, CitationsEvent) and e.agent == "hr_copilot"]
    assert citations[0].citations == ()
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.agents == ("hr_copilot",)


async def test_stream_unprovisioned_module_streams_abstention() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["crm_assistant"], "confidence": 0.95}),
    )
    service = make_service(router=router, provisioned={"crm_assistant": False})

    events = await collect(service, query="Who are our top customers?")

    assert [e.agent for e in events if isinstance(e, AgentStartEvent)] == ["crm_assistant"]
    assert "not provisioned" in tokens_text(events, "crm_assistant")
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.agents == ("crm_assistant",)


async def test_stream_multi_agent_sequential_segments() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps(
            {"agents": ["inventory_monitor", "hr_copilot"], "confidence": 0.9}
        ),
        stream_tokens=["5 ", "units."],
    )
    service = make_service(router=router, hr_copilot=FakeHrCopilot(answer="Answer two."))

    events = await collect(service, query="Stock and leave policies?")

    starts = [e for e in events if isinstance(e, AgentStartEvent)]
    assert [e.agent for e in starts] == ["inventory_monitor", "hr_copilot"]
    assert tokens_text(events, "inventory_monitor") == "5 units."
    assert tokens_text(events, "hr_copilot") == "Answer two."
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.agents == ("inventory_monitor", "hr_copilot")


async def test_stream_inventory_deterministic_without_provider() -> None:
    router = FakeLlmRouter(has_providers=False)
    gateway = FakeGateway(
        levels=[
            StockLevelRow(
                product_id=uuid.uuid4(),
                warehouse_id=uuid.uuid4(),
                qty_on_hand=Decimal("10"),
                qty_reserved=Decimal("1"),
            )
        ]
    )
    service = make_service(router=router, gateway=gateway)

    events = await collect(service, query="stock levels")

    text = tokens_text(events, "inventory_monitor")
    assert text
    assert "10" in text
    assert router.stream_calls == 0  # never hit a provider


async def test_stream_delegate_failure_degrades_not_raises() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["hr_copilot"], "confidence": 0.9}),
    )
    hr_copilot = FakeHrCopilot(error=AiUnavailableError("hr backend down"))
    service = make_service(router=router, hr_copilot=hr_copilot)

    events = await collect(service, query="Leave policy")

    assert "temporarily unavailable" in tokens_text(events, "hr_copilot")
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1


# --- Sales Coach + Audit Guardian delegates (SKY-90) -------------------------


async def test_classify_sales_coach_keyword_fallback() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(router=router)

    decision = await service.classify("What coaching suggestions do I have?")

    assert decision.agents == ("sales_coach",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"


async def test_classify_audit_guardian_keyword_fallback() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(router=router)

    decision = await service.classify("Show me the latest audit integrity report")

    assert decision.agents == ("audit_guardian",)
    assert decision.abstain is False
    assert decision.reason == "keyword_fallback"


async def test_classify_rejects_unknown_agent_keys() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["not_a_real_agent"], "confidence": 0.9}),
    )
    service = make_service(router=router)

    decision = await service.classify("weird question")

    assert decision.agents == ()
    assert decision.abstain is True


async def test_stream_sales_coach_no_suggestions() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["sales_coach"], "confidence": 0.95}),
    )
    service = make_service(router=router, coach_suggestions=FakeCoachSuggestions())

    events = await collect(service, query="Do I have any coaching suggestions?")

    assert "no pending coaching suggestions" in tokens_text(events, "sales_coach")
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.agents == ("sales_coach",)


async def test_stream_sales_coach_deterministic_without_provider() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(
        router=router,
        coach_suggestions=FakeCoachSuggestions(
            [
                {
                    "status": "pending",
                    "title": "Follow up on Acme deal",
                    "body": "The proposal was sent 5 days ago.",
                }
            ]
        ),
    )

    events = await collect(service, query="What coaching should I work on?")

    text = tokens_text(events, "sales_coach")
    assert "Follow up on Acme deal" in text
    assert "The proposal was sent 5 days ago." in text
    assert router.complete_calls == 0


async def test_stream_sales_coach_llm_path_uses_suggestion_context() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["sales_coach"], "confidence": 0.95}),
    )
    service = make_service(
        router=router,
        coach_suggestions=FakeCoachSuggestions(
            [
                {
                    "status": "pending",
                    "title": "Pipeline review",
                    "body": "Three deals are stuck in negotiation.",
                }
            ]
        ),
    )

    events = await collect(service, query="Summarize my coaching")

    assert router.complete_calls >= 1  # classification call
    assert tokens_text(events, "sales_coach")  # non-empty text segment


async def test_stream_guardian_no_report() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["audit_guardian"], "confidence": 0.95}),
    )
    service = make_service(router=router, guardian_reports=FakeGuardianReports())

    events = await collect(service, query="Any security findings this week?")

    assert "no Audit Guardian report" in tokens_text(events, "audit_guardian")


async def test_stream_guardian_deterministic_without_provider() -> None:
    router = FakeLlmRouter(has_providers=False)
    service = make_service(
        router=router,
        guardian_reports=FakeGuardianReports(
            reports=[
                {
                    "id": uuid.uuid4(),
                    "summary": "One auth burst outside business hours.",
                    "total_events_scanned": 42,
                    "flagged_count": 2,
                }
            ],
            events=[
                {
                    "severity": "high",
                    "reason": "auth_burst",
                    "source_table": "identity_audit_log",
                    "event_action": "sign_in.failed",
                },
                {
                    "severity": "medium",
                    "reason": "off_hours_access",
                    "source_table": "ai_audit_log",
                    "event_action": "chat.stream",
                },
            ],
        ),
    )

    events = await collect(service, query="Summarize the audit report")

    text = tokens_text(events, "audit_guardian")
    assert "42 events scanned" in text
    assert "2 flagged" in text
    assert "auth_burst" in text
    assert router.complete_calls == 0


async def test_stream_guardian_llm_path_emits_citation() -> None:
    router = FakeLlmRouter(
        has_providers=True,
        completion_text=json.dumps({"agents": ["audit_guardian"], "confidence": 0.95}),
    )
    report_id = uuid.uuid4()
    service = make_service(
        router=router,
        guardian_reports=FakeGuardianReports(
            reports=[
                {
                    "id": report_id,
                    "summary": "No suspicious activity detected.",
                    "total_events_scanned": 10,
                    "flagged_count": 0,
                }
            ]
        ),
    )

    events = await collect(service, query="Latest audit report?")

    citations = [e for e in events if isinstance(e, CitationsEvent) and e.agent == "audit_guardian"]
    assert len(citations) == 1
    assert citations[0].citations[0].module == "audit_guardian"
    assert str(report_id) in citations[0].citations[0].source_ref
    assert tokens_text(events, "audit_guardian")  # non-empty text segment
