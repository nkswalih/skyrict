"""Stock-health analytics HTTP API tests (INV-ANL-001) — full app stack.

Verifies the /inventory/health/* endpoints end-to-end, with special attention
to the server-side cost gate: the ``erp.inventory.cost`` permission controls
whether cost/tied-up figures are returned, without making the whole endpoint
fail for callers who only hold ``erp.inventory.read``.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import pytest
from jose import jwt
from sqlalchemy import text

from core.core.config import settings
from core.core.permissions import (
    ERP_INVENTORY_ADJUST,
    ERP_INVENTORY_COST,
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
)
from core.db.session import async_session_factory
from core.models.core_role import CoreRoleModel
from core.models.core_user_role import CoreUserRoleModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from httpx import AsyncClient

pytestmark = pytest.mark.integration

_SUB_READ = str(uuid.uuid4())
_SUB_COST = str(uuid.uuid4())
_SUB_NONE = str(uuid.uuid4())


def _token_for(rsa_private_key: str, tenant_id: str, subject: str) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "iss": settings.JWKS_ISSUER,
        "aud": settings.JWKS_AUDIENCE,
        "iat": now,
        "nbf": now - 10,
        "exp": now + 300,
        "type": "access",
    }
    return jwt.encode(payload, rsa_private_key, algorithm="RS256")


def _auth(token: str) -> dict[str, str]:
    return {"X-Tenant-Slug": "olympus", "Authorization": f"Bearer {token}"}


def _suffix() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
async def health_rbac(integration_db: dict[str, str]) -> AsyncGenerator[dict[str, str], None]:
    """Seed identities: read-only, read+write, and read+write+cost."""
    acme = uuid.UUID(integration_db["acme_id"])
    role_read = uuid.uuid4()
    role_cost = uuid.uuid4()

    async with async_session_factory() as session:
        for sub in (_SUB_READ, _SUB_COST, _SUB_NONE):
            await session.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, full_name) "
                    "VALUES (:id, :tid, :email, :hash, :name)"
                ),
                {
                    "id": uuid.UUID(sub),
                    "tid": acme,
                    "email": f"{sub}@skyrict.integration.test",
                    "hash": "not-a-real-hash",
                    "name": sub[:8],
                },
            )
        session.add_all(
            [
                CoreRoleModel(
                    tenant_id=acme,
                    id=role_read,
                    name="health-read",
                    permissions=[ERP_INVENTORY_READ],
                ),
                CoreRoleModel(
                    tenant_id=acme,
                    id=role_cost,
                    name="health-cost",
                    permissions=[
                        ERP_INVENTORY_READ,
                        ERP_INVENTORY_WRITE,
                        ERP_INVENTORY_ADJUST,
                        ERP_INVENTORY_COST,
                    ],
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                CoreUserRoleModel(
                    tenant_id=acme, id=uuid.uuid4(), user_id=uuid.UUID(_SUB_READ), role_id=role_read
                ),
                CoreUserRoleModel(
                    tenant_id=acme, id=uuid.uuid4(), user_id=uuid.UUID(_SUB_COST), role_id=role_cost
                ),
            ]
        )
        await session.commit()

    yield {"acme_id": integration_db["acme_id"]}

    role_ids = (role_read, role_cost)
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM core_user_roles WHERE role_id IN (:r1, :r2)"),
            {"r1": role_ids[0], "r2": role_ids[1]},
        )
        await session.execute(
            text("DELETE FROM core_roles WHERE id IN (:r1, :r2)"),
            {"r1": role_ids[0], "r2": role_ids[1]},
        )
        await session.execute(
            text("DELETE FROM users WHERE id IN (:u1, :u2, :u3)"),
            {"u1": uuid.UUID(_SUB_READ), "u2": uuid.UUID(_SUB_COST), "u3": uuid.UUID(_SUB_NONE)},
        )
        await session.commit()


@pytest.fixture
def health_tokens(health_rbac: dict[str, str], rsa_private_key: str) -> dict[str, str]:
    return {
        "read": _token_for(rsa_private_key, health_rbac["acme_id"], _SUB_READ),
        "cost": _token_for(rsa_private_key, health_rbac["acme_id"], _SUB_COST),
        "none": _token_for(rsa_private_key, health_rbac["acme_id"], _SUB_NONE),
    }


async def _create_product(client: AsyncClient, token: str, *, sku: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/inventory/products",
        headers=_auth(token),
        json={
            "sku": sku,
            "name": "Health Widget",
            "reorder_point": "0",
            "cost_price": [12.5, "USD"],
            "sell_price": [19.99, "USD"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_warehouse(client: AsyncClient, token: str, *, name: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/inventory/warehouses",
        headers=_auth(token),
        json={"name": name, "location": "A1"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _adjust(client: AsyncClient, token: str, *, product_id: str, warehouse_id: str) -> object:
    return await client.post(
        "/api/v1/inventory/stock/adjustments",
        headers=_auth(token),
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "qty": 10,
            "reason": "integ-test",
            "ref_id": f"ref-{_suffix()}",
        },
    )


class TestHealthCostGate:
    async def test_summary_cost_requires_cost_permission(
        self, client: AsyncClient, health_tokens: dict[str, str]
    ) -> None:
        product = await _create_product(client, health_tokens["cost"], sku=f"HC-{_suffix()}")
        wh = await _create_warehouse(client, health_tokens["cost"], name="HC-WH")

        resp = await _adjust(
            client,
            health_tokens["cost"],
            product_id=product["id"],
            warehouse_id=wh["id"],
        )
        assert resp.status_code == 201, resp.text

        # Caller WITHOUT the cost key gets the summary but no cost figures.
        plain = await client.get(
            "/api/v1/inventory/health/summary", headers=_auth(health_tokens["read"])
        )
        assert plain.status_code == 200, plain.text
        plain_data = plain.json()["data"]
        assert plain_data["total_sku_count"] >= 1
        assert plain_data["tied_up_capital"] is None

        # Caller WITH the cost key sees the tied-up capital figure.
        cost = await client.get(
            "/api/v1/inventory/health/summary", headers=_auth(health_tokens["cost"])
        )
        assert cost.status_code == 200, cost.text
        assert cost.json()["data"]["tied_up_capital"] is not None

    async def test_dead_stock_cost_fields_gated(
        self, client: AsyncClient, health_tokens: dict[str, str]
    ) -> None:
        product = await _create_product(client, health_tokens["cost"], sku=f"HD-{_suffix()}")
        wh = await _create_warehouse(client, health_tokens["cost"], name="HD-WH")
        await _adjust(
            client,
            health_tokens["cost"],
            product_id=product["id"],
            warehouse_id=wh["id"],
        )

        plain = await client.get(
            "/api/v1/inventory/health/dead-stock", headers=_auth(health_tokens["read"])
        )
        assert plain.status_code == 200, plain.text
        items = plain.json()["data"]
        assert items, "a newly received product is dead stock until sold"
        assert all(i["cost_price"] is None and i["tied_up_value"] is None for i in items)

        cost = await client.get(
            "/api/v1/inventory/health/dead-stock", headers=_auth(health_tokens["cost"])
        )
        assert cost.status_code == 200, cost.text
        assert any(i["tied_up_value"] is not None for i in cost.json()["data"])

    async def test_health_requires_read_permission(
        self, client: AsyncClient, health_tokens: dict[str, str]
    ) -> None:
        resp = await client.get(
            "/api/v1/inventory/health/summary", headers=_auth(health_tokens["none"])
        )
        assert resp.status_code == 403, resp.text
