"""OpenAI-compatible chat-completions adapter (raw httpx, no vendor SDK).

Speaks ``POST {base_url}/chat/completions`` - the de-facto standard dialect
shared by OpenAI, OpenRouter, Groq, OmniRoute, AgentRouter and self-hosted
gateways. One adapter therefore serves every preset in the registry.

Error mapping (the router relies on this distinction):

- transport failure, timeout, or any HTTP error status -> AiUnavailableError
  ("this provider could not serve the request" - try the next one);
- HTTP 200 with a body that fails schema validation -> AiInvalidResponseError
  ("the provider answered but unusably").

API keys are sent as Bearer headers and never appear in logs, results, or
exception strings.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from ai_agent.core.exceptions import AiInvalidResponseError, AiUnavailableError
from ai_agent.core.providers.base import LlmCompletion, LlmRequest, LlmStreamChunk

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger("ai_agent.providers")

# The only JSON paths we read; anything missing/mistyped is a 502, not a crash.
_MIN_TIMEOUT_SECONDS = 1.0


class OpenAiCompatibleProvider:
    """One configured provider endpoint speaking the OpenAI-compatible dialect.

    ``native=True`` switches to the provider's NATIVE /api/chat dialect
    (Ollama). Reason: Ollama's /v1/chat/completions shim returns qwen3's
    reasoning in ``reasoning_content`` and an EMPTY ``message.content``,
    which breaks any strict-output consumer. The native endpoint honors
    ``think`` + the JSON grammar (``format: json``), so structured extraction
    works there. Error mapping is identical for both dialects.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        local_only: bool,
        native: bool = False,
        timeout_seconds: float,
    ) -> None:
        if not model.strip():
            raise ValueError("model is required")
        if not base_url.strip().lower().startswith(("http://", "https://")):
            raise ValueError("base_url must be an http(s) URL")
        self.name = name
        self.model = model
        self.local_only = local_only
        self._native = native
        self._base_url = base_url.rstrip("/")
        if native and self._base_url.endswith("/v1"):
            # Ollama native endpoints live at the server root (/api/chat),
            # not under the /v1 OpenAI-compat prefix.
            self._base_url = self._base_url[:-3]
        # Empty key allowed: some local gateways need no auth. Never logged.
        self._api_key = api_key
        self._timeout_seconds = max(timeout_seconds, _MIN_TIMEOUT_SECONDS)

    def _create_client(self) -> httpx.AsyncClient:
        """Create the per-call HTTP client (overridable seam for tests)."""
        return httpx.AsyncClient(timeout=self._timeout_seconds)

    @staticmethod
    def _build_user_content(
        request: LlmRequest,
    ) -> str | list[dict[str, object]]:
        """Build the user message content for the API payload.

        When ``request.image_blocks`` is present, returns an array of content
        blocks (text + image_url) for multimodal/vision requests.  Otherwise
        returns a plain string.
        """
        if request.image_blocks:
            blocks: list[dict[str, object]] = [{"type": "text", "text": request.user_prompt}]
            blocks.extend(request.image_blocks)
            return blocks
        return request.user_prompt

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        """POST one generation and parse the completion text."""
        if self._native:
            return await self._complete_native(request)
        return await self._complete_openai(request)

    async def _complete_openai(self, request: LlmRequest) -> LlmCompletion:
        """POST one chat completion and parse choices[0].message.content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": self._build_user_content(request)},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.think is not None:
            payload["think"] = request.think
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        started = time.perf_counter()
        try:
            async with self._create_client() as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "provider.http_error",
                provider=self.name,
                status_code=exc.response.status_code,
            )
            raise AiUnavailableError(f"Provider '{self.name}' could not serve the request") from exc
        except httpx.HTTPError as exc:
            # TimeoutException, ConnectError, and every other transport issue.
            logger.warning("provider.transport_error", provider=self.name)
            raise AiUnavailableError(f"Provider '{self.name}' is unreachable") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        text, model_used = _parse_completion_payload(response)
        return LlmCompletion(text=text, model_used=model_used, latency_ms=latency_ms)

    async def _complete_native(self, request: LlmRequest) -> LlmCompletion:
        """POST a native /api/chat generation (e.g. Ollama) and parse it.

        ``format: json`` grammatically constrains the output to valid JSON
        (Ollama) — combined with ``think: false`` this turns qwen3 into a
        fast, obedient structured extractor (its /v1 shim otherwise returns
        empty content).
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "stream": False,
            "temperature": request.temperature,
            # Grammar-constrained JSON: cheap, reliable structured extraction
            # even on small local models that otherwise ramble.
            "options": {"num_predict": request.max_tokens},
            "keep_alive": "1h",
        }
        if request.json_mode:
            payload["format"] = "json"
        if request.think is not None:
            payload["think"] = request.think
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        started = time.perf_counter()
        try:
            async with self._create_client() as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "provider.http_error",
                provider=self.name,
                status_code=exc.response.status_code,
            )
            raise AiUnavailableError(f"Provider '{self.name}' could not serve the request") from exc
        except httpx.HTTPError as exc:
            logger.warning("provider.transport_error", provider=self.name)
            raise AiUnavailableError(f"Provider '{self.name}' is unreachable") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        text, model_used = _parse_native_completion(response)
        return LlmCompletion(text=text, model_used=model_used, latency_ms=latency_ms)

    async def stream(
        self,
        request: LlmRequest,
    ) -> AsyncIterator[LlmStreamChunk]:
        """POST a streaming generation and yield token deltas (SKY-60)."""
        if self._native:
            async for chunk in self._stream_native(request):
                yield chunk
            return
        async for chunk in self._stream_openai(request):
            yield chunk

    async def _stream_openai(
        self,
        request: LlmRequest,
    ) -> AsyncIterator[LlmStreamChunk]:
        """POST a streaming chat completion and yield token deltas (SKY-60).

        Uses ``stream: true`` and parses ``data:`` SSE frames as they arrive
        - the response is NEVER buffered whole. The http client lives for the
        generator's lifetime: when the consumer stops iterating or closes the
        iterator (client disconnect), the ``async with`` exits and the
        upstream request is cancelled (disconnect propagation).

        Error mapping matches :meth:`complete`:

        - transport failure, timeout, or any HTTP error status ->
          :class:`AiUnavailableError`;
        - a frame whose schema fails validation ->
          :class:`AiInvalidResponseError`.

        Both are raised on iteration; a pre-yield failure lets the router
        fail over, a post-yield failure surfaces mid-stream.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": self._build_user_content(request)},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.think is not None:
            payload["think"] = request.think
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with (
                self._create_client() as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response,
            ):
                if response.status_code >= 400:
                    logger.warning(
                        "provider.stream_http_error",
                        provider=self.name,
                        status_code=response.status_code,
                    )
                    raise AiUnavailableError(f"Provider '{self.name}' could not serve the request")
                model_used = ""
                async for line in response.aiter_lines():
                    text_frame = _parse_stream_frame(line)
                    if text_frame is None:
                        continue
                    delta, frame_model = text_frame
                    if delta or frame_model:
                        model_used = frame_model or model_used
                        if delta:
                            yield LlmStreamChunk(
                                token_delta=delta,
                                model_used=model_used,
                            )
        except httpx.HTTPError as exc:
            # Connect/timeout/etc. - the provider never served the request.
            logger.warning("provider.stream_transport_error", provider=self.name)
            raise AiUnavailableError(f"Provider '{self.name}' is unreachable") from exc

    async def _stream_native(
        self,
        request: LlmRequest,
    ) -> AsyncIterator[LlmStreamChunk]:
        """Stream via the native /api/chat SSE dialect (e.g. Ollama)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "stream": True,
            "temperature": request.temperature,
            "options": {"num_predict": request.max_tokens},
            "keep_alive": "1h",
        }
        if request.json_mode:
            payload["format"] = "json"
        if request.think is not None:
            payload["think"] = request.think
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with (
                self._create_client() as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                    headers=headers,
                ) as response,
            ):
                if response.status_code >= 400:
                    logger.warning(
                        "provider.stream_http_error",
                        provider=self.name,
                        status_code=response.status_code,
                    )
                    raise AiUnavailableError(f"Provider '{self.name}' could not serve the request")
                model_used = ""
                async for line in response.aiter_lines():
                    text_frame = _parse_native_stream_frame(line)
                    if text_frame is None:
                        continue
                    delta, frame_model = text_frame
                    if delta or frame_model:
                        model_used = frame_model or model_used
                        if delta:
                            yield LlmStreamChunk(
                                token_delta=delta,
                                model_used=model_used,
                            )
        except httpx.HTTPError as exc:
            logger.warning("provider.stream_transport_error", provider=self.name)
            raise AiUnavailableError(f"Provider '{self.name}' is unreachable") from exc


