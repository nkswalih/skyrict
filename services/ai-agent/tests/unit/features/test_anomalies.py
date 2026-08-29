"""Unit tests for anomaly rules and the scan/review service logic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_agent.features.anomalies.rules import (
    detect_all,
    detect_duplicate_refs,
    detect_off_hours,
    detect_sudden_drops,
    detect_unusual_adjustments,
)
from ai_agent.features.anomalies.service import AnomalyService
from ai_agent.features.nl_query.gateway import MovementRow

TENANT_ID = uuid.uuid4()
PRODUCT_ID = uuid.uuid4()
WAREHOUSE_ID = uuid.uuid4()


def _movement(
    *,
    movement_type: str = "receipt",
    qty: Decimal = Decimal(10),
    hours_ago: float = 1.0,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    ref_id: str | None = None,
    hour: int | None = None,
) -> MovementRow:
    created = datetime.now(tz=UTC) - timedelta(hours=hours_ago)
    if hour is not None:
        created = created.replace(hour=hour, minute=0, second=0, microsecond=0)
    return MovementRow(
        id=uuid.uuid4(),
        product_id=product_id or PRODUCT_ID,
        warehouse_id=warehouse_id or WAREHOUSE_ID,
        movement_type=movement_type,
        qty=qty,
        created_at=created,
        ref_id=ref_id,
    )


class TestSuddenDrops:
    def test_high_drop_within_window_flags(self) -> None:
        movements = [
            _movement(movement_type="receipt", qty=Decimal(100), hours_ago=10),
            _movement(movement_type="issue", qty=Decimal(-60), hours_ago=5),
        ]
        findings = detect_sudden_drops(movements)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "high"
        assert f.affected_product_id == PRODUCT_ID
        assert len(f.related_movement_ids) == 1

    def test_small_outflow_not_flagged(self) -> None:
        movements = [
            _movement(movement_type="receipt", qty=Decimal(100), hours_ago=10),
            _movement(movement_type="issue", qty=Decimal(-30), hours_ago=5),
        ]
        assert detect_sudden_drops(movements) == []

    def test_no_inflow_means_no_ratio_to_flag(self) -> None:
        movements = [_movement(movement_type="issue", qty=Decimal(-90), hours_ago=2)]
        assert detect_sudden_drops(movements) == []


class TestUnusualAdjustments:
    def test_statistical_outlier_adjustment_flags(self) -> None:
        movements = [
            _movement(movement_type="adjustment", qty=Decimal(2), ref_id=None) for _ in range(6)
        ] + [
            _movement(movement_type="adjustment", qty=Decimal(-500), ref_id=None),
            _movement(movement_type="receipt", qty=Decimal(3)),
        ]
        findings = detect_unusual_adjustments(movements)
        assert len(findings) == 1
        assert findings[0].anomaly_type == "unusual_adjustment_size"
        assert findings[0].severity == "medium"

    def test_uniform_adjustments_do_not_flag(self) -> None:
        movements = [
            _movement(movement_type="adjustment", qty=Decimal(5), ref_id=None) for _ in range(6)
        ]
        assert detect_unusual_adjustments(movements) == []

    def test_few_adjustments_are_skipped_as_noise(self) -> None:
        movements = [
            _movement(movement_type="adjustment", qty=Decimal(9999), ref_id=None),
            _movement(movement_type="adjustment", qty=Decimal(-9998), ref_id=None),
        ]
        assert detect_unusual_adjustments(movements) == []


class TestDuplicateRefs:
    def test_same_ref_twice_flags_once_with_both_ids(self) -> None:
        a, b = _movement(ref_id="PO-77"), _movement(ref_id="PO-77")
        findings = detect_duplicate_refs([a, b])
        assert len(findings) == 1
        assert findings[0].related_movement_ids == [a.id, b.id]
        assert findings[0].severity == "high"

    def test_distinct_refs_do_not_flag(self) -> None:
        assert detect_duplicate_refs([_movement(ref_id="A"), _movement(ref_id="B")]) == []

    def test_null_refs_never_flag(self) -> None:
        assert detect_duplicate_refs([_movement(ref_id=None), _movement(ref_id=None)]) == []


class TestOffHours:
    def test_movement_between_midnight_and_06_utc_flags_low(self) -> None:
        # Deterministic: construct explicitly instead of relying on wall clock.
        early = MovementRow(
            id=uuid.uuid4(),
            product_id=PRODUCT_ID,
            warehouse_id=WAREHOUSE_ID,
            movement_type="adjustment",
            qty=Decimal(1),
            created_at=datetime.now(tz=UTC).replace(hour=2, minute=0, second=0),
            ref_id=None,
        )
        findings = detect_off_hours([early])
        assert len(findings) == 1
        assert findings[0].severity == "low"

    def test_business_hours_do_not_flag(self) -> None:
        midday = MovementRow(
            id=uuid.uuid4(),
            product_id=PRODUCT_ID,
            warehouse_id=WAREHOUSE_ID,
            movement_type="receipt",
            qty=Decimal(1),
            created_at=datetime.now(tz=UTC).replace(hour=14, minute=0, second=0),
            ref_id=None,
        )
        assert detect_off_hours([midday]) == []


class TestDetectAllComposition:
    def test_all_rules_run_and_findings_sorted_by_rule(self) -> None:
        dup_a, dup_b = _movement(ref_id="PO-DUP"), _movement(ref_id="PO-DUP")
        movements = [
            _movement(movement_type="receipt", qty=Decimal(100), hours_ago=20),
            _movement(movement_type="issue", qty=Decimal(-70), hours_ago=4),
            dup_a,
            dup_b,
        ]
        types = {f.anomaly_type for f in detect_all(movements)}
        assert {"sudden_stock_drop", "duplicate_movement_ref"} <= types


class FakeGateway:
    def __init__(self, movements: list[MovementRow]) -> None:
        self.movements = movements

    async def list_movements(
        self, *, product_id=None, warehouse_id=None, movement_type=None
    ) -> list[MovementRow]:
        return self.movements

    async def get_stock_levels(self, *, product_id=None, warehouse_id=None):
        return []


class FakeAnomalies:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.open_scopes: set[tuple[str, uuid.UUID | None, uuid.UUID | None]] = set()

    async def has_open(
        self,
        *,
        tenant_id: uuid.UUID,
        anomaly_type: str,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> bool:
        return (anomaly_type, product_id, warehouse_id) in self.open_scopes

    async def create(self, **kwargs):
        row = SimpleNamespace(**kwargs, id=uuid.uuid4())
        self.created.append(kwargs)
        return row


class FakeAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def log(self, *, action, **kwargs):
        self.actions.append(action)


def _make_service(movements):
    async def factory():
        return FakeGateway(movements)

    repo, audit = FakeAnomalies(), FakeAudit()
    service = AnomalyService(gateway_factory=factory, anomalies=repo, audit=audit)
    return service, repo, audit


class TestScan:
    async def test_creates_rows_and_audit_events(self) -> None:
        base = datetime.now(tz=UTC).replace(hour=14, minute=0, second=0, microsecond=0)
        movements = [
            MovementRow(
                id=uuid.uuid4(),
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                movement_type="receipt",
                qty=Decimal(100),
                created_at=base,
                ref_id=None,
            ),
            MovementRow(
                id=uuid.uuid4(),
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                movement_type="issue",
                qty=Decimal(-80),
                created_at=base + timedelta(hours=2),
                ref_id=None,
            ),
        ]
        service, repo, audit = _make_service(movements)

        report = await service.run_scan(tenant_id=TENANT_ID)

        assert report.detected == 1
        assert repo.created[0]["anomaly_type"] == "sudden_stock_drop"
        assert any(a.endswith("anomaly.detected") for a in audit.actions)

    async def test_open_anomaly_of_same_type_is_skipped(self) -> None:
        base = datetime.now(tz=UTC).replace(hour=14, minute=0, second=0, microsecond=0)
        movements = [
            MovementRow(
                id=uuid.uuid4(),
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                movement_type="receipt",
                qty=Decimal(100),
                created_at=base,
                ref_id=None,
            ),
            MovementRow(
                id=uuid.uuid4(),
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                movement_type="issue",
                qty=Decimal(-80),
                created_at=base + timedelta(hours=2),
                ref_id=None,
            ),
        ]
        service, repo, _audit = _make_service(movements)
        repo.open_scopes.add(
            ("sudden_stock_drop", movements[1].product_id, movements[1].warehouse_id)
        )

        report = await service.run_scan(tenant_id=TENANT_ID)

        assert report.detected == 0
        assert report.duplicates_skipped == 1
        assert repo.created == []


class TestReview:
    def _row(self, status: str):
        return SimpleNamespace(id=uuid.uuid4(), status=status)

    async def test_resolve_open_row_transitions(self) -> None:
        service, _repo, audit = _make_service([])
        row = self._row("open")

        captured = {}

        async def fake_get(*, tenant_id, anomaly_id):
            return row

        async def fake_record(**kwargs):
            captured.update(kwargs)
            kwargs["row"].status = kwargs["status"]
            return kwargs["row"]

        service._anomalies.get = fake_get
        service._anomalies.record_review = fake_record

        await service.review(
            tenant_id=TENANT_ID,
            user_id=uuid.uuid4(),
            anomaly_id=row.id,
            decision="resolved",
            note="fixed",
        )

        assert captured["status"] == "resolved"
        assert any(a.endswith("anomaly.resolved") for a in audit.actions)

    async def test_dismiss_open_row_allowed(self) -> None:
        service, _repo, audit = _make_service([])

        async def fake_get(*, tenant_id, anomaly_id):
            return self._row("open")

        service._anomalies.get = fake_get

        async def fake_record(**kwargs):
            kwargs["row"].status = kwargs["status"]
            return kwargs["row"]

        service._anomalies.record_review = fake_record
        await service.review(
            tenant_id=TENANT_ID,
            user_id=uuid.uuid4(),
            anomaly_id=uuid.uuid4(),
            decision="dismissed",
            note=None,
        )
        assert any(a.endswith("anomaly.dismissed") for a in audit.actions)

    async def test_escalate_allows_resolved_source(self) -> None:
        service, _repo, audit = _make_service([])
        row = self._row("resolved")
        seen = {}

        async def fake_get(*, tenant_id, anomaly_id):
            return row

        async def fake_record(**kwargs):
            seen.update(kwargs)
            return kwargs["row"]

        service._anomalies.get = fake_get
        service._anomalies.record_review = fake_record

        await service.review(
            tenant_id=TENANT_ID,
            user_id=uuid.uuid4(),
            anomaly_id=row.id,
            decision="escalated",
            note="needs admin",
        )
        assert seen["status"] == "escalated"
        # Regression: escalation must audit as its own event, never as a
        # dismissal (the pre-dedicated-constant bug).
        assert "ai.anomaly.escalated" in audit.actions
        assert all(a != "ai.anomaly.dismissed" for a in audit.actions)

    async def test_invalid_decision_raises(self) -> None:

        service, _repo, _audit = _make_service([])

        async def fake_get(*, tenant_id, anomaly_id):
            return self._row("open")

        service._anomalies.get = fake_get

        with pytest.raises(ValueError, match="invalid review decision"):
            await service.review(
                tenant_id=TENANT_ID,
                user_id=uuid.uuid4(),
                anomaly_id=uuid.uuid4(),
                decision="nonsense",
                note=None,
            )

    async def test_dismissed_row_cannot_be_escalated(self) -> None:
        """Spec §4.4 workflow: escalated only from open or resolved."""
        from skyrict_common.exceptions import ConflictError

        service, _repo, _audit = _make_service([])

        async def fake_get(*, tenant_id, anomaly_id):
            return self._row("dismissed")

        service._anomalies.get = fake_get

        with pytest.raises(ConflictError):
            await service.review(
                tenant_id=TENANT_ID,
                user_id=uuid.uuid4(),
                anomaly_id=uuid.uuid4(),
                decision="escalated",
                note=None,
            )
