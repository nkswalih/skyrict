"""/ai/agents/chat/stream - real-time supervisor chat for the Agents shell.

POST returns a ``text/event-stream`` response: one SSE event per supervisor
turn step, in order:

  ``classification`` → (per module agent) ``agent_start`` → ``token``* →
  ``citations`` → ``done``   (``error`` replaces the stream on failure)

Authentication happens here (JWT re-verification); authorization happened
upstream at the core monolith's proxy (``erp.ai.invoke`` + module keys checked
before forwarding - SKY-57 "AI is a proxy, not a bypass"). This router
composes per-request dependencies the same way nl_query/hr_copilot/rag do:
caller identity, gateways bound to the CALLER'S token, and the shared LLM
router from ``app.state``.

Disconnect handling (SKY-60): client disconnects cancel the StreamingResponse
generator, which closes the supervisor turn generator and in turn the upstream
LLM stream - no orphaned generation runs server-side.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from asyncio import CancelledError
from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.chat import AttachmentData, ChatStreamRequest
from ai_agent.core.audit_service import AuditService
from ai_agent.core.config import settings
from ai_agent.core.embedding import build_embedding_provider
from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.core.rate_limit import limiter
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.query_cache_repository import QueryCacheRepository
from ai_agent.db.rag_repository import RagRepository
from ai_agent.features.crm.gateway import HttpCrmGateway
from ai_agent.features.finance.gateway import HttpFinanceGateway
from ai_agent.features.forecast.service import ForecastService
from ai_agent.features.hr_copilot.engine import HrCopilotEngine
from ai_agent.features.hr_copilot.gateway import HttpHrGateway
from ai_agent.features.hr_copilot.service import HrCopilotService
from ai_agent.features.nl_query.gateway import HttpInventoryGateway, InventoryGatewayPort
from ai_agent.features.rag.retrieval import RedisQueryCache
from ai_agent.features.rag.retrieval.service import RagRetrievalService
from ai_agent.features.supervisor.schemas import (
    AgentStartEvent,
    CitationsEvent,
    ClassificationEvent,
    DoneEvent,
    SupervisorEvent,
    TokenEvent,
)
from ai_agent.graphs.supervisor import SupervisorRuntime

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger("ai_agent.chat")

router = APIRouter(prefix="/ai/agents/chat", tags=["ai-agent-chat"])

# SSE event names the shell consumes (Q&A decision #4).
EVENT_CLASSIFICATION = "classification"
EVENT_AGENT_START = "agent_start"
EVENT_TOKEN = "token"
EVENT_CITATIONS = "citations"
EVENT_DONE = "done"
EVENT_ERROR = "error"


def _build_runtime(request: Request, session: AsyncSession) -> SupervisorRuntime:
    """Compose the supervisor stack for one request (test-visible seam).

    Every gateway is bound to THIS request's identity (the caller's own JWT -
    never service credentials), so each delegated read runs with exactly the
    access the human user already has. RAG and forecast are optional by
    design: the supervisor degrades to live inventory/HR answers without
    embeddings or a forecast backend, and the deterministic keyword classifier
    keeps the shell usable without an LLM.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    tenant_slug = TenantContext.get_tenant_slug() or ""
    gateway = HttpInventoryGateway(
        base_url=str(settings.INVENTORY_SERVICE_URL),
        bearer_token=token,
        tenant_slug=tenant_slug,
    )

    async def gateway_factory() -> InventoryGatewayPort:
        return gateway

    rag: RagRetrievalService | None = None
    embedding_provider = build_embedding_provider(settings)
    if embedding_provider is not None:
        rag = RagRetrievalService(
            embedding_provider=embedding_provider,
            store=RagRepository(session),
            cache=RedisQueryCache(),
            top_k_retrieve=settings.RAG_TOP_K_RETRIEVE,
            top_k_return=settings.RAG_TOP_K_RETURN,
            cache_ttl_seconds=settings.RAG_CACHE_TTL_SECONDS,
            rate_limit_per_minute=settings.RATE_LIMIT_RAG_SEARCH_PER_MIN,
            tenant_limit_per_minute=settings.RATE_LIMIT_TENANT_PER_MIN,
            persistent_cache=QueryCacheRepository(session),
        )

    hr_copilot = HrCopilotService(
        engine=HrCopilotEngine(
            llm_router=request.app.state.llm_router,
            gateway_factory=HttpHrGateway(
                base_url=str(settings.INVENTORY_SERVICE_URL),
                bearer_token=token,
                tenant_slug=tenant_slug,
            ),
        ),
        audit=AuditService(AiAuditLogRepository(session)),
        rate_limit_per_minute=settings.RATE_LIMIT_HR_COPILOT_PER_MIN,
        tenant_limit_per_minute=settings.RATE_LIMIT_TENANT_PER_MIN,
    )

    crm_gateway = HttpCrmGateway(
        base_url=str(settings.INVENTORY_SERVICE_URL),
        bearer_token=token,
        tenant_slug=tenant_slug,
    )

    async def crm_gateway_factory() -> HttpCrmGateway:
        return crm_gateway

    finance_gateway = HttpFinanceGateway(
        base_url=str(settings.INVENTORY_SERVICE_URL),
        bearer_token=token,
        tenant_slug=tenant_slug,
    )

    async def finance_gateway_factory() -> HttpFinanceGateway:
        return finance_gateway

    from ai_agent.db.memory_repository import MemoryRepository
    from ai_agent.features.crm.memory import MemoryService

    memory_service = MemoryService(
        llm_router=request.app.state.llm_router,
        repo=MemoryRepository(session),
    )

    return SupervisorRuntime(
        session=session,
        llm_router=request.app.state.llm_router,
        gateway_factory=gateway_factory,
        rag=rag,
        hr_copilot=hr_copilot,
        crm_gateway_factory=crm_gateway_factory,
        finance_gateway_factory=finance_gateway_factory,
        memory_service=memory_service,
        forecast=ForecastService(gateway_factory=gateway_factory),
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
    )


