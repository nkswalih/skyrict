"""Supervisor service - intent classification + cross-module delegation (SKY-60).

The supervisor is the Agents shell's router: one turn classifies the question
into one or more module agents, streams each segment sequentially with per-agent
attribution, and emits grounding citations. It is a STATELESS orchestration
layer - unlike the checkpointed :class:`AgentRuntime` (SKY-59) there is no
HITL pause; every segment streams and the shell renders tokens live.

Routing contract:
  * ``classify()`` → :class:`RouteDecision` - LLM intent classification (strict
    JSON) with a deterministic keyword fallback when no provider is configured
    or unavailable. Low confidence abstains (a normal explicit answer, never an
    error), mirroring the nl_query abstention pattern.
  * ``stream_answer()`` → :class:`SupervisorEvent` stream - classification,
    then per agent: ``AgentStartEvent``, ``TokenEvent``*d, ``CitationsEvent``.
    Modules that registry marks disabled stream a clean "not provisioned yet"
    abstention (SKY-60 decision #6: crm/finance start disabled).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.core.providers import LlmRequest
from ai_agent.features.attachments.processor import ProcessedAttachments, process_attachments
from ai_agent.features.supervisor.delegates import (
    CrmAssistantDelegator,
    Delegator,
    FinanceDelegator,
    ForecastPort,
    HrCopilotDelegator,
    HrCopilotPort,
    InventoryMonitorDelegator,
    RagSearchPort,
)
from ai_agent.features.supervisor.prompts import (
    ABSTENTION,
    CLASSIFY_SYSTEM_PROMPT,
    DEGRADED,
    GREETING,
    SUPERVISOR_SYSTEM_PROMPT,
    not_provisioned_message,
)
from ai_agent.features.supervisor.schemas import (
    AGENT_CRM,
    AGENT_DISPLAY_NAMES,
    AGENT_FINANCE,
    AGENT_HR,
    AGENT_INVENTORY,
    AgentStartEvent,
    Citation,
    CitationsEvent,
    ClassificationEvent,
    DoneEvent,
    RouteDecision,
    SupervisorEvent,
    TokenEvent,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping

    from ai_agent.api.v1.schemas.chat import AttachmentData
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.crm.gateway import CrmGatewayPort
    from ai_agent.features.crm.memory import MemoryService
    from ai_agent.features.finance.gateway import FinanceGatewayPort
    from ai_agent.features.nl_query.gateway import InventoryGatewayPort

logger = structlog.get_logger("ai_agent.supervisor")

_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        AGENT_INVENTORY,
        (
            "stock",
            "inventory",
            "reorder",
            "movement",
            "sku",
            "warehouse",
            "receipt",
            "reserved",
            "on hand",
            "forecast",
            "demand",
        ),
    ),
    (
        AGENT_HR,
        (
            "hr",
            "leave",
            "policy",
            "employee",
            "onboarding",
            "payroll",
            "benefit",
            "appraisal",
            "attrition",
            "headcount",
        ),
    ),
    (AGENT_CRM, ("crm", "customer", "lead", "opportunity", "pipeline", "sales")),
    (
        AGENT_FINANCE,
        ("finance", "invoice", "revenue", "expense", "budget", "p&l", "cash flow", "costs"),
    ),
)


class ConversationHistoryPort(Protocol):
    async def get_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> list[dict[str, Any]]: ...


class SupervisorService:
    """Routes one Agents-shell question and streams the delegated answer."""

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        rag: RagSearchPort | None = None,
        hr_copilot: HrCopilotPort | None = None,
        crm_gateway_factory: Callable[[], Awaitable[CrmGatewayPort]] | None = None,
        finance_gateway_factory: Callable[[], Awaitable[FinanceGatewayPort]] | None = None,
        memory_service: MemoryService | None = None,
        forecast: ForecastPort | None = None,
        conversation_history: ConversationHistoryPort | None = None,
        provisioned: Mapping[str, bool],
        confidence_threshold: float = 0.75,
    ) -> None:
        self._conversation_history = conversation_history
        self._llm_router = llm_router
        self._confidence_threshold = confidence_threshold
        self._provisioned = dict(provisioned)

        delegates: dict[str, Delegator] = {
            AGENT_INVENTORY: InventoryMonitorDelegator(
                llm_router=llm_router,
                gateway_factory=gateway_factory,
                rag=rag,
                forecast=forecast,
            )
        }
        if hr_copilot is not None:
            delegates[AGENT_HR] = HrCopilotDelegator(hr_copilot=hr_copilot)
        if crm_gateway_factory is not None:
            delegates[AGENT_CRM] = CrmAssistantDelegator(
                llm_router=llm_router,
                crm_gateway_factory=crm_gateway_factory,
                memory_service=memory_service,
            )
        if finance_gateway_factory is not None:
            delegates[AGENT_FINANCE] = FinanceDelegator(
                llm_router=llm_router,
                finance_gateway_factory=finance_gateway_factory,
            )
        self._delegates = delegates

    async def classify(self, query: str) -> RouteDecision:
        """Route one question; never raises - falls back to keywords."""
        if not self._llm_router.has_providers:
            return _keyword_route(query)
        try:
            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=CLASSIFY_SYSTEM_PROMPT,
                    user_prompt=query.strip(),
                    max_tokens=128,
                    temperature=0.0,
                )
            )
        except AiUnavailableError as exc:
            logger.warning("supervisor.classifier_unavailable", error=str(exc))
            return _keyword_route(query)

        try:
            agents, confidence = _parse_classification(completion.text)
        except ValueError:
            logger.warning("supervisor.unparseable_classification")
            return RouteDecision(
                agents=(), confidence=0.0, abstain=True, reason="unparseable_classifier_output"
            )
        if not agents:
            return RouteDecision(agents=(), confidence=confidence, abstain=True, reason="no_agents")
        if confidence < self._confidence_threshold:
            return RouteDecision(
                agents=agents, confidence=confidence, abstain=True, reason="low_confidence"
            )
        return RouteDecision(agents=agents, confidence=confidence, abstain=False, reason="routed")

    async def stream_answer(
        self,
        *,
        query: str,
        attachments: list[AttachmentData] | None = None,
        conversation_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[SupervisorEvent]:
        """Stream one full supervisor turn as ordered events.

        When attachments are present, their text content is extracted and
        appended to the query so the LLM has full context.  Images are passed
        as multimodal content blocks to the vision-capable LLM.

        When ``conversation_id`` is provided, the prior conversation history is
        loaded from the database and injected into the supervisor system prompt
        so the LLM has multi-turn context.
        """
        # --- Process attachments into LLM-ready format ---
        processed = process_attachments(attachments) if attachments else ProcessedAttachments()

        # Build the enhanced query: original question + extracted document text.
        enhanced_query = query
        if processed.extracted_text:
            enhanced_query = (
                f"{query}\n\n"
                f"--- Attached file content ---\n"
                f"{processed.extracted_text}\n"
                f"--- End of attached content ---"
            )

        # --- Load conversation history for multi-turn context ---
        conversation_history = ""
        if conversation_id is not None:
            conversation_history = await self._load_conversation_history(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
            )

        # --- Classify intent (uses original query for routing, not file content) ---
        decision = await self.classify(query)
        yield ClassificationEvent(
            agents=decision.agents,
            confidence=decision.confidence,
            abstain=decision.abstain,
            reason=decision.reason,
        )

        if decision.abstain or not decision.agents:
            yield AgentStartEvent(
                agent="supervisor", display_name=AGENT_DISPLAY_NAMES["supervisor"]
            )
            if _is_greeting(query):
                # Genuine greeting - a short, friendly redirect.
                for event in _yield_text(agent="supervisor", text=GREETING):
                    yield event
            else:
                # A real question that did not route to a module: answer it as
                # the supervisor instead of deflecting with canned text, so the
                # response actually varies with what the user asked.
                async for sup_event in self._supervisor_answer(
                    query=enhanced_query,
                    image_blocks=processed.image_blocks,
                    conversation_history=conversation_history,
                ):
                    yield sup_event
            yield CitationsEvent(agent="supervisor", citations=())
            yield DoneEvent(agents=("supervisor",))
            return

        handled: list[str] = []
        for agent in decision.agents:
            handled.append(agent)
            display_name = AGENT_DISPLAY_NAMES.get(agent, agent)
            yield AgentStartEvent(agent=agent, display_name=display_name)

            if not self._provisioned.get(agent, False):
                for event in _yield_text(agent=agent, text=not_provisioned_message(display_name)):
                    yield event
                yield CitationsEvent(agent=agent, citations=())
                continue

            delegator = self._delegates.get(agent)
            if delegator is None:
                for event in _yield_text(
                    agent=agent, text=f"The {display_name} module has no live delegate yet."
                ):
                    yield event
                yield CitationsEvent(agent=agent, citations=())
                continue

            citations: list[Citation] = []
            try:
                async for delta in delegator.stream(
                    query=enhanced_query.strip(),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    citations=citations,
                ):
                    yield TokenEvent(agent=agent, delta=delta)
            except AiUnavailableError as exc:
                logger.warning("supervisor.delegate_unavailable", agent=agent, error=str(exc))
                for event in _yield_text(agent=agent, text=DEGRADED):
                    yield event
            yield CitationsEvent(agent=agent, citations=tuple(citations))

        yield DoneEvent(agents=tuple(handled))

    async def _supervisor_answer(
        self,
        *,
        query: str,
        image_blocks: list[dict[str, object]] | None = None,
        conversation_history: str = "",
    ) -> AsyncIterator[SupervisorEvent]:
        """Answer as the general supervisor, varying with the actual question.

        Used when a real request does not clearly route to a module agent. The
        supervisor answers from its own knowledge so the reply differs with the
        input, instead of returning one fixed canned string. Degrades to the
        short abstention text only when no LLM provider can be reached.

        When ``image_blocks`` are present (user attached images), the request
        is sent as a multimodal/vision call so the LLM can see the images.

        When ``conversation_history`` is provided, it is prepended to the
        system prompt so the LLM has multi-turn context.
        """
        if not self._llm_router.has_providers:
            for event in _yield_text(agent="supervisor", text=ABSTENTION):
                yield event
            return
        try:
            system_prompt = SUPERVISOR_SYSTEM_PROMPT
            if conversation_history:
                system_prompt = (
                    f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
                    f"--- Conversation history ---\n"
                    f"{conversation_history}\n"
                    f"--- End of conversation history ---"
                )
            completion = await self._llm_router.complete(
                LlmRequest(
                    system_prompt=system_prompt,
                    user_prompt=query.strip(),
                    max_tokens=512,
                    temperature=0.3,
                    image_blocks=image_blocks,
                )
            )
        except AiUnavailableError as exc:
            logger.warning("supervisor.answer_unavailable", error=str(exc))
            for event in _yield_text(agent="supervisor", text=DEGRADED):
                yield event
            return
        text = (completion.text or "").strip()
        for event in _yield_text(agent="supervisor", text=text or ABSTENTION):
            yield event

    async def _load_conversation_history(
        self,
        *,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> str:
        """Load conversation messages and format them as multi-turn context.

        Returns a formatted string of prior messages (up to the last 20) for
        injection into the supervisor system prompt. Returns empty string on
        any failure - history is best-effort and must never block the turn.
        """
        if self._conversation_history is None:
            return ""

        try:
            messages = await self._conversation_history.get_messages(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
            )
            if not messages:
                return ""

            # Take the last 20 messages to stay within token limits.
            recent = messages[-20:]
            lines: list[str] = []
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{role}: {msg['content']}")
            return "\n".join(lines)
        except Exception:
            logger.warning(
                "supervisor.history_load_failed",
                conversation_id=str(conversation_id),
                exc_info=True,
            )
            return ""


def _parse_classification(text: str) -> tuple[tuple[str, ...], float]:
    """Parse+Lint the classifier's JSON into (valid agent keys, confidence)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.strip().startswith("```")
        ).strip()
    try:
        payload = json.loads(cleaned)
    except ValueError as exc:
        raise ValueError("classifier output is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("classifier output is not an object")

    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        return (), 0.0
    agents: list[str] = []
    for raw in raw_agents:
        if isinstance(raw, str) and raw in AGENT_DISPLAY_NAMES and raw not in agents:
            agents.append(raw)

    raw_confidence = payload.get("confidence")
    if isinstance(raw_confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    else:
        confidence = 0.0
    return tuple(agents), confidence


def _keyword_route(query: str) -> RouteDecision:
    """Deterministic fallback used when no LLM provider is available."""
    lowered = query.casefold()
    matched = [key for key, keywords in _KEYWORD_RULES if any(w in lowered for w in keywords)]
    if not matched:
        return RouteDecision(
            agents=(), confidence=0.0, abstain=True, reason="no_provider_no_keywords"
        )
    return RouteDecision(
        agents=tuple(matched), confidence=0.65, abstain=False, reason="keyword_fallback"
    )


_GREETING_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hola",
        "howdy",
        "greetings",
        "thanks",
        "thank you",
        "thank",
        "cheers",
        "bye",
        "goodbye",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "how's it going",
        "what's up",
        "sup",
        "yo",
    }
)

