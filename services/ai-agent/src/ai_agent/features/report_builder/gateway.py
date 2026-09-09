"""Report gateway - read-only catalog + create access to Core's reporting API.

The AI agent owns NO report tables: the catalog, the parametrized execution,
and the create path all live in the Core monolith (RPT-AI-001, SKY-80). The
:class:`ReportGatewayPort` protocol is what engines depend on; tests fake it,
production binds :class:`HttpReportGateway`.

The NL report builder is a proxy, never a bypass (SKY-57 rule): every call
forwards the CALLER's JWT and tenant slug, so Core enforces the caller's own
``erp.reports.read`` / ``erp.reports.create`` scopes. The ai-agent invents no
catalog and no SQL - Core resolves stored SQL from its whitelisted templates.

Error mapping: Core answers with RFC 7807 problem+json and meaningful HTTP
statuses, so this gateway translates them into the matching domain exceptions
(422 -> ValidationError, 409 -> ConflictError, ...). Transport failures and
5xx become the typed 503 ai-unavailable; the client never sees Core internals.

Adapter notes (verified against Core's reports router):
- base path ``/api/v1/reports``; list/create respond with the shared envelope
  ``{"success": ..., "data": ...}``; run responds with
  ``{"success": ..., "data": {columns, rows, truncated, ...}}``;
- decimals arrive as strings and money values are stringified by Core's JSON
  encoder, so the engine treats every row value as an opaque scalar (they are
  only ever surfaced to the UI, never reinterpreted here);
- Core returns ``dataset``/``dimensions``/``measures`` on each definition - the
  selectable vocabulary the LLM prompt and the server-side validator share.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import structlog

from ai_agent.core.exceptions import (
    AiUnavailableError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)

logger = structlog.get_logger("ai_agent.report_gateway")


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    """One row of the Core report catalog (metadata only - never the SQL)."""

    slug: str
    module: str
    title: str
    description: str | None
    params: tuple[str, ...]
    # NL-builder selectable vocabulary (Core enriches from its canonical seeds).
    dataset: str | None
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportRun:
    """Result of one parametrized report execution from Core."""

    columns: list[str]
    rows: list[dict[str, str]]
    truncated: bool


@dataclass(frozen=True, slots=True)
class CreatedReport:
    """A persisted definition returned by Core's create path."""

    definition: ReportDefinition
    default_params: dict[str, Any]


class ReportGatewayPort(Protocol):
    """Read catalog, execute, create - scoped by the forwarded caller identity."""

    async def list_definitions(self) -> list[ReportDefinition]: ...
    async def run_report(self, slug: str, params: dict[str, Any]) -> ReportRun: ...
    async def create_definition(
        self,
        *,
        slug: str,
        title: str,
        module: str,
        description: str | None,
        source_slug: str,
        params: list[str],
        default_params: dict[str, Any] | None = None,
    ) -> CreatedReport: ...


