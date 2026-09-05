"""LLM router - ordered provider chain with typed failure semantics.

Executes one generation request across the configured providers in order
(primary first, then fallback). The router is the ONLY component engines may
use to reach an LLM, because it owns three cross-cutting contracts:

1. Fallback: a provider failing (unreachable / HTTP error) moves the request
   to the next provider transparently.
2. Typed errors after exhaustion (SKY-57 error contract):
   - every attempt unreachable/HTTP-failed            -> 503 AiUnavailableError
   - every attempt reached but returned garbage        -> 502 AiInvalidResponseError
   - mixed (some down, some garbage)                   -> 503 (the service
     genuinely could not complete; 502 would imply it tried and only got
     unusable answers)
   - no provider configured at all                     -> 503
3. Data residency: when a prompt carries local-only data
   (``require_local_only=True``), only providers flagged ``local_only`` are
   eligible; with none eligible the request fails closed as 422
   AiDataResidencyError BEFORE any data leaves.

Per-attempt failures are logged with the provider NAME and failure class only
- never keys, prompts, or response bodies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from ai_agent.core.exceptions import (
    AiDataResidencyError,
    AiInvalidResponseError,
    AiUnavailableError,
)
from ai_agent.core.providers.base import LlmRequest
from ai_agent.redaction import Redactor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from ai_agent.core.providers.base import (
        LlmCompletion,
        LlmProvider,
        LlmStreamChunk,
    )

logger = structlog.get_logger("ai_agent.llm_router")


class LlmRouter:
    """Ordered failover across zero or more providers.

    The router is the single choke-point through which every LLM request
    passes. As such it also enforces the PII redaction gate (HR-AI-001): every
    ``LlmRequest`` is passed through ``self._redactor`` BEFORE it reaches any
    provider adapter, so no raw sensitive value can ever be serialized into an
    outbound provider payload. The gate fails closed - anything that matches a
    sensitive pattern is masked.
    """

    def __init__(
        self,
        providers: Sequence[LlmProvider],
        *,
        redactor: Redactor | None = None,
    ) -> None:
        self._providers: list[LlmProvider] = list(providers)
        # Default to the real redactor; tests may inject a fake. A redactor is
        # always present so the gate is never silently disabled by omission.
        self._redactor: Redactor = redactor if redactor is not None else Redactor()

    @property
    def has_providers(self) -> bool:
        """False when no provider is configured - AI endpoints degrade to 503."""
        return bool(self._providers)

    @property
    def provider_count(self) -> int:
        """Number of configured providers (for startup logging/metrics)."""
        return len(self._providers)

    def has_local_only_clearance(self) -> bool:
        """True when at least one provider is cleared for local-only data."""
        return any(provider.local_only for provider in self._providers)

    async def complete(
        self,
        request: LlmRequest,
        *,
        require_local_only: bool = False,
    ) -> LlmCompletion:
        """Run ``request`` through the provider chain and return one completion.

        Raises:
            AiDataResidencyError: Local-only data but no cleared provider.
            AiUnavailableError: No eligible provider served the request.
            AiInvalidResponseError: All eligible providers answered unusably.
        """
        if require_local_only and not self.has_local_only_clearance():
            raise AiDataResidencyError()

        eligible = (
            [provider for provider in self._providers if provider.local_only]
            if require_local_only
            else self._providers
        )
        if not eligible:
            raise AiUnavailableError("No AI provider is configured")

        # REDACTION GATE (HR-AI-001): mask PII from both prompt parts BEFORE any
        # provider serializes the payload. This is the single enforcement point
        # for every outbound provider call in ai-agent.
        redacted = self._redactor.redact(request.user_prompt)
        if redacted.text != request.user_prompt:
            logger.info(
                "llm_router.redacted",
                mask_counts=redacted.mask_counts,
            )
            request = LlmRequest(
                system_prompt=request.system_prompt,
                user_prompt=redacted.text,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                think=request.think,
                json_mode=request.json_mode,
                image_blocks=request.image_blocks,
            )

        saw_unavailable = False
        for provider in eligible:
            try:
                completion = await provider.complete(request)
            except AiInvalidResponseError:
                logger.warning(
                    "llm_router.provider_invalid_response",
                    provider=provider.name,
                    model=provider.model,
                )
            except AiUnavailableError:
                saw_unavailable = True
                logger.warning(
                    "llm_router.provider_unavailable",
                    provider=provider.name,
                    model=provider.model,
                )
            else:
                logger.info(
                    "llm_router.completed",
                    provider=provider.name,
                    model_used=completion.model_used,
                    latency_ms=completion.latency_ms,
                )
                return completion

        if saw_unavailable:
            # At least one provider never answered at all - the service could
            # not complete the request, which outranks "answers were garbage".
            raise AiUnavailableError()
        # Every eligible provider answered, but none produced usable output.
        raise AiInvalidResponseError()

    async def stream(
        self,
        request: LlmRequest,
        *,
        require_local_only: bool = False,
    ) -> AsyncIterator[LlmStreamChunk]:
        """Stream ``request`` through the provider chain (SKY-60).

        Shares ``complete``'s contracts - data residency gate, PII redaction
        gate, ordered provider chain - with one streaming-specific nuance:
        failover is ONLY possible until the first yielded token. Once a
        provider has begun answering, tokens are visible to the client and a
        mid-stream failure cannot be replayed; it is raised to the consumer
        as-is (mapped to an ``error`` SSE event by the caller).

        Raises (on iteration, before any yield unless noted):
            AiDataResidencyError: Local-only data but no cleared provider.
            AiUnavailableError: No eligible provider served the request.
            AiInvalidResponseError: Every eligible provider answered unusably.
        """
        if require_local_only and not self.has_local_only_clearance():
            raise AiDataResidencyError()

        eligible = (
            [provider for provider in self._providers if provider.local_only]
            if require_local_only
            else self._providers
        )
        if not eligible:
            raise AiUnavailableError("No AI provider is configured")

        # REDACTION GATE (HR-AI-001): identical to complete() - mask PII from
        # the prompt BEFORE any provider serializes a streaming payload.
        redacted = self._redactor.redact(request.user_prompt)
        if redacted.text != request.user_prompt:
            logger.info(
                "llm_router.redacted",
                mask_counts=redacted.mask_counts,
            )
            request = LlmRequest(
                system_prompt=request.system_prompt,
                user_prompt=redacted.text,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                think=request.think,
                json_mode=request.json_mode,
                image_blocks=request.image_blocks,
            )

        saw_unavailable = False
        for provider in eligible:
            started = False
            try:
                async for chunk in provider.stream(request):
                    if not started:
                        started = True
                        logger.info(
                            "llm_router.stream_started",
                            provider=provider.name,
                            model_used=chunk.model_used,
                        )
                    yield chunk
            except AiInvalidResponseError:
                logger.warning(
                    "llm_router.provider_invalid_stream",
                    provider=provider.name,
                    model=provider.model,
                )
                if started:
                    raise
            except AiUnavailableError:
                saw_unavailable = True
                logger.warning(
                    "llm_router.provider_unavailable_stream",
                    provider=provider.name,
                    model=provider.model,
                )
                if started:
                    raise
            else:
                logger.info(
                    "llm_router.stream_completed",
                    provider=provider.name,
                    model=provider.model,
                )
                return

        if saw_unavailable:
            raise AiUnavailableError()
        raise AiInvalidResponseError()
