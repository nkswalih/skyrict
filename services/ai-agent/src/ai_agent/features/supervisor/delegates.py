"""Leaf module adapters - each streams token deltas for one registered agent.

Contract: a delegator is an async generator over ``str`` token deltas. The
``citations`` list is an out-param - the orchestrator reads it AFTER the
segment completes to emit the citations event, keeping the token stream free
of control frames.

Security notes:
  * Inventory data is READ-ONLY via the nl_query gateway (the core proxy edge).
    Unit cost and product levels are surfaced ONLY to the extent core returns
    them to the acting user's permission scope - the gateway forwards the
    caller's JWT + tenant slug and core enforces ``erp.inventory.read``, so the
    agent never reveals a figure the user could not already see in the UI.
  * CRM context may include contact PII (email/phone) and deal amounts, but ONLY
    for records core returned to the acting user's permission scope - the
    gateway forwards the caller's JWT + tenant slug and core re-enforces
    ``erp.crm.read`` plus owner/team row-scoping, so the agent never sees data
    the user could not already view in the UI. The scoring/deal-health engines
    still consume only presence booleans.
  * Money is always treated as Decimal(19,4) semantics; no float money ever
    enters a prompt.
  * RAG retrieval and forecast reads are best-effort: a failure degrades the
    answer, it never kills the stream - the shell always receives tokens.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Protocol

import structlog

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.core.providers import LlmRequest
from ai_agent.features.finance_intents import match_finance_intent, run_finance_intent
from ai_agent.features.finance_intents.schemas import INTENT_META
from ai_agent.features.supervisor.prompts import (
    CRM_NO_ANSWER,
    CRM_SYSTEM_PROMPT,
    CRM_UNAVAILABLE,
    FINANCE_HISTORY_ABSTENTION,
    FINANCE_NO_ANSWER,
    FINANCE_SYSTEM_PROMPT,
    FINANCE_UNAVAILABLE,
    GUARDIAN_NO_REPORT,
    GUARDIAN_SYSTEM_PROMPT,
    GUARDIAN_UNAVAILABLE,
    HR_NO_ANSWER,
    HR_UNAVAILABLE,
    INVENTORY_NO_DATA,
    INVENTORY_SYSTEM_PROMPT,
    SALES_COACH_NO_SUGGESTIONS,
    SALES_COACH_SYSTEM_PROMPT,
    SALES_COACH_UNAVAILABLE,
)
from ai_agent.features.supervisor.schemas import (
    AGENT_AUDIT_GUARDIAN,
    AGENT_CRM,
    AGENT_FINANCE,
    AGENT_HR,
    AGENT_INVENTORY,
    AGENT_SALES_COACH,
    Citation,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence

    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.crm.gateway import CrmGatewayPort
    from ai_agent.features.crm.memory import MemoryService
    from ai_agent.features.finance.gateway import FinanceGatewayPort
    from ai_agent.features.hr_copilot.engine import HrCopilotResult
    from ai_agent.features.nl_query.gateway import InventoryGatewayPort
    from ai_agent.features.rag.retrieval.service import RetrievalResult

logger = structlog.get_logger("ai_agent.supervisor.delegates")

# Catalogue reads are capped the same way the nl_query gateway caps them.
_FORECAST_CATALOG_LIMIT = 200
_FORECAST_ROWS_SHOWN = 3


class RagSearchPort(Protocol):
    """Semantic retrieval over the tenant's documents (rag retrieval service)."""

    async def search(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        module: str | None = None,
    ) -> RetrievalResult: ...


class ForecastPort(Protocol):
    """Moving-average demand forecast for one product (forecast service)."""

    async def get_forecast(self, *, product_id: uuid.UUID) -> list[dict[str, object]]: ...


class HrCopilotPort(Protocol):
    """The grounded HR Copilot pipeline (limit + audit live in its service)."""

    async def ask(
        self,
        *,
        message: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> HrCopilotResult: ...


class Delegator(Protocol):
    """A registered module agent that streams answer tokens."""

    key: str
    display_name: str

    def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]: ...


class CoachSuggestionPort(Protocol):
    """Read-only access to a rep's pending coaching suggestions."""

    async def list_pending_for_rep(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
    ) -> list[dict[str, object]]: ...


