"""CRM HTTP API integration tests - real Postgres, full app stack.

End-to-end coverage of CRM-BE-002 over the FastAPI app: lead lifecycle
(create/list/get/patch/qualify/disqualify), the opportunity pipeline with its
one-step-forward rule and the won->customer promotion, money normalization on
updates (bare currency rejected, amount+currency accepted), DB-resolved
permission enforcement (401/403), two-tenant isolation, and the audit trail.
The suite skips when Postgres is unavailable (see tests/integration/conftest.py).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import select

from core.db.session import async_session_factory
from core.features.audit.models.audit_log import AuditLogModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from httpx import AsyncClient

pytestmark = pytest.mark.integration

_LEADS_URL = "/api/v1/crm/leads"
_OPPS_URL = "/api/v1/crm/opportunities"
_CUSTOMERS_URL = "/api/v1/crm/customers"


def _suffix() -> str:
    return uuid.uuid4().hex[:12]


async def _create_lead(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    email: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "source": "web",
    }
    if email is not None:
        payload["email"] = email
    if company is not None:
        payload["company"] = company
    response = await client.post(_LEADS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return cast("dict[str, Any]", response.json()["data"])


async def _qualify_lead(
    client: AsyncClient, headers: dict[str, str], lead_id: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{_LEADS_URL}/{lead_id}/qualify", json=body or None, headers=headers
    )
    assert response.status_code == 201, response.text
    return cast("dict[str, Any]", response.json()["data"])


async def _move_stage(
    client: AsyncClient,
    headers: dict[str, str],
    opportunity_id: str,
    stage: str,
    **body: Any,
) -> Any:
    response = await client.post(
        f"{_OPPS_URL}/{opportunity_id}/stage",
        json={"stage": stage, **body},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestLeadLifecycle:
    async def test_create_and_get_lead(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        created = await _create_lead(client, headers, email=f"ada-{_suffix()}@example.com")
        assert created["status"] == "new"
        assert created["email"].startswith("ada-")
        assert created["first_name"] == "Ada"

        response = await client.get(f"{_LEADS_URL}/{created['id']}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["id"] == created["id"]

    async def test_list_leads_paginated_and_filtered(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        await _create_lead(client, headers)
        response = await client.get(f"{_LEADS_URL}?offset=0&limit=1&source=web", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["meta"]["page"] == 1
        assert len(body["data"]) <= 1
        assert all(lead["source"] == "web" for lead in body["data"])

    async def test_update_lead(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        response = await client.patch(
            f"{_LEADS_URL}/{lead['id']}",
            json={"company": "Analytical Engines"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["company"] == "Analytical Engines"

    async def test_qualify_creates_opportunity_and_replay_is_idempotent(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(
            client, headers, lead["id"], amount="15000.00", currency="USD", probability=60
        )
        assert opportunity["stage"] == "prospecting"
        assert opportunity["amount"] == "15000.0000"
        assert opportunity["probability"] == 60

        # Replay: same lead cannot be qualified again (already promoted).
        response = await client.post(f"{_LEADS_URL}/{lead['id']}/qualify", json={}, headers=headers)
        assert response.status_code == 201, response.text
        assert response.json()["data"]["id"] == opportunity["id"]

        # The lead itself is qualified.
        lead_response = await client.get(f"{_LEADS_URL}/{lead['id']}", headers=headers)
        assert lead_response.json()["data"]["status"] == "qualified"

    async def test_disqualified_lead_cannot_qualify(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        response = await client.post(f"{_LEADS_URL}/{lead['id']}/disqualify", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "disqualified"

        response = await client.post(f"{_LEADS_URL}/{lead['id']}/qualify", json={}, headers=headers)
        assert response.status_code == 409, response.text

    async def test_missing_lead_404(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        response = await client.get(f"{_LEADS_URL}/{uuid.uuid4()}", headers=tenant_headers())
        assert response.status_code == 404, response.text


class TestOpportunityPipeline:
    async def test_stage_moves_one_step_forward(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        for stage in ("qualified", "proposal", "negotiation"):
            response = await client.post(
                f"{_OPPS_URL}/{opportunity['id']}/stage",
                json={"stage": stage},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["data"]["opportunity"]["stage"] == stage

    async def test_stage_move_is_visible_to_an_immediate_reread(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        """A 2xx stage move must be durable before the response is returned.

        The pipeline board re-reads the whole board immediately after a move.
        The write used to be committed in the ``get_db`` teardown, which runs
        at the tail of the request, so that re-read raced the commit - and when
        it lost, the board rendered the card back in its previous column and
        settled there, looking exactly like a move that silently failed.

        Asserting the list endpoint right after the move is the shape of that
        race, so it is the right regression guard: the write has to be visible
        to the very next request.
        """
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        for stage in ("qualified", "proposal", "negotiation"):
            response = await client.post(
                f"{_OPPS_URL}/{opportunity['id']}/stage",
                json={"stage": stage},
                headers=headers,
            )
            assert response.status_code == 200, response.text

            # No sleep, no retry: immediately re-read what the board re-reads.
            listed = await client.get(f"{_OPPS_URL}?limit=100", headers=headers)
            assert listed.status_code == 200, listed.text
            stages = {item["id"]: item["stage"] for item in listed.json()["data"]}
            assert stages[opportunity["id"]] == stage

    async def test_skipping_a_stage_is_rejected(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        response = await client.post(
            f"{_OPPS_URL}/{opportunity['id']}/stage",
            json={"stage": "proposal"},
            headers=headers,
        )
        assert response.status_code == 409, response.text

    async def test_won_promotes_customer(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers, company="Hollerith Ltd")
        opportunity = await _qualify_lead(client, headers, lead["id"], amount="4200.00")

        body = await _move_stage(client, headers, opportunity["id"], "won")
        assert body["opportunity"]["stage"] == "won"
        customer = body["customer"]
        assert customer is not None
        assert customer["name"] == "Hollerith Ltd"
        assert customer["customer_code"].startswith("CUST-")
        assert customer["source_opportunity_id"] == opportunity["id"]

    async def test_won_replay_raises_409(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])
        await _move_stage(client, headers, opportunity["id"], "won")

        response = await client.post(
            f"{_OPPS_URL}/{opportunity['id']}/stage",
            json={"stage": "won"},
            headers=headers,
        )
        assert response.status_code == 409, response.text

    async def test_lost_from_any_non_terminal(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        body = await _move_stage(client, headers, opportunity["id"], "lost", lost_reason="budget")
        assert body["opportunity"]["stage"] == "lost"
        assert body["opportunity"]["lost_reason"] == "budget"
        assert body["customer"] is None

    async def test_update_opportunity_with_money_pair(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        response = await client.patch(
            f"{_OPPS_URL}/{opportunity['id']}",
            json={"amount": "9999.99", "currency": "EUR", "probability": 80},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        updated = response.json()["data"]
        assert updated["amount"] == "9999.9900"
        assert updated["currency"] == "EUR"
        assert updated["probability"] == 80

    async def test_bare_currency_change_is_rejected(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        response = await client.patch(
            f"{_OPPS_URL}/{opportunity['id']}",
            json={"currency": "EUR"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_bad_probability_is_rejected(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        opportunity = await _qualify_lead(client, headers, lead["id"])

        response = await client.patch(
            f"{_OPPS_URL}/{opportunity['id']}",
            json={"probability": 101},
            headers=headers,
        )
        assert response.status_code == 422, response.text


class TestCustomers:
    async def test_create_get_and_patch_customer(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        response = await client.post(
            _CUSTOMERS_URL,
            json={"name": "Babbage Works", "credit_limit": "5000.00"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        customer = response.json()["data"]
        assert customer["customer_code"].startswith("CUST-")
        assert customer["credit_limit"] == "5000.0000"
        assert customer["currency"] == "USD"

        response = await client.patch(
            f"{_CUSTOMERS_URL}/{customer['id']}",
            json={"credit_limit": "7500.00", "currency": "EUR"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["credit_limit"] == "7500.0000"
        assert response.json()["data"]["currency"] == "EUR"

    async def test_deactivate_customer(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        response = await client.post(_CUSTOMERS_URL, json={"name": "Turing Co"}, headers=headers)
        customer = response.json()["data"]

        response = await client.delete(f"{_CUSTOMERS_URL}/{customer['id']}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["is_active"] is False

        # Hidden by default, visible with include_inactive.
        listed = (await client.get(_CUSTOMERS_URL, headers=headers)).json()
        assert all(item["id"] != customer["id"] for item in listed["data"])
        all_customers = (
            await client.get(_CUSTOMERS_URL, params={"include_inactive": True}, headers=headers)
        ).json()
        assert any(item["id"] == customer["id"] for item in all_customers["data"])

    async def test_customer_bare_currency_change_rejected(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        response = await client.post(
            _CUSTOMERS_URL, json={"name": "Analytical Co"}, headers=headers
        )
        customer = response.json()["data"]

        response = await client.patch(
            f"{_CUSTOMERS_URL}/{customer['id']}",
            json={"currency": "EUR"},
            headers=headers,
        )
        assert response.status_code == 422, response.text


class TestAuthorization:
    async def test_unprivileged_gets_403(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers(unprivileged=True)
        response = await client.get(_LEADS_URL, headers=headers)
        assert response.status_code == 403, response.text

        response = await client.post(_LEADS_URL, json={"first_name": "Ada"}, headers=headers)
        assert response.status_code == 403, response.text

    async def test_missing_token_gets_401(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        # Tenant context present, no Authorization header → route-level auth.
        response = await client.get(_LEADS_URL, headers={"X-Tenant-Slug": "olympus"})
        assert response.status_code == 401, response.text
        assert response.json()["type"].endswith("/authentication-error")


class TestTenantIsolation:
    async def test_globex_does_not_see_olympus_leads(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        olympus = tenant_headers()
        await _create_lead(client, olympus, email=f"ada-{_suffix()}@example.com")

        globex = tenant_headers("globex")
        response = await client.get(_LEADS_URL, headers=globex)
        assert response.status_code == 200, response.text
        assert response.json()["data"] == []

        # Globex creates its own lead and cannot read olympus' directly.
        globex_lead = await _create_lead(client, globex, email=f"grace-{_suffix()}@example.com")
        olympus_lead_id = (await client.get(_LEADS_URL, headers=olympus)).json()["data"][0]["id"]
        olympus_lead_tenant = (
            await client.get(f"{_LEADS_URL}/{olympus_lead_id}", headers=olympus)
        ).json()["data"]["tenant_id"]
        assert globex_lead["tenant_id"] != olympus_lead_tenant

        response = await client.get(f"{_LEADS_URL}/{olympus_lead_id}", headers=globex)
        assert response.status_code == 404, response.text


class TestAuditTrail:
    async def test_qualify_writes_audit_row(
        self, client: AsyncClient, tenant_headers: Callable[..., dict[str, str]]
    ) -> None:
        headers = tenant_headers()
        lead = await _create_lead(client, headers)
        await _qualify_lead(client, headers, lead["id"])

        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLogModel)
                        .where(
                            AuditLogModel.target == f"lead:{lead['id']}",
                            AuditLogModel.tenant_id == lead["tenant_id"],
                        )
                        .order_by(AuditLogModel.created_at)
                    )
                )
                .scalars()
                .all()
            )
        actions = [row.action for row in rows]
        assert "crm.lead.status_changed" in actions
