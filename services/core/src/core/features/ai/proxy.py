"""Transport logic for proxying requests to the ai-agent microservice.

Pure asyncio/httpx - no FastAPI router/request imports - so failure mapping
and header hygiene are exhaustively unit-testable with ``httpx.MockTransport``.
The only FastAPI surface is the two response wrappers (buffered + streaming).

Security posture:
- ONLY the caller's ``Authorization: Bearer`` header and the resolved
  tenant slug are relayed. Cookies, hop-by-hop headers, and client
  fingerprint headers are never forwarded.
- ai-agent re-verifies the JWT and cross-checks it against the relayed
  slug (spec §1.4), so a spoofed slug cannot widen access.
- The proxy only ever talks to the client's configured origin: the final
  request target's host is checked against the client ``base_url`` host
  before sending, so a crafted path can never redirect a relay to another
  destination (SSRF defence in depth on top of UUID-validated path ids).
- Transport failures (connect/timeout) raise the typed 503 problem the
  frontend mock-fallback policy consumes; upstream application errors
  pass through untouched (ai-agent speaks RFC 7807 already).
- Streaming relays (``stream=True``) keep the upstream connection open and
  forward each chunk as it arrives; a client disconnect closes that
  connection, cancelling the upstream SSE stream - no orphaned generation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from fastapi.responses import Response, StreamingResponse

from core.core.exceptions import AiServiceUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def build_forward_headers(*, authorization: str | None, tenant_slug: str | None) -> dict[str, str]:
    """The exact header set relayed upstream - nothing else survives."""
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if tenant_slug:
        headers["X-Tenant-Slug"] = tenant_slug
    return headers


async def forward_to_ai_agent(
    client: httpx.AsyncClient,
    *,
    method: str,
    upstream_path: str,
    authorization: str | None,
    tenant_slug: str | None,
    body: bytes | None = None,
    params: httpx.QueryParams | None = None,
    stream: bool = False,
) -> httpx.Response:
    """Send one request to ai-agent and return its response untouched.

    ``stream=True`` returns a streaming response whose body must be consumed
    via ``aiter_bytes()`` and closed with ``aclose()`` - use it only with
    :func:`relay_stream_response`.

    Raises:
        AiServiceUnavailableError: On any transport-level failure
            (connection refused, DNS, TLS, timeout). Never on HTTP error
            statuses - those are valid upstream application responses.
        ValueError: If the resolved request target points at a host other
            than the client's configured origin - the proxy refuses to
            relay anywhere else.
    """
    headers = build_forward_headers(authorization=authorization, tenant_slug=tenant_slug)
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = client.build_request(
        method,
        upstream_path,
        content=body if body is not None else b"",
        headers=headers,
        params=params,
    )
    # Host allowlist: relative paths resolve against base_url, so any
    # mismatch means the path escaped the configured origin.
    if request.url.host != client.base_url.host:
        raise ValueError(f"refusing to relay to non-configured host: {request.url.host!r}")
    try:
        return await client.send(request, stream=stream)
    except httpx.TransportError as exc:
        raise AiServiceUnavailableError("AI agent service did not respond") from exc


def relay_response(upstream: httpx.Response) -> Response:
    """Materialise an upstream response as a Starlette reply.

    Status and body pass through verbatim; only Content-Type is carried
    over (ai-agent always answers JSON/problem+json). ``Retry-After`` is the
    one extra header relayed so 429 rate-limit contracts survive the hop.
    """
    headers: dict[str, str] = {}
    if upstream.headers.get("retry-after"):
        headers["Retry-After"] = upstream.headers["retry-after"]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
        headers=headers or None,
    )


def relay_stream_response(upstream: httpx.Response) -> Response:
    """Relay a streaming upstream body chunk-by-chunk (SSE never buffered).

    The upstream connection is closed when the stream ends OR the client
    disconnects, which cancels the ai-agent generator upstream - no orphaned
    LLM generation keeps running server-side.
    """

    async def _iter_body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        _iter_body(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
