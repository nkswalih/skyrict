"""Finance automation repo regression tests - verified against REAL Postgres.

Covers the SKY-56/SKY-64 wave-1 read-models that live in
:class:`core.features.finance.repository.FinanceRepository`:

- close_checklist (B2) - prior-period / posted-entries / balanced-TB gates;
- duplicates (B10) - grouped by memo + entry date;
- tenant settings KV round-trip;
- ai anomaly/suggestion upsert dedupe;
- journal entry reversal (B8) - marks a posted entry REVERSED; concurrent reversals can only flip it once.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from core.core.audit_service import AuditService
from core.db.audit_repository import AuditLogRepository
from core.db.session import async_session_factory, engine
from core.domain.entities import AuditLogEntry
from core.domain.value_objects import AccountType, EntryStatus, InvoiceStatus, PaymentStatus
from core.features.finance.automation import FinanceAutomationService
from core.features.finance.models.chart_of_account import ErpChartOfAccountModel
from core.features.finance.models.fiscal_period import ErpFiscalPeriodModel
from core.features.finance.models.invoice import ErpInvoiceModel
from core.features.finance.models.journal_entry import ErpJournalEntryModel
from core.features.finance.models.journal_line import ErpJournalLineModel
from core.features.finance.models.payment import ErpPaymentModel
from core.features.finance.repository import FinanceRepository
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration

PIVOT = date(2026, 6, 30)


@pytest.fixture(scope="module")
def automation_world(migrated_schema: None) -> dict[str, str]:
    """Seed one tenant with posted journal entries, an open period, and an invoice."""

    async def _setup() -> dict[str, str]:
        tenant_id = uuid.uuid4()
        periods = [
            ("2025 Q4", date(2025, 10, 1), date(2025, 12, 31), True),
            ("2026 Q1", date(2026, 1, 1), date(2026, 3, 31), False),
        ]
        accounts = [
            ("1100", "Cash", AccountType.ASSET),
            ("4000", "Service Revenue", AccountType.REVENUE),
        ]
        async with async_session_factory() as session:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name="Automation Tenant",
                    slug=f"auto-{tenant_id.hex[:8]}",
                    plan_tier="free",
                    is_active=True,
                )
            )
            await session.flush()
            account_ids: list[uuid.UUID] = []
            for code, name, acct_type in accounts:
                acc = ErpChartOfAccountModel(
                    tenant_id=tenant_id, code=code, name=name, account_type=acct_type
                )
                session.add(acc)
                await session.flush()
                account_ids.append(acc.id)

            period_ids: list[uuid.UUID] = []
            for name, start, end, closed in periods:
                p = ErpFiscalPeriodModel(
                    tenant_id=tenant_id,
                    name=name,
                    start_date=start,
                    end_date=end,
                    is_closed=closed,
                )
                session.add(p)
                await session.flush()
                period_ids.append(p.id)

            # Two posted journal entries with the SAME memo + entry date -> duplicate group.
            for _ in range(2):
                je = ErpJournalEntryModel(
                    tenant_id=tenant_id,
                    entry_date=date(2026, 2, 10),
                    memo="February rent",
                    status=EntryStatus.POSTED,
                    source="manual",
                    source_ref=None,
                    posted_at=PIVOT - timedelta(days=100),
                )
                session.add(je)
                await session.flush()
                session.add(
                    ErpJournalLineModel(
                        tenant_id=tenant_id,
                        entry_id=je.id,
                        account_id=account_ids[0],
                        debit=Decimal("1000"),
                        credit=None,
                    )
                )
                session.add(
                    ErpJournalLineModel(
                        tenant_id=tenant_id,
                        entry_id=je.id,
                        account_id=account_ids[1],
                        debit=None,
                        credit=Decimal("1000"),
                    )
                )

            # An approved invoice due >90 days past -> over_90 aging bucket.
            session.add(
                ErpInvoiceModel(
                    tenant_id=tenant_id,
                    invoice_number="AUT-001",
                    customer_id=uuid.uuid4(),
                    invoice_date=PIVOT - timedelta(days=200),
                    due_date=PIVOT - timedelta(days=120),
                    status=InvoiceStatus.APPROVED,
                    total=Decimal("500"),
                    source="manual",
                    source_ref=None,
                )
            )
            await session.commit()
            await engine.dispose()
        return {"tenant_id": str(tenant_id), "period_id": str(period_ids[1])}

    async def _teardown(created: str) -> None:
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tid"), {"tid": uuid.UUID(created)}
            )
            await session.commit()
            await engine.dispose()

    created = asyncio.run(_setup())
    try:
        yield created
    finally:
        asyncio.run(_teardown(created["tenant_id"]))


async def test_close_checklist_returns_gates(automation_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    period_id = uuid.UUID(automation_world["period_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        checklist = await repo.close_checklist(tenant_id, period_id)
        await session.rollback()

    assert checklist.period_name == "2026 Q1"
    labels = [item.label for item in checklist.items]
    assert "Trial balance balanced" in labels
    assert any(
        item.label == "Previous period closed" and item.status == "ok" for item in checklist.items
    )


async def test_duplicates_groups_by_memo_and_date(automation_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        groups = await repo.duplicates(tenant_id)
        await session.rollback()

    assert any(g.key.startswith("February rent") and len(g.entries) == 2 for g in groups)


async def test_working_capital_alert_threshold(automation_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        alert = await repo.working_capital_alert(tenant_id, PIVOT)
        await session.rollback()
    assert isinstance(alert.ratio, Decimal)
    assert alert.threshold == Decimal("1.5")


async def test_tenant_setting_roundtrip() -> None:
    tenant_id = uuid.uuid4()
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        await repo.upsert_tenant_setting(tenant_id, "wc_threshold", "2.0")
        setting = await repo.get_tenant_setting(tenant_id, "wc_threshold")
        assert setting is not None and setting.value == "2.0"
        # upsert updates in place (dedupe on tenant+key)
        await repo.upsert_tenant_setting(tenant_id, "wc_threshold", "1.25")
        again = await repo.get_tenant_setting(tenant_id, "wc_threshold")
        assert again is not None and again.value == "1.25"
        await session.rollback()


async def test_ai_anomaly_upsert_dedupes(automation_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    entity_id = uuid.uuid4()
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        from core.domain.entities import AiFinanceAnomaly

        await repo.upsert_ai_anomaly(
            tenant_id,
            AiFinanceAnomaly(
                tenant_id=tenant_id,
                entity_type="journal_entry",
                entity_id=entity_id,
                anomaly_type="duplicate_entry",
                severity="medium",
                description="first",
            ),
        )
        await repo.upsert_ai_anomaly(
            tenant_id,
            AiFinanceAnomaly(
                tenant_id=tenant_id,
                entity_type="journal_entry",
                entity_id=entity_id,
                anomaly_type="duplicate_entry",
                severity="high",
                description="updated",
            ),
        )
        open_anomalies = await repo.list_open_ai_anomalies(tenant_id)
        matches = [a for a in open_anomalies if a.entity_id == entity_id]
        assert len(matches) == 1
        assert matches[0].severity == "high"
        await session.rollback()


async def test_reverse_marks_posted_entry_reversed(automation_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        entries = await repo.list_journal_entries(tenant_id, status=EntryStatus.POSTED)
        entry = entries[0]
        reversed_entry = await repo.reverse_journal_entry(
            entry.id,
            tenant_id,
            reversed_by_user_id=uuid.uuid4(),
            reversed_at=PIVOT,
        )
        await session.rollback()

    assert reversed_entry is not None
    assert reversed_entry.status == EntryStatus.REVERSED


async def test_concurrent_reversals_only_one_wins(migrated_schema: None) -> None:
    """Two sessions racing to reverse the same posted entry - exactly one wins.

    Regression for the non-atomic select-then-mutate reversal: both racers used
    to read POSTED in their own transaction and both flipped the status, doubling
    the reversal and its audit event. The guarded UPDATE now serialises them and
    the loser matches zero rows.
    """
    tenant_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    async with async_session_factory() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Race Tenant",
                slug=f"race-{tenant_id.hex[:8]}",
                plan_tier="free",
                is_active=True,
            )
        )
        await session.flush()
        account = ErpChartOfAccountModel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code="1100",
            name="Cash",
            account_type=AccountType.ASSET,
        )
        session.add(account)
        await session.flush()
        entry = ErpJournalEntryModel(
            tenant_id=tenant_id,
            id=entry_id,
            entry_date=date(2026, 6, 1),
            memo="race reversal",
            status=EntryStatus.POSTED,
            source="manual",
            source_ref=None,
            posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        session.add(entry)
        await session.flush()
        session.add(
            ErpJournalLineModel(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=account.id,
                debit=Decimal("100"),
                credit=None,
                currency="USD",
            )
        )
        await session.commit()

    async def _reverse() -> bool:
        async with async_session_factory() as session:
            repo = FinanceRepository(session)
            got = await repo.reverse_journal_entry(
                entry_id,
                tenant_id,
                reversed_by_user_id=uuid.uuid4(),
                reversed_at=PIVOT,
            )
            await session.commit()
            return got is not None

    async with asyncio.TaskGroup() as tg:
        racer_a = tg.create_task(_reverse())
        racer_b = tg.create_task(_reverse())

    wins = sum([await racer_a, await racer_b])
    assert wins == 1


async def test_concurrent_posts_only_one_wins(migrated_schema: None) -> None:
    """Two sessions posting the same DRAFT entry - exactly one wins.

    Regression for the unguarded select-then-mutate post: both racers used to
    read DRAFT and both flushed POSTED, so two callers got success, two audit
    ``FINANCE_JOURNAL_ENTRY_POSTED`` events fired, and the money event was
    emitted twice. The guarded UPDATE now serialises them and the loser matches
    zero rows.
    """
    tenant_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    async with async_session_factory() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Post Race Tenant",
                slug=f"postrace-{tenant_id.hex[:8]}",
                plan_tier="free",
                is_active=True,
            )
        )
        await session.flush()
        account = ErpChartOfAccountModel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code="1100",
            name="Cash",
            account_type=AccountType.ASSET,
        )
        session.add(account)
        await session.flush()
        session.add(
            ErpJournalEntryModel(
                tenant_id=tenant_id,
                id=entry_id,
                entry_date=date(2026, 6, 1),
                memo="race post",
                status=EntryStatus.DRAFT,
                source="manual",
                source_ref=None,
            )
        )
        await session.commit()

    async def _post() -> bool:
        async with async_session_factory() as session:
            repo = FinanceRepository(session)
            got = await repo.post_journal_entry(
                entry_id,
                tenant_id,
                posted_by_user_id=uuid.uuid4(),
                posted_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
            await session.commit()
            return got is not None

    async with asyncio.TaskGroup() as tg:
        racer_a = tg.create_task(_post())
        racer_b = tg.create_task(_post())

    wins = sum([await racer_a, await racer_b])
    assert wins == 1


async def test_concurrent_issues_only_one_wins(migrated_schema: None) -> None:
    """Two sessions issuing the same DRAFT invoice - exactly one wins.

    Regression for the unguarded select-then-mutate issue/approve/void/mark-paid
    family: both racers used to read DRAFT and both flip ISSUED, emitting two
    ``FINANCE_INVOICE_ISSUED`` audits. The guarded UPDATE now serialises them
    and the loser matches zero rows.
    """
    tenant_id = uuid.uuid4()
    invoice_id = uuid.uuid4()
    async with async_session_factory() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Issue Race Tenant",
                slug=f"issuerace-{tenant_id.hex[:8]}",
                plan_tier="free",
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            ErpInvoiceModel(
                id=invoice_id,
                tenant_id=tenant_id,
                invoice_number="RACE-0001",
                customer_id=uuid.uuid4(),
                invoice_date=date(2026, 6, 1),
                due_date=date(2026, 7, 1),
                total=Decimal("200"),
                status=InvoiceStatus.DRAFT,
                currency="USD",
            )
        )
        await session.commit()

    async def _issue() -> bool:
        async with async_session_factory() as session:
            repo = FinanceRepository(session)
            got = await repo.issue_invoice(
                invoice_id, tenant_id, issued_at=datetime(2026, 6, 1, tzinfo=UTC)
            )
            await session.commit()
            return got is not None

    async with asyncio.TaskGroup() as tg:
        racer_a = tg.create_task(_issue())
        racer_b = tg.create_task(_issue())

    wins = sum([await racer_a, await racer_b])
    assert wins == 1


class _NoopAuditSink:
    async def log(self, **kwargs: object) -> None:
        pass


async def test_scan_closes_resolved_duplicate_anomaly(
    automation_world: dict[str, str],
) -> None:
    """A duplicate that was resolved (one copy reversed) stops surfacing.

    Regression: the anomaly scan only upserted anomalies and never closed one
    whose duplicate group no longer existed, so a stale open anomaly persisted
    across rescans and refreshes.
    """
    tenant_id = uuid.UUID(automation_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        svc = FinanceAutomationService(repo=repo, audit=_NoopAuditSink())
        detected = await svc.run_anomaly_scan(tenant_id)
        assert any(a.anomaly_type == "duplicate_entry" for a in detected)
        dup_group = next(g for g in await repo.duplicates(tenant_id))
        await repo.reverse_journal_entry(
            dup_group.entries[0].entry_id,
            tenant_id,
            reversed_by_user_id=uuid.uuid4(),
            reversed_at=PIVOT,
        )
        await svc.run_anomaly_scan(tenant_id)
        open_anomalies = await repo.list_open_ai_anomalies(tenant_id)
        assert not [a for a in open_anomalies if a.anomaly_type == "duplicate_entry"]
        await session.rollback()


@pytest.fixture(scope="module")
def wave2_world(migrated_schema: None) -> dict[str, str]:
    """Seed one tenant with wave-2 data: balanced entry, 2 invoices, applied payments."""

    async def _setup() -> dict[str, str]:
        tenant_id = uuid.uuid4()
        cust_a = uuid.uuid4()
        cust_b = uuid.uuid4()
        async with async_session_factory() as session:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name="Wave2 Tenant",
                    slug=f"w2-{tenant_id.hex[:8]}",
                    plan_tier="free",
                    is_active=True,
                )
            )
            await session.flush()
            account_ids: dict[str, uuid.UUID] = {}
            for code, name, acct_type in [
                ("1100", "Cash", AccountType.ASSET),
                ("2100", "Accounts Payable", AccountType.LIABILITY),
                ("4000", "Service Revenue", AccountType.REVENUE),
            ]:
                acc = ErpChartOfAccountModel(
                    tenant_id=tenant_id, code=code, name=name, account_type=acct_type
                )
                session.add(acc)
                await session.flush()
                account_ids[code] = acc.id

            je = ErpJournalEntryModel(
                tenant_id=tenant_id,
                entry_date=date(2026, 2, 10),
                memo="Balanced sale",
                status=EntryStatus.POSTED,
                source="manual",
                source_ref=None,
                posted_at=datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC),
            )
            session.add(je)
            await session.flush()
            session.add(
                ErpJournalLineModel(
                    tenant_id=tenant_id,
                    entry_id=je.id,
                    account_id=account_ids["1100"],
                    debit=Decimal("1000"),
                    credit=None,
                )
            )
            session.add(
                ErpJournalLineModel(
                    tenant_id=tenant_id,
                    entry_id=je.id,
                    account_id=account_ids["4000"],
                    debit=None,
                    credit=Decimal("1000"),
                )
            )

            inv_a = ErpInvoiceModel(
                tenant_id=tenant_id,
                invoice_number="W2-A",
                customer_id=cust_a,
                invoice_date=date(2026, 2, 1),
                due_date=date(2026, 3, 1),
                status=InvoiceStatus.APPROVED,
                total=Decimal("400"),
                source="manual",
                source_ref=None,
            )
            inv_b = ErpInvoiceModel(
                tenant_id=tenant_id,
                invoice_number="W2-B",
                customer_id=cust_b,
                invoice_date=date(2026, 3, 1),
                due_date=date(2026, 4, 1),
                status=InvoiceStatus.APPROVED,
                total=Decimal("100"),
                source="manual",
                source_ref=None,
            )
            session.add_all([inv_a, inv_b])
            await session.flush()
            # Applied payments: 2x card on A (400 total), 1x bank on B (100 total).
            payments = [
                ("PAY-1", inv_a.id, "card", Decimal("200"), date(2026, 2, 5)),
                ("PAY-2", inv_a.id, "card", Decimal("200"), date(2026, 2, 20)),
                ("PAY-3", inv_b.id, "bank", Decimal("100"), date(2026, 3, 10)),
            ]
            for number, invoice_id, method, amount, paid_on in payments:
                session.add(
                    ErpPaymentModel(
                        tenant_id=tenant_id,
                        payment_number=number,
                        invoice_id=invoice_id,
                        amount=amount,
                        method=method,
                        paid_at=datetime(
                            paid_on.year, paid_on.month, paid_on.day, 9, 0, 0, tzinfo=UTC
                        ),
                        status=PaymentStatus.APPLIED,
                        source="manual",
                        source_ref=None,
                    )
                )
            await session.commit()
            await engine.dispose()
        return {
            "tenant_id": str(tenant_id),
            "cust_a": str(cust_a),
            "cust_b": str(cust_b),
        }

    async def _teardown(created: str) -> None:
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tid"), {"tid": uuid.UUID(created)}
            )
            await session.commit()
            await engine.dispose()

    created = asyncio.run(_setup())
    try:
        yield created
    finally:
        asyncio.run(_teardown(created["tenant_id"]))


async def test_revenue_concentration_flags_top_customer(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    cust_a = uuid.UUID(wave2_world["cust_a"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        concentration = await repo.revenue_concentration(
            tenant_id, date(2026, 1, 1), date(2026, 12, 31)
        )
        await session.rollback()

    assert concentration.total_revenue == Decimal("500")
    assert len(concentration.entries) == 2
    top = concentration.entries[0]
    assert top.customer_id == cust_a
    assert top.amount == Decimal("400")
    assert top.share == Decimal("0.8")
    assert top.above_threshold is True
    assert concentration.entries[1].above_threshold is False


async def test_working_capital_series_shape(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        series = await repo.working_capital_series(tenant_id, date(2026, 6, 30), months=3)
        await session.rollback()

    assert len(series.positions) == 3
    months = [position.month for position in series.positions]
    assert months == sorted(months)
    for position in series.positions:
        assert isinstance(position.assets, Decimal)
        assert isinstance(position.liabilities, Decimal)
        assert position.working_capital == position.assets - position.liabilities


async def test_cashflow_projection_runs_on_postgres(wave2_world: dict[str, str]) -> None:
    """Regression: the monthly aggregation must group by the CAST'd trunc.

    The SKY-99 rewrite selected ``CAST(date_trunc(...) AS DATE)`` but grouped
    by the raw ``date_trunc(...)``, which Postgres rejected
    (``GROUPING ERROR: column due_date must appear in the GROUP BY``); the
    sqlite unit suite is laxer and never caught it. The benchmark harness did.
    """
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        projection = await repo.cashflow_projection(tenant_id, date(2026, 6, 30))
        await session.rollback()

    assert len(projection.positions) == 6
    months = [position.month for position in projection.positions]
    assert months == sorted(months)
    assert months[0] == "2026-06"
    for position in projection.positions:
        assert position.closing == position.opening + position.inflows - position.outflows


async def test_payment_method_analytics_groups_by_method(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        analytics = await repo.payment_method_analytics(
            tenant_id, date(2026, 1, 1), date(2026, 12, 31)
        )
        await session.rollback()

    assert analytics.total_amount == Decimal("500")
    by_method = {entry.method: entry for entry in analytics.entries}
    assert by_method["card"].count == 2
    assert by_method["card"].amount == Decimal("400")
    assert by_method["card"].share == Decimal("0.8")
    assert by_method["bank"].count == 1
    assert by_method["bank"].amount == Decimal("100")
    assert by_method["bank"].share == Decimal("0.2")


async def test_customer_payment_analytics_avg_days_and_consistency(
    wave2_world: dict[str, str],
) -> None:
    """B14 - slow-payer picture: days-to-pay mean and consistency per customer."""
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    cust_a = uuid.UUID(wave2_world["cust_a"])
    cust_b = uuid.UUID(wave2_world["cust_b"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        analytics = await repo.customer_payment_analytics(
            tenant_id, date(2026, 1, 1), date(2026, 12, 31)
        )
        await session.rollback()

    assert len(analytics.entries) == 2
    # cust_a first: higher total paid.
    top, bottom = analytics.entries
    assert top.customer_id == cust_a
    assert top.payment_count == 2
    assert top.total_paid == Decimal("400")
    assert top.avg_days_to_pay == Decimal("11.5")
    assert top.consistency_score == Decimal("0.3478")  # 1 - pstdev/mean
    assert bottom.customer_id == cust_b
    assert bottom.payment_count == 1
    assert bottom.total_paid == Decimal("100")
    assert bottom.avg_days_to_pay == Decimal("9")
    assert bottom.consistency_score is None  # single payment: no variance


async def test_health_score_weights_snapshot(wave2_world: dict[str, str]) -> None:
    """Pin SKY-64 health-score component weights to guard against drift."""
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        score = await repo.health_score(tenant_id, date(2026, 6, 30))
        await session.rollback()

    assert {component.name: component.weight for component in score.components} == {
        "working_capital": Decimal("0.4"),
        "receivables_aging": Decimal("0.3"),
        "journal_cleanliness": Decimal("0.3"),
    }
    assert sum((component.weight for component in score.components), Decimal("0")) == Decimal("1.0")
    assert Decimal("100.00") >= score.overall >= Decimal("0.00")


@pytest.fixture(scope="module")
def readiness_world(migrated_schema: None) -> dict[str, str]:
    """Seed one fully audit-ready tenant for B32 checks.

    Balanced posted entry, an open current fiscal period (covers today),
    one approved invoice due within 90 days (non-overdue AR), and no
    drafts/anomalies/duplicates.
    """

    async def _setup() -> dict[str, str]:
        tenant_id = uuid.uuid4()
        async with async_session_factory() as session:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name="Readiness Tenant",
                    slug=f"rdy-{tenant_id.hex[:8]}",
                    plan_tier="free",
                    is_active=True,
                )
            )
            await session.flush()
            account_ids: dict[str, uuid.UUID] = {}
            for code, name, acct_type in [
                ("1100", "Cash", AccountType.ASSET),
                ("2100", "Accounts Payable", AccountType.LIABILITY),
                ("4000", "Service Revenue", AccountType.REVENUE),
            ]:
                acc = ErpChartOfAccountModel(
                    tenant_id=tenant_id, code=code, name=name, account_type=acct_type
                )
                session.add(acc)
                await session.flush()
                account_ids[code] = acc.id

            # Anchored to today rather than a fixed quarter.
            #
            # Audit readiness counts a period as open when it is not closed and
            # its end date has not passed, so the hardcoded "2026 Q3" window this
            # fixture used to seed started failing the moment the calendar rolled
            # past 2026-09-30 - the suite broke on a date change, not a code
            # change. Deriving the window from today keeps the check meaningful on
            # any run date.
            today = date.today()
            session.add(
                ErpFiscalPeriodModel(
                    tenant_id=tenant_id,
                    name=f"{today.year} readiness period",
                    start_date=today - timedelta(days=60),
                    end_date=today + timedelta(days=60),
                    is_closed=False,
                )
            )

            je = ErpJournalEntryModel(
                tenant_id=tenant_id,
                entry_date=date(2026, 7, 15),
                memo="Q3 revenue",
                status=EntryStatus.POSTED,
                source="manual",
                source_ref=None,
                posted_at=datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC),
            )
            session.add(je)
            await session.flush()
            session.add(
                ErpJournalLineModel(
                    tenant_id=tenant_id,
                    entry_id=je.id,
                    account_id=account_ids["1100"],
                    debit=Decimal("1000"),
                    credit=None,
                )
            )
            session.add(
                ErpJournalLineModel(
                    tenant_id=tenant_id,
                    entry_id=je.id,
                    account_id=account_ids["4000"],
                    debit=None,
                    credit=Decimal("1000"),
                )
            )

            # Not overdue, matching this fixture's docstring. Anchored to the same `today`
            # as the period above so it cannot age into the over_90 bucket and
            # fail the receivables check a few weeks from now.
            session.add(
                ErpInvoiceModel(
                    tenant_id=tenant_id,
                    invoice_number="RDY-001",
                    customer_id=uuid.uuid4(),
                    invoice_date=today - timedelta(days=30),
                    due_date=today + timedelta(days=45),
                    status=InvoiceStatus.APPROVED,
                    total=Decimal("400"),
                    source="manual",
                    source_ref=None,
                )
            )
            await session.commit()
            await engine.dispose()
        return {"tenant_id": str(tenant_id)}

    async def _teardown(created: str) -> None:
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tid"), {"tid": uuid.UUID(created)}
            )
            await session.commit()
            await engine.dispose()

    created = asyncio.run(_setup())
    try:
        yield created
    finally:
        asyncio.run(_teardown(created["tenant_id"]))


async def test_audit_readiness_returns_eight_checks_all_ok(
    readiness_world: dict[str, str],
) -> None:
    tenant_id = uuid.UUID(readiness_world["tenant_id"])
    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        readiness = await repo.audit_readiness(tenant_id)
        await session.rollback()

    assert readiness.ready is True
    assert len(readiness.checks) >= 8
    for check in readiness.checks:
        assert check.status == "ok", f"{check.key}: {check.status} - {check.detail}"


async def test_audit_readiness_flags_draft_journal_entry(
    readiness_world: dict[str, str],
) -> None:
    tenant_id = uuid.UUID(readiness_world["tenant_id"])
    async with async_session_factory() as session:
        session.add(
            ErpJournalEntryModel(
                tenant_id=tenant_id,
                entry_date=date(2026, 8, 1),
                memo="Unposted draft",
                status=EntryStatus.DRAFT,
                source="manual",
                source_ref=None,
            )
        )
        await session.commit()
        await engine.dispose()

    async with async_session_factory() as session:
        repo = FinanceRepository(session)
        readiness = await repo.audit_readiness(tenant_id)
        await session.rollback()

    by_key = {check.key: check for check in readiness.checks}
    assert by_key["journal_entries_posted"].status == "missing"
    assert by_key["journal_entries_posted"].detail
    assert readiness.ready is False


async def _seed_audit_entries(tenant_id: uuid.UUID, repo: AuditLogRepository, n: int) -> None:
    for i in range(n):
        await repo.add(
            AuditLogEntry(
                tenant_id=tenant_id,
                action="invoice.approved",
                target=f"invoice:W2-{i}",
            )
        )


async def test_audit_repository_filter_and_count(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    actor = uuid.uuid4()
    async with async_session_factory() as session:
        repo = AuditLogRepository(session)
        for action, target in [
            ("invoice.approved", "invoice:W2-A"),
            ("invoice.approved", "invoice:W2-B"),
            ("payment.applied", "payment:PAY-1"),
        ]:
            await repo.add(
                AuditLogEntry(
                    tenant_id=tenant_id,
                    action=action,
                    target=target,
                    actor_user_id=actor if action == "payment.applied" else None,
                )
            )
        await session.flush()

        by_q = await repo.list(tenant_id, q="invoice")
        by_action = await repo.list(tenant_id, action="payment.applied")
        by_actor = await repo.list(tenant_id, actor_user_id=actor)
        total = await repo.count(tenant_id)
        await session.rollback()

    assert len(by_q) == 2
    assert len(by_action) == 1
    assert len(by_actor) == 1
    assert total == 3


async def test_audit_repository_pagination(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = AuditLogRepository(session)
        await _seed_audit_entries(tenant_id, repo, 5)
        await session.flush()
        first = await repo.list(tenant_id, offset=0, limit=2)
        second = await repo.list(tenant_id, offset=2, limit=2)
        total = await repo.count(tenant_id)
        await session.rollback()

    assert len(first) == 2
    assert len(second) == 2
    assert {e.id for e in first}.isdisjoint({e.id for e in second})
    assert total == 5


async def test_audit_service_search_returns_total(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = AuditLogRepository(session)
        await _seed_audit_entries(tenant_id, repo, 4)
        await session.flush()
        service = AuditService(repo)
        entries, total = await service.search(tenant_id, q="invoice", offset=0, limit=2)
        await session.rollback()

    assert total == 4
    assert len(entries) == 2


async def test_core_audit_log_hashes_chain(wave2_world: dict[str, str]) -> None:
    tenant_id = uuid.UUID(wave2_world["tenant_id"])
    async with async_session_factory() as session:
        repo = AuditLogRepository(session)
        first = await repo.add(
            AuditLogEntry(tenant_id=tenant_id, action="user.login", target="auth")
        )
        second = await repo.add(
            AuditLogEntry(tenant_id=tenant_id, action="user.logout", target="auth")
        )
        assert first.hash is not None
        assert second.prev_hash == first.hash
        await session.rollback()
