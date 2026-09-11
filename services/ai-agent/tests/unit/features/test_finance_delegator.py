"""Unit tests for the supervisor's FinanceDelegator.

The delegator must (a) answer deterministic finance questions without an LLM,
(b) fall back to the LLM grounded in live finance context, and (c) degrade to a
clean "unavailable" message rather than killing the stream when finance is down.
These tests return Decimal money end-to-end and never leak a float.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.core.providers import LlmCompletion, LlmRequest
from ai_agent.features.finance.gateway import (
    AccountRef,
    ArAgingBucketRef,
    ArAgingRef,
    CashflowPositionRef,
    CashflowProjectionRef,
    InvoiceRef,
    PnlRef,
    TrialBalanceRef,
    TrialBalanceRowRef,
)
from ai_agent.features.supervisor.delegates import FinanceDelegator

if TYPE_CHECKING:
    from ai_agent.features.supervisor.schemas import Citation

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeLlmRouter:
    def __init__(self, completion_text: str = "Finance fallback answer.") -> None:
        self.completion_text = completion_text
        self.calls: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        self.calls.append(request)
        return LlmCompletion(text=self.completion_text, model_used="fake-model", latency_ms=1)


class FakeFinanceGateway:
    def __init__(
        self,
        *,
        invoices: list[InvoiceRef] | None = None,
        pnl: PnlRef | None = None,
        ar: ArAgingRef | None = None,
        trial_balance: TrialBalanceRef | None = None,
        cashflow: CashflowProjectionRef | None = None,
        fail: bool = False,
    ) -> None:
        self._invoices = invoices or []
        self._pnl = pnl
        self._ar = ar
        self._trial_balance = trial_balance
        self._cashflow = cashflow
        self._fail = fail

    async def list_accounts(self) -> list[AccountRef]:
        return []

    async def list_invoices(self) -> list[InvoiceRef]:
        if self._fail:
            raise AiUnavailableError("finance down")
        return self._invoices

    async def get_pnl(self) -> PnlRef | None:
        if self._fail:
            raise AiUnavailableError("finance down")
        return self._pnl

    async def get_ar_aging(self) -> ArAgingRef | None:
        if self._fail:
            raise AiUnavailableError("finance down")
        return self._ar

    async def get_trial_balance(self, *, as_of: date) -> TrialBalanceRef | None:
        if self._fail:
            raise AiUnavailableError("finance down")
        return self._trial_balance

    async def get_cashflow_projection(self, *, as_of: date) -> CashflowProjectionRef | None:
        if self._fail:
            raise AiUnavailableError("finance down")
        return self._cashflow


async def collect(delegator: FinanceDelegator, query: str) -> str:
    return "".join(
        [
            delta
            async for delta in delegator.stream(
                query=query, tenant_id=TENANT_ID, user_id=USER_ID, citations=[]
            )
        ]
    )


async def collect_with_citations(
    delegator: FinanceDelegator, query: str
) -> tuple[str, list[Citation]]:
    citations: list[Citation] = []
    text = "".join(
        [
            delta
            async for delta in delegator.stream(
                query=query, tenant_id=TENANT_ID, user_id=USER_ID, citations=citations
            )
        ]
    )
    return text, citations


def make_delegator(router: FakeLlmRouter, gateway: FakeFinanceGateway) -> FinanceDelegator:
    async def factory() -> FakeFinanceGateway:
        return gateway

    return FinanceDelegator(llm_router=router, finance_gateway_factory=factory)


def _invoice(status: str = "issued", total: str = "100.0000", month: int = 8) -> InvoiceRef:
    return InvoiceRef(
        id=uuid.uuid4(),
        invoice_number="INV-0001",
        customer_name="Acme",
        status=status,
        total=Decimal(total),
        invoice_date=date(2026, month, 1),
        due_date=date(2026, month, 28),
    )


def _history_invoices(months: list[int] | None = None) -> list[InvoiceRef]:
    """>= 3 distinct invoice months so the delegator's history guard passes."""
    return [_invoice(month=month) for month in (months or [1, 2, 3, 4, 5, 6])]


def _pnl() -> PnlRef:
    return PnlRef(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
        total_revenue=Decimal("120000.0000"),
        total_expenses=Decimal("80000.0000"),
        net_income=Decimal("40000.0000"),
    )


def _ar() -> ArAgingRef:
    return ArAgingRef(
        as_of=date(2026, 8, 31),
        total_ar=Decimal("9000.0000"),
        buckets=(
            ArAgingBucketRef(bucket="current", count=5, amount=Decimal("4000.0000")),
            ArAgingBucketRef(bucket=">90", count=2, amount=Decimal("5000.0000")),
        ),
    )


