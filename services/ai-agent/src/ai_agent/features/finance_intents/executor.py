"""Finance intent executor (SKY-82 / FIN-AI-003 A3).

Each whitelisted intent calls the *same* gateway method that backs the matching
dashboard report endpoint, so the chat figure reconciles to the report run by
construction (proven by the Phase 2 reconciliation suite). Money stays ``Decimal``
end-to-end; no float is ever rendered. Every result carries the endpoint anchor
and the exact rows surfaced, which the UI turns into a citation.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ai_agent.features.finance_intents.matcher import match_finance_intent
from ai_agent.features.finance_intents.schemas import INTENT_META, FinanceIntentResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_agent.features.finance.gateway import FinanceGatewayPort
    from ai_agent.features.finance_intents.schemas import FinanceIntentId


async def run_finance_intent(
    *,
    gateway: FinanceGatewayPort,
    query: str,
    as_of: date | None = None,
) -> FinanceIntentResult | None:
    """Match ``query`` to a whitelisted intent and run it against ``gateway``.

    Returns ``None`` when no intent matched or the report had no data to answer
    from (caller falls through to the existing delegator paths).
    """
    intent: FinanceIntentId | None = match_finance_intent(query)
    if intent is None:
        return None
    handler = _HANDLERS[intent]
    return await handler(gateway=gateway, as_of=as_of or date.today())


async def _net_income(*, gateway: FinanceGatewayPort, as_of: date) -> FinanceIntentResult | None:
    del as_of
    pnl = await gateway.get_pnl()
    if pnl is None:
        return None
    meta = INTENT_META["net_income"]
    return FinanceIntentResult(
        intent="net_income",
        answer=(
            f"P&L for {pnl.from_date} to {pnl.to_date}: revenue {pnl.total_revenue}, "
            f"expenses {pnl.total_expenses}, net income {pnl.net_income}."
        ),
        endpoint=meta.endpoint,
        title=meta.title,
        rows=(
            {
                "total_revenue": pnl.total_revenue,
                "total_expenses": pnl.total_expenses,
                "net_income": pnl.net_income,
            },
        ),
        filters={},
    )


async def _ar_aging(*, gateway: FinanceGatewayPort, as_of: date) -> FinanceIntentResult | None:
    del as_of
    ar = await gateway.get_ar_aging()
    if ar is None:
        return None
    meta = INTENT_META["ar_aging"]
    buckets = "; ".join(f"{bucket.bucket} {bucket.amount}" for bucket in ar.buckets)
    return FinanceIntentResult(
        intent="ar_aging",
        answer=(f"Accounts receivable total {ar.total_ar} as of {ar.as_of}. Buckets: {buckets}."),
        endpoint=meta.endpoint,
        title=meta.title,
        rows=tuple(
            {"bucket": bucket.bucket, "count": bucket.count, "amount": bucket.amount}
            for bucket in ar.buckets
        ),
        filters={"as_of": ar.as_of.isoformat()},
    )


async def _invoice_summary(
    *, gateway: FinanceGatewayPort, as_of: date
) -> FinanceIntentResult | None:
    del as_of
    invoices = await gateway.list_invoices()
    if not invoices:
        return None
    meta = INTENT_META["invoice_summary"]
    counts: dict[str, int] = {}
    for invoice in invoices:
        counts[str(invoice.status)] = counts.get(str(invoice.status), 0) + 1
    summary = ", ".join(f"{status} {count}" for status, count in counts.items())
    return FinanceIntentResult(
        intent="invoice_summary",
        answer=f"There are {len(invoices)} invoices: {summary}.",
        endpoint=meta.endpoint,
        title=meta.title,
        rows=tuple({"status": status, "count": count} for status, count in counts.items()),
        filters={},
    )


async def _trial_balance(*, gateway: FinanceGatewayPort, as_of: date) -> FinanceIntentResult | None:
    tb = await gateway.get_trial_balance(as_of=as_of)
    if tb is None:
        return None
    meta = INTENT_META["trial_balance"]
    lines = "; ".join(f"{row.code} {row.name} {row.debit or row.credit}" for row in tb.rows[:5])
    answer = (
        f"Trial balance as of {tb.as_of}: total debits {tb.total_debit}, "
        f"total credits {tb.total_credit}."
    )
    if lines:
        answer += f" Accounts: {lines}."
    return FinanceIntentResult(
        intent="trial_balance",
        answer=answer,
        endpoint=meta.endpoint,
        title=meta.title,
        rows=tuple(
            {
                "code": row.code,
                "name": row.name,
                "account_type": row.account_type,
                "debit": row.debit,
                "credit": row.credit,
            }
            for row in tb.rows
        ),
        filters={"as_of": as_of.isoformat()},
    )


async def _cashflow_projection(
    *, gateway: FinanceGatewayPort, as_of: date
) -> FinanceIntentResult | None:
    cf = await gateway.get_cashflow_projection(as_of=as_of)
    if cf is None or not cf.positions:
        return None
    meta = INTENT_META["cashflow_projection"]
    positions = "; ".join(
        f"{pos.month} opening {pos.opening} inflow {pos.inflows} "
        f"outflow {pos.outflows} closing {pos.closing}"
        for pos in cf.positions
    )
    return FinanceIntentResult(
        intent="cashflow_projection",
        answer=f"Cash flow projection as of {as_of}: {positions}.",
        endpoint=meta.endpoint,
        title=meta.title,
        rows=tuple(
            {
                "month": pos.month,
                "opening": pos.opening,
                "inflows": pos.inflows,
                "outflows": pos.outflows,
                "closing": pos.closing,
            }
            for pos in cf.positions
        ),
        filters={"as_of": as_of.isoformat()},
    )


_HANDLERS: dict[str, Callable[..., Awaitable[FinanceIntentResult | None]]] = {
    "net_income": _net_income,
    "ar_aging": _ar_aging,
    "invoice_summary": _invoice_summary,
    "trial_balance": _trial_balance,
    "cashflow_projection": _cashflow_projection,
}