def _parse_native_stream_frame(line: str) -> tuple[str, str] | None:
    """Parse one native /api/chat SSE frame into (token_delta, model) or None.

    Frames are bare JSON objects (no ``data:`` prefix): ``{"message":
    {"content": "..."}, "done": false}``. ``done: true`` frames and
    schema-less keep-alives return None. Reasoning-only frames (empty content)
    are skipped so a thinking block never leaks into the client stream.
    """
    payload = line.strip()
    if not payload:
        return None
    try:
        frame = json.loads(payload)
        if frame.get("done") is True:
            return None
        message = frame.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if content is not None and not isinstance(content, str):
            raise TypeError("message content must be a string")
        model = frame.get("model")
        if model is not None and not isinstance(model, str):
            raise TypeError("model must be a string")
    except (ValueError, TypeError) as exc:
        logger.warning("provider.invalid_stream_schema")
        raise AiInvalidResponseError(
            "Provider returned a stream frame that failed schema validation"
        ) from exc
    return (content or "", model or "")


def _parse_native_completion(response: httpx.Response) -> tuple[str, str]:
    """Extract (text, model) from a native /api/chat 200 body."""
    try:
        data = response.json()
        message = data["message"]
        content = message["content"]
        model = data.get("model") or ""
        if not isinstance(content, str) or not isinstance(model, str):
            raise TypeError("content/model must be strings")
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("provider.invalid_response_schema")
        raise AiInvalidResponseError(
            "Provider returned a response that failed schema validation"
        ) from exc
    return content, model