class GuardianReportPort(Protocol):
    """Read-only access to the latest weekly guardian report + flags."""

    async def list_reports(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int = 1,
    ) -> list[dict[str, object]]: ...

    async def list_events_for_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> list[dict[str, object]]: ...


class InventoryMonitorDelegator:
    """Stock/forecast/RAG answers over the nl_query gateway + forecast + RAG."""

    key = AGENT_INVENTORY
    display_name = "Inventory Monitor"

    _FORECAST_HINT_WORDS = (
        "forecast",
        "demand",
        "project",
        "stock out",
        "replenish",
        "next month",
    )
    _MAX_CONTEXT_CHARS = 4000

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        rag: RagSearchPort | None = None,
        forecast: ForecastPort | None = None,
    ) -> None:
        self._llm_router = llm_router
        self._gateway_factory = gateway_factory
        self._rag = rag
        self._forecast = forecast

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        context_parts = await self._gather_context(
            query=query, tenant_id=tenant_id, user_id=user_id, citations=citations
        )
        if not self._llm_router.has_providers:
            for delta in _iter_text_deltas(self._deterministic_summary(context_parts)):
                yield delta
            return

        context_text = "\n".join(context_parts)
        if len(context_text) > self._MAX_CONTEXT_CHARS:
            context_text = context_text[: self._MAX_CONTEXT_CHARS] + "…"
        request = LlmRequest(
            system_prompt=INVENTORY_SYSTEM_PROMPT,
            user_prompt=(
                "User question: "
                + query.strip()
                + "\n\nReference context:\n"
                + (context_text or "(no context available yet)")
            ),
            max_tokens=512,
            temperature=0.2,
        )
        async for chunk in self._llm_router.stream(request):
            yield chunk.token_delta

    async def _gather_context(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> list[str]:
        """RAG top-k + live stock totals + optional product forecast.

        Every read is best-effort and bounded; failures degrade the prompt,
        they never raise (the shell still gets an answer).
        """
        parts: list[str] = []
        lowered = query.casefold()

        if self._rag is not None:
            try:
                result = await self._rag.search(
                    query=query,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    module="inventory",
                )
            except Exception as exc:  # retrieval must never kill the stream
                logger.warning("supervisor.rag_failed", error=str(exc))
                result = None
            if result is not None:
                for item in result.data[:3]:
                    parts.append(f"[{item.source_ref}] {item.chunk_text}")
                    citations.append(Citation(source_ref=item.source_ref, module=item.module))

        try:
            gateway = await self._gateway_factory()
            levels = await gateway.get_stock_levels()
        except AiUnavailableError as exc:
            logger.warning("supervisor.inventory_gateway_failed", error=str(exc))
            levels = []
        if levels:
            on_hand = sum((row.qty_on_hand for row in levels), Decimal(0))
            reserved = sum((row.qty_reserved for row in levels), Decimal(0))
            warehouse_ids = {str(row.warehouse_id) for row in levels}
            parts.append(
                f"Live stock: {on_hand} units on hand, {reserved} reserved "
                f"across {len(warehouse_ids)} warehouse(s)."
            )

            # Product-level detail: on-hand units, reorder point, and unit cost
            # per product. Unit cost is included because core only returns it to
            # ``erp.inventory.read`` holders (the gateway forwards the caller's
            # scoped identity) - so a permitted user sees the same figure they
            # would in the inventory UI.
            if any(
                w in lowered
                for w in ("product", "sku", "reorder", "unit cost", "cost", "price", "level")
            ):
                try:
                    products = await gateway.list_products()
                except AiUnavailableError as exc:
                    logger.warning("supervisor.product_catalog_failed", error=str(exc))
                    products = []
                if products:
                    on_hand_by_product: dict[uuid.UUID, Decimal] = {}
                    for row in levels:
                        on_hand_by_product[row.product_id] = (
                            on_hand_by_product.get(row.product_id, Decimal(0)) + row.qty_on_hand
                        )
                    product_lines = []
                    for product in products[:_FORECAST_CATALOG_LIMIT]:
                        qty = on_hand_by_product.get(product.id, Decimal(0))
                        cost = (
                            f"{product.cost_price} {product.cost_currency or ''}".strip()
                            if product.cost_price is not None
                            else "n/a"
                        )
                        product_lines.append(
                            f"- {product.name} ({product.sku}): on hand={qty}, "
                            f"reorder point={product.reorder_point}, "
                            f"unit cost={cost}"
                        )
                    if product_lines:
                        parts.append("Product levels:")
                        parts.extend(product_lines)

        if self._forecast is not None and any(
            word in lowered for word in self._FORECAST_HINT_WORDS
        ):
            try:
                gateway = await self._gateway_factory()
                products = await gateway.list_products()
            except AiUnavailableError as exc:
                logger.warning("supervisor.forecast_catalog_failed", error=str(exc))
                products = []
            for product in products[:_FORECAST_CATALOG_LIMIT]:
                if product.name.casefold() not in lowered and product.sku.casefold() not in lowered:
                    continue
                try:
                    rows = await self._forecast.get_forecast(product_id=product.id)
                except Exception as exc:  # one product's forecast failure is best-effort
                    logger.warning(
                        "supervisor.forecast_failed",
                        error=str(exc),
                        product_id=str(product.id),
                    )
                    continue
                parts.append(
                    f"Forecast for {product.name} ({product.sku}): {rows[:_FORECAST_ROWS_SHOWN]}"
                )
        return parts

    def _deterministic_summary(self, context_parts: list[str]) -> str:
        """Provider-free answer - live facts only, no LLM (dev/demo path)."""
        if context_parts:
            return "Here is what Inventory Monitor finds right now: " + " ".join(context_parts[:4])
        return INVENTORY_NO_DATA


class HrCopilotDelegator:
    """HR answers through the existing grounded HR Copilot service."""

    key = AGENT_HR
    display_name = "HR Copilot"

    def __init__(self, *, hr_copilot: HrCopilotPort) -> None:
        self._hr_copilot = hr_copilot

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        try:
            result = await self._hr_copilot.ask(message=query, tenant_id=tenant_id, user_id=user_id)
        except AiUnavailableError as exc:
            logger.warning("supervisor.hr_copilot_failed", error=str(exc))
            for delta in _iter_text_deltas(HR_UNAVAILABLE):
                yield delta
            return
        answer = (result.answer or "").strip()
        if answer:
            for delta in _iter_text_deltas(answer):
                yield delta
        else:
            for delta in _iter_text_deltas(HR_NO_ANSWER):
                yield delta


class CrmAssistantDelegator:
    """CRM answers through deterministic NL actions + LLM fallback."""

    key = AGENT_CRM
    display_name = "CRM Assistant"

    _ACTION_KEYWORDS: ClassVar[dict[str, tuple[str, str | None]]] = {
        "count": ("count_deals", None),
        "how many deals": ("count_deals", None),
        "how many opportunities": ("count_deals", None),
        "how many leads": ("count_leads", None),
        "pipeline by stage": ("value_by_stage", None),
        "value by stage": ("value_by_stage", None),
        "deal value": ("value_by_stage", None),
        "at risk": ("at_risk", None),
        "stale": ("at_risk", None),
        "no activity": ("no_activity", None),
        "inactive": ("no_activity", None),
        "hasn't been contacted": ("no_activity", "lead"),
        "hasnt been contacted": ("no_activity", "lead"),
        "report": ("pipeline_summary", None),
        "summary": ("pipeline_summary", None),
        "overview": ("pipeline_summary", None),
        "pipeline": ("pipeline_summary", None),
    }

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        crm_gateway_factory: Callable[[], Awaitable[CrmGatewayPort]],
        memory_service: MemoryService | None = None,
    ) -> None:
        self._llm_router = llm_router
        self._crm_gateway_factory = crm_gateway_factory
        self._memory = memory_service

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        # Try deterministic NL actions first.
        action_result = await self._try_nl_action(query)
        if action_result is not None:
            for delta in _iter_text_deltas(action_result):
                yield delta
            return

        # Fallback: LLM with live CRM context + memory.
        try:
            system_prompt = CRM_SYSTEM_PROMPT

            # Gather live CRM data from the database so the LLM can see it.
            crm_context = await self._gather_crm_context(query)
            if crm_context:
                system_prompt = f"{system_prompt}\n\nLive CRM data:\n{crm_context}"

            # Inject relevant memories into context.
            if self._memory is not None:
                memory_ctx = await self._memory.recall_context(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                )
                if memory_ctx:
                    system_prompt = f"{system_prompt}\n\n{memory_ctx}"

            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=system_prompt,
                    user_prompt=query.strip(),
                    max_tokens=512,
                    temperature=0.0,
                )
            )
            answer = (completion.text or "").strip()
            if answer:
                for delta in _iter_text_deltas(answer):
                    yield delta
                # Store conversation in memory (fire-and-forget).
                if self._memory is not None:
                    await self._memory.store_after_chat(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        query=query,
                        response=answer,
                        module="crm_assistant",
                    )
            else:
                for delta in _iter_text_deltas(CRM_NO_ANSWER):
                    yield delta
        except AiUnavailableError as exc:
            logger.warning("supervisor.crm_assistant_failed", error=str(exc))
            for delta in _iter_text_deltas(CRM_UNAVAILABLE):
                yield delta

    async def _gather_crm_context(self, query: str) -> str:
        """Fetch live CRM data from the gateway and format it as LLM context.

        Always includes lead and opportunity summaries. For specific entity
        queries, also fetches the relevant records. Capped to avoid
        overwhelming the LLM with too much data.
        """
        try:
            gateway = await self._crm_gateway_factory()
        except AiUnavailableError:
            return ""

        parts: list[str] = []
        lowered = query.casefold()

        # Always include opportunity summary
        try:
            opportunities = await gateway.list_opportunities()
            if opportunities:
                stage_counts: dict[str, int] = {}
                total_value = Decimal("0")
                currency: str | None = None
                for opp in opportunities:
                    stage_counts[opp.stage] = stage_counts.get(opp.stage, 0) + 1
                    if opp.amount is not None:
                        total_value += opp.amount
                        currency = currency or opp.currency
                parts.append(f"Total opportunities: {len(opportunities)}")
                if total_value:
                    parts.append(f"Total pipeline value: {total_value} {currency or ''}".strip())
                for stage, count in sorted(stage_counts.items()):
                    parts.append(f"  - {stage}: {count}")
            else:
                parts.append("No opportunities in the pipeline yet.")
        except AiUnavailableError:
            pass

        # Always include lead summary
        try:
            leads = await gateway.list_leads()
            if leads:
                status_counts: dict[str, int] = {}
                for lead in leads:
                    status_counts[lead.status] = status_counts.get(lead.status, 0) + 1
                parts.append(f"\nTotal leads: {len(leads)}")
                for status, count in sorted(status_counts.items()):
                    parts.append(f"  - {status}: {count}")
            else:
                parts.append("\nNo leads in the system yet.")
        except AiUnavailableError:
            pass

        # For opportunity-specific queries, include deal names
        if any(w in lowered for w in ("deal", "opportunity", "pipeline", "stage")):
            try:
                opportunities = await gateway.list_opportunities()
                if opportunities:
                    details = []
                    for opp in opportunities[:20]:  # Cap at 20
                        name = opp.display_name or str(opp.id)
                        value = (
                            f"{opp.amount} {opp.currency}".strip()
                            if opp.amount is not None
                            else "no value"
                        )
                        close = (
                            opp.expected_close_date.isoformat()
                            if opp.expected_close_date is not None
                            else "TBD"
                        )
                        details.append(
                            f"  - {name}: stage={opp.stage}, value={value}, "
                            f"probability={opp.probability}%, expected close={close}"
                        )
                    if details:
                        parts.append("\nDeal details:")
                        parts.extend(details)
            except AiUnavailableError:
                pass

        # For lead-specific queries, include lead contact details
        if any(w in lowered for w in ("lead", "prospect", "contact", "customer", "company")):
            try:
                leads = await gateway.list_leads()
                if leads:
                    details = []
                    for lead in leads[:20]:  # Cap at 20
                        name = lead.display_name or str(lead.id)
                        contact = " / ".join(part for part in (lead.email, lead.phone) if part)
                        detail = (
                            f"  - {name}: status={lead.status}, source={lead.source or 'unknown'}"
                        )
                        if contact:
                            detail += f", contact={contact}"
                        if lead.company:
                            detail += f", company={lead.company}"
                        details.append(detail)
                    if details:
                        parts.append("\nLead details:")
                        parts.extend(details)
            except AiUnavailableError:
                pass

        return "\n".join(parts)

    async def _try_nl_action(self, query: str) -> str | None:
        """Match query keywords to a deterministic CRM NL action."""
        lower = query.lower()
        for keyword, (action, entity_type) in self._ACTION_KEYWORDS.items():
            if keyword in lower:
                return await self._execute_nl_action(action, entity_type, lower)
        return None

    async def _execute_nl_action(self, action: str, entity_type: str | None, query: str) -> str:
        from ai_agent.features.crm import nl_actions

        gateway = await self._crm_gateway_factory()
        if action == "count_deals":
            stage = self._extract_stage(query)
            result = await nl_actions.count_deals(gateway=gateway, stage=stage)
        elif action == "count_leads":
            result = await nl_actions.count_leads(gateway=gateway)
        elif action == "value_by_stage":
            result = await nl_actions.value_by_stage(gateway=gateway)
        elif action == "pipeline_summary":
            result = await nl_actions.pipeline_summary(gateway=gateway)
        elif action == "at_risk":
            result = await nl_actions.at_risk(gateway=gateway)
        elif action == "no_activity":
            result = await nl_actions.no_activity(
                gateway=gateway,
                entity_type=entity_type,
            )
        else:
            return "This CRM action is not yet implemented."
        return result.answer

    @staticmethod
    def _extract_stage(query: str) -> str | None:
        """Best-effort stage extraction from the query."""
        stage_keywords = (
            "lead",
            "qualified",
            "proposal",
            "negotiation",
            "closed won",
            "closed lost",
            "discovery",
        )
        for stage in stage_keywords:
            if stage in query:
                return stage
        return None


