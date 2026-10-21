"""Finance HTTP API integration tests - real Postgres, full app stack.

Regression coverage for the read-after-write contract on finance mutations.
``get_db`` commits in the dependency teardown, which runs at the tail of the
request; a route that returns before committing lets the very next request read
the previous state (or miss a just-created row entirely). That is exactly what
made the CRM + Finance Playwright journey flake: a reverse returned ``200``
while the immediate re-read still showed ``posted``, and freshly created
journal entries/invoices intermittently 404'd on the next call.

Finance write routes therefore call ``commit_writes`` before returning. These
tests assert the write is visible to an immediate re-read across the full
lifecycle exercised by the browser journey. The suite skips when Postgres is
unavailable (see tests/integration/conftest.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import select

from core.db.session import async_session_factory
from core.models.core_role import CoreRoleModel
from core.seed import seed_tenant_finance_defaults

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from httpx import AsyncClient

pytestmark = pytest.mark.integration

_JOURNAL_ENTRIES_URL = "/api/v1/finance/journal-entries"
_AUTOMATION_URL = "/api/v1/finance/automation"
_INVOICES_URL = "/api/v1/finance/invoices"
_CUSTOMERS_URL = "/api/v1/crm/customers"

# ``organization_admin`` carries ``erp.finance.approve`` but not the read/write
# keys, so the finance journeys need both granted alongside the admin identity.
_FINANCE_KEYS = ("erp.finance.read", "erp.finance.write")


def _suffix() -> str:
    return uuid.uuid4().hex[:12]


async def _set_finance_permissions(tenant_id: uuid.UUID, permissions: list[str]) -> None:
    async with async_session_factory() as session:
        role = await session.scalar(
            select(CoreRoleModel).where(
                CoreRoleModel.tenant_id == tenant_id,
                CoreRoleModel.name == "organization_admin",
            )
        )
        assert role is not None, "organization_admin role must be seeded"
        role.permissions = permissions
        await session.commit()


async def _get_role_permissions(tenant_id: uuid.UUID) -> list[str]:
    async with async_session_factory() as session:
        role = await session.scalar(
            select(CoreRoleModel).where(
                CoreRoleModel.tenant_id == tenant_id,
                CoreRoleModel.name == "organization_admin",
            )
        )
        assert role is not None, "organization_admin role must be seeded"
        return list(role.permissions)


@pytest.fixture
async def finance_headers(
    seeded_test_rbac: None,
    tenant_headers: Callable[..., dict[str, str]],
    integration_db: dict[str, str],
) -> AsyncGenerator[dict[str, str], None]:
    """Tenant-admin headers with finance read/write granted, plus seed accounts."""
    tenant_id = uuid.UUID(integration_db["acme_id"])
    await seed_tenant_finance_defaults(tenant_id)

    original = await _get_role_permissions(tenant_id)
    await _set_finance_permissions(tenant_id, list(dict.fromkeys([*original, *_FINANCE_KEYS])))
    try:
        yield tenant_headers()
    finally:
        await _set_finance_permissions(tenant_id, original)


async def _create_customer(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        _CUSTOMERS_URL,
        json={"name": f"Durability Customer {_suffix()}", "currency": "USD"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return cast("str", response.json()["data"]["id"])


async def _create_balanced_entry(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        _JOURNAL_ENTRIES_URL,
        json={
            "entry_date": date.today().isoformat(),
            "memo": f"durability-{_suffix()}",
            "lines": [
                {"account_code": "1200", "debit": "1250.00"},
                {"account_code": "4000", "credit": "1250.00"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return cast("str", response.json()["data"]["id"])


async def _reread_entry(
    client: AsyncClient, headers: dict[str, str], entry_id: str
) -> dict[str, Any]:
    response = await client.get(f"{_JOURNAL_ENTRIES_URL}/{entry_id}", headers=headers)
    assert response.status_code == 200, response.text
    return cast("dict[str, Any]", response.json()["data"])


class TestJournalEntryDurability:
    async def test_create_post_and_reverse_are_visible_to_an_immediate_reread(
        self, client: AsyncClient, finance_headers: dict[str, str]
    ) -> None:
        """Each 2xx must be durable before the client's next request lands.

        Mirrors the browser journey: create -> detail page, post -> refetch,
        reverse -> refetch. Every re-read here happens with no sleep and no
        retry, which is precisely the race the UI loses under load.
        """
        entry_id = await _create_balanced_entry(client, finance_headers)

        created = await _reread_entry(client, finance_headers, entry_id)
        assert created["id"] == entry_id
        assert created["status"] == "draft"

        posted = await client.post(
            f"{_JOURNAL_ENTRIES_URL}/{entry_id}/post", headers=finance_headers
        )
        assert posted.status_code == 200, posted.text
        assert posted.json()["data"]["status"] == "posted"

        assert (await _reread_entry(client, finance_headers, entry_id))["status"] == "posted"

        reversed_response = await client.post(
            f"{_AUTOMATION_URL}/journal-entries/{entry_id}/reverse", headers=finance_headers
        )
        assert reversed_response.status_code == 200, reversed_response.text
        assert reversed_response.json()["data"]["status"] == "reversed"

        assert (await _reread_entry(client, finance_headers, entry_id))["status"] == "reversed"


class TestInvoiceDurability:
    async def test_create_issue_approve_and_pay_are_visible_to_an_immediate_reread(
        self, client: AsyncClient, finance_headers: dict[str, str]
    ) -> None:
        """The invoice lifecycle must be readable back at every step."""
        headers = finance_headers
        customer_id = await _create_customer(client, headers)

        created = await client.post(
            _INVOICES_URL,
            json={
                "customer_id": customer_id,
                "invoice_date": date.today().isoformat(),
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "lines": [
                    {
                        "description": "Durability engagement",
                        "account_code": "4000",
                        "quantity": "1",
                        "unit_price": "100.00",
                    }
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        invoice_id = cast("str", created.json()["data"]["id"])

        async def reread() -> dict[str, Any]:
            response = await client.get(f"{_INVOICES_URL}/{invoice_id}", headers=headers)
            assert response.status_code == 200, response.text
            return cast("dict[str, Any]", response.json()["data"])

        assert (await reread())["id"] == invoice_id
        assert (await reread())["status"] == "draft"

        issued = await client.post(f"{_INVOICES_URL}/{invoice_id}/issue", headers=headers)
        assert issued.status_code == 200, issued.text
        assert issued.json()["data"]["status"] == "issued"
        assert (await reread())["status"] == "issued"

        approved = await client.post(f"{_INVOICES_URL}/{invoice_id}/approve", headers=headers)
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["status"] == "approved"
        assert (await reread())["status"] == "approved"

        paid = await client.post(
            f"{_INVOICES_URL}/{invoice_id}/payments",
            json={
                "amount": "100.00",
                "method": "bank_transfer",
                "paid_at": datetime.now(UTC).isoformat(),
            },
            headers=headers,
        )
        assert paid.status_code == 201, paid.text
        assert (await reread())["status"] == "paid"
