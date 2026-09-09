"""Unit tests for the OpenAI-compatible adapter and the provider registry.

The adapter is exercised over ``httpx.MockTransport`` - real HTTP semantics,
no network. Security assertions: the API key travels ONLY in the Authorization
header and never leaks into results, logs, or exception strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_agent.core.exceptions import AiInvalidResponseError, AiUnavailableError, StartupError
from ai_agent.core.providers import LlmRequest, OpenAiCompatibleProvider
from ai_agent.core.providers.registry import (
    build_provider,
    build_providers_from_settings,
    resolve_base_url,
)


def _make_provider(
    handler: Any,
    *,
    api_key: str = "sk-secret-key",
    local_only: bool = False,
) -> tuple[OpenAiCompatibleProvider, list[httpx.Request]]:
    """Build a provider wired to a MockTransport; capture outbound requests."""
    seen: list[httpx.Request] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    provider = OpenAiCompatibleProvider(
        name="testprovider",
        model="test-model-1",
        base_url="https://api.test.example/v1",
        api_key=api_key,
        local_only=local_only,
        timeout_seconds=5,
    )
    # Swap the client factory for one bound to the mock transport (the
    # production path constructs a real client per call).
    provider._create_client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        timeout=5,
        transport=httpx.MockTransport(_transport_handler),
    )
    return provider, seen


_REQUEST = LlmRequest(system_prompt="be terse", user_prompt="say hi")


class TestOpenAiCompatibleProvider:
    async def test_successful_completion(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
                    "model": "test-model-1",
                },
            )

        provider, _ = _make_provider(handler)
        completion = await provider.complete(_REQUEST)

        assert completion.text == "hi there"
        assert completion.model_used == "test-model-1"
        assert completion.latency_ms >= 0

    async def test_request_shape_and_auth_header(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}], "model": "m"},
            )

        provider, _ = _make_provider(handler)
        await provider.complete(_REQUEST)

        assert captured["auth"] == "Bearer sk-secret-key"
        body = captured["body"]
        assert body["model"] == "test-model-1"
        assert body["stream"] is False
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "be terse"
        assert body["messages"][1]["content"] == "say hi"

    async def test_non_stream_retry_when_gateway_streams_by_default(self) -> None:
        """A gateway that streams unless told not to must get a clean 200.

        Some OpenAI-compatible gateways (self-hosted omniroute) answer SSE
        frames even for a non-stream request unless ``stream: false`` is
        explicit. The adapter must send it so a JSON completion (184) is not
        misparsed as a schema failure (502).
        """
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}], "model": "m"},
            )

        provider, _ = _make_provider(handler)
        completion = await provider.complete(_REQUEST)

        assert captured["body"]["stream"] is False
        assert completion.text == "ok"

    async def test_think_false_omitted_from_openai_payload(self) -> None:
        """``think=False`` must NOT be sent to OpenAI-compatible endpoints.

        Regression: the report builder always sends ``think=False`` (and
        json_mode=True). Groq's chat-completions API has no ``think`` field
        and rejects the request with 400 "property 'think' is unsupported",
        killing the fallback chain when the primary gateway is unreachable.
        ``think=False`` is the endpoint default anyway (no reasoning), so
        omitting it is semantically identical and keeps the request portable.
        """
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}], "model": "m"},
            )

        provider, _ = _make_provider(handler)
        request = LlmRequest(
            system_prompt="You are a report spec extractor. Reply in JSON.",
            user_prompt="sales orders by day for last quarter",
            temperature=0.0,
            max_tokens=512,
            json_mode=True,
            think=False,
        )
        await provider.complete(request)

        body = captured["body"]
        assert "think" not in body
        assert body["response_format"] == {"type": "json_object"}

    async def test_think_true_is_forwarded_to_supporting_gateway(self) -> None:
        """Explicit ``think=True`` is a supported extension (OmniRoute etc.)."""

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}], "model": "m"},
            )

        captured: dict[str, Any] = {}
        provider, _ = _make_provider(handler)
        await provider.complete(LlmRequest(system_prompt="s", user_prompt="u", think=True))

        assert captured["body"]["think"] is True

    async def test_http_error_maps_to_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "overloaded"})

        provider, _ = _make_provider(handler)
        with pytest.raises(AiUnavailableError):
            await provider.complete(_REQUEST)

    async def test_timeout_maps_to_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        provider, _ = _make_provider(handler)
        with pytest.raises(AiUnavailableError):
            await provider.complete(_REQUEST)

    async def test_malformed_json_maps_to_invalid_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json{{{")

        provider, _ = _make_provider(handler)
        with pytest.raises(AiInvalidResponseError):
            await provider.complete(_REQUEST)

    async def test_missing_choices_maps_to_invalid_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"object": "chat.completion"})

        provider, _ = _make_provider(handler)
        with pytest.raises(AiInvalidResponseError):
            await provider.complete(_REQUEST)

    async def test_non_string_content_maps_to_invalid_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": 42}}]})

        provider, _ = _make_provider(handler)
        with pytest.raises(AiInvalidResponseError):
            await provider.complete(_REQUEST)

    async def test_api_key_never_in_error_messages(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider, _ = _make_provider(handler)
        with pytest.raises(AiUnavailableError) as exc_info:
            await provider.complete(_REQUEST)
        assert "sk-secret-key" not in str(exc_info.value)


def _sse_stream(content: str, *, model: str = "test-model-1") -> httpx.Response:
    """Build an httpx response carrying one OpenAI-style SSE stream body."""
    frames = [
        f"data: {json.dumps({'choices': [{'delta': {'content': c}}], 'model': model})}"
        for c in content
    ]
    body = "\n\n".join(frames) + "\n\ndata: [DONE]\n\n"
    return httpx.Response(
        200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"}
    )


class TestOpenAiCompatibleProviderStream:
    async def test_stream_yields_token_deltas_in_order(self) -> None:
        provider, _ = _make_provider(lambda request: _sse_stream("Hello world"))
        chunks = [c async for c in provider.stream(_REQUEST)]
        assert "".join(c.token_delta for c in chunks) == "Hello world"
        assert all(c.model_used == "test-model-1" for c in chunks)

    async def test_stream_sends_stream_true_and_chat_shape(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.content)
            return _sse_stream("ok")

        provider, _ = _make_provider(handler)
        _ = [c async for c in provider.stream(_REQUEST)]

        assert captured["auth"] == "Bearer sk-secret-key"
        body = captured["body"]
        assert body["stream"] is True
        assert body["model"] == "test-model-1"
        assert body["messages"][1]["content"] == "say hi"

    async def test_stream_omits_think_false_from_payload(self) -> None:
        """The streaming path must obey the same think portability rule."""
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return _sse_stream("ok")

        provider, _ = _make_provider(handler)
        _ = [
            c
            async for c in provider.stream(
                LlmRequest(system_prompt="s", user_prompt="u", think=False)
            )
        ]

        assert "think" not in captured["body"]

    async def test_stream_http_error_maps_to_unavailable(self) -> None:
        provider, _ = _make_provider(
            lambda request: httpx.Response(503, json={"error": "overloaded"})
        )
        with pytest.raises(AiUnavailableError):
            _ = [c async for c in provider.stream(_REQUEST)]

    async def test_stream_transport_error_maps_to_unavailable(self) -> None:
        provider, _ = _make_provider(
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused"))
        )
        with pytest.raises(AiUnavailableError):
            _ = [c async for c in provider.stream(_REQUEST)]

    async def test_stream_invalid_frame_maps_to_invalid_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"data: not-json\n\n")

        provider, _ = _make_provider(handler)
        with pytest.raises(AiInvalidResponseError):
            _ = [c async for c in provider.stream(_REQUEST)]

    async def test_stream_close_stops_iteration_cleanly(self) -> None:
        """Closing the iterator after first token cancels the rest quietly."""
        provider, _ = _make_provider(lambda request: _sse_stream("Hello world"))
        gen = provider.stream(_REQUEST)
        first = await anext(gen)
        assert first.token_delta == "H"
        await gen.aclose()
        # aclose must not raise; iterating again yields nothing.
        with pytest.raises(StopAsyncIteration):
            await anext(gen)


class TestRegistryFactory:
    def test_preset_resolved_without_override(self) -> None:
        assert resolve_base_url("openrouter", "") == "https://openrouter.ai/api/v1"

    def test_override_wins_over_preset(self) -> None:
        assert resolve_base_url("groq", "https://mirror.example/v1") == "https://mirror.example/v1"

    def test_unknown_key_rejected_at_build(self) -> None:
        with pytest.raises(StartupError, match="Unknown AI provider"):
            build_provider(
                provider_key="ollama",
                model="llama3",
                timeout_seconds=5,
            )

    def test_presetless_key_requires_base_url(self) -> None:
        with pytest.raises(StartupError, match="base URL"):
            build_provider(provider_key="omniroute", model="m", timeout_seconds=5)

    def test_settings_with_no_providers_builds_empty_chain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("AI_FALLBACK_PROVIDER", raising=False)
        from ai_agent.core.config import Settings

        config = Settings(_env_file=None)  # type: ignore[call-arg]
        assert build_providers_from_settings(config) == []

    def test_primary_plus_fallback_built_from_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AI_PROVIDER", "openrouter")
        monkeypatch.setenv("AI_MODEL", "org/model-a")
        monkeypatch.setenv("AI_API_KEY", "key-a")
        monkeypatch.setenv("AI_FALLBACK_PROVIDER", "omniroute")
        monkeypatch.setenv("AI_FALLBACK_MODEL", "model-b")
        monkeypatch.setenv("AI_FALLBACK_BASE_URL", "https://gateway.internal/v1")
        from ai_agent.core.config import Settings

        config = Settings(_env_file=None)  # type: ignore[call-arg]
        providers = build_providers_from_settings(config)

        assert [p.name for p in providers] == ["openrouter", "omniroute"]
        assert providers[0].local_only is False

    def test_compose_llm_chain_contract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """docker-compose.dev.yml keeps env_file providers, corrects two ends.

        Value of this test is the CONTRACT, not the providers: the container
        must pair the env_file's omniroute primary with a reachable base URL
        (host.docker.internal, since localhost inside a container is the
        container itself) and keep the groq fallback coherent (a current
        model on groq's own endpoint - the old llama-3.1-8b-instant no longer
        exists, and an openrouter model on groq's URL is a 400).
        """
        monkeypatch.setenv("AI_PROVIDER", "omniroute")
        monkeypatch.setenv("AI_MODEL", "openlad")
        monkeypatch.setenv("AI_BASE_URL", "http://host.docker.internal:20128/v1")
        monkeypatch.setenv("AI_FALLBACK_PROVIDER", "groq")
        monkeypatch.setenv("AI_FALLBACK_MODEL", "qwen/qwen3.8-27b")
        monkeypatch.setenv("AI_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("AI_FALLBACK_LOCAL_ONLY", "false")
        from ai_agent.core.config import Settings

        config = Settings(_env_file=None)  # type: ignore[call-arg]
        providers = build_providers_from_settings(config)

        assert [p.name for p in providers] == ["omniroute", "groq"]
        assert providers[0].model == "openlad"
        # Omniroute has no preset - the bare override IS the effective URL.
        assert resolve_base_url("omniroute", "http://host.docker.internal:20128/v1") == (
            "http://host.docker.internal:20128/v1"
        )
        assert providers[1].model == "qwen/qwen3.8-27b"
        assert providers[1].local_only is False
        assert resolve_base_url("groq", "https://api.groq.com/openai/v1") == (
            "https://api.groq.com/openai/v1"
        )

    def test_compose_boot_runs_migrations(self) -> None:
        """docker-compose.dev.yml must migrate each service's DB before boot.

        Regression for SKY-80: stale dev DBs (core three heads behind, ai-agent
        three heads behind, identity stamped under a revision the built-in
        alembic tree could not find) silently broke the NL report builder's
        generate/save. Each dev service therefore prepends
        `alembic upgrade head` to its CMD and mounts the `alembic` tree so the
        container sees the repo's revision scripts. If either half of that
        contract regresses, the stack can drift again without any CI signal.
        """
        import yaml

        repo_root = Path(__file__).resolve().parents[4]
        compose_file = repo_root / "infra" / "docker" / "docker-compose.dev.yml"
        compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))

        for service in ("identity", "core", "ai-agent"):
            service_def = compose["services"][service]
            command = " ".join(service_def["command"])
            assert "alembic upgrade head" in command, (
                f"{service} dev CMD must migrate before boot: {command}"
            )
            assert "uvicorn" in command
            volume_specs = [str(v) for v in service_def["volumes"]]
            assert any("alembic" in v for v in volume_specs), (
                f"{service} dev volumes must mount the alembic tree: {volume_specs}"
            )
