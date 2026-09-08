"""L3 narrative API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class L3NarrativeResponse(BaseModel):
    status: str
    source: str
    as_of: date
    kind: str
    title: str | None
    summary: str | None
    points: list[str]
    caveat: str | None
    generated_at: datetime | None
    model_used: str | None
    figures: dict[str, str] | None