def _trial_balance() -> TrialBalanceRef:
    return TrialBalanceRef(
        as_of=date(2026, 8, 31),
        rows=(
            TrialBalanceRowRef(
                code="1000",
                name="Cash",
                account_type="asset",
                debit=Decimal("21000.0000"),
                credit=Decimal("0.0000"),
            ),
            TrialBalanceRowRef(
                code="4000",
                name="Revenue",
                account_type="revenue",
                debit=Decimal("0.0000"),
                credit=Decimal("21000.0000"),
            ),
        ),
        total_debit=Decimal("21000.0000"),
        total_credit=Decimal("21000.0000"),
    )


def _cashflow() -> CashflowProjectionRef:
    return CashflowProjectionRef(
        positions=(
            CashflowPositionRef(
                month="2026-09",
                opening=Decimal("10000.0000"),
                inflows=Decimal("5000.0000"),
                outflows=Decimal("3000.0000"),
                closing=Decimal("12000.0000"),
            ),
        ),
    )


class TestDeterministic:
    async def test_invoice_summary_counts_by_status(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(
            invoices=[_invoice("issued"), _invoice("paid"), _invoice("draft")]
        )
        text = await collect(make_delegator(router, gateway), "How many invoices do we have?")

        assert "3 invoices" in text
        assert "issued 1" in text
        assert "paid 1" in text
        assert "draft 1" in text
        assert router.calls == []  # answered without the LLM

    async def test_invoice_summary_answers_without_history(
        self,
    ) -> None:
        """Snapshot catalog reads are exempt from the history guardrail."""
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=[_invoice("issued", month=8)])
        text = await collect(make_delegator(router, gateway), "How many invoices do we have?")

        assert "1 invoices" in text
        assert "issued 1" in text
        assert router.calls == []

    async def test_net_income_answer(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=_history_invoices(), pnl=_pnl())
        text = await collect(make_delegator(router, gateway), "What is our net income?")

        assert "40000" in text
        assert router.calls == []

    async def test_ar_aging_answer(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=_history_invoices(), ar=_ar())
        text = await collect(make_delegator(router, gateway), "Show me the AR aging report.")

        assert "9000" in text
        assert "current 4000" in text
        assert ">90 5000" in text
        assert router.calls == []


class TestIntents:
    async def test_trial_balance_answer(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=_history_invoices(), trial_balance=_trial_balance())
        text = await collect(make_delegator(router, gateway), "Show me the trial balance.")

        assert "total debits 21000" in text
        assert "total credits 21000" in text
        assert "Cash" in text
        assert router.calls == []

    async def test_cashflow_projection_answer(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=_history_invoices(), cashflow=_cashflow())
        text = await collect(make_delegator(router, gateway), "How much cash do we have coming in?")

        assert "Cash flow projection" in text
        assert "opening 10000" in text
        assert "closing 12000" in text
        assert router.calls == []

    async def test_insufficient_history_abstains(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=[_invoice(month=8)], pnl=_pnl(), ar=_ar())
        text = await collect(make_delegator(router, gateway), "What is our net income?")

        assert "history" in text.casefold()
        assert "40000" not in text
        assert router.calls == []

    async def test_intent_answer_emits_citation_to_report(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(invoices=_history_invoices(), pnl=_pnl())
        text, citations = await collect_with_citations(
            make_delegator(router, gateway), "What is our net income?"
        )

        assert "40000" in text
        assert len(citations) == 1
        assert citations[0].module == "finance"
        assert citations[0].source_ref == "/api/v1/finance/reports/profit-and-loss"
        assert citations[0].title == "Profit & Loss"


class TestLlmFallback:
    async def test_grounds_llm_in_live_finance_context(self) -> None:
        router = FakeLlmRouter(completion_text="Here is the finance overview.")
        gateway = FakeFinanceGateway(invoices=[_invoice("issued")], pnl=_pnl())
        text = await collect(make_delegator(router, gateway), "Summarize our finances.")

        assert text == "Here is the finance overview."
        assert len(router.calls) == 1
        assert "120000" in router.calls[0].system_prompt
        assert "issued" in router.calls[0].system_prompt


class TestDegradation:
    async def test_gateway_down_streams_unavailable_not_fatal(self) -> None:
        router = FakeLlmRouter()
        gateway = FakeFinanceGateway(fail=True)
        text = await collect(make_delegator(router, gateway), "Any invoices?")

        assert "unavailable" in text.casefold()

    async def test_llm_outage_streams_unavailable(self) -> None:
        class _Boom:
            async def complete(self, request: LlmRequest) -> LlmCompletion:
                raise AiUnavailableError("llm down")

        router = _Boom()  # type: ignore[assignment]
        gateway = FakeFinanceGateway(invoices=[_invoice("issued")])
        text = await collect(make_delegator(router, gateway), "Summarize our finances.")

        assert "unavailable" in text.casefold()
