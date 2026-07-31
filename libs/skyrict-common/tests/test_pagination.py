from __future__ import annotations

from skyrict_common.pagination import PaginationParams


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.page == 1
        assert p.page_size == 20
        assert p.offset == 0
        assert p.limit == 20

    def test_offset_calculation(self):
        p = PaginationParams(page=3, page_size=10)
        assert p.offset == 20

    def test_create_clamps_values(self):
        p = PaginationParams.create(page=0, page_size=200)
        assert p.page == 1
        assert p.page_size == 100

    def test_create_accepts_none(self):
        p = PaginationParams.create()
        assert p.page == 1
        assert p.page_size == 20
