"""Anomaly detection rules - deterministic checks over recent movements.

Each rule takes the fetched movement window plus reference data and returns
zero or more :class:`AnomalyFinding` objects. Rules are pure functions so
they are exhaustively unit-testable; the service only orchestrates.

All eight rules from spec 4.2:
1. detect_sudden_drops         - >50% drop in 48h                     HIGH
2. detect_unusual_adjustments  - adjustment > 3x stddev               MEDIUM
3. detect_duplicate_refs       - same ref_id twice                    HIGH
4. detect_transfer_without_receipt - transfer source without dest     HIGH
5. detect_off_hours            - movement between 00:00-06:00         LOW
6. detect_reorder_alert_ignored - below reorder for 30+ days          MEDIUM
7. detect_negative_adjustment_spike - many negative adjustments       MEDIUM
8. detect_ledger_mismatch      - qty_on_hand != ledger sum            CRITICAL
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from ai_agent.features.nl_query.gateway import MovementRow, StockLevelRow

# Spec 4.2 thresholds.
_DROP_WINDOW_HOURS = 48
_DROP_RATIO = Decimal("0.5")  # >50% drop within the window is High severity.
_ADJUSTMENT_SIGMA_FACTOR = Decimal(3)  # >3x standard deviation is Medium.
_MIN_ADJUSTMENT_BASELINE = 4  # stddev over fewer adjustments is noise
_OFF_HOUR_START = 0  # local-hour window [0, 6) counts as off-hours.
_OFF_HOUR_END = 6
_REORDER_IGNORED_DAYS = 30  # below reorder for 30+ days is Medium.
_NEGATIVE_SPIKE_WINDOW_DAYS = 7  # 7-day window for frequency analysis.
_NEGATIVE_SPIKE_THRESHOLD = 5  # more than 5 negative adjustments in window.
_SEVERITIES = {"low", "medium", "high", "critical"}

# Movements that feed qty_reserved and are EXCLUDED from qty_on_hand
# (mirrors core's canonical stock-level definition).
_RESERVATION_TYPES = frozenset({"reservation", "release"})


@dataclass(frozen=True, slots=True)
class AnomalyFinding:
    """One detection result, ready for persistence."""

    anomaly_type: str
    severity: str
    title: str
    description: str
    affected_product_id: uuid.UUID | None
    affected_warehouse_id: uuid.UUID | None
    related_movement_ids: list[uuid.UUID] = field(default_factory=list)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def detect_all(
    movements: list[MovementRow],
    stock_levels: list[StockLevelRow] | None = None,
) -> list[AnomalyFinding]:
    """Run every v1 rule over the movement window.

    *stock_levels* is required for the ledger_mismatch rule; when None that
    rule is skipped (gateway may not have fetched levels).
    """
    findings: list[AnomalyFinding] = []
    findings.extend(detect_sudden_drops(movements))
    findings.extend(detect_unusual_adjustments(movements))
    findings.extend(detect_duplicate_refs(movements))
    findings.extend(detect_transfer_without_receipt(movements))
    findings.extend(detect_off_hours(movements))
    findings.extend(detect_reorder_alert_ignored(movements))
    findings.extend(detect_negative_adjustment_spike(movements))
    if stock_levels is not None:
        findings.extend(detect_ledger_mismatch(movements, stock_levels))
    return findings


def detect_sudden_drops(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """>50% of a product's recent inflow vanished via issues/adjustments in 48h."""
    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=_DROP_WINDOW_HOURS)
    by_product: dict[uuid.UUID, list[MovementRow]] = defaultdict(list)
    for m in movements:
        if (
            m.movement_type in ("receipt", "issue", "adjustment")
            and _as_utc(m.created_at) >= cutoff
        ):
            by_product[m.product_id].append(m)

    findings: list[AnomalyFinding] = []
    for product_id, rows in by_product.items():
        inflow = sum((m.qty for m in rows if m.qty > 0), Decimal(0))
        outflow = abs(sum((m.qty for m in rows if m.qty < 0), Decimal(0)))
        if inflow <= 0 or outflow / inflow <= _DROP_RATIO:
            continue
        involved = sorted(m.id for m in rows if m.qty < 0)
        findings.append(
            AnomalyFinding(
                anomaly_type="sudden_stock_drop",
                severity="high",
                title=f"Sudden stock drop for product {product_id}",
                description=(
                    f"{outflow} units left against {inflow} received "
                    f"within {_DROP_WINDOW_HOURS} hours."
                ),
                affected_product_id=product_id,
                affected_warehouse_id=rows[-1].warehouse_id,
                related_movement_ids=involved,
            )
        )
    return findings