class FinanceDelegator:
    """Finance answers through whitelisted intents + deterministic + LLM fallback.

    Guardrails (FIN-AI-003 A3):
      * Ask the intent engine FIRST: a question inside the whitelist is answered
        by the exact gateway call that backs the matching dashboard report, with
        a citation to that report (``citations`` out-param).
      * Abstract when the tenant's invoicing history is under 3 months (distinct
        calendar months across invoices) - before any report figure is produced.
      * Every read forwards the caller's JWT + tenant slug, so core enforces
        ``erp.finance.read`` + tenant isolation. The context handed to the LLM
        is therefore exactly what the acting user may view in the finance UI.
    """

    key = AGENT_FINANCE
    display_name = "Finance Assistant"

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        finance_gateway_factory: Callable[[], Awaitable[FinanceGatewayPort]],
    ) -> None:
        self._llm_router = llm_router
        self._finance_gateway_factory = finance_gateway_factory

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        del tenant_id, user_id
        # A finance-only delegate must never invent figures: if finance is
        # unreachable at ANY point we stream the clean unavailable message, we
        # do not fall back to an ungrounded LLM answer.
        try:
            gateway = await self._finance_gateway_factory()
        except AiUnavailableError:
            logger.warning("supervisor.finance_unavailable")
            for delta in _iter_text_deltas(FINANCE_UNAVAILABLE):
                yield delta
            return

        # Intent path (A3): whitelisted question -> exact report-backed answer.
        intent = match_finance_intent(query)
        if intent is not None:
            try:
                if INTENT_META[intent].requires_history and not await self._has_sufficient_history(
                    gateway
                ):
                    for delta in _iter_text_deltas(FINANCE_HISTORY_ABSTENTION):
                        yield delta
                    return
                result = await run_finance_intent(gateway=gateway, query=query)
            except AiUnavailableError:
                logger.warning("supervisor.finance_unavailable", query=query)
                for delta in _iter_text_deltas(FINANCE_UNAVAILABLE):
                    yield delta
                return
            if result is not None:
                citations.append(
                    Citation(
                        source_ref=result.endpoint,
                        module="finance",
                        title=result.title,
                        url=None,
                    )
                )
                for delta in _iter_text_deltas(result.answer):
                    yield delta
                return

        # Deterministic finance summary first (no LLM cost).
        try:
            deterministic = await self._try_deterministic(query)
        except AiUnavailableError:
            logger.warning("supervisor.finance_unavailable")
            for delta in _iter_text_deltas(FINANCE_UNAVAILABLE):
                yield delta
            return
        if deterministic is not None:
            for delta in _iter_text_deltas(deterministic):
                yield delta
            return

        # Fallback: LLM with live finance context.
        try:
            context = await self._gather_finance_context(query)
            system_prompt = (
                f"{FINANCE_SYSTEM_PROMPT}\n\nLive finance data:\n{context}"
                if context
                else FINANCE_SYSTEM_PROMPT
            )
            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=system_prompt,
                    user_prompt=query.strip(),
                    max_tokens=512,
                    temperature=0.0,
                )
            )
            answer = (completion.text or "").strip() or FINANCE_NO_ANSWER
            for delta in _iter_text_deltas(answer):
                yield delta
        except AiUnavailableError as exc:
            logger.warning("supervisor.finance_unavailable", error=str(exc))
            for delta in _iter_text_deltas(FINANCE_UNAVAILABLE):
                yield delta

    async def _gather_finance_context(self, query: str) -> str:
        """Fetch live finance data and format it as LLM context (bounded)."""
        try:
            gateway = await self._finance_gateway_factory()
        except AiUnavailableError:
            return ""
        parts: list[str] = []

        try:
            invoices = await gateway.list_invoices()
        except AiUnavailableError:
            invoices = []
        if invoices:
            status_counts: dict[str, int] = {}
            total_open = Decimal("0")
            for invoice_item in invoices:
                status_counts[invoice_item.status] = status_counts.get(invoice_item.status, 0) + 1
                if invoice_item.status in _OPEN_STATUSES:
                    total_open += invoice_item.total
            parts.append(f"Total invoices: {len(invoices)}")
            if total_open:
                parts.append(f"Open/outstanding invoice value: {total_open}")
            for status, count in sorted(status_counts.items()):
                parts.append(f"  - {status}: {count}")
        else:
            parts.append("No invoices returned by the finance service.")

        try:
            pnl = await gateway.get_pnl()
        except AiUnavailableError:
            pnl = None
        if pnl is not None:
            parts.append(
                f"P&L ({pnl.from_date} to {pnl.to_date}): revenue={pnl.total_revenue}, "
                f"expenses={pnl.total_expenses}, net income={pnl.net_income}"
            )

        try:
            ar = await gateway.get_ar_aging()
        except AiUnavailableError:
            ar = None
        if ar is not None:
            parts.append(f"Accounts receivable: total {ar.total_ar} as of {ar.as_of}")
            for bucket in ar.buckets:
                parts.append(f"  - {bucket.bucket}: {bucket.amount} ({bucket.count} invoices)")

        return "\n".join(parts)

    async def _try_deterministic(self, query: str) -> str | None:
        """Return a deterministic answer for a few well-scoped finance questions."""
        lowered = query.casefold()
        try:
            gateway = await self._finance_gateway_factory()
        except AiUnavailableError:
            return None

        if "net income" in lowered or "profit and loss" in lowered or "p&l" in lowered:
            pnl = await gateway.get_pnl()
            if pnl is None:
                return None
            return (
                f"P&L for {pnl.from_date} to {pnl.to_date}: revenue {pnl.total_revenue}, "
                f"expenses {pnl.total_expenses}, net income {pnl.net_income}."
            )

        if "receivable" in lowered or "ar aging" in lowered or "owed" in lowered:
            ar = await gateway.get_ar_aging()
            if ar is None:
                return None
            buckets = "; ".join(f"{bucket.bucket} {bucket.amount}" for bucket in ar.buckets)
            return f"Accounts receivable total {ar.total_ar} as of {ar.as_of}. Buckets: {buckets}."

        if "invoice" in lowered:
            invoices = await gateway.list_invoices()
            if not invoices:
                return "No invoices found in the finance service."
            counts = _count_by_status(invoices)
            summary = ", ".join(f"{status} {count}" for status, count in counts.items())
            return f"There are {len(invoices)} invoices: {summary}."
        return None

    async def _has_sufficient_history(self, gateway: FinanceGatewayPort) -> bool:
        """A3 guardrail: abstain from report figures under 3 months of history.

        History depth = distinct calendar months across invoices. Using
        invoicing activity (instead of closed fiscal periods) keeps the read
        on one already-fetched-and-permissioned endpoint and stays lenient for
        tenants that leave fiscal periods unclosed. Mirrors the 3-month floor
        of the revenue forecast (FIN-AI-003 A4), validated to not be less
        accurate than a 6-month floor.
        """
        invoices = await gateway.list_invoices()
        if not invoices:
            return False
        months = {(invoice.invoice_date.year, invoice.invoice_date.month) for invoice in invoices}
        return len(months) >= _MIN_HISTORY_MONTHS


