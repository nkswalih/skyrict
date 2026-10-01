"""CRM & Sales integration tests (CRM-DATA-001) - real Postgres, real migrations.

Covers what a model/unit test cannot:

  - RLS on the five new ``erp_crm_*`` / ``erp_sales_*`` tables (non-owner role
    ``core_rls_smoke`` + the ``app.current_tenant_id`` GUC);
  - cross-tenant INSERTs rejected by RLS ``WITH CHECK``;
  - the composite-FK convention blocking cross-tenant children even as the
    table OWNER (order -> customer, order line -> product);
  - the DB CHECKs (contact_present, probability range, stage outcome,
    currency_present, status/confirmed_at, quantity > 0);
  - the 4 native enum types created by migration 0003;
  - repository behavior: CRUD, OWNER/TEAM/ALL scoping, the soft dedupe probe,
    customer deactivation, atomic order state guards, unique order number
    translated to a 409 ConflictError;
  - the module-scoped downgrade round-trip (``alembic downgrade`` back to the
    CRM migration's parent -> ``upgrade head``), declared LAST so every other
    test sees the head schema and the chain is restored before any other
    module runs.

Skipped automatically when Postgres is unreachable (``migrated_schema``).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from core.db.session import async_session_factory, engine
from core.domain.entities import Customer, Lead, Opportunity, SalesOrder, SalesOrderLine
from core.domain.value_objects import (
    CreditCheckResult,
    DataScope,
    LeadStatus,
    Money,
    OpportunityStage,
    OrderStatus,
)
from core.features.audit.repository import AuditRepository
from core.features.audit.service import AuditService
from core.features.crm.models.customer import ErpCrmCustomerModel
from core.features.crm.repository import CrmRepository
from core.features.crm.service import CrmService
from core.features.inventory.models.product import ErpProductModel
from core.features.sales.repository import ConflictError, SalesRepository
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

RLS_ROLE = "core_rls_smoke"

_CORE_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
_CORE_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "alembic"

_CRM_SALES_TABLES = (
    "erp_sales_order_lines",
    "erp_sales_orders",
    "erp_crm_customers",
    "erp_crm_opportunities",
    "erp_crm_leads",
)

_UTC = UTC


def _now() -> datetime:
    return datetime(2026, 8, 1, tzinfo=_UTC)


@pytest.fixture(scope="module")
def crm_world(migrated_schema: None) -> dict[str, str]:
    """Seed two tenants, one product + one customer each.

    Plain (sync) fixture: all DB work runs inside one ``asyncio.run()`` and the
    engine pool is disposed before that run's loop closes, so the function-
    scoped async tests that follow get a clean pool bound to their own loops.
    """

    async def _setup() -> dict[str, str]:
        tenant_a = str(uuid.uuid4())
        tenant_b = str(uuid.uuid4())
        product_a = str(uuid.uuid4())
        product_b = str(uuid.uuid4())
        customer_a = str(uuid.uuid4())
        customer_b = str(uuid.uuid4())

        async with async_session_factory() as session:
            session.add_all(
                [
                    TenantModel(
                        id=uuid.UUID(tenant_a),
                        name="CRM Tenant A",
                        slug=f"crm-a-{tenant_a[:8]}",
                        plan_tier="free",
                        is_active=True,
                    ),
                    TenantModel(
                        id=uuid.UUID(tenant_b),
                        name="CRM Tenant B",
                        slug=f"crm-b-{tenant_b[:8]}",
                        plan_tier="free",
                        is_active=True,
                    ),
                ]
            )
            await session.flush()
            # Same SKU in both tenants - uniqueness is per-tenant, and both
            # tenants have a valid product so FK tests differ only by tenant.
            session.add_all(
                [
                    ErpProductModel(
                        tenant_id=uuid.UUID(tenant_a),
                        id=uuid.UUID(product_a),
                        sku="SKU-A",
                        name="Product A",
                    ),
                    ErpProductModel(
                        tenant_id=uuid.UUID(tenant_b),
                        id=uuid.UUID(product_b),
                        sku="SKU-A",
                        name="Product A",
                    ),
                    ErpCrmCustomerModel(
                        tenant_id=uuid.UUID(tenant_a),
                        id=uuid.UUID(customer_a),
                        customer_code="CUST-A",
                        name="Customer A",
                    ),
                    ErpCrmCustomerModel(
                        tenant_id=uuid.UUID(tenant_b),
                        id=uuid.UUID(customer_b),
                        customer_code="CUST-B",
                        name="Customer B",
                    ),
                ]
            )
            await session.commit()
            await engine.dispose()

        return {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "product_a": product_a,
            "product_b": product_b,
            "customer_a": customer_a,
            "customer_b": customer_b,
        }

    async def _teardown() -> None:
        # Children first (RESTRICT FKs), then the tenants themselves.
        async with async_session_factory() as session:
            for tid in (crm_world_data["tenant_a"], crm_world_data["tenant_b"]):
                for table in _CRM_SALES_TABLES:
                    await session.execute(
                        text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                        {"tid": uuid.UUID(tid)},
                    )
                await session.execute(
                    text("DELETE FROM erp_products WHERE tenant_id = :tid"),
                    {"tid": uuid.UUID(tid)},
                )
                await session.execute(
                    text("DELETE FROM tenants WHERE id = :tid"), {"tid": uuid.UUID(tid)}
                )
            await session.commit()
            await engine.dispose()

    crm_world_data = asyncio.run(_setup())
    try:
        yield crm_world_data
    finally:
        asyncio.run(_teardown())


async def _ensure_crm_sales_rls_role() -> None:
    """Create the non-owner RLS test role + grants on the tables it reads.

    The dev ``skyrict`` user owns the tables (and bypasses RLS), so a
    NON-OWNER role is needed to prove the policies bite. Skipped with an
    actionable message when the local ``skyrict`` lacks CREATEROLE.
    """
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{RLS_ROLE}') "
                f"THEN CREATE ROLE {RLS_ROLE} NOLOGIN; "
                "END IF; END $$;"
            )
            await conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            for table in _CRM_SALES_TABLES:
                await conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT ON TABLE public.{table} TO {RLS_ROLE}"
                )
            for table in ("erp_products", "erp_currencies"):
                await conn.exec_driver_sql(f"GRANT SELECT ON TABLE public.{table} TO {RLS_ROLE}")
    except ProgrammingError as exc:
        if "permission denied to create role" not in str(exc).lower():
            raise
        pytest.skip(
            "SQL-level RLS smoke tests require a role with CREATEROLE to create "
            "the non-owner 'core_rls_smoke' test role. The compose/CI stack's "
            "skyrict superuser can; a non-superuser local skyrict cannot. "
            "Run the tests against the compose stack, or grant CREATEROLE to "
            'skyrict with: psql -U postgres -c "ALTER ROLE skyrict CREATEROLE"'
        )


class TestCrmSalesSeededData:
    async def test_crm_sales_permissions_seeded(self, migrated_schema: None) -> None:
        # Migration 0003 seeds exactly the three new permission keys (0001
        # already seeded erp.sales.read/write; 0006 seeded erp.finance.*).
        async with async_session_factory() as session:
            keys = (await session.execute(text("SELECT key FROM core_permissions"))).scalars().all()
        assert "erp.crm.read" in keys
        assert "erp.crm.write" in keys
        assert "erp.sales.approve" in keys


class TestCrmSalesRls:
    async def test_tenant_b_cannot_read_tenant_a_leads(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        await _ensure_crm_sales_rls_role()

        async with engine.connect() as conn:
            # Seed a lead for tenant A as the table owner (bypasses RLS).
            await conn.execute(
                text(
                    "INSERT INTO erp_crm_leads "
                    "(tenant_id, id, status, first_name, email) "
                    "VALUES (:tid, gen_random_uuid(), 'new', 'Alice', 'alice@x.com')"
                ),
                {"tid": uuid.UUID(crm_world["tenant_a"])},
            )
            await conn.exec_driver_sql(f"SET ROLE {RLS_ROLE}")

            # --- as tenant A: only tenant A's lead is visible ---
            await conn.exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                (crm_world["tenant_a"],),
            )
            a_emails = (await conn.execute(text("SELECT email FROM erp_crm_leads"))).scalars().all()
            assert "alice@x.com" in a_emails

            # --- as tenant B: tenant A's lead is invisible ---
            await conn.exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                (crm_world["tenant_b"],),
            )
            b_emails = (await conn.execute(text("SELECT email FROM erp_crm_leads"))).scalars().all()
            assert "alice@x.com" not in b_emails

            await conn.exec_driver_sql("RESET ROLE")

        await engine.dispose()

    async def test_tenant_b_cannot_read_tenant_a_orders(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        await _ensure_crm_sales_rls_role()

        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO erp_sales_orders "
                    "(tenant_id, id, order_number, customer_id, status) "
                    "VALUES (:tid, gen_random_uuid(), 'ORD-0001', :cust, 'draft')"
                ),
                {
                    "tid": uuid.UUID(crm_world["tenant_a"]),
                    "cust": uuid.UUID(crm_world["customer_a"]),
                },
            )
            await conn.exec_driver_sql(f"SET ROLE {RLS_ROLE}")

            await conn.exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                (crm_world["tenant_a"],),
            )
            a_numbers = (
                (await conn.execute(text("SELECT order_number FROM erp_sales_orders")))
                .scalars()
                .all()
            )
            assert "ORD-0001" in a_numbers

            await conn.exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                (crm_world["tenant_b"],),
            )
            b_numbers = (
                (await conn.execute(text("SELECT order_number FROM erp_sales_orders")))
                .scalars()
                .all()
            )
            assert "ORD-0001" not in b_numbers

            await conn.exec_driver_sql("RESET ROLE")

        await engine.dispose()

    async def test_cross_tenant_insert_blocked_by_rls(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        await _ensure_crm_sales_rls_role()

        async with engine.connect() as conn:
            await conn.exec_driver_sql(f"SET ROLE {RLS_ROLE}")
            # GUC pinned to tenant A, but the INSERT targets tenant B.
            await conn.exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                (crm_world["tenant_a"],),
            )
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_leads "
                        "(tenant_id, id, status, first_name, email) "
                        "VALUES (:tid, gen_random_uuid(), 'new', 'Sneaky', 's@x.com')"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_b"])},
                )
            assert "row-level security" in str(excinfo.value).lower()
            await conn.rollback()
            await conn.exec_driver_sql("RESET ROLE")

        await engine.dispose()


class TestCrmSalesCompositeFkConvention:
    async def test_cross_tenant_order_customer_rejected_even_as_owner(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        # The table owner bypasses RLS, so this can ONLY be stopped by the
        # composite FK (tenant_b, customer_a) -> erp_crm_customers(tenant_b, id):
        # customer_a belongs to tenant A, so the composite key doesn't exist.
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_orders "
                        "(tenant_id, id, order_number, customer_id, status) "
                        "VALUES (:tenant_b, gen_random_uuid(), 'ORD-SNEAKY', :customer_a, 'draft')"
                    ),
                    {
                        "tenant_b": uuid.UUID(crm_world["tenant_b"]),
                        "customer_a": uuid.UUID(crm_world["customer_a"]),
                    },
                )
            assert "fk_erp_sales_orders_customer_tenant" in str(excinfo.value)

        await engine.dispose()

    async def test_cross_tenant_order_line_product_rejected_even_as_owner(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        # The order is valid in tenant B (customer_b exists there), so the ONLY
        # constraint that can fire is the composite line FK on the product:
        # product_a belongs to tenant A -> (tenant_b, product_a) doesn't exist.
        async with engine.connect() as conn:
            order_b = (
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_orders "
                        "(tenant_id, id, order_number, customer_id, status) "
                        "VALUES (:tenant_b, gen_random_uuid(), 'ORD-LINE', :customer_b, 'draft') "
                        "RETURNING id"
                    ),
                    {
                        "tenant_b": uuid.UUID(crm_world["tenant_b"]),
                        "customer_b": uuid.UUID(crm_world["customer_b"]),
                    },
                )
            ).scalar_one()

            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_order_lines "
                        "(tenant_id, id, order_id, product_id, product_name, sku, quantity) "
                        "VALUES (:tenant_b, gen_random_uuid(), :order_b, :product_a, "
                        "'Product A', 'SKU-A', 1)"
                    ),
                    {
                        "tenant_b": uuid.UUID(crm_world["tenant_b"]),
                        "order_b": order_b,
                        "product_a": uuid.UUID(crm_world["product_a"]),
                    },
                )
            assert "fk_erp_sales_order_lines_product_tenant" in str(excinfo.value)

        await engine.dispose()


class TestCrmSalesConstraints:
    async def test_lead_requires_contact_channel(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_leads "
                        "(tenant_id, id, status, first_name, last_name, email) "
                        "VALUES (:tid, gen_random_uuid(), 'new', NULL, NULL, NULL)"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_a"])},
                )
            assert "ck_erp_crm_leads_contact_present" in str(excinfo.value)

        await engine.dispose()

    async def test_opportunity_probability_range(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_opportunities "
                        "(tenant_id, id, name, stage, probability) "
                        "VALUES (:tid, gen_random_uuid(), 'Too Sure', 'prospecting', 101)"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_a"])},
                )
            assert "ck_erp_crm_opportunities_probability_range" in str(excinfo.value)

        await engine.dispose()

    async def test_opportunity_amount_requires_currency(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_opportunities "
                        "(tenant_id, id, name, stage, amount, currency_code, probability) "
                        "VALUES (:tid, gen_random_uuid(), 'No Currency', 'prospecting', "
                        "100.00, NULL, 50)"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_a"])},
                )
            assert "ck_erp_crm_opportunities_currency_present" in str(excinfo.value)

        await engine.dispose()

    async def test_opportunity_won_requires_won_at(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_opportunities "
                        "(tenant_id, id, name, stage, probability) "
                        "VALUES (:tid, gen_random_uuid(), 'Won But When?', 'won', 100)"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_a"])},
                )
            assert "ck_erp_crm_opportunities_stage_outcome" in str(excinfo.value)

        await engine.dispose()

    async def test_order_line_quantity_must_be_positive(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            order_a = (
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_orders "
                        "(tenant_id, id, order_number, customer_id, status) "
                        "VALUES (:tid, gen_random_uuid(), 'ORD-QTY', :cust, 'draft') "
                        "RETURNING id"
                    ),
                    {
                        "tid": uuid.UUID(crm_world["tenant_a"]),
                        "cust": uuid.UUID(crm_world["customer_a"]),
                    },
                )
            ).scalar_one()

            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_order_lines "
                        "(tenant_id, id, order_id, product_id, product_name, sku, quantity) "
                        "VALUES (:tid, gen_random_uuid(), :order_a, :product_a, "
                        "'Product A', 'SKU-A', 0)"
                    ),
                    {
                        "tid": uuid.UUID(crm_world["tenant_a"]),
                        "order_a": order_a,
                        "product_a": uuid.UUID(crm_world["product_a"]),
                    },
                )
            assert "ck_erp_sales_order_lines_quantity_positive" in str(excinfo.value)

        await engine.dispose()

    async def test_confirmed_order_requires_confirmed_at(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_sales_orders "
                        "(tenant_id, id, order_number, customer_id, status) "
                        "VALUES (:tid, gen_random_uuid(), 'ORD-CONF', :cust, 'confirmed')"
                    ),
                    {
                        "tid": uuid.UUID(crm_world["tenant_a"]),
                        "cust": uuid.UUID(crm_world["customer_a"]),
                    },
                )
            assert "ck_erp_sales_orders_status_confirmed_at" in str(excinfo.value)

        await engine.dispose()

    async def test_customer_credit_limit_requires_currency(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO erp_crm_customers "
                        "(tenant_id, id, customer_code, name, credit_limit, currency_code) "
                        "VALUES (:tid, gen_random_uuid(), 'NO-CUR', 'No Currency', "
                        "1000.00, NULL)"
                    ),
                    {"tid": uuid.UUID(crm_world["tenant_a"])},
                )
            assert "ck_erp_crm_customers_currency_present" in str(excinfo.value)

        await engine.dispose()


class TestCrmSalesNativeEnums:
    async def test_migration_created_enum_types(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        async with engine.connect() as conn:
            lead_status = (
                (
                    await conn.execute(
                        text("SELECT unnest(enum_range(NULL::erp_crm_lead_status))::text")
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(lead_status) == ["contacted", "disqualified", "new", "qualified"]

            opportunity_stage = (
                (
                    await conn.execute(
                        text("SELECT unnest(enum_range(NULL::erp_crm_opportunity_stage))::text")
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(opportunity_stage) == [
                "lost",
                "negotiation",
                "proposal",
                "prospecting",
                "qualified",
                "won",
            ]

            order_status = (
                (
                    await conn.execute(
                        text("SELECT unnest(enum_range(NULL::erp_sales_order_status))::text")
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(order_status) == ["cancelled", "confirmed", "draft", "fulfilled"]

            credit_check = (
                (
                    await conn.execute(
                        text("SELECT unnest(enum_range(NULL::erp_sales_credit_check_result))::text")
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(credit_check) == ["failed", "passed", "pending"]

        await engine.dispose()


class TestCrmRepository:
    async def test_lead_roundtrip(self, migrated_schema: None, crm_world: dict[str, str]) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            lead = Lead(
                tenant_id=tenant_a,
                first_name="Alice",
                last_name="Anderson",
                email="alice@acme.test",
                source="website",
            )
            created = await repo.create_lead(lead)
            assert created.id is not None
            assert created.status == LeadStatus.NEW

            fetched = await repo.get_lead(
                created.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert fetched is not None
            assert fetched.email == "alice@acme.test"
            assert fetched.source == "website"
            await session.commit()

    async def test_owner_scope_hides_other_users_leads(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        user1 = uuid.uuid4()
        user2 = uuid.uuid4()
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            mine = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Mine", email="mine@x.test", owner_id=user1)
            )
            other = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Other", email="other@x.test", owner_id=user2)
            )

            mine_ids = {
                lead.id
                for lead in await repo.list_leads(
                    tenant_id=tenant_a,
                    scope=DataScope.OWNER,
                    user_id=user1,
                    team_id=None,
                )
            }
            assert mine.id in mine_ids
            assert other.id not in mine_ids

            # Direct fetch of someone else's row is also blocked at OWNER scope.
            hidden = await repo.get_lead(
                other.id,
                tenant_id=tenant_a,
                scope=DataScope.OWNER,
                user_id=user1,
                team_id=None,
            )
            assert hidden is None

            # ALL scope (owner/admins) sees everything.
            all_ids = {
                lead.id
                for lead in await repo.list_leads(
                    tenant_id=tenant_a,
                    scope=DataScope.ALL,
                    user_id=None,
                    team_id=None,
                )
            }
            assert mine.id in all_ids
            assert other.id in all_ids
            await session.commit()

    async def test_team_scope_sees_owner_and_team_rows(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        user1 = uuid.uuid4()
        user2 = uuid.uuid4()
        team1 = uuid.uuid4()
        team2 = uuid.uuid4()
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            owned = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Owned", email="owned@x.test", owner_id=user1)
            )
            teamed = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Teamed", email="teamed@x.test", team_id=team1)
            )
            foreign = await repo.create_lead(
                Lead(
                    tenant_id=tenant_a,
                    first_name="Foreign",
                    email="foreign@x.test",
                    owner_id=user2,
                    team_id=team2,
                )
            )
            unassigned = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Unassigned", email="unassigned@x.test")
            )

            team_ids = {
                lead.id
                for lead in await repo.list_leads(
                    tenant_id=tenant_a,
                    scope=DataScope.TEAM,
                    user_id=user1,
                    team_id=team1,
                )
            }
            assert owned.id in team_ids  # owner match
            assert teamed.id in team_ids  # team match
            assert foreign.id not in team_ids
            assert unassigned.id not in team_ids  # unassigned is ALL-scope only
            await session.commit()

    async def test_find_leads_by_email_is_a_soft_dedupe_probe(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        # Locked SKY-43 decision: the (tenant_id, email) index is NON-unique -
        # the probe answers "has anyone here been approached", and the service
        # layer decides how to act. Duplicates must be allowed.
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            await repo.create_lead(Lead(tenant_id=tenant_a, first_name="One", email="dup@x.test"))
            await repo.create_lead(Lead(tenant_id=tenant_a, first_name="Two", email="dup@x.test"))

            found = await repo.find_leads_by_email("dup@x.test", tenant_id=tenant_a)
            assert len(found) == 2

            # The same address in a different tenant is a different prospect.
            tenant_b = uuid.UUID(crm_world["tenant_b"])
            assert await repo.find_leads_by_email("dup@x.test", tenant_id=tenant_b) == []
            await session.commit()

    async def test_update_lead_status_respects_scope(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        user1 = uuid.uuid4()
        user2 = uuid.uuid4()
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            mine = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Mine", email="mine@x.test", owner_id=user1)
            )
            other = await repo.create_lead(
                Lead(tenant_id=tenant_a, first_name="Other", email="other@x.test", owner_id=user2)
            )

            qualified = await repo.update_lead_status(
                mine.id,
                tenant_id=tenant_a,
                status=LeadStatus.QUALIFIED,
                scope=DataScope.OWNER,
                user_id=user1,
                team_id=None,
            )
            assert qualified is not None
            assert qualified.status == LeadStatus.QUALIFIED

            # Updating someone else's lead at OWNER scope must not work.
            blocked = await repo.update_lead_status(
                other.id,
                tenant_id=tenant_a,
                status=LeadStatus.QUALIFIED,
                scope=DataScope.OWNER,
                user_id=user1,
                team_id=None,
            )
            assert blocked is None
            await session.commit()

    async def test_opportunity_stage_lifecycle(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            opportunity = await repo.create_opportunity(
                Opportunity(
                    tenant_id=tenant_a,
                    name="Big Deal",
                    amount=Money("10000.00", "USD"),
                    probability=30,
                )
            )
            assert opportunity.id is not None
            assert opportunity.stage == OpportunityStage.PROSPECTING
            assert opportunity.amount == Money("10000.00", "USD")

            won = await repo.update_opportunity_stage(
                opportunity.id,
                tenant_id=tenant_a,
                stage=OpportunityStage.WON,
                won_at=_now(),
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert won is not None
            assert won.stage == OpportunityStage.WON
            assert won.won_at == _now()

            fetched = await repo.get_opportunity(
                opportunity.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert fetched is not None
            assert fetched.stage == OpportunityStage.WON
            await session.commit()

    async def test_customer_roundtrip_and_deactivate(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            created = await repo.create_customer(
                Customer(
                    tenant_id=tenant_a,
                    customer_code="NEW-CUST",
                    name="New Customer",
                    credit_limit=Money("5000.00", "USD"),
                )
            )
            assert created.id is not None
            assert created.is_active is True

            by_code = await repo.get_customer_by_code("NEW-CUST", tenant_id=tenant_a)
            assert by_code is not None
            assert by_code.credit_limit == Money("5000.00", "USD")

            deactivated = await repo.deactivate_customer(created.id, tenant_id=tenant_a)
            assert deactivated is not None
            assert deactivated.is_active is False

            # Direct get still returns the row (soft delete); list hides it.
            assert await repo.get_customer(created.id, tenant_id=tenant_a) is not None
            listed = await repo.list_customers(tenant_id=tenant_a)
            assert all(customer.id != created.id for customer in listed)
            with_inactive = await repo.list_customers(tenant_id=tenant_a, include_inactive=True)
            assert any(customer.id == created.id for customer in with_inactive)
            await session.commit()


class TestCrmServiceWriteVisibility:
    """CRM writes must be durable BEFORE the handler returns (regression).

    Post-merge E2E failure run 35991947086 (2026-09-24): ``core/db/session.py``
    ``get_db`` commits in the yield-teardown AFTER the response is sent, and
    the CRM feature never committed inside its handlers - so a client that
    followed a write with another request could observe pre-commit state:

      * ``qualify`` 201 -> immediate stage move -> 404 "Opportunity not found"
        (the created opportunity row was still uncommitted);
      * stage move 200 -> immediate next stage move -> 409 "Cannot move
        opportunity from 'prospecting' to 'proposal'" (the previous stage
        update was still uncommitted).

    These tests drive :class:`CrmService` and then read through a FRESH
    session. With the teardown-only commit the fresh session could not see the
    write and the assertions failed deterministically; with the explicit
    in-handler commit they pass immediately.
    """

    @staticmethod
    def _make_service(session: AsyncSession) -> CrmService:
        """Compose CrmService exactly as ``get_crm_service`` does (deps.py)."""
        repo = CrmRepository(session)
        return CrmService(
            repository=repo,
            audit=AuditService(AuditRepository(session)),
            timeline=repo,
        )

    async def test_qualify_visible_to_fresh_session(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        """E2E attempt-1 mirror: qualify 201 then an immediate read by id."""
        tenant_a = uuid.UUID(crm_world["tenant_a"])

        async with async_session_factory() as session:
            svc = self._make_service(session)
            lead = await svc.create_lead(
                tenant_id=tenant_a,
                first_name="Lost",
                last_name="Flow",
                email=f"lost-{uuid.uuid4()}@example.test",
            )
            assert lead.id is not None
            opportunity = await svc.qualify_lead(
                lead.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert opportunity.id is not None

        # A fresh session/transaction must see the qualified opportunity
        # immediately - the old code committed only after the response.
        async with async_session_factory() as session:
            repo = CrmRepository(session)
            fetched = await repo.get_opportunity(
                opportunity.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert fetched is not None
            assert fetched.stage == OpportunityStage.PROSPECTING

    async def test_stage_moves_visible_to_fresh_session(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        """E2E retry-2 mirror: qualified 200 then an immediate next-stage read."""
        tenant_a = uuid.UUID(crm_world["tenant_a"])

        async with async_session_factory() as session:
            svc = self._make_service(session)
            lead = await svc.create_lead(
                tenant_id=tenant_a,
                company=f"Deal {uuid.uuid4()}",
                email=f"deal-{uuid.uuid4()}@example.test",
            )
            assert lead.id is not None
            opportunity = await svc.qualify_lead(
                lead.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert opportunity.id is not None
            qualified, _ = await svc.change_stage(
                opportunity.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
                stage=OpportunityStage.QUALIFIED,
            )
            assert qualified.id is not None

        async with async_session_factory() as session:
            repo = CrmRepository(session)
            fetched = await repo.get_opportunity(
                qualified.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert fetched is not None
            # Old code: the qualified UPDATE was still uncommitted, so this read
            # saw the stale 'prospecting' and the E2E next move hit the 409.
            assert fetched.stage == OpportunityStage.QUALIFIED

            proposal, _ = await self._make_service(session).change_stage(
                qualified.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
                stage=OpportunityStage.PROPOSAL,
            )
            assert proposal.id is not None

        async with async_session_factory() as session:
            repo = CrmRepository(session)
            fetched = await repo.get_opportunity(
                proposal.id,
                tenant_id=tenant_a,
                scope=DataScope.ALL,
                user_id=None,
                team_id=None,
            )
            assert fetched is not None
            assert fetched.stage == OpportunityStage.PROPOSAL


class TestSalesRepository:
    async def test_create_order_stamps_order_id_on_lines(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)
            created = await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-0001",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [
                    SalesOrderLine(
                        tenant_id=tenant_a,
                        product_id=uuid.UUID(crm_world["product_a"]),
                        product_name="Product A",
                        sku="SKU-A",
                        quantity=Decimal("2"),
                        unit_price=Decimal("10.00"),
                        line_total=Decimal("20.00"),
                    ),
                    SalesOrderLine(
                        tenant_id=tenant_a,
                        product_id=uuid.UUID(crm_world["product_a"]),
                        product_name="Product A",
                        sku="SKU-A",
                        quantity=Decimal("1"),
                        unit_price=Decimal("5.00"),
                        line_total=Decimal("5.00"),
                    ),
                ],
            )
            assert created.id is not None
            assert created.status == OrderStatus.DRAFT
            assert created.subtotal == Money("0", "USD")  # cached projection default

            lines = await repo.list_order_lines(created.id, tenant_id=tenant_a)
            assert len(lines) == 2
            # The repository stamped the generated header id onto every line.
            assert all(line.order_id == created.id for line in lines)
            assert {line.quantity for line in lines} == {Decimal("1"), Decimal("2")}
            assert all(line.product_name == "Product A" for line in lines)

            fetched = await repo.get_order(created.id, tenant_id=tenant_a)
            assert fetched is not None
            assert fetched.order_number == "SO-0001"
            await session.commit()

    async def test_get_order_by_number(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)
            created = await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-LOOKUP",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [],
            )
            by_number = await repo.get_order_by_number("SO-LOOKUP", tenant_id=tenant_a)
            assert by_number is not None
            assert by_number.id == created.id
            # Same number in another tenant is a different order.
            assert (
                await repo.get_order_by_number(
                    "SO-LOOKUP", tenant_id=uuid.UUID(crm_world["tenant_b"])
                )
                is None
            )
            await session.commit()

    async def test_list_orders_filters(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)
            draft = await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-FILT-1",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [],
            )
            other = await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-FILT-2",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [],
            )
            assert other.id is not None
            await repo.confirm_order(
                other.id,
                tenant_id=tenant_a,
                confirmed_at=_now(),
                credit_check=CreditCheckResult.PASSED,
            )

            drafts = await repo.list_orders(tenant_id=tenant_a, status=OrderStatus.DRAFT)
            # Membership assertions (not exact-list equality): earlier tests in
            # this module leave draft orders in the same tenant, and the
            # repository returns everything in scope by design.
            draft_ids = {order.id for order in drafts}
            assert draft.id in draft_ids
            assert other.id not in draft_ids

            confirmed = await repo.list_orders(tenant_id=tenant_a, status=OrderStatus.CONFIRMED)
            assert other.id in {order.id for order in confirmed}
            await session.commit()

    async def test_unique_order_number_raises_conflict(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)
            await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-DUP",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [],
            )
            with pytest.raises(ConflictError):
                await repo.create_order(
                    SalesOrder(
                        tenant_id=tenant_a,
                        order_number="SO-DUP",
                        customer_id=uuid.UUID(crm_world["customer_a"]),
                    ),
                    [],
                )
            await session.rollback()

            # The same number in a different tenant is perfectly fine.
            other = await repo.create_order(
                SalesOrder(
                    tenant_id=uuid.UUID(crm_world["tenant_b"]),
                    order_number="SO-DUP",
                    customer_id=uuid.UUID(crm_world["customer_b"]),
                ),
                [],
            )
            assert other.id is not None
            await session.commit()

    async def test_order_state_machine_guards(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        customer_a = uuid.UUID(crm_world["customer_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)

            def _order(number: str) -> SalesOrder:
                return SalesOrder(tenant_id=tenant_a, order_number=number, customer_id=customer_a)

            draft = await repo.create_order(_order("SO-GUARD-1"), [])
            assert draft.id is not None

            # Fulfilling a draft must fail the guard.
            assert await repo.fulfil_order(draft.id, tenant_id=tenant_a) is None

            # draft -> confirmed, atomic guard wins once.
            confirmed = await repo.confirm_order(
                draft.id,
                tenant_id=tenant_a,
                confirmed_at=_now(),
                credit_check=CreditCheckResult.PASSED,
            )
            assert confirmed is not None
            assert confirmed.status == OrderStatus.CONFIRMED
            assert confirmed.confirmed_at == _now()
            assert confirmed.credit_check == CreditCheckResult.PASSED

            # A replay of confirm loses the guard.
            assert (
                await repo.confirm_order(
                    draft.id,
                    tenant_id=tenant_a,
                    confirmed_at=_now(),
                    credit_check=CreditCheckResult.PASSED,
                )
                is None
            )

            # confirmed -> fulfilled.
            fulfilled = await repo.fulfil_order(draft.id, tenant_id=tenant_a)
            assert fulfilled is not None
            assert fulfilled.status == OrderStatus.FULFILLED

            # fulfilled is terminal - cancel must lose the guard.
            assert await repo.cancel_order(draft.id, tenant_id=tenant_a) is None

            # A cancelled draft stays cancelled; the guard wins exactly once.
            cancelled = await repo.create_order(_order("SO-GUARD-2"), [])
            assert cancelled.id is not None
            done = await repo.cancel_order(cancelled.id, tenant_id=tenant_a)
            assert done is not None
            assert done.status == OrderStatus.CANCELLED
            assert done.confirmed_at is None
            assert await repo.cancel_order(cancelled.id, tenant_id=tenant_a) is None

            # Confirming a cancelled order must fail the guard.
            assert (
                await repo.confirm_order(
                    cancelled.id,
                    tenant_id=tenant_a,
                    confirmed_at=_now(),
                    credit_check=CreditCheckResult.FAILED,
                )
                is None
            )
            await session.commit()

    async def test_confirm_order_with_failed_credit_check(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        tenant_a = uuid.UUID(crm_world["tenant_a"])
        async with async_session_factory() as session:
            repo = SalesRepository(session)
            created = await repo.create_order(
                SalesOrder(
                    tenant_id=tenant_a,
                    order_number="SO-CREDIT",
                    customer_id=uuid.UUID(crm_world["customer_a"]),
                ),
                [],
            )
            assert created.id is not None
            confirmed = await repo.confirm_order(
                created.id,
                tenant_id=tenant_a,
                confirmed_at=_now(),
                credit_check=CreditCheckResult.FAILED,
            )
            assert confirmed is not None
            assert confirmed.credit_check == CreditCheckResult.FAILED
            await session.commit()


class TestDowngradeRoundTrip:
    """Module-scoped downgrade round-trip - MUST stay the last class here.

    ``alembic downgrade`` walks back to just before migration 0003 (its parent
    revision, resolved dynamically), then ``upgrade head`` re-applies the
    CRM/sales block and everything above it, so the version table is back at
    head before any other test module runs. On this branch the HR/ERP
    migrations 0010-0014 sit on top of 0003, so "0003 is the head" no longer
    holds; the parent is derived from the script directory instead.
    """

    def _run_alembic(self, *args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(_CORE_ALEMBIC_INI), *args],
            cwd=_CORE_ALEMBIC_INI.parent,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout

    async def test_downgrade_then_upgrade_restores_head(
        self, migrated_schema: None, crm_world: dict[str, str]
    ) -> None:
        scripts = ScriptDirectory(str(_CORE_ALEMBIC_DIR))
        core_head = scripts.get_current_head()
        crm_parent = scripts.get_revision("0003").down_revision
        assert isinstance(crm_parent, str)

        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version_core"))
            ).scalar_one()
            assert version == core_head
        await engine.dispose()

        self._run_alembic("downgrade", crm_parent)

        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version_core"))
            ).scalar_one()
            assert version != core_head
            tables = (
                (
                    await conn.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                .scalars()
                .all()
            )
            for table in _CRM_SALES_TABLES:
                assert table not in tables  # the whole CRM/sales block is gone
        await engine.dispose()

        self._run_alembic("upgrade", "head")

        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version_core"))
            ).scalar_one()
            assert version == core_head
            tables = (
                (
                    await conn.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                .scalars()
                .all()
            )
            for table in _CRM_SALES_TABLES:
                assert table in tables  # the block is back
        await engine.dispose()