def detect_unusual_adjustments(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Adjustments larger than 3x the stddev of the OTHER adjustments.

    The baseline is computed leave-one-out: a single huge outlier inflates
    its own baseline so much that it could otherwise never exceed
    mean + 3*sigma (the max achievable z-score in a sample of n is
    (n-1)/sqrt(n) < 3). Comparing each adjustment against the statistics of
    the remaining window is the statistically sound reading of the spec's
    ">3x standard deviation" rule (spec §4.2).
    """
    adjustment_rows = [m for m in movements if m.movement_type == "adjustment"]
    if len(adjustment_rows) < _MIN_ADJUSTMENT_BASELINE:
        return []  # stddev over a handful of points is noise

    findings: list[AnomalyFinding] = []
    for i, candidate in enumerate(adjustment_rows):
        others = [abs(m.qty) for j, m in enumerate(adjustment_rows) if j != i]
        if len(others) < _MIN_ADJUSTMENT_BASELINE - 1:
            continue
        mean = sum(others, Decimal(0)) / len(others)
        sigma = Decimal(str(statistics.stdev(float(a) for a in others)))
        threshold = mean + sigma * _ADJUSTMENT_SIGMA_FACTOR
        size = abs(candidate.qty)
        if size <= threshold:
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="unusual_adjustment_size",
                severity="medium",
                title=f"Unusual adjustment size ({size} units)",
                description=(
                    f"Adjustment of {size} exceeds {threshold:.2f} "
                    f"(peer mean {mean:.2f} + {_ADJUSTMENT_SIGMA_FACTOR}x std dev)."
                ),
                affected_product_id=candidate.product_id,
                affected_warehouse_id=candidate.warehouse_id,
                related_movement_ids=[candidate.id],
            )
        )
    return findings


def detect_duplicate_refs(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Same ref_id posted more than once for the same warehouse (spec: High)."""
    refs_by_wh: dict[tuple[uuid.UUID, str], list[MovementRow]] = defaultdict(list)
    for m in movements:
        if m.ref_id:
            refs_by_wh[(m.warehouse_id, str(m.ref_id))].append(m)

    findings: list[AnomalyFinding] = []
    for (_wh, ref_id), rows in refs_by_wh.items():
        if len(rows) < 2:
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="duplicate_movement_ref",
                severity="high",
                title=f"Duplicate movement reference '{ref_id}'",
                description=(
                    f"Reference '{ref_id}' appears {len(rows)} times at warehouse "
                    f"{rows[0].warehouse_id} - possible double-posting."
                ),
                affected_product_id=rows[0].product_id,
                affected_warehouse_id=rows[0].warehouse_id,
                related_movement_ids=[m.id for m in rows],
            )
        )
    return findings