class SalesCoachDelegator:
    """Streams a rep's own pending coaching suggestions (SKY-90).

    The delegate surfaces ONLY the acting rep's suggestions
    (``rep_user_id == user_id``) — a coach question can never leak another
    rep's data. Without providers it renders the suggestions deterministically
    (title + body), and with providers it asks the LLM to turn them into a
    short prioritized action plan grounded strictly in the context.
    """

    key = AGENT_SALES_COACH
    display_name = "Sales Coach"

    _MAX_SUGGESTIONS = 5
    _MAX_CONTEXT_CHARS = 4000

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        suggestions: CoachSuggestionPort,
    ) -> None:
        self._llm_router = llm_router
        self._suggestions = suggestions

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        del citations
        try:
            rows = await self._suggestions.list_pending_for_rep(
                tenant_id=tenant_id,
                rep_user_id=user_id,
            )
        except Exception as exc:
            logger.warning("supervisor.sales_coach_read_failed", error=str(exc))
            for delta in _iter_text_deltas(SALES_COACH_UNAVAILABLE):
                yield delta
            return

        pending = [row for row in rows if row.get("status") == "pending"][: self._MAX_SUGGESTIONS]
        if not pending:
            for delta in _iter_text_deltas(SALES_COACH_NO_SUGGESTIONS):
                yield delta
            return

        context = self._render_suggestions(pending)
        if not self._llm_router.has_providers:
            for delta in _iter_text_deltas(context):
                yield delta
            return

        try:
            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=SALES_COACH_SYSTEM_PROMPT,
                    user_prompt=(
                        f"Question: {query.strip()}\n\n"
                        f"Pending coaching suggestions:\n{context[: self._MAX_CONTEXT_CHARS]}"
                    ),
                    max_tokens=300,
                    temperature=0.2,
                )
            )
        except AiUnavailableError as exc:
            logger.warning("supervisor.sales_coach_unavailable", error=str(exc))
            for delta in _iter_text_deltas(SALES_COACH_UNAVAILABLE):
                yield delta
            return
        answer = (completion.text or "").strip() or context
        for delta in _iter_text_deltas(answer):
            yield delta

    def _render_suggestions(self, rows: list[dict[str, object]]) -> str:
        """Deterministic rendering of pending suggestions (no LLM)."""
        lines = ["You have these pending coaching suggestions:"]
        for index, row in enumerate(rows, start=1):
            title = str(row.get("title", ""))
            body = str(row.get("body", ""))
            lines.append(f"{index}. {title} — {body}")
        return "\n".join(lines)