class HttpReportGateway:
    """One request's gateway: forwards the user's JWT + tenant slug to Core."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        tenant_slug: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._tenant_slug = tenant_slug
        self._timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer_token}",
            # Core resolves tenants via subdomain in prod, X-Tenant-Slug in
            # dev/test; forwarding the slug keeps behavior identical either way.
            "X-Tenant-Slug": self._tenant_slug,
        }

    def _create_client(self) -> httpx.AsyncClient:
        """Create the per-call HTTP client (overridable seam for tests)."""
        return httpx.AsyncClient(timeout=self._timeout_seconds)

    async def list_definitions(self) -> list[ReportDefinition]:
        try:
            async with self._create_client() as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/reports",
                    headers=self._headers(),
                )
                _raise_for_response(response, "list")
        except httpx.TransportError as exc:
            logger.warning("report_gateway_unreachable", path="list")
            raise AiUnavailableError("Reporting service is temporarily unavailable") from exc
        data = _envelope_data(response, "list")
        if not isinstance(data, list):
            raise AiUnavailableError("Reporting service returned an unusable response")
        return [_parse_definition(item) for item in data]

    async def run_report(self, slug: str, params: dict[str, Any]) -> ReportRun:
        try:
            async with self._create_client() as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/reports/{slug}/run",
                    json={"params": params},
                    headers=self._headers(),
                )
                _raise_for_response(response, f"run/{slug}")
        except httpx.TransportError as exc:
            logger.warning("report_gateway_unreachable", path=f"run/{slug}")
            raise AiUnavailableError("Reporting service is temporarily unavailable") from exc
        data = _envelope_data(response, f"run/{slug}")
        if not isinstance(data, dict):
            raise AiUnavailableError("Reporting service returned an unusable response")
        columns = [str(c) for c in (data.get("columns") or [])]
        raw_rows = data.get("rows")
        if not isinstance(raw_rows, list):
            raise AiUnavailableError("Reporting service returned an unusable response")
        rows = [_scalar_strings(row) for row in raw_rows]
        return ReportRun(
            columns=columns,
            rows=rows,
            truncated=bool(data.get("truncated", False)),
        )

    async def create_definition(
        self,
        *,
        slug: str,
        title: str,
        module: str,
        description: str | None,
        source_slug: str,
        params: list[str],
        default_params: dict[str, Any] | None = None,
    ) -> CreatedReport:
        try:
            async with self._create_client() as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/reports",
                    json={
                        "slug": slug,
                        "title": title,
                        "module": module,
                        "description": description,
                        "source_slug": source_slug,
                        "params": params,
                        "default_params": default_params or {},
                        # NOTE: no "sql" - Core resolves the template SQL from
                        # source_slug server-side (SKY-80 invariant).
                    },
                    headers=self._headers(),
                )
                _raise_for_response(response, "create")
        except httpx.TransportError as exc:
            logger.warning("report_gateway_unreachable", path="create")
            raise AiUnavailableError("Reporting service is temporarily unavailable") from exc
        data = _envelope_data(response, "create")
        if not isinstance(data, dict):
            raise AiUnavailableError("Reporting service returned an unusable response")
        definition_data = data.get("definition")
        if not isinstance(definition_data, dict):
            raise AiUnavailableError("Reporting service returned an unusable response")
        return CreatedReport(
            definition=_parse_definition(definition_data),
            default_params=data.get("default_params", {}),
        )


def _raise_for_response(response: httpx.Response, path: str) -> None:
    """Map Core's HTTP status to the matching domain exception.

    Transport failures are handled by callers; this only covers the status
    codes Core actually returns. 5xx and anything unexpected become the typed
    503 ai-unavailable; client-correctable codes map to their RFC 7807 types.
    """
    if response.is_success:
        return
    status = response.status_code
    if status in (401, 403):
        raise AuthorizationError("Not authorized to perform that report action")
    if status == 404:
        raise NotFoundError("Report not found")
    if status == 409:
        raise ConflictError("A report with that slug already exists")
    if status == 422:
        raise ValidationError("The requested report configuration is invalid")
    logger.warning("report_gateway_rejected", path=path, status=status)
    raise AiUnavailableError("Reporting service returned an unusable response")


def _envelope_data(response: httpx.Response, path: str) -> Any:
    """Parse the shared envelope's ``data``; any anomaly is a typed 503."""
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("report_gateway_bad_body", path=path)
        raise AiUnavailableError("Reporting service returned an unusable response") from exc
    if not isinstance(payload, dict):
        raise AiUnavailableError("Reporting service returned an unusable response")
    data = payload.get("data")
    if data is None:
        raise AiUnavailableError("Reporting service returned an unusable response")
    return data


def _parse_definition(item: dict[str, Any]) -> ReportDefinition:
    params = item.get("params") or []
    dimensions = item.get("dimensions") or []
    measures = item.get("measures") or []
    dataset = item.get("dataset")
    return ReportDefinition(
        slug=str(item["slug"]),
        module=str(item.get("module", "")),
        title=str(item.get("title", "")),
        description=None if item.get("description") is None else str(item["description"]),
        params=tuple(str(p) for p in params),
        dataset=None if dataset is None else str(dataset),
        dimensions=tuple(str(d) for d in dimensions),
        measures=tuple(str(m) for m in measures),
    )


def _scalar_strings(row: Any) -> dict[str, str]:
    """Project a raw row onto a flat ``{column: string}`` dict (typesafe).

    Core stringifies money and numeric scalars in JSON; view-like numeric
    values are already strings when they reach us. Any nested or non-scalar
    value is excluded so the UI only ever sees flat, renderable cells.
    """
    if not isinstance(row, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            out[str(key)] = str(value)
    return out
