"""Pydantic schemas for the reports API (RPT-BE-001)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportDefinitionRead(BaseModel):
    """Metadata for one report definition (the UI's build-from-metadata contract).

    ``dataset``, ``dimensions`` and ``measures`` are the NL report builder's
    selectable vocabulary (RPT-AI-001, SKY-80): the only dataset/grouping
    dimensions/numeric measures an LLM may pick for this definition. They are
    pure metadata populated from the canonical seed (matched by SQL content,
    so user-created saved reports inherit their template's semantics); they
    default to None/empty for any definition without a matching template.
    """

    id: uuid.UUID
    slug: str
    title: str
    module: str
    description: str | None = None
    params: list[str] = Field(default_factory=list)
    dataset: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    permission_key: str
    version: int
    updated_at: datetime


class ReportRunRequest(BaseModel):
    """Payload for POST /api/v1/reports/{slug}/run - raw user params."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Values for the definition's declared params (dates are ISO YYYY-MM-DD)",
    )


class ReportCreateRequest(BaseModel):
    """Payload for POST /api/v1/reports (RPT-AI-001, SKY-80).

    Carries everything needed to persist a generated report spec as a new
    definition. ``source_slug`` names the canonical whitelisted template the
    builder matched - the create path never accepts arbitrary or AI-generated
    SQL. When ``sql`` is omitted the server resolves the template SQL from
    ``source_slug`` itself (the ai-agent never has the SQL, so Core keeps the
    stored SQL byte-for-byte the reviewed read-only template); when supplied
    it must match that template exactly. ``params`` must equal the template's
    declared params; ``default_params`` are never persisted here (no schema
    column by design) and travel back to the client only so the run form can
    be pre-filled.
    """

    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    module: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    sql: str | None = Field(
        default=None,
        max_length=64_000,
        description=(
            "Template SQL; omit to resolve it server-side from source_slug "
            "(must match the whitelisted template exactly when supplied)"
        ),
    )
    source_slug: str = Field(
        min_length=1,
        max_length=64,
        description="Slug of the canonical whitelisted template this spec resolved to",
    )
    params: list[str] = Field(
        default_factory=list,
        description="Declared bind parameters (must equal the template's declared params)",
    )
    default_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved param values for the UI to pre-fill the run form; not persisted",
    )


class ReportRunResult(BaseModel):
    """Result of one parametrized report run."""

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = Field(
        default=False,
        description="True when the UI cap truncated rows (export streams the full set)",
    )
    period: date
    snapshot_id: uuid.UUID
    generated_at: datetime


class ReportSnapshotRead(BaseModel):
    """One stored snapshot for a report definition."""

    id: uuid.UUID
    definition_id: uuid.UUID
    period: date
    generated_at: datetime


class ReportCreateResult(BaseModel):
    """Result of POST /api/v1/reports (RPT-AI-001, SKY-80).

    Returns the persisted definition (runnable via the existing
    ``/{slug}/run`` path) plus the resolved default params so the client can
    pre-fill the run form immediately.
    """

    definition: ReportDefinitionRead
    default_params: dict[str, Any] = Field(default_factory=dict)
