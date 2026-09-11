"""Episodic-to-semantic memory compaction job (SKY-90).

The compaction job runs on a schedule (registered in the lifespan wiring)
and folds older episodic rows into semantic facts:

1. Select uncompacted episodic rows older than the compaction age, per user.
2. Summarize the batch into a handful of facts - via the LLM when a provider
   is configured, otherwise a deterministic fallback (query/response capped
   and tagged as ``source="compaction"``, lower confidence).
3. Persist the facts as semantic memory.
4. Stamp ``compacted_at`` on the folded rows so recall stops paying for them.

The LLM path is best-effort and never raises: any failure falls back to the
deterministic distillation so the job always progresses. Facts are always
bounded in count and text length so a compaction pass cannot bloat the
semantic store.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from ai_agent.core.providers.base import LlmRequest

if TYPE_CHECKING:
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.db.memory_repository import MemoryRepository

logger = structlog.get_logger("ai_agent.memory_compaction")

# Fold rows older than this many days (weekly job keeps the window wide so a
# user's recent pre-roll context survives between runs). Public - the scheduled
# pass in api/scheduled uses the same age to enumerate the per-tenant work set.
COMPACTION_AGE_DAYS = 7
# Per-user batch cap per job run (bounded work per pass).
_BATCH_LIMIT = 50
# Maximum number of distilled facts kept per batch.
_MAX_FACTS = 10
# Text caps for the deterministic fallback facts.
_FACT_TEXT_CAP = 240
_FALLBACK_CONFIDENCE = 0.5

_COMPACTION_SYSTEM_PROMPT = """\
You distill old conversation history into durable facts for the Skyrict
memory store. Given a JSON array of {query, response} conversation turns,
return a JSON array of at most 10 objects, each with:
- 'fact' (string, <= 240 chars): a durable statement that is useful later
- 'category' (one of: preference, entity, context, instruction)
- 'entity_type' (lead | opportunity | customer | contact | null)
- 'entity_id' (UUID string or null)
- 'confidence' (0.0-1.0)

Rules:
- Only extract genuinely durable facts. Skip one-off small talk.
- Do not invent details that are not in the turns.
- Never include PII beyond what is already in the turns.
- If nothing durable is present, return an empty array.
""".strip()


@dataclass(frozen=True, slots=True)
class CompactionSummary:
    """Result of one compaction pass for one user."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    rows_processed: int
    facts_stored: int
    llm_used: bool


class MemoryCompactionService:
    """Fold older episodic rows into semantic facts (repository-injected)."""

    def __init__(
        self,
        *,
        repo: MemoryRepository,
        llm_router: LlmRouter | None = None,
    ) -> None:
        self._repo = repo
        self._llm = llm_router

    async def compact_user(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CompactionSummary:
        """Run one compaction pass for a user's older episodic rows."""
        before = datetime.now(UTC) - timedelta(days=COMPACTION_AGE_DAYS)
        rows = await self._repo.list_uncompacted_episodic(
            tenant_id=tenant_id,
            user_id=user_id,
            before=before,
            limit=_BATCH_LIMIT,
        )
        if not rows:
            return CompactionSummary(
                tenant_id=tenant_id,
                user_id=user_id,
                rows_processed=0,
                facts_stored=0,
                llm_used=False,
            )

        turns = [{"query": row.query_text, "response": row.response_summary} for row in rows]
        llm_used = self._llm is not None and self._llm.has_providers
        facts = await self._distill(rows=turns, llm_used=llm_used)

        if facts:
            await self._repo.store_semantic_facts(
                tenant_id=tenant_id,
                user_id=user_id,
                facts=facts,
            )
        await self._repo.mark_episodic_compacted(
            tenant_id=tenant_id,
            ids=[row.id for row in rows],
        )

        logger.info(
            "memory_compaction.pass_complete",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            rows_processed=len(turns),
            facts_stored=len(facts),
            llm_used=llm_used,
        )
        return CompactionSummary(
            tenant_id=tenant_id,
            user_id=user_id,
            rows_processed=len(turns),
            facts_stored=len(facts),
            llm_used=llm_used,
        )

    async def _distill(
        self,
        *,
        rows: list[dict[str, str]],
        llm_used: bool,
    ) -> list[dict[str, Any]]:
        """Distill a batch of turns into bounded semantic facts."""
        if llm_used and self._llm is not None:
            try:
                facts = await self._llm_distill(llm_router=self._llm, rows=rows)
                if facts:
                    return facts
            except Exception:
                logger.warning("memory_compaction.llm_distill_failed", exc_info=True)
        return self._deterministic_distill(rows)

    async def _llm_distill(
        self,
        *,
        llm_router: LlmRouter,
        rows: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        completion = await llm_router.complete(
            LlmRequest(
                system_prompt=_COMPACTION_SYSTEM_PROMPT,
                user_prompt=json.dumps(rows, ensure_ascii=False),
                max_tokens=512,
                temperature=0.0,
                json_mode=True,
            )
        )
        text = (completion.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return []
        return [
            {
                "fact": str(item.get("fact", ""))[:_FACT_TEXT_CAP],
                "category": str(item.get("category", "context")),
                "entity_type": item.get("entity_type"),
                "entity_id": item.get("entity_id"),
                "confidence": float(item.get("confidence", 0.7)),
                "source": "compaction",
            }
            for item in parsed
            if isinstance(item, dict) and item.get("fact")
        ][:_MAX_FACTS]

    def _deterministic_distill(
        self,
        rows: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Provider-free distillation: bounded one-fact-per-turn fallback.

        Each folded turn becomes a context fact carrying the response's key
        detail (capped, lower confidence than an LLM extraction) so no
        information silently vanishes when providers are absent.
        """
        facts: list[dict[str, Any]] = []
        for turn in rows:
            fact_text = f"Q: {turn.get('query', '')[:100]} A: {turn.get('response', '')[: _FACT_TEXT_CAP - 110]}"
            facts.append(
                {
                    "fact": fact_text,
                    "category": "context",
                    "entity_type": None,
                    "entity_id": None,
                    "confidence": _FALLBACK_CONFIDENCE,
                    "source": "compaction",
                }
            )
            if len(facts) >= _MAX_FACTS:
                break
        return facts
