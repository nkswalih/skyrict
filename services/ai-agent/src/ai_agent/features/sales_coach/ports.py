"""Sales Coach domain port — protocol the graph and service depend on.

Tests provide fake implementations; production wires the repository. The port
does NOT import ORM models (import-linter contract: only repositories touch
SQLAlchemy).
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class CoachingSuggestionPort(Protocol):
    """Write-only port for creating coaching suggestions."""

    async def create_suggestion(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
        opportunity_id: uuid.UUID | None,
        lead_id: uuid.UUID | None,
        suggestion_type: str,
        title: str,
        body: str,
        evidence: list[dict[str, Any]],
    ) -> uuid.UUID:
        """Persist a coaching suggestion and return its id."""
        ...

    async def list_pending_for_rep(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """List pending suggestions for a specific rep."""
        ...

    async def list_all_pending(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """List all pending suggestions for manager view."""
        ...

    async def mark_viewed(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
    ) -> None:
        """Mark a suggestion as viewed."""
        ...
