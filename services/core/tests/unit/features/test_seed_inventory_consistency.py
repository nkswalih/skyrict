"""Seed-data consistency — stock levels must reconcile with the movement ledger.

The AI-agent ledger-mismatch rule (and core's recompute_stock_level) define
``qty_on_hand`` as the sum of all non-reservation/release movements. The demo
seed backs each opening-balance stock level with a balancing movement
(``_opening_balance_rows``), so the two constant tables must always reconcile
once that balancing set is applied.
"""

from __future__ import annotations

from decimal import Decimal

from core.seed_demo import (
    STOCK_LEVEL_ROWS,
    STOCK_MOVEMENT_ROWS,
    _opening_balance_rows,
)


def test_every_stock_level_reconciles_with_ledger() -> None:
    opening_rows = _opening_balance_rows(STOCK_LEVEL_ROWS, STOCK_MOVEMENT_ROWS)
    reservation_types = {"reservation", "release"}
    ledger_sum: dict[tuple[int, int], Decimal] = {}
    for mrow in [*STOCK_MOVEMENT_ROWS, *opening_rows]:
        if mrow["type"].value in reservation_types:
            continue
        key = (int(str(mrow["prod"])), int(str(mrow["wh"])))
        ledger_sum[key] = ledger_sum.get(key, Decimal(0)) + Decimal(str(mrow["qty"]))

    assert STOCK_LEVEL_ROWS, "expected at least one stock level row"
    for srow in STOCK_LEVEL_ROWS:
        key = (int(str(srow["prod"])), int(str(srow["wh"])))
        assert ledger_sum.get(key, Decimal(0)) == Decimal(str(srow["on_hand"])), (
            f"stock level {srow} does not reconcile with the movement ledger"
        )
