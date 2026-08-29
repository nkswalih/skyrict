"""Unit tests for ABC Pareto classification."""

from __future__ import annotations

import uuid
from decimal import Decimal

from ai_agent.features.abc.classifier import classify_abc


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TestClassifyAbc:
    def test_empty_input(self) -> None:
        assert classify_abc([]) == []

    def test_single_product_is_band_a(self) -> None:
        pid = _uuid()
        entries = classify_abc([(pid, Decimal("1000"))])
        assert len(entries) == 1
        assert entries[0].band == "A"
        assert entries[0].product_id == pid

    def test_two_products_split_a_and_b(self) -> None:
        p1, p2 = _uuid(), _uuid()
        entries = classify_abc([(p1, Decimal("800")), (p2, Decimal("200"))])
        bands = {e.product_id: e.band for e in entries}
        assert bands[p1] == "A"
        assert bands[p2] == "B"

    def test_three_products_abc_split(self) -> None:
        p1, p2, p3 = _uuid(), _uuid(), _uuid()
        entries = classify_abc([(p1, Decimal("500")), (p2, Decimal("300")), (p3, Decimal("200"))])
        bands = {e.product_id: e.band for e in entries}
        assert bands[p1] == "A"
        assert bands[p2] == "A"
        assert bands[p3] == "B"

    def test_zero_total_revenue_all_band_c(self) -> None:
        p1, p2 = _uuid(), _uuid()
        entries = classify_abc([(p1, Decimal("0")), (p2, Decimal("0"))])
        assert all(e.band == "C" for e in entries)

    def test_sorted_by_revenue_descending(self) -> None:
        p1, p2, p3 = _uuid(), _uuid(), _uuid()
        entries = classify_abc([(p3, Decimal("100")), (p1, Decimal("500")), (p2, Decimal("300"))])
        assert entries[0].product_id == p1
        assert entries[1].product_id == p2
        assert entries[2].product_id == p3

    def test_revenue_shares_sum_to_one(self) -> None:
        pids = [_uuid() for _ in range(5)]
        entries = classify_abc([(p, Decimal(str(100 * (i + 1)))) for i, p in enumerate(pids)])
        total_share = sum(e.revenue_share for e in entries)
        assert abs(total_share - Decimal("1")) < Decimal("0.001")
