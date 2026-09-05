"""Provider-agnostic LLM abstraction - protocol and value types.

The AI agent never talks to a vendor SDK: every provider is an
:class:`LlmProvider` speaking one of two dialects (today only OpenAI-compatible
HTTP; SKY-59 may add more). Engines depend ONLY on this protocol, so providers
are swappable via configuration without touching business code.

Security invariants every implementation MUST keep:

- API keys travel in Authorization headers only and are NEVER logged,
  returned in results, or embedded in exceptions.
- Exceptions carry sanitized, client-safe detail strings (failure MODE, not
  provider internals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """One generation request, already engine-sanitized.

    Prompts carry tenant DATA (product names, quantities) - residency rules
    decide which providers may see them (``require_local_only`` routing).
    """

    system_prompt: str
    user_prompt: str
    max_tokens: int = 512
    temperature: float = 0.2
    # Reasoning toggle for models that support it (e.g. Ollama qwen3). ``None``
    # means "provider default"; ``False`` disables the model's internal chain
    # of thought for fast, token-cheap structured extraction.
    think: bool | None = None
    # Force grammar-constrained JSON output when the provider supports it
    # (Ollama native ``format: json``; OpenAI-compatible ``json_object``).
    # ``True`` guarantees the completion is valid JSON, never prose.
    json_mode: bool = False
    """Optional multimodal content blocks (OpenAI vision format).

    When present, the provider sends ``content`` as an array of blocks
    instead of a plain string for the user message.  Each block is a dict
    with a ``"type"`` key (``"text"`` or ``"image_url"``).
    """
    image_blocks: list[dict[str, object]] | None = None


@dataclass(frozen=True, slots=True)
class LlmCompletion:
    """A successful generation with its provenance for audit trails."""

    text: str
    model_used: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class LlmStreamChunk:
    """One token delta from a streaming generation (SKY-60).

    ``token_delta`` is the exact text the provider emitted for this chunk
    (never a whole-response buffer); consumers concatenate deltas in order.
    """

    token_delta: str
    model_used: str


@runtime_checkable
class LlmProvider(Protocol):
    """Structural contract satisfied by every provider adapter."""

    name: str
    model: str
    local_only: bool

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        """Return one completion or raise a typed AI error."""
        ...

    def stream(
        self,
        request: LlmRequest,
    ) -> AsyncIterator[LlmStreamChunk]:
        """Yield token deltas in order, or raise a typed AI error.

        Contract for stream-aware consumers (SKY-60):

        - Errors raised BEFORE the first yielded chunk mean "this provider
          could not serve the request" - the caller may fail over to the next
          provider.
        - Errors raised AFTER the first chunk mean the stream is broken
          mid-flight; the caller must surface them to the client (tokens are
          already visible, rewinding is impossible).
        - Closing the returned async iterator MUST cancel the upstream
          request (client disconnect propagation), and the implementation
          must not buffer the full response before yielding.
        """
        ...
