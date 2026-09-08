"""Unit tests for the L3 HR/Payroll narrator (HR-AI-003).

Fake gateway (canned core payload), fake cache, fake audit and a fake LLM
router: no DB, no IO. The reconciliation contract is the headline assertion
set - for payroll_cost, every ``{{TOKEN}}`` in the narrative must be replaced
with the exact figure string from the core source payload (token substitution,
never a number the model typed).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from ai_agent.features.l3.extract import (
    build_payroll_cost_signals,
    build_prompt,
    has_material_activity,
)
from ai_agent.features.l3.gateway import L3CoreGatewayPort
from ai_agent.features.l3.narrate import _parse_json, narrate_l3
from ai_agent.features.l3.render import render_narrative
from ai_agent.features.l3.service import L3NarrativeService
from skyrict_common.exceptions import PermissionDeniedError

AS_OF = date(2026, 9, 8)
TENANT = uuid.uuid4()
USER = uuid.uuid4()

_SPIKE_PAYLOAD = {
    "current_period_start": "2026-03-01",
    "current_period_end": "2026-03-31",
    "current_run_code": "PR-2026-03",
    "previous_period_start": "2026-02-01",
    "previous_period_end": "2026-02-28",
    "previous_run_code": "PR-2026-02",
    "current_headcount": 12,
    "previous_headcount": 12,
    "headcount_delta": 0,
    "current_gross": "132400.00",
    "previous_gross": "118000.00",
    "gross_delta": "14400.00",
    "current_net": "105520.00",
    "previous_net": "96400.00",
    "net_delta": "9120.00",
    "current_overtime": "21600.00",
    "previous_overtime": "0.00",
    "overtime_delta": "21600.00",
    "department_breakdown": [
        {"department_name": "Operations", "current_net": "52060.00", "previous_net": "41400.00",
         "net_delta": "10660.00"},
        {"department_name": "Engineering", "current_net": "53460.00", "previous_net": "55000.00",
         "net_delta": "-1540.00"},
    ],
}

_FLAT_PAYLOAD = {**dict(_SPIKE_PAYLOAD), **{key: ("0" if key.endswith("_delta") else value)
                                             for key, value in _SPIKE_PAYLOAD.items()}}

_GOOD_JSON = ('{"title": "Overtime drove payroll cost up {{overtime_delta}}",'
              ' "summary": "March payroll rose {{net_delta}} headcount-flat,'
              ' led by a {{overtime_delta}} overtime spike in Operations.",'
              ' "points": ["Net pay up {{net_delta}} with headcount unchanged'
              ' ({{headcount_delta}})", "Overtime spike of {{overtime_delta}}'
              ' concentrated in Operations"],'
              ' "caveat": "Figures verified against payroll runs."}')


class FakeGateway(L3CoreGatewayPort):
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def get_payroll_cost_movement(self, as_of: object) -> dict[str, object]:
        return self.payload

    async def get_leave_pay_pairs(self, as_of: object) -> dict[str, object]:
        raise NotImplementedError

    async def get_compliance_risk(self, as_of: object) -> dict[str, object]:
        raise NotImplementedError


class FakeLlm:
    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, request: object) -> object:
        class _Completion:
            text = self.text
            model_used = "fake-model"

        return _Completion()


class FakeCache:
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str, date], object] = {}
        self.inserted: list[object] = []

    async def latest_for_kind(
        self, tenant_id: uuid.UUID, kind: str, as_of: date
    ) -> object | None:
        return self.rows.get((tenant_id, kind, as_of))

    async def insert(
        self,
        *,
        tenant_id: uuid.UUID,
        kind: str,
        status: str,
        as_of: date,
        title: str | None,
        summary: str | None,
        points: list[str] | None,
        caveat: str | None,
        figures: dict[str, str] | None,
        model_used: str | None,
        generated_at: datetime,
    ) -> object:
        class Row:
            pass

        row = Row()
        row.status = status  # type: ignore[attr-defined]
        row.kind = kind  # type: ignore[attr-defined]
        row.as_of = as_of
        row.title = title
        row.summary = summary
        row.points = points or []
        row.caveat = caveat
        row.figures = figures
        row.model_used = model_used
        row.generated_at = generated_at
        self.rows[(tenant_id, kind, as_of)] = row
        self.inserted.append(row)
        return row


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def log(self, **kwargs: object) -> None:
        self.events.append(kwargs)


class FakeCacheWithFreshness(FakeCache):
    @staticmethod
    def is_fresh_for(row: object, as_of: date) -> bool:
        return isinstance(row, object) and getattr(row, "as_of", None) == as_of


def _service(*, gateway: FakeGateway | None = None, llm: FakeLlm | None = None,
             allow_llm: bool = True, allow_refresh: bool = True) -> tuple[
                 L3NarrativeService, FakeCache, FakeAudit, FakeLlm
             ]:
    cache = FakeCacheWithFreshness()
    audit = FakeAudit()
    fake_llm = llm or FakeLlm(text=_GOOD_JSON)
    svc = L3NarrativeService(
        gateway=gateway or FakeGateway(_SPIKE_PAYLOAD),
        llm_router=fake_llm,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        allow_llm=allow_llm,
        allow_refresh=allow_refresh,
    )
    return svc, cache, audit, fake_llm


class TestPayrollCostSignals:
    def test_figures_reconcile_to_core_payload(self) -> None:
        signals = build_payroll_cost_signals(_SPIKE_PAYLOAD)
        figures = signals["figures"]
        # Every figure token carries the EXACT string from the source payload.
        assert figures["{{overtime_delta}}"] == "21600.00"
        assert figures["{{net_delta}}"] == "9120.00"
        assert figures["{{gross_delta}}"] == "14400.00"
        assert figures["{{headcount_delta}}"] == "0"
        assert signals["has_material_activity"] is True

    def test_flat_month_is_not_material(self) -> None:
        signals = build_payroll_cost_signals(_FLAT_PAYLOAD)
        assert signals["has_material_activity"] is False
        assert has_material_activity("payroll_cost", signals) is False

    def test_material_activity_true_on_spike(self) -> None:
        signals = build_payroll_cost_signals(_SPIKE_PAYLOAD)
        assert has_material_activity("payroll_cost", signals) is True

    def test_build_prompt_exposes_tokens_not_numbers(self) -> None:
        signals = build_payroll_cost_signals(_SPIKE_PAYLOAD)
        prompt = build_prompt("payroll_cost", signals)
        assert "{{overtime_delta}}" in prompt
        assert "payroll_cost" in prompt


class TestRender:
    def test_tokens_replaced_with_verified_figures(self) -> None:
        from ai_agent.features.l3.narrate import L3NarrativeText

        text = L3NarrativeText(
            title="Cost up {{net_delta}}",
            summary="Net pay rose {{net_delta}}, overtime {{overtime_delta}}.",
            points=["{{gross_delta}} gross", "hc {{headcount_delta}}"],
            caveat="",
            model_used="fake",
            latency_ms=10,
        )
        figures = build_payroll_cost_signals(_SPIKE_PAYLOAD)["figures"]
        rendered = render_narrative(text, figures)
        assert "{{" not in rendered.title
        assert rendered.title == "Cost up 9120.00"
        assert "9120.00" in rendered.summary
        assert "14400.00" in rendered.points[0]
        assert "hc 0" in rendered.points[1]

    def test_unknown_tokens_survive_unreplaced(self) -> None:
        from ai_agent.features.l3.narrate import L3NarrativeText

        text = L3NarrativeText("t", "{{MISSING}} kept", ["x"], "", "fake", 1)
        rendered = render_narrative(text, {"{{known}}": "1"})
        assert "{{MISSING}}" in rendered.summary


class TestNarrate:
    def test_parses_fenced_json(self) -> None:
        raw = '```json\n{"title": "T", "summary": "S", "points": ["a"], "caveat": ""}\n```'
        assert isinstance(_parse_json(raw), dict)
        assert _parse_json(raw)["title"] == "T"  # type: ignore[index]

    def test_parse_invalid_returns_none(self) -> None:
        assert _parse_json("not json") is None


class TestService:
    async def test_generates_and_persists(self) -> None:
        svc, cache, audit, _ = _service()
        result = await svc.generate(
            kind="payroll_cost", tenant_id=TENANT, user_id=USER, as_of=AS_OF,
            force_refresh=False,
        )
        assert result.status == "generated"
        assert result.source == "live"
        assert result.title == "Overtime drove payroll cost up 21600.00"
        assert result.figures["{{overtime_delta}}"] == "21600.00"
        assert audit.events, "generation must audit"
        assert cache.inserted, "generation must persist a snapshot"

    async def test_cache_hit_skips_llm(self) -> None:
        svc, cache, audit, _ = _service()
        await svc.generate(kind="payroll_cost", tenant_id=TENANT, user_id=USER,
                           as_of=AS_OF, force_refresh=False)
        result = await svc.generate(kind="payroll_cost", tenant_id=TENANT,
                                    user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.source == "cache"
        assert len(cache.inserted) == 1

    async def test_force_refresh_allowed_when_gate_open(self) -> None:
        svc, cache, _, _ = _service()
        result = await svc.generate(kind="payroll_cost", tenant_id=TENANT,
                                    user_id=USER, as_of=AS_OF, force_refresh=True)
        assert result.source == "live"
        assert len(cache.inserted) == 1

    async def test_force_refresh_denied_when_gate_closed(self) -> None:
        svc, _, _, _ = _service(allow_refresh=False)
        with pytest.raises(PermissionDeniedError):
            await svc.generate(kind="payroll_cost", tenant_id=TENANT, user_id=USER,
                               as_of=AS_OF, force_refresh=True)

    async def test_llm_disabled_abstains(self) -> None:
        svc, cache, audit, _ = _service(allow_llm=False)
        result = await svc.generate(kind="payroll_cost", tenant_id=TENANT,
                                    user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.status == "abstained"
        assert result.source == "llm_disabled"
        assert audit.events == []

    async def test_unparseable_llm_abstains(self) -> None:
        svc, _, audit, _ = _service(llm=FakeLlm(text="not json at all"))
        result = await svc.generate(kind="payroll_cost", tenant_id=TENANT,
                                    user_id=USER, as_of=AS_OF, force_refresh=False)
        assert result.status == "abstained"
        assert result.source == "unparseable"

    async def test_unknown_kind_raises(self) -> None:
        svc, _, _, _ = _service()
        with pytest.raises(ValueError):
            await svc.generate(kind="nope", tenant_id=TENANT, user_id=USER,
                               as_of=AS_OF, force_refresh=False)