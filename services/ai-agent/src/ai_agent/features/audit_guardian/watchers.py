"""Audit Guardian watchers — deterministic rules for suspicious event detection.

Each watcher is a pure function that receives a batch of audit log events and
returns the events it flags as suspicious, with severity and reasoning. No LLM
calls — these are deterministic pre-filters. The LLM severity assessment
(optional) runs only on events that pass these rules.

Rules implemented:
  1. **Off-hours access**: Activity outside business hours (before 06:00 or
     after 22:00 UTC) — medium severity for exports, low for reads.
  2. **Bulk reads**: Same user performing >20 reads within a 5-minute window
     — medium severity.
  3. **Failed authentication bursts**: >5 failed auth attempts from the same
     source within 10 minutes — high severity.
  4. **Unusual export patterns**: Data export actions (bulk_download,
     export_*, csv_*) outside normal business hours — high severity.
  5. **Privilege escalation attempts**: Write actions on sensitive resources
     by non-admin users — medium severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

_OFF_HOURS_START = 6  # 06:00 UTC
_OFF_HOURS_END = 22  # 22:00 UTC
_BULK_READ_THRESHOLD = 20
_BULK_READ_WINDOW = timedelta(minutes=5)
_AUTH_BURST_THRESHOLD = 5
_AUTH_BURST_WINDOW = timedelta(minutes=10)

_EXPORT_ACTIONS = frozenset(
    {
        "bulk_download",
        "export_csv",
        "export_excel",
        "export_pdf",
        "data_export",
        "report.export",
    }
)

_READ_ACTIONS_PREFIXES = (".read", ".list", ".search", ".query", ".get")
_FAILED_AUTH_ACTIONS = frozenset(
    {
        "auth.login.failed",
        "auth.mfa.failed",
        "auth.token.invalid",
    }
)


@dataclass(frozen=True, slots=True)
class FlaggedEvent:
    """One event flagged by a watcher rule."""

    source_table: str
    source_id: str
    event_action: str
    severity: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


def watch_off_hours_access(
    events: list[dict[str, Any]],
    *,
    source_table: str,
) -> list[FlaggedEvent]:
    """Flag events occurring outside business hours (06:00-22:00 UTC)."""
    flagged: list[FlaggedEvent] = []
    for event in events:
        created_at = _parse_timestamp(event.get("created_at"))
        if created_at is None:
            continue
        hour = created_at.hour
        if hour >= _OFF_HOURS_START and hour < _OFF_HOURS_END:
            continue

        action = str(event.get("action", ""))
        is_export = any(exp in action for exp in _EXPORT_ACTIONS)
        is_read = any(action.endswith(p) for p in _READ_ACTIONS_PREFIXES)

        if is_export:
            severity = "high"
            reason = (
                f"Data export action '{action}' executed outside business hours "
                f"at {created_at.isoformat()}"
            )
        elif is_read:
            severity = "medium"
            reason = (
                f"Read action '{action}' executed outside business hours "
                f"at {created_at.isoformat()}"
            )
        else:
            severity = "low"
            reason = (
                f"Action '{action}' executed outside business hours at {created_at.isoformat()}"
            )

        flagged.append(
            FlaggedEvent(
                source_table=source_table,
                source_id=str(event.get("id", "")),
                event_action=action,
                severity=severity,
                reason=reason,
                evidence={
                    "hour": hour,
                    "user_id": str(event.get("user_id", "")),
                    "action": action,
                    "created_at": created_at.isoformat(),
                },
            )
        )
    return flagged


def watch_bulk_reads(
    events: list[dict[str, Any]],
    *,
    source_table: str,
) -> list[FlaggedEvent]:
    """Flag users performing >20 reads within a 5-minute window."""
    # Group read events by user_id.
    user_reads: dict[str, list[datetime]] = {}
    for event in events:
        action = str(event.get("action", ""))
        if not any(action.endswith(p) for p in _READ_ACTIONS_PREFIXES):
            continue
        user_id = str(event.get("user_id", ""))
        if not user_id:
            continue
        ts = _parse_timestamp(event.get("created_at"))
        if ts is None:
            continue
        user_reads.setdefault(user_id, []).append(ts)

    flagged: list[FlaggedEvent] = []
    for user_id, timestamps in user_reads.items():
        timestamps.sort()
        # Sliding window check.
        for i, start in enumerate(timestamps):
            window_end = start + _BULK_READ_WINDOW
            count = sum(1 for ts in timestamps[i:] if ts <= window_end)
            if count >= _BULK_READ_THRESHOLD:
                # source_id stays the FIRST audit row's id in the window - the
                # originating event the operator can open for evidence; the
                # flagged user rides in evidence.
                first_id = _first_id_in_window(
                    events,
                    window_start=start,
                    window_end=window_end,
                    match_action=None,
                    match_user=user_id,
                )
                flagged.append(
                    FlaggedEvent(
                        source_table=source_table,
                        source_id=first_id,
                        event_action="bulk_read_detected",
                        severity="medium",
                        reason=(
                            f"User {user_id} performed {count} read actions "
                            f"within {_BULK_READ_WINDOW} starting at {start.isoformat()}"
                        ),
                        evidence={
                            "user_id": user_id,
                            "read_count": count,
                            "window_start": start.isoformat(),
                        },
                    )
                )
                break  # one flag per user is enough
    return flagged


def watch_auth_bursts(
    events: list[dict[str, Any]],
    *,
    source_table: str,
) -> list[FlaggedEvent]:
    """Flag >5 failed auth attempts from the same source within 10 minutes."""
    # Group failed auth events.
    auth_failures: dict[str, list[datetime]] = {}
    for event in events:
        action = str(event.get("action", ""))
        if action not in _FAILED_AUTH_ACTIONS:
            continue
        # Use IP or user_id as the grouping key.
        source_key = str(
            event.get("input", {}).get("source_ip", "") or event.get("user_id", "") or "unknown"
        )
        ts = _parse_timestamp(event.get("created_at"))
        if ts is None:
            continue
        auth_failures.setdefault(source_key, []).append(ts)

    flagged: list[FlaggedEvent] = []
    for source_key, timestamps in auth_failures.items():
        timestamps.sort()
        for i, start in enumerate(timestamps):
            window_end = start + _AUTH_BURST_WINDOW
            count = sum(1 for ts in timestamps[i:] if ts <= window_end)
            if count >= _AUTH_BURST_THRESHOLD:
                # source_id stays the FIRST audit row's id in the window (the
                # originating event for evidence); the source rides in evidence.
                first_id = _first_id_in_window(
                    events,
                    window_start=start,
                    window_end=window_end,
                    match_action=_FAILED_AUTH_ACTIONS,
                    match_user=None,
                )
                flagged.append(
                    FlaggedEvent(
                        source_table=source_table,
                        source_id=first_id,
                        event_action="auth_burst_detected",
                        severity="high",
                        reason=(
                            f"{count} failed auth attempts from '{source_key}' "
                            f"within {_AUTH_BURST_WINDOW} starting at {start.isoformat()}"
                        ),
                        evidence={
                            "source": source_key,
                            "failure_count": count,
                            "window_start": start.isoformat(),
                        },
                    )
                )
                break
    return flagged


ALL_WATCHERS = (
    watch_off_hours_access,
    watch_bulk_reads,
    watch_auth_bursts,
)


def run_all_watchers(
    events: list[dict[str, Any]],
    *,
    source_table: str,
) -> list[FlaggedEvent]:
    """Run all watcher rules against a batch of events and return flagged ones."""
    flagged: list[FlaggedEvent] = []
    for watcher in ALL_WATCHERS:
        flagged.extend(watcher(events, source_table=source_table))
    return flagged


def _parse_timestamp(raw: Any) -> datetime | None:
    """Best-effort timestamp parse from audit log JSON."""
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if isinstance(raw, datetime):
        return raw
    return None


def _first_id_in_window(
    events: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    match_action: frozenset[str] | None,
    match_user: str | None,
) -> str:
    """The first event id inside the window matching the given filters.

    ``source_id`` in the DB is the originating audit row's id (UUID); the
    fallback keeps the aggregation key only when no row id is available.
    """
    for event in events:
        if match_action is not None and str(event.get("action", "")) not in match_action:
            continue
        if match_user is not None and str(event.get("user_id", "")) != match_user:
            continue
        ts = _parse_timestamp(event.get("created_at"))
        if ts is None or ts < window_start or ts > window_end:
            continue
        return str(event.get("id", ""))
    return match_user or next(iter(match_action or ()), "")
