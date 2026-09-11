"""Unit tests for the finance_intents module (SKY-82 / FIN-AI-003 A3).

The matcher must classify only whitelisted questions, and the executor must
answer strictly from the gateway report calls it maps 1:1 to - every row it
surfaces stays Decimal and each result carries the canonical report endpoint
(the citation + reconciliation anchor).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

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
from ai_agent.features.finance_intents.executor import run_finance_intent
from ai_agent.features.finance_intents.matcher import match_finance_intent

AS_OF = date(2026, 8, 31)


class FakeFinanceGateway:
    """Sender-implemented FinanceGatewayPort: returns the seeded report refs."""

    def __init__(
        self,
        *,
        invoices: list[InvoiceRef] | None = None,
        pnl: PnlRef | None = None,
        ar: ArAgingRef | None = None,
        trial_balance: TrialBalanceRef | None = None,
        cashflow: CashflowProjectionRef | None = None,
    ) -> None:
        self._invoices = invoices or []
        self._pnl = pnl
        self._ar = ar
        self._trial_balance = trial_balance
        self._cashflow = cashflow
        self.calls: list[str] = []

    async def list_accounts(self) -> list[AccountRef]:
        return []

    async def list_invoices(self) -> list[InvoiceRef]:
        self.calls.append("list_invoices")
        return self._invoices

    async def get_pnl(self) -> PnlRef | None:
        self.calls.append("get_pnl")
        return self._pnl

    async def get_ar_aging(self) -> ArAgingRef | None:
        self.calls.append("get_ar_aging")
        return self._ar

    async def get_trial_balance(self, *, as_of: date) -> TrialBalanceRef | None:
        self.calls.append("get_trial_balance")
        return self._trial_balance

    async def get_cashflow_projection(self, *, as_of: date) -> CashflowProjectionRef | None:
        self.calls.append("get_cashflow_projection")
        return self._cashflow


def _invoice(total: str = "100.0000", status: str = "issued") -> InvoiceRef:
    return InvoiceRef(
        id=uuid.uuid4(),
        invoice_number="INV-0001",
        customer_name="Acme",
        status=status,
        total=Decimal(total),
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
    )


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
        as_of=AS_OF,
        total_ar=Decimal("9000.0000"),
        buckets=(
            ArAgingBucketRef(bucket="current", count=5, amount=Decimal("4000.0000")),
            ArAgingBucketRef(bucket=">90", count=2, amount=Decimal("5000.0000")),
        ),
    )


def _trial_balance() -> TrialBalanceRef:
    return TrialBalanceRef(
        as_of=AS_OF,
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


class TestMatcher:
    def test_classifies_all_whitelisted_intents(self) -> None:
        cases = {
            "what is our net income": "net_income",
            "show profit and loss": "net_income",
            "the p&l for last quarter": "net_income",
            "total revenue for the period": "net_income",
            "accounts receivable aging": "ar_aging",
            "how much is owed to us": "ar_aging",
            "total receivable": "ar_aging",
            "trial balance as of today": "trial_balance",
            "what is our payables balance": "trial_balance",
            "how much cash is projected": "cashflow_projection",
            "cash flow next quarter": "cashflow_projection",
            "list our invoices": "invoice_summary",
            "how many outstanding invoices": "invoice_summary",
        }
        for question, expected in cases.items():
            assert match_finance_intent(question) == expected, question

    def test_non_finance_returns_none(self) -> None:
        assert match_finance_intent("summarize our finances") is None
        assert match_finance_intent("greet the team") is None
        assert match_finance_intent("") is None


class TestExecutor:
    async def test_pnl_answer_matches_gateway_and_is_decimal(self) -> None:
        gateway = FakeFinanceGateway(pnl=_pnl())
        result = await run_finance_intent(gateway=gateway, query="net income", as_of=AS_OF)

        assert result is not None
        assert result.endpoint == "/api/v1/finance/reports/profit-and-loss"
        assert result.title == "Profit & Loss"
        assert "40000" in result.answer
        assert gateway.calls == ["get_pnl"]
        row = result.rows[0]
        assert isinstance(row["net_income"], Decimal)
        assert row["net_income"] == Decimal("40000.0000")

    async def test_ar_answer_surfaces_bucket_rows(self) -> None:
        gateway = FakeFinanceGateway(ar=_ar())
        result = await run_finance_intent(gateway=gateway, query="AR aging", as_of=AS_OF)

        assert result is not None
        assert result.endpoint == "/api/v1/finance/reports/ar-aging"
        assert len(result.rows) == 2
        assert all(isinstance(row["amount"], Decimal) for row in result.rows)
        assert result.filters == {"as_of": "2026-08-31"}

    async def test_cashflow_answer_uses_expected_gateway_call(self) -> None:
        gateway = FakeFinanceGateway(cashflow=_cashflow())
        result = await run_finance_intent(
            gateway=gateway, query="cash received next quarter", as_of=AS_OF
        )

        assert result is not None
        assert result.endpoint == "/api/v1/finance/automation/cashflow-projection"
        assert gateway.calls == ["get_cashflow_projection"]
        assert result.rows[0]["closing"] == Decimal("12000.0000")

    async def test_trial_balance_answer_reconciles_rows(self) -> None:
        gateway = FakeFinanceGateway(trial_balance=_trial_balance())
        result = await run_finance_intent(gateway=gateway, query="trial balance", as_of=AS_OF)

        assert result is not None
        assert result.endpoint == "/api/v1/finance/reports/trial-balance"
        assert len(result.rows) == 2
        assert result.rows[0]["debit"] == Decimal("21000.0000")
        assert "total credits 21000" in result.answer

    async def test_unmatched_query_returns_none(self) -> None:
        gateway = FakeFinanceGateway(pnl=_pnl())
        result = await run_finance_intent(gateway=gateway, query="summarize our books", as_of=AS_OF)

        assert result is None

    async def test_missing_report_data_returns_none(self) -> None:
        gateway = FakeFinanceGateway()
        result = await run_finance_intent(gateway=gateway, query="net income", as_of=AS_OF)

        assert result is None