def detect_off_hours(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Movements between midnight and early morning are Low severity."""
    findings: list[AnomalyFinding] = []
    for m in movements:
        hour = _as_utc(m.created_at).hour
        if not (_OFF_HOUR_START <= hour < _OFF_HOUR_END):
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="off_hours_movement",
                severity="low",
                title=f"Off-hours movement ({_as_utc(m.created_at):%H:%M} UTC)",
                description=(
                    f"{m.movement_type} of {m.qty} recorded outside business hours "
                    f"at warehouse {m.warehouse_id}."
                ),
                affected_product_id=m.product_id,
                affected_warehouse_id=m.warehouse_id,
                related_movement_ids=[m.id],
            )
        )
    return findings


def detect_transfer_without_receipt(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Transfer source (issue) without a paired receipt at the destination.

    For each transfer, core creates two movements: an issue at the source
    warehouse and a receipt at the destination, linked by the same ref_id.
    A mismatch (issue exists, receipt missing) is High severity (spec 4.2).
    """
    transfers_by_ref: dict[str, list[MovementRow]] = defaultdict(list)
    for m in movements:
        if m.movement_type == "transfer" and m.ref_id:
            transfers_by_ref[m.ref_id].append(m)

    findings: list[AnomalyFinding] = []
    for ref_id, rows in transfers_by_ref.items():
        if len(rows) < 2:
            # Only one side of the transfer exists — possible mismatch.
            only = rows[0]
            findings.append(
                AnomalyFinding(
                    anomaly_type="transfer_without_receipt",
                    severity="high",
                    title=f"Transfer '{ref_id}' missing paired movement",
                    description=(
                        f"Transfer ref '{ref_id}' has only {only.movement_type} "
                        f"({only.qty} units) at warehouse {only.warehouse_id} — "
                        f"the counter-movement appears missing."
                    ),
                    affected_product_id=only.product_id,
                    affected_warehouse_id=only.warehouse_id,
                    related_movement_ids=[only.id],
                )
            )
    return findings


def detect_reorder_alert_ignored(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Products that have been below reorder point for 30+ days (spec 4.2: Medium).

    This rule examines movement patterns: if a product has had issues (outflow)
    but no receipts (inflow) for 30+ days, it is effectively ignored at reorder.
    """
    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(days=_REORDER_IGNORED_DAYS)

    # Group issue-only products (products with only outflow, no inflow in window).
    by_product: dict[uuid.UUID, list[MovementRow]] = defaultdict(list)
    for m in movements:
        if m.movement_type in ("issue", "receipt") and _as_utc(m.created_at) >= cutoff:
            by_product[m.product_id].append(m)

    findings: list[AnomalyFinding] = []
    for product_id, rows in by_product.items():
        receipts = [m for m in rows if m.movement_type == "receipt"]
        issues = [m for m in rows if m.movement_type == "issue"]
        if receipts or not issues:
            continue  # has inflow or no outflow — not "ignored"
        oldest_issue = min(_as_utc(m.created_at) for m in issues)
        days_without_receipt = (now - oldest_issue).days
        if days_without_receipt < _REORDER_IGNORED_DAYS:
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="reorder_alert_ignored",
                severity="medium",
                title=f"Reorder alert ignored for {days_without_receipt} days",
                description=(
                    f"Product {product_id} has had {len(issues)} issue(s) but no "
                    f"receipts for {days_without_receipt} days — reorder appears ignored."
                ),
                affected_product_id=product_id,
                affected_warehouse_id=rows[-1].warehouse_id,
                related_movement_ids=[m.id for m in issues],
            )
        )
    return findings


def detect_negative_adjustment_spike(movements: list[MovementRow]) -> list[AnomalyFinding]:
    """Multiple negative adjustments in a short window (spec 4.2: Medium).

    Flags when more than 5 negative adjustments occur within 7 days for the
    same product+warehouse, suggesting a systematic data-entry or theft issue.
    """
    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(days=_NEGATIVE_SPIKE_WINDOW_DAYS)

    negative_adjustments = [
        m
        for m in movements
        if m.movement_type == "adjustment" and m.qty < 0 and _as_utc(m.created_at) >= cutoff
    ]

    by_pair: dict[tuple[uuid.UUID, uuid.UUID], list[MovementRow]] = defaultdict(list)
    for m in negative_adjustments:
        by_pair[(m.product_id, m.warehouse_id)].append(m)

    findings: list[AnomalyFinding] = []
    for (product_id, warehouse_id), rows in by_pair.items():
        if len(rows) <= _NEGATIVE_SPIKE_THRESHOLD:
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="negative_adjustment_spike",
                severity="medium",
                title=f"Negative adjustment spike ({len(rows)} in {_NEGATIVE_SPIKE_WINDOW_DAYS}d)",
                description=(
                    f"{len(rows)} negative adjustments detected for product "
                    f"{product_id} at warehouse {warehouse_id} within "
                    f"{_NEGATIVE_SPIKE_WINDOW_DAYS} days — possible systematic issue."
                ),
                affected_product_id=product_id,
                affected_warehouse_id=warehouse_id,
                related_movement_ids=[m.id for m in rows],
            )
        )
    return findings


def detect_ledger_mismatch(
    movements: list[MovementRow],
    stock_levels: list[StockLevelRow],
) -> list[AnomalyFinding]:
    """qty_on_hand does not match ledger sum (spec 4.2: CRITICAL).

    Compares the materialized stock_level.qty_on_hand against the sum of
    all signed movement quantities for each product+warehouse pair.
    Reservation/release movements feed qty_reserved, not qty_on_hand, so
    they are excluded from the ledger sum (matching core's definition).
    """
    # Compute ledger sum from movements (reservations/releases excluded).
    ledger: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = defaultdict(lambda: Decimal(0))
    for m in movements:
        if m.movement_type in _RESERVATION_TYPES:
            continue
        key = (m.product_id, m.warehouse_id)
        ledger[key] += m.qty

    # Compare against materialized stock levels.
    findings: list[AnomalyFinding] = []
    for level in stock_levels:
        key = (level.product_id, level.warehouse_id)
        ledger_sum = ledger.get(key, Decimal(0))
        if ledger_sum == level.qty_on_hand:
            continue
        delta = level.qty_on_hand - ledger_sum
        findings.append(
            AnomalyFinding(
                anomaly_type="ledger_mismatch",
                severity="critical",
                title=f"Ledger mismatch: delta of {delta} units",
                description=(
                    f"Stock level shows {level.qty_on_hand} on hand but the "
                    f"ledger sums to {ledger_sum} for product {level.product_id} "
                    f"at warehouse {level.warehouse_id} (delta: {delta})."
                ),
                affected_product_id=level.product_id,
                affected_warehouse_id=level.warehouse_id,
            )
        )
    return findings


def valid_severity(severity: str) -> bool:
    """True when the value is one of the spec 4.2 severities."""
    return severity in _SEVERITIES