def get_supervisor_runtime(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SupervisorRuntime:
    """FastAPI dependency wrapping :func:`_build_runtime`."""
    return _build_runtime(request, session)


@router.post("/stream")
async def stream_chat(
    body: ChatStreamRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    runtime: Annotated[SupervisorRuntime, Depends(get_supervisor_runtime)],
) -> StreamingResponse:
    """Stream one supervisor turn as SSE events (real-time shell chat).

    Rate limits are enforced HERE (before any streaming starts) so an
    exhausted quota returns a clean RFC 7807 429 instead of killing a stream
    mid-turn. Keys follow the module pattern (ai:chat:{tenant}:{user} +
    tenant-level ai:tenant_total:{tenant}); no prompt content touches Redis.
    """
    await limiter.enforce(
        key=f"ai:chat:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CHAT_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )

    return StreamingResponse(
        _event_stream(
            runtime=runtime,
            message=body.message,
            attachments=body.attachments,
            conversation_id=body.conversation_id,
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_stream(
    *,
    runtime: SupervisorRuntime,
    message: str,
    attachments: list[AttachmentData] | None = None,
    conversation_id: uuid.UUID | None = None,
    tenant_id: Any,
    user_id: Any,
) -> AsyncIterator[str]:
    """Map supervisor events to SSE frames; sanitized failure frames only.

    Lifecycle guarantees:
      - A ``done`` event is ALWAYS the last frame, even when the generator
        is cancelled (client disconnect) or the upstream LLM fails.
      - ``CancelledError`` (client disconnect) is caught explicitly because
        it inherits from ``BaseException`` in Python 3.9+ and would bypass
        ``except Exception``.
    """
    done_sent = False
    try:
        async for event in runtime.stream_answer(
            query=message,
            attachments=attachments,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
        ):
            name, payload = _to_sse(event)
            if name == EVENT_DONE:
                done_sent = True
            yield f"event: {name}\ndata: {json.dumps(payload)}\n\n"
    except CancelledError:
        # Client disconnected - the ASGI server cancelled this task.
        # Do NOT yield here; the generator is being torn down.
        logger.info("chat.stream_cancelled")
    except AiUnavailableError as exc:
        logger.warning("chat.stream_unavailable", error=str(exc))
        yield _error_frame("The AI service is temporarily unavailable. Please try again.")
    except Exception:
        logger.exception("chat.stream_failed")
        yield _error_frame("An unexpected error occurred. Please try again.")
    finally:
        # Safety net: always send a done event so the client never stays
        # stuck on loading dots if the generator exits without one.
        # On CancelledError the client is already gone, so we skip the yield.
        if not done_sent:
            with contextlib.suppress(GeneratorExit):
                yield f"event: {EVENT_DONE}\ndata: {json.dumps({'agents': []})}\n\n"


def _to_sse(event: SupervisorEvent) -> tuple[str, dict[str, object]]:
    """One supervisor event → (SSE event name, JSON-safe payload)."""
    if isinstance(event, ClassificationEvent):
        return EVENT_CLASSIFICATION, {
            "agents": list(event.agents),
            "confidence": event.confidence,
            "abstain": event.abstain,
            "reason": event.reason,
        }
    if isinstance(event, AgentStartEvent):
        return EVENT_AGENT_START, {
            "agent": event.agent,
            "display_name": event.display_name,
        }
    if isinstance(event, TokenEvent):
        return EVENT_TOKEN, {"agent": event.agent, "delta": event.delta}
    if isinstance(event, CitationsEvent):
        return EVENT_CITATIONS, {
            "agent": event.agent,
            "citations": [
                {
                    "source_ref": citation.source_ref,
                    "module": citation.module,
                    "title": citation.title,
                    "url": citation.url,
                }
                for citation in event.citations
            ],
        }
    if isinstance(event, DoneEvent):
        return EVENT_DONE, {"agents": list(event.agents)}
    raise AssertionError(f"unknown supervisor event: {event!r}")  # pragma: no cover


def _error_frame(message: str) -> str:
    """A sanitized error frame - failure MODE, never provider internals."""
    return f"event: {EVENT_ERROR}\ndata: {json.dumps({'message': message})}\n\n"