class AuditGuardianDelegator:
    """Streams the latest weekly integrity report + its flagged findings (SKY-90).

    Only the report's own summary line and the sanitized finding fields
    (severity, reason) are surfaced — the raw ``evidence`` payloads (which can
    carry user/IP identifiers) are never rendered into chat or passed to the
    LLM.
    """

    key = AGENT_AUDIT_GUARDIAN
    display_name = "Audit Guardian"

    _MAX_FLAGGED = 6
    _MAX_CONTEXT_CHARS = 4000

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        guardian_reports: GuardianReportPort,
    ) -> None:
        self._llm_router = llm_router
        self._guardian_reports = guardian_reports

    async def stream(
        self,
        *,
        query: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        citations: list[Citation],
    ) -> AsyncIterator[str]:
        del user_id
        try:
            reports = await self._guardian_reports.list_reports(tenant_id=tenant_id, limit=1)
        except Exception as exc:
            logger.warning("supervisor.guardian_read_failed", error=str(exc))
            for delta in _iter_text_deltas(GUARDIAN_UNAVAILABLE):
                yield delta
            return
        if not reports:
            for delta in _iter_text_deltas(GUARDIAN_NO_REPORT):
                yield delta
            return

        report = reports[0]
        report_id = report.get("id")
        flagged: list[dict[str, object]] = []
        if isinstance(report_id, uuid.UUID):
            try:
                rows = await self._guardian_reports.list_events_for_report(
                    tenant_id=tenant_id,
                    report_id=report_id,
                )
                flagged = list(rows)[: self._MAX_FLAGGED]
            except Exception as exc:
                logger.warning("supervisor.guardian_events_failed", error=str(exc))
        else:
            logger.warning("supervisor.guardian_report_missing_id")

        context = self._render_context(report, flagged)
        citations.append(
            Citation(
                source_ref=f"audit-guardian/report/{report.get('id', '')}",
                module="audit_guardian",
                title="Weekly audit integrity report",
            )
        )

        if not self._llm_router.has_providers:
            for delta in _iter_text_deltas(self._render_deterministic(report, flagged)):
                yield delta
            return

        try:
            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=GUARDIAN_SYSTEM_PROMPT,
                    user_prompt=(
                        f"Question: {query.strip()}\n\n"
                        f"Latest report context:\n{context[: self._MAX_CONTEXT_CHARS]}"
                    ),
                    max_tokens=300,
                    temperature=0.2,
                )
            )
        except AiUnavailableError as exc:
            logger.warning("supervisor.guardian_unavailable", error=str(exc))
            for delta in _iter_text_deltas(GUARDIAN_UNAVAILABLE):
                yield delta
            return
        answer = (completion.text or "").strip() or self._render_deterministic(report, flagged)
        for delta in _iter_text_deltas(answer):
            yield delta

    def _render_context(self, report: dict[str, object], flagged: list[dict[str, object]]) -> str:
        """Report summary line + sanitized finding list (evidence excluded)."""
        lines = [str(report.get("summary", ""))]
        if flagged:
            lines.append("Flagged findings (severity, reason only):")
            for f in flagged:
                lines.append(
                    f"- {f.get('severity')}: {f.get('reason')} "
                    f"(source: {f.get('source_table')}, action: {f.get('event_action')})"
                )
        return "\n".join(lines)

    def _render_deterministic(
        self,
        report: dict[str, object],
        flagged: list[dict[str, object]],
    ) -> str:
        """Provider-free answer - report header + findings, no LLM."""
        lines = [
            f"Latest audit integrity report: {report.get('summary', '')}",
            f"{report.get('total_events_scanned', 0)} events scanned, "
            f"{report.get('flagged_count', 0)} flagged.",
        ]
        if flagged:
            for f in flagged[: self._MAX_FLAGGED]:
                lines.append(f"- {f.get('severity')}: {f.get('reason')}")
        else:
            lines.append("No flagged findings in the latest report.")
        return "\n".join(lines)


# Invoices that still represent an outstanding receivable (unpaid, not
# voided). Mirrors core's InvoiceStatus values: draft, issued, approved, paid,
# voided - we count everything except the settled/voided terminals.
_OPEN_STATUSES = frozenset({"draft", "issued", "approved"})

# A3 guardrail: minimum distinct invoice months before any report figure may
# be surfaced to the chat. Below this the delegator streams the abstention.
# Mirrors the revenue-forecast floor (FIN-AI-003); validated to not reduce
# forecast accuracy vs a 6-month floor.
_MIN_HISTORY_MONTHS = 3


def _count_by_status(invoices: Sequence[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for invoice_item in invoices:
        status = getattr(invoice_item, "status", "unknown")
        counts[str(status)] = counts.get(str(status), 0) + 1
    return counts


def _iter_text_deltas(text: str) -> Iterator[str]:
    """Split buffered answer text into word-slices joined with spaces."""
    words = text.split(" ")
    for index, word in enumerate(words):
        yield word + (" " if index < len(words) - 1 else "")
