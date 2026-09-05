"""Unit tests for the cross-module narrator (SKY-63).

Fake gateway (canned signals), fake cache, fake audit and a fake LLM router:
no DB, no IO. Covers cache reuse, force-refresh gating, material-activity
abstention, LLM-disabled abstention, unparseable abstention, successful
narration, and the pure extract/parse helpers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from ai_agent.core.audit_events import AI_NARRATOR_GENERATED
from ai_agent.features.narrator.extract import (
    build_prompt,
    build_signals_dict,
    has_material_activity,
)
from ai_agent.features.narrator.gateway import (
    CoreGatewayPort,
    CrmSignals,
    FinanceSignals,
    HttpCoreGateway,
    InventorySignals,
    SalesSignals,
    StockHealthSignals,
)
from ai_agent.features.narrator.narrate import _parse_digest_json, narrate
from ai_agent.features.narrator.service import NarratorService
from skyrict_common.exceptions import PermissionDeniedError

AS_OF = date(2026, 8, 27)
TENANT = uuid.uuid4()
USER = uuid.uuid4()


class FakeGateway(CoreGatewayPort):
    def __init__(self, *, material: bool = True) -> None:
        self.material = material
        self.finance_calls = 0

    async def get_finance(self, as_of: date) -> FinanceSignals:
        self.finance_calls += 1
        ar = {"current": Decimal("100"), "over_90": Decimal("50")} if self.material else {}
        return FinanceSignals(
            cash_balance=Decimal("1000") if self.material else Decimal("0"),
            total_ar=Decimal("150") if self.material else Decimal("0"),
            ar_buckets=ar,
            payables=Decimal("200") if self.material else Decimal("0"),
            net_income=Decimal("0"),
        )

    async def get_sales(self, as_of: date) -> SalesSignals:
        return SalesSignals(
            confirmed_unfulfilled_value=Decimal("500") if self.material else Decimal("0")
        )

    async def get_inventory(self) -> InventorySignals:
        return (
            InventorySignals(stock_out_count=1, low_stock_count=2, total_sku_count=10)
            if self.material
            else InventorySignals(0, 0, 0)
        )

    async def get_inventory_health(self) -> StockHealthSignals:
        return (
            StockHealthSignals(
                dead_stock_count=4,
                slow_mover_count=3,
                tied_up_capital=Decimal("2500"),
            )
            if self.material
            else StockHealthSignals(0, 0, Decimal("0"))
        )

    async def get_crm(self, as_of: date) -> CrmSignals:
        return (
            CrmSignals(open_opportunities=3, won_recent_days=2, win_rate=Decimal("0.5"))
            if self.material
            else CrmSignals(0, 0, Decimal("0"))
        )


class FakeCache:
    def __init__(self) -> None:
        self.rows: dict[date, object] = {}
        self.inserted: list[object] = []

    async def latest_for_date(self, tenant_id: uuid.UUID, as_of: date) -> object | None:
        return self.rows.get(as_of)

    async def insert(
        self,
        *,
        tenant_id: uuid.UUID,
        status: str,
        as_of: date,
        title: str | None,
        summary: str | None,
        points: list[str] | None,
        caveat: str | None,
        signals: dict[str, object] | None,
        model_used: str | None,
        latency_ms: int | None,
        generated_at: datetime,
    ) -> object:
        class Row:
            pass

        row = Row()
        row.status = status  # type: ignore[attr-defined]
        row.as_of = as_of
        row.title = title
        row.summary = summary
        row.points = points or []
        row.caveat = caveat
        row.signals = signals or {}
        row.model_used = model_used
        row.generated_at = generated_at
        self.rows[as_of] = row
        self.inserted.append(row)
        return row

    def is_fresh_for(self, row: object, as_of: date) -> bool:
        return row.as_of == as_of


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def log(
        self,
        *,
        action: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        input_payload: dict[str, object] | None = None,
        output_payload: dict[str, object] | None = None,
        model_used: str | None = None,
        latency_ms: int | None = None,
    ) -> object:
        self.events.append({"action": action})
        return None


class FakeLlm:
    def __init__(self, *, text: str | None = None, raise_error: bool = False) -> None:
        self._text = text
        self._raise_error = raise_error

    async def complete(self, request: object) -> object:
        if self._raise_error:
            from ai_agent.core.exceptions import AiUnavailableError

            raise AiUnavailableError("boom")
        from ai_agent.core.providers import LlmCompletion

        return LlmCompletion(text=self._text or "{}", model_used="fake-model", latency_ms=10)


def _service(
    *,
    gateway: FakeGateway | None = None,
    cache: FakeCache | None = None,
    audit: FakeAudit | None = None,
    llm: FakeLlm | None = None,
    allow_llm: bool = True,
    allow_refresh: bool = True,
) -> tuple[NarratorService, FakeCache, FakeAudit, FakeGateway]:
    gw = gateway or FakeGateway(material=True)
    ca = cache or FakeCache()
    au = audit or FakeAudit()
    svc = NarratorService(
        gateway=gw,
        llm_router=llm or FakeLlm(text=_GOOD_JSON),  # type: ignore[arg-type]
        cache=ca,  # type: ignore[arg-type]
        audit=au,  # type: ignore[arg-type]
        allow_llm=allow_llm,
        allow_refresh=allow_refresh,
    )
    return svc, ca, au, gw


_GOOD_JSON = (
    '{"title": "Healthy cash, watch receivables", '
    '"summary": "Cash is strong but AR is aging.", '
    '"points": ["AR over 90 is 50", "One stock-out"], '
    '"caveat": ""}'
)


class TestNarratorService:
    async def test_cache_hit_skips_llm(self) -> None:
        cache = FakeCache()
        # Pre-seed a fresh cached row.
        row = await cache.insert(
            tenant_id=TENANT,
            status="generated",
            as_of=AS_OF,
            title="cached",
            summary="old",
            points=["x"],
            caveat="",
            signals={},
            model_used="m",
            latency_ms=1,
            generated_at=datetime.now(tz=UTC),
        )
        cache.rows[AS_OF] = row
        svc, _, audit, _ = _service(cache=cache, llm=FakeLlm(text=_GOOD_JSON))
        result = await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.source == "cache"
        assert result.title == "cached"
        assert audit.events == []

    async def test_force_refresh_regenerates_and_audits(self) -> None:
        svc, cache, audit, _ = _service(llm=FakeLlm(text=_GOOD_JSON))
        result = await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=True)
        assert result.status == "generated"
        assert result.source == "live"
        assert result.title == "Healthy cash, watch receivables"
        assert result.points == ["AR over 90 is 50", "One stock-out"]
        assert audit.events == [{"action": AI_NARRATOR_GENERATED}]
        assert len(cache.inserted) == 1

    async def test_force_refresh_denied_raises(self) -> None:
        svc, _, _, _ = _service(allow_refresh=False)
        with pytest.raises(PermissionDeniedError):
            await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=True)

    async def test_non_material_day_abstains(self) -> None:
        svc, _, audit, _ = _service(
            gateway=FakeGateway(material=False), llm=FakeLlm(text=_GOOD_JSON)
        )
        result = await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.status == "abstained"
        assert result.source == "abstention"
        assert audit.events == []

    async def test_llm_disabled_abstains(self) -> None:
        svc, _, audit, _ = _service(allow_llm=False, llm=FakeLlm(text=_GOOD_JSON))
        result = await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.status == "abstained"
        assert result.source == "llm_disabled"
        assert audit.events == []

    async def test_unparseable_llm_abstains(self) -> None:
        svc, _, audit, _ = _service(llm=FakeLlm(text="not json at all"))
        result = await svc.digest(tenant_id=TENANT, user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.status == "abstained"
        assert result.source == "unparseable"
        assert audit.events == []


class TestExtract:
    def test_build_signals_dict_serializes_money(self) -> None:
        signals = build_signals_dict(
            as_of=AS_OF,
            finance=FinanceSignals(
                Decimal("1000"),
                Decimal("150"),
                {"over_90": Decimal("50")},
                Decimal("200"),
                Decimal("0"),
            ),
            sales=SalesSignals(Decimal("500")),
            inventory=InventorySignals(1, 2, 10),
            inventory_health=StockHealthSignals(4, 3, Decimal("2500")),
            crm=CrmSignals(3, 2, Decimal("0.5")),
        )
        assert signals["as_of"] == "2026-08-27"
        assert signals["finance"]["cash_balance"] == "1000.00"  # type: ignore[index]
        assert signals["inventory"]["stock_out_count"] == 1  # type: ignore[index]
        assert signals["inventory"]["dead_stock_count"] == 4  # type: ignore[index]
        assert signals["inventory"]["slow_mover_count"] == 3  # type: ignore[index]
        assert signals["inventory"]["tied_up_capital"] == "2500.00"  # type: ignore[index]

    def test_material_activity_true_when_any_module_nonempty(self) -> None:
        signals = build_signals_dict(
            as_of=AS_OF,
            finance=FinanceSignals(Decimal("0"), Decimal("0"), {}, Decimal("0"), Decimal("0")),
            sales=SalesSignals(Decimal("0")),
            inventory=InventorySignals(0, 0, 0),
            inventory_health=StockHealthSignals(0, 0, Decimal("0")),
            crm=CrmSignals(3, 0, Decimal("0")),
        )
        assert has_material_activity(signals) is True

    def test_material_activity_false_when_all_empty(self) -> None:
        signals = build_signals_dict(
            as_of=AS_OF,
            finance=FinanceSignals(Decimal("0"), Decimal("0"), {}, Decimal("0"), Decimal("0")),
            sales=SalesSignals(Decimal("0")),
            inventory=InventorySignals(0, 0, 0),
            inventory_health=StockHealthSignals(0, 0, Decimal("0")),
            crm=CrmSignals(0, 0, Decimal("0")),
        )
        assert has_material_activity(signals) is False

    def test_material_activity_true_on_health_issues_alone(self) -> None:
        signals = build_signals_dict(
            as_of=AS_OF,
            finance=FinanceSignals(Decimal("0"), Decimal("0"), {}, Decimal("0"), Decimal("0")),
            sales=SalesSignals(Decimal("0")),
            inventory=InventorySignals(0, 0, 0),
            inventory_health=StockHealthSignals(4, 3, Decimal("2500")),
            crm=CrmSignals(0, 0, Decimal("0")),
        )
        assert has_material_activity(signals) is True

    def test_build_prompt_contains_signal_keys(self) -> None:
        signals = build_signals_dict(
            as_of=AS_OF,
            finance=FinanceSignals(Decimal("1000"), Decimal("0"), {}, Decimal("0"), Decimal("0")),
            sales=SalesSignals(Decimal("0")),
            inventory=InventorySignals(0, 0, 0),
            inventory_health=StockHealthSignals(0, 0, Decimal("0")),
            crm=CrmSignals(0, 0, Decimal("0")),
        )
        prompt = build_prompt(signals)
        assert '"finance"' in prompt
        assert '"as_of"' in prompt


class TestHttpGateway:
    def _gateway(self) -> HttpCoreGateway:
        return HttpCoreGateway(base_url="http://core", bearer_token="t", tenant_slug="acme")

    async def test_get_inventory_health_parses_counts_and_money(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get_data(
            self: HttpCoreGateway, path: str, params: dict[str, str]
        ) -> dict[str, object]:
            assert path == "/inventory/health/summary"
            assert params == {"days": "90"}
            return {"dead_stock_count": 4, "slow_mover_count": 3, "tied_up_capital": [2500, "USD"]}

        monkeypatch.setattr(HttpCoreGateway, "_get_data", fake_get_data)
        signal = await self._gateway().get_inventory_health()
        assert signal.dead_stock_count == 4
        assert signal.slow_mover_count == 3
        assert signal.tied_up_capital == Decimal("2500")

    async def test_get_inventory_health_tolerates_missing_cost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get_data(
            self: HttpCoreGateway, path: str, params: dict[str, str]
        ) -> dict[str, object]:
            return {"dead_stock_count": 2, "slow_mover_count": 0, "tied_up_capital": None}

        monkeypatch.setattr(HttpCoreGateway, "_get_data", fake_get_data)
        signal = await self._gateway().get_inventory_health()
        assert signal.dead_stock_count == 2
        assert signal.slow_mover_count == 0
        assert signal.tied_up_capital == Decimal("0")


class TestNarrate:
    def test_parses_fenced_json(self) -> None:
        text = '```json\n{"title": "T", "summary": "S", "points": ["a"], "caveat": ""}\n```'
        payload = _parse_digest_json(text)
        assert isinstance(payload, dict)
        assert payload["title"] == "T"

    def test_parse_invalid_returns_none(self) -> None:
        assert _parse_digest_json("not json") is None

    async def test_narrate_success(self) -> None:
        llm = FakeLlm(text=_GOOD_JSON)
        digest = await narrate(llm, "prompt")  # type: ignore[arg-type]
        assert digest is not None
        assert digest.title == "Healthy cash, watch receivables"
        assert digest.points == ["AR over 90 is 50", "One stock-out"]

    async def test_narrate_invalid_returns_none(self) -> None:
        llm = FakeLlm(text="garbage")
        assert await narrate(llm, "prompt") is None  # type: ignore[arg-type]
