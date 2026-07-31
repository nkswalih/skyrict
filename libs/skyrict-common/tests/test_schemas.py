from __future__ import annotations

from skyrict_common.schemas import (
    ErrorDetail,
    ErrorResponse,
    ListResponse,
    PaginationMeta,
    ResponseEnvelope,
)


class TestPaginationMeta:
    def test_create_calculates_total_pages(self):
        meta = PaginationMeta.create(total=95, page=1, page_size=20)
        assert meta.total_pages == 5
        assert meta.total == 95
        assert meta.page == 1
        assert meta.page_size == 20

    def test_zero_items_yields_zero_pages(self):
        meta = PaginationMeta.create(total=0, page=1, page_size=20)
        assert meta.total_pages == 0


class TestResponseEnvelope:
    def test_default_success(self):
        env = ResponseEnvelope()
        assert env.success is True
        assert env.data is None
        assert env.message is None
        assert env.meta is None

    def test_with_data(self):
        env = ResponseEnvelope(data={"key": "value"}, message="ok")
        assert env.data == {"key": "value"}
        assert env.message == "ok"


class TestErrorResponse:
    def test_default_fields(self):
        err = ErrorResponse(error=ErrorDetail(message="nope", code="ERR"))
        assert err.success is False
        assert err.error.message == "nope"
        assert err.error.code == "ERR"
        assert err.request_id is None


class TestListResponse:
    def test_empty_list(self):
        meta = PaginationMeta.create(total=0, page=1, page_size=20)
        resp = ListResponse(data=[], meta=meta)
        assert resp.data == []
        assert resp.meta.total == 0
