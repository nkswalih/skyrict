"""Supervisor graph - routes Agents-shell questions to registered module agents.

Composition root for the supervisor feature: reads the global ``agent_registry``
to decide which leaves are provisioned (enabled), then delegates through the
leaf services the API layer already composes. Unlike the checkpointed
:class:`AgentRuntime` (SKY-59) this is a STATELESS streaming facade - no
checkpointer, no HITL pause; SKY-60 chats render tokens live.

Route contract (SKY-60 Q&A decision #6): registry rows are seeded by migration
0009 - ``inventory_monitor`` and ``hr_copilot`` start enabled, while
``crm_assistant`` and ``finance_assistant`` start disabled so the supervisor
streams a clean "not provisioned yet" abstention instead of erroring. Migrations
flip those flags when the module backends land.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_agent.db.agent_registry_repository import AgentRegistryRepository
from ai_agent.db.conversation_repository import ConversationRepository
from ai_agent.features.supervisor.schemas import (
    AGENT_CRM,
    AGENT_FINANCE,
    AGENT_HR,
    AGENT_INVENTORY,
    SupervisorEvent,
)
from ai_agent.features.supervisor.service import SupervisorService

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_agent.api.v1.schemas.chat import AttachmentData
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.crm.gateway import CrmGatewayPort
    from ai_agent.features.crm.memory import MemoryService
    from ai_agent.features.finance.gateway import FinanceGatewayPort
    from ai_agent.features.hr_copilot.service import HrCopilotService
    from ai_agent.features.nl_query.gateway import InventoryGatewayPort
    from ai_agent.features.rag.retrieval.service import RagRetrievalService
    from ai_agent.features.supervisor.delegates import ForecastPort


class SupervisorRuntime:
    """Resolves registry-provisioned leaves and streams one supervisor turn."""

    REGISTERED_AGENTS: tuple[str, ...] = (AGENT_INVENTORY, AGENT_HR, AGENT_CRM, AGENT_FINANCE)

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_router: LlmRouter,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        rag: RagRetrievalService | None = None,
        hr_copilot: HrCopilotService | None = None,
        crm_gateway_factory: Callable[[], Awaitable[CrmGatewayPort]] | None = None,
        finance_gateway_factory: Callable[[], Awaitable[FinanceGatewayPort]] | None = None,
        memory_service: MemoryService | None = None,
        forecast: ForecastPort | None = None,
        confidence_threshold: float = 0.75,
    ) -> None:
        self._session = session
        self._llm_router = llm_router
        self._gateway_factory = gateway_factory
        self._rag = rag
        self._hr_copilot = hr_copilot
        self._crm_gateway_factory = crm_gateway_factory
        self._finance_gateway_factory = finance_gateway_factory
        self._memory_service = memory_service
        self._forecast = forecast
        self._confidence_threshold = confidence_threshold

    async def stream_answer(
        self,
        *,
        query: str,
        attachments: list[AttachmentData] | None = None,
        conversation_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[SupervisorEvent]:
        """Stream one full turn; registry provisioned-state is read per turn."""
        service = await self._build_service()
        async for event in service.stream_answer(
            query=query,
            attachments=attachments,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
        ):
            yield event

    async def _build_service(self) -> SupervisorService:
        repo = AgentRegistryRepository(self._session)
        provisioned = {name: await repo.get_enabled(name) for name in self.REGISTERED_AGENTS}
        return SupervisorService(
            llm_router=self._llm_router,
            gateway_factory=self._gateway_factory,
            rag=self._rag,
            hr_copilot=self._hr_copilot,
            crm_gateway_factory=self._crm_gateway_factory,
            finance_gateway_factory=self._finance_gateway_factory,
            memory_service=self._memory_service,
            forecast=self._forecast,
            conversation_history=ConversationRepository(self._session),
            provisioned=provisioned,
            confidence_threshold=self._confidence_threshold,
        )
