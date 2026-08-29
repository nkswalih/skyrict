"""Extended anomaly detection — tests for the 4 new rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_agent.features.anomalies.rules import (
    detect_all,
    detect_ledger_mismatch,
    detect_negative_adjustment_spike,
    detect_reorder_alert_ignored,
    detect_transfer_without_receipt,
)
from ai_agent.features.nl_query.gateway import MovementRow, StockLevelRow

PRODUCT_ID = uuid.uuid4()
WAREHOUSE_ID = uuid.uuid4()
DEST_WAREHOUSE_ID = uuid.uuid4()


def _movement(
    *,
    movement_type: str = "receipt",
    qty: Decimal = Decimal(10),
    hours_ago: float = 1.0,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    ref_id: str | None = None,
) -> MovementRow:
    return MovementRow(
        id=uuid.uuid4(),
        product_id=product_id or PRODUCT_ID,
        warehouse_id=warehouse_id or WAREHOUSE_ID,
        movement_type=movement_type,
        qty=qty,
        created_at=datetime.now(tz=UTC) - timedelta(hours=hours_ago),
        ref_id=ref_id,
    )


def _stock_level(
    *,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    qty_on_hand: Decimal = Decimal(100),
) -> StockLevelRow:
    return StockLevelRow(
        product_id=product_id or PRODUCT_ID,
        warehouse_id=warehouse_id or WAREHOUSE_ID,
        qty_on_hand=qty_on_hand,
        qty_reserved=Decimal(0),
    )


class TestTransferWithoutReceipt:
    def test_single_transfer_no_pair_flags(self) -> None:
        m = _movement(movement_type="transfer", qty=Decimal(-20), ref_id="TRF-001")
        findings = detect_transfer_without_receipt([m])
        assert len(findings) == 1
        assert findings[0].anomaly_type == "transfer_without_receipt"
        assert findings[0].severity == "high"
        assert findings[0].related_movement_ids == [m.id]

    def test_paired_transfer_no_flag(self) -> None:
        source = _movement(
            movement_type="transfer", qty=Decimal(-20), ref_id="TRF-002", warehouse_id=WAREHOUSE_ID
        )
        dest = _movement(
            movement_type="transfer",
            qty=Decimal(20),
            ref_id="TRF-002",
            warehouse_id=DEST_WAREHOUSE_ID,
        )
        findings = detect_transfer_without_receipt([source, dest])
        assert len(findings) == 0

    def test_non_transfer_movements_ignored(self) -> None:
        m = _movement(movement_type="issue", qty=Decimal(-10), ref_id="PO-001")
        assert detect_transfer_without_receipt([m]) == []


class TestReorderAlertIgnored:
    def test_issue_only_below_30_days_no_flag(self) -> None:
        old_issue = _movement(movement_type="issue", qty=Decimal(-5), hours_ago=25 * 24)
        recent_issue = _movement(movement_type="issue", qty=Decimal(-3), hours_ago=24)
        findings = detect_reorder_alert_ignored([old_issue, recent_issue])
        assert len(findings) == 0

    def test_issue_with_receipt_no_flag(self) -> None:
        old_issue = _movement(movement_type="issue", qty=Decimal(-5), hours_ago=35 * 24)
        receipt = _movement(movement_type="receipt", qty=Decimal(10), hours_ago=10 * 24)
        findings = detect_reorder_alert_ignored([old_issue, receipt])
        assert len(findings) == 0

    def test_recent_issue_only_no_flag(self) -> None:
        recent = _movement(movement_type="issue", qty=Decimal(-5), hours_ago=5 * 24)
        assert detect_reorder_alert_ignored([recent]) == []

    def test_only_receipts_no_flag(self) -> None:
        r1 = _movement(movement_type="receipt", qty=Decimal(10), hours_ago=10 * 24)
        r2 = _movement(movement_type="receipt", qty=Decimal(5), hours_ago=5 * 24)
        assert detect_reorder_alert_ignored([r1, r2]) == []


class TestNegativeAdjustmentSpike:
    def test_six_negative_adjustments_in_7d_flags(self) -> None:
        negatives = [
            _movement(movement_type="adjustment", qty=Decimal(-1), hours_ago=i) for i in range(6)
        ]
        findings = detect_negative_adjustment_spike(negatives)
        assert len(findings) == 1
        assert findings[0].anomaly_type == "negative_adjustment_spike"
        assert findings[0].severity == "medium"
        assert len(findings[0].related_movement_ids) == 6

    def test_five_negative_adjustments_no_flag(self) -> None:
        negatives = [
            _movement(movement_type="adjustment", qty=Decimal(-1), hours_ago=i) for i in range(5)
        ]
        assert detect_negative_adjustment_spike(negatives) == []

    def test_positive_adjustments_not_counted(self) -> None:
        positives = [
            _movement(movement_type="adjustment", qty=Decimal(1), hours_ago=i) for i in range(7)
        ]
        assert detect_negative_adjustment_spike(positives) == []


class TestLedgerMismatch:
    def test_matching_ledger_no_flag(self) -> None:
        m1 = _movement(movement_type="receipt", qty=Decimal(10))
        m2 = _movement(movement_type="receipt", qty=Decimal(10))
        level = _stock_level(qty_on_hand=Decimal(20))
        assert detect_ledger_mismatch([m1, m2], [level]) == []

    def test_mismatch_flags_critical(self) -> None:
        m1 = _movement(movement_type="receipt", qty=Decimal(10))
        level = _stock_level(qty_on_hand=Decimal(25))
        findings = detect_ledger_mismatch([m1], [level])
        assert len(findings) == 1
        assert findings[0].anomaly_type == "ledger_mismatch"
        assert findings[0].severity == "critical"
        assert findings[0].affected_product_id == PRODUCT_ID
        assert findings[0].affected_warehouse_id == WAREHOUSE_ID

    def test_empty_movements_with_stock_level_flags(self) -> None:
        level = _stock_level(qty_on_hand=Decimal(50))
        findings = detect_ledger_mismatch([], [level])
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_reservation_release_excluded_from_ledger(self) -> None:
        reserve = _movement(movement_type="reservation", qty=Decimal(-5))
        release = _movement(movement_type="release", qty=Decimal(2))
        level = _stock_level(qty_on_hand=Decimal(0))
        assert detect_ledger_mismatch([reserve, release], [level]) == []

    def test_reservation_release_do_not_mask_real_mismatch(self) -> None:
        receipt = _movement(movement_type="receipt", qty=Decimal(10))
        reserve = _movement(movement_type="reservation", qty=Decimal(-5))
        level = _stock_level(qty_on_hand=Decimal(20))
        findings = detect_ledger_mismatch([receipt, reserve], [level])
        assert len(findings) == 1
        assert findings[0].anomaly_type == "ledger_mismatch"


class TestDetectAllWithStockLevels:
    def test_stock_levels_passed_through(self) -> None:
        m = _movement(movement_type="receipt", qty=Decimal(10))
        level = _stock_level(qty_on_hand=Decimal(999))
        findings = detect_all([m], stock_levels=[level])
        types = {f.anomaly_type for f in findings}
        assert "ledger_mismatch" in types

    def test_stock_levels_none_skips_ledger(self) -> None:
        m = _movement(movement_type="receipt", qty=Decimal(10))
        _stock_level(qty_on_hand=Decimal(999))
        findings = detect_all([m], stock_levels=None)
        types = {f.anomaly_type for f in findings}
        assert "ledger_mismatch" not in types
