"""Request/response schemas for the NL report builder endpoints (SKY-80)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReportBuilderGenerateRequest(BaseModel):
    """POST /ai/report-builder/generate body - one free-text report request."""

    prompt: str = Field(min_length=1, max_length=500)


class ReportBuilderGenerateResponse(BaseModel):
    """POST /ai/report-builder/generate response.

    Abstentions/clarifications are 200 responses with an ``answer`` and no
    ``data`` - per the SKY-57 error contract they are not errors.
    """

    answer: str
    data: dict[str, object] | None = None
    model_used: str | None = None
    latency_ms: int


class ReportBuilderSaveRequest(BaseModel):
    """POST /ai/report-builder/save body.

    Persists a resolved report as a new Core definition. The caller supplies
    the display metadata + the chosen template + resolved params. The server
    derives ``module`` and declared params from the template's catalog entry
    (never from the client), and Core resolves the template SQL from
    ``template_slug`` (the ai-agent holds no SQL).
    ``slug`` must be a valid Core report slug ([a-z0-9_-]).
    """

    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    template_slug: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved run params (dates ISO YYYY-MM-DD); NOT persisted - pre-fill only",
    )


class ReportBuilderSaveResponse(BaseModel):
    """POST /ai/report-builder/save response."""

    slug: str
    title: str
    module: str
    answer: str
    default_params: dict[str, Any] = Field(default_factory=dict)
