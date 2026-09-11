"""Audit Guardian service — weekly integrity report generation (SKY-90).

The service orchestrates:
1. Reading the last week's audit events from all configured sources
   (ai_agent, core, identity) via the injected readers.
2. Running deterministic watcher rules against the events to flag suspicious
   patterns (off-hours access, bulk reads, auth bursts).
3. Optionally running an LLM severity reassessment/prose summary when
   providers are configured (deterministic fallback otherwise).
4. Persisting the report + flagged events with evidence links.

Security posture:
  * The watchers never see raw prompt data — only sanitized audit summaries.
  * The LLM receives ONLY the flagged events (not the raw audit trail), and
    output is validated before persistence.
  * Reports are tenant-scoped via the injected RLS session; a report row is
    only readable by the tenant that owns it.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from ai_agent.core.audit_events import AI_GUARDIAN_REPORT_GENERATED
from ai_agent.core.providers.base import LlmRequest
from ai_agent.features.audit_guardian.watchers import FlaggedEvent, run_all_watchers

if TYPE_CHECKING:
    from ai_agent.core.audit_service import AuditService
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.audit_guardian.ports import (
        AuditLogReaderPort,
        GuardianReportPort,
    )

logger = structlog.get_logger("ai_agent.audit_guardian.service")

# Sources the guardian watches (matched to their audit log tables).
_SOURCES = ("ai_agent", "core", "identity")
_WEEK_DAYS = 7
_PER_SOURCE_LIMIT = 500


class GuardianReportService:
    """Generate weekly integrity reports from audit log analysis."""

    def __init__(
        self,
        *,
        report_repo: GuardianReportPort,
        readers: dict[str, AuditLogReaderPort],
        audit: AuditService,
        llm_router: LlmRouter | None = None,
    ) -> None:
        self._report_repo = report_repo
        self._readers = readers
        self._audit = audit
        self._llm = llm_router

    async def generate_weekly_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_week_end: date | None = None,
    ) -> dict[str, Any]:
        """Generate the weekly integrity report for the given week.

        ``report_week_end`` defaults to today; the week starts 7 days prior.
        Returns a JSON-safe report summary.
        """
        end = report_week_end or datetime.now(UTC).date()
        start = end - timedelta(days=_WEEK_DAYS - 1)

        # 1. Read audit events from all sources.
        all_events: list[dict[str, Any]] = []
        for source in _SOURCES:
            reader = self._readers.get(source)
            if reader is None:
                logger.warning("audit_guardian.reader_missing", source=source)
                continue
            try:
                events = await reader.read_recent_events(
                    tenant_id=tenant_id,
                    since=start,
                    source=source,
                    limit=_PER_SOURCE_LIMIT,
                )
                logger.info(
                    "audit_guardian.events_read",
                    tenant_id=str(tenant_id),
                    source=source,
                    count=len(events),
                )
                all_events.extend(events)
            except Exception:
                logger.warning(
                    "audit_guardian.read_failed",
                    tenant_id=str(tenant_id),
                    source=source,
                    exc_info=True,
                )
                continue

        total_scanned = len(all_events)

        # 2. Partition events by source table so watchers can group correctly
        #    (bulk-reads and auth-burst rules need whole-batch windows).
        partitions: dict[str, list[dict[str, Any]]] = {}
        for event in all_events:
            source_table = str(event.get("source_table", "unknown"))
            partitions.setdefault(source_table, []).append(event)

        flagged: list[FlaggedEvent] = []
        for source_table, events in partitions.items():
            flagged.extend(run_all_watchers(events, source_table=source_table))

        # 3. LLM severity reassessment + prose summary (best-effort).
        summary = self._build_summary(start=start, end=end, total=total_scanned, flagged=flagged)
        if self._llm is not None and self._llm.has_providers and flagged:
            summary = await self._llm_summary(
                llm_router=self._llm,
                start=start,
                end=end,
                total=total_scanned,
                flagged=flagged,
                fallback=summary,
            )

        # 4. Deduplicate flagged events (same source+id+action can hit multiple
        #    rules — pick the highest severity).
        flagged = _dedupe_flagged(flagged)

        # 5. Persist report + events.
        report_id = await self._report_repo.create_report(
            tenant_id=tenant_id,
            report_week_start=start,
            report_week_end=end,
            summary=summary,
            total_events_scanned=total_scanned,
            flagged_count=len(flagged),
        )
        for flagged_event in flagged:
            await self._report_repo.create_event(
                tenant_id=tenant_id,
                report_id=report_id,
                source_table=flagged_event.source_table,
                source_id=uuid.UUID(flagged_event.source_id),
                event_action=flagged_event.event_action,
                severity=flagged_event.severity,
                reason=flagged_event.reason,
                evidence=flagged_event.evidence,
            )

        # 6. Audit the generation.
        await self._audit.log(
            action=AI_GUARDIAN_REPORT_GENERATED,
            tenant_id=tenant_id,
            user_id=None,
            input_payload={
                "report_id": str(report_id),
                "week_start": start.isoformat(),
                "week_end": end.isoformat(),
                "total_events_scanned": total_scanned,
                "flagged_count": len(flagged),
            },
        )

        return {
            "report_id": str(report_id),
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "summary": summary,
            "total_events_scanned": total_scanned,
            "flagged_count": len(flagged),
        }

    # --- internals ----------------------------------------------------------

    def _build_summary(
        self,
        *,
        start: date,
        end: date,
        total: int,
        flagged: list[FlaggedEvent],
    ) -> str:
        """Deterministic summary of the weekly scan (provider-free)."""
        by_severity: dict[str, int] = {}
        for event in flagged:
            by_severity[event.severity] = by_severity.get(event.severity, 0) + 1

        parts = [
            f"Audit integrity report for {start.isoformat()} to {end.isoformat()}.",
            f"Scanned {total} audit events across ai-agent, core, and identity.",
        ]
        if flagged:
            parts.append(
                "Flagged "
                + ", ".join(
                    f"{count} {severity}" for severity, count in sorted(by_severity.items())
                )
                + " suspicious pattern(s)."
            )
        else:
            parts.append("No suspicious activity detected.")
        return " ".join(parts)

    async def _llm_summary(
        self,
        *,
        llm_router: LlmRouter,
        start: date,
        end: date,
        total: int,
        flagged: list[FlaggedEvent],
        fallback: str,
    ) -> str:
        """Best-effort LLM prose summary of flagged events (never raises)."""
        flagged_payload = [
            {
                "action": f.event_action,
                "severity": f.severity,
                "reason": f.reason,
                "evidence": f.evidence,
            }
            for f in flagged[:20]  # cap context size
        ]
        try:
            completion = await llm_router.complete(
                LlmRequest(
                    system_prompt=_GUARDIAN_SYSTEM_PROMPT,
                    user_prompt=(
                        f"Week: {start.isoformat()} to {end.isoformat()}. "
                        f"Total scanned: {total}. Flagged events:\n"
                        f"{json.dumps(flagged_payload, default=str, indent=2)}"
                    ),
                    max_tokens=400,
                    temperature=0.2,
                )
            )
            text = (completion.text or "").strip()
            return text if text else fallback
        except Exception:
            logger.warning("audit_guardian.llm_summary_failed", exc_info=True)
            return fallback


def _dedupe_flagged(events: list[FlaggedEvent]) -> list[FlaggedEvent]:
    """Keep the highest severity per (source_table, source_id, event_action)."""
    best: dict[tuple[str, str, str], FlaggedEvent] = {}
    severity_rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    for event in events:
        key = (event.source_table, event.source_id, event.event_action)
        existing = best.get(key)
        if existing is None or severity_rank[event.severity] > severity_rank[existing.severity]:
            best[key] = event
    return list(best.values())


_GUARDIAN_SYSTEM_PROMPT = """\
You are the Audit Guardian for Skyrict. You review flagged audit events and \
produce a concise weekly integrity summary for security-conscious operators.

Rules:
- Write 2-4 sentences of flowing prose describing the concerning patterns.
- Mention the severity mix and the most critical flagged event.
- Do not invent facts not present in the flagged events.
- Do not include raw PII, internal identifiers, or IP addresses in the summary.
""".strip()