def _parse_stream_frame(line: str) -> tuple[str, str] | None:
    """Parse one SSE ``data:`` frame into (token_delta, model) or None.

    Returns None for keep-alive/schema-less frames every streaming API sends;
    raises :class:`AiInvalidResponseError` for a data frame whose schema is
    unusable (the provider "answered but unusably" - 502 semantics).
    """
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        frame = json.loads(payload)
        choices = frame.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        content = delta.get("content") if isinstance(delta, dict) else None
        if content is not None and not isinstance(content, str):
            raise TypeError("delta content must be a string")
        model = frame.get("model")
        if model is not None and not isinstance(model, str):
            raise TypeError("model must be a string")
    except (ValueError, TypeError) as exc:
        logger.warning("provider.invalid_stream_schema")
        raise AiInvalidResponseError(
            "Provider returned a stream frame that failed schema validation"
        ) from exc
    return (content or "", model or "")


def _parse_completion_payload(response: httpx.Response) -> tuple[str, str]:
    """Extract (text, model) from a 200 body; schema failures are 502s."""
    try:
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        model = data.get("model") or ""
        if not isinstance(content, str) or not isinstance(model, str):
            raise TypeError("content/model must be strings")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("provider.invalid_response_schema")
        raise AiInvalidResponseError(
            "Provider returned a response that failed schema validation"
        ) from exc
    return content, model
