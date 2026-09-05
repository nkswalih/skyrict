"""Unit tests for the snapshot sync endpoint (SKY-70).

The route handler is a plain async function, so we exercise it without a
database or middleware: token-gating via ``require_sync_token`` (the shared
secret must match exactly, fails closed) and the full payload-to-response
wiring against a fake session/embedding provider.
"""

from __future__ import annotations

import uuid

import pytest
from starlette.requests import Request

from ai_agent.api.v1.routers.inventory_sync import (
    inventory_sync,
    require_sync_token,
)
from ai_agent.api.v1.schemas.inventory_sync import (
    InventorySyncRequest,
    ProductRemove,
    ProductUpsert,
)
from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiUnavailableError, AuthenticationError
from ai_agent.core.tenant_context import TenantContext

TENANT_ID = uuid.uuid4()


def _request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/ai/inventory/embeddings/sync",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
        ],
    }
    return Request(scope)


class _FakeSession:
    """Records commits; execute() is an inert seam for store calls."""

    def __init__(self) -> None:
        self.commits = 0

    async def execute(self, statement: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class TestRequireSyncToken:
    def test_valid_token_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "sync-secret")
        assert require_sync_token(_request({"Authorization": "Bearer sync-secret"})) is None

    def test_mismatched_token_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "sync-secret")
        with pytest.raises(AuthenticationError):
            require_sync_token(_request({"Authorization": "Bearer wrong"}))

    def test_missing_header_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "sync-secret")
        with pytest.raises(AuthenticationError):
            require_sync_token(_request())

    def test_unconfigured_endpoint_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "")
        with pytest.raises(AiUnavailableError):
            require_sync_token(_request({"Authorization": "Bearer anything"}))


class TestInventorySyncHandler:
    @pytest.mark.anyio
    async def test_applies_batch_and_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "sync-secret")
        # No embedding provider in the test env, so upserts degrade.
        monkeypatch.setattr(
            "ai_agent.api.v1.routers.inventory_sync.build_embedding_provider",
            lambda settings_obj: None,
        )
        TenantContext.set(str(TENANT_ID))
        try:
            session = _FakeSession()
            upsert_id = uuid.uuid4()
            remove_id = uuid.uuid4()
            body = InventorySyncRequest(
                upserts=[
                    ProductUpsert(
                        product_id=upsert_id,
                        sku="CBL-100",
                        name="Cat6 Patch Cable",
                        category="Networking",
                        unit="m",
                    )
                ],
                removes=[ProductRemove(product_id=remove_id)],
            )

            response = await inventory_sync(
                body=body,
                _token=None,
                session=session,  # type: ignore[arg-type]
            )

            # No embedding provider in the test env, so upserts degrade
            # (skipped) while removes still apply and the batch commits.
            assert response.upserts_applied == 0
            assert response.removes_applied == 1
            assert response.skipped is True
            assert response.model_used is None
            assert session.commits == 1
        finally:
            TenantContext.reset()

    @pytest.mark.anyio
    async def test_removes_only_batch_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "INVENTORY_SYNC_TOKEN", "sync-secret")
        TenantContext.set(str(TENANT_ID))
        try:
            session = _FakeSession()
            body = InventorySyncRequest(
                upserts=[],
                removes=[ProductRemove(product_id=uuid.uuid4())],
            )

            response = await inventory_sync(body=body, _token=None, session=session)  # type: ignore[arg-type]

            assert response.upserts_applied == 0
            assert response.removes_applied == 1
            assert response.skipped is False
            assert session.commits == 1
        finally:
            TenantContext.reset()