# Words that may follow a greeting without turning it into a real question.
_GREETING_FILLERS = frozenset(
    {
        "there",
        "hello",
        "hi",
        "hey",
        "u",
        "you",
        "ya",
        "everyone",
        "guys",
        "all",
        "mate",
        "man",
    }
)


def _is_greeting(query: str) -> bool:
    """True when the message is essentially a bare greeting, not a question.

    A message is only a greeting when it holds no real content. A question such
    as "hi, what is our revenue?" is NOT a greeting, even though it starts with
    one - it is a genuine request that must be routed or answered.
    """
    normalized = " ".join(query.strip().split())
    lowered = normalized.casefold().strip("!.? \t")
    if not lowered:
        return False

    tokens = lowered.split()
    # Single greeting word, e.g. "hi", "hey", "thanks".
    if lowered in _GREETING_WORDS:
        return True
    # Short greeting plus filler, e.g. "hi there", "hello everyone".
    if len(tokens) <= 3 and tokens[0] in _GREETING_WORDS:
        rest = tokens[1:]
        if all(word in _GREETING_FILLERS for word in rest):
            return True
    return False


def _yield_text(*, agent: str, text: str) -> Iterator[TokenEvent]:
    for delta in _iter_text_deltas(text):
        yield TokenEvent(agent=agent, delta=delta)


def _iter_text_deltas(text: str) -> Iterator[str]:
    """Split buffered text into word-slices joined with spaces (streaming shape)."""
    words = text.split(" ")
    for index, word in enumerate(words):
        yield word + (" " if index < len(words) - 1 else "")
