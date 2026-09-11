"""Seed approved invoice history so the A3/A4 finance demo can be tested.

FIN-AI-003 A3/A4 abstain until a tenant has ≥3 distinct months of invoicing
history (chat) / approved revenue (forecast). New demo tenants often have
only a few weeks of invoices, so this seed backfills 8 months of APPROVED
invoices (``INV-HIST-<YEAR>-<MM>-<seq>``) for one tenant, which both activates
the forecast and gives the walk-forward backtest room to narrow its band as
history grows.

Non-destructive and idempotent: it never touches existing rows and skips any
invoice number that already exists; if the tenant already has ≥3 distinct
approved months it does nothing.

Usage:
    core seed-revenue-history --tenant-id <UUID>
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import distinct, func, select

from core.db.session import async_session_factory
from core.domain.value_objects import InvoiceStatus
from core.features.crm.models.customer import ErpCrmCustomerModel
from core.features.finance.models.chart_of_account import ErpChartOfAccountModel
from core.features.finance.models.invoice import ErpInvoiceModel
from core.features.finance.models.invoice_line import ErpInvoiceLineModel
from core.features.revenue_forecast.calculator import MIN_HISTORY_MONTHS

if TYPE_CHECKING:
    import uuid

logger = structlog.get_logger("core.seed.revenue_history")

_REVENUE_ACCOUNT_CODE = "4010"

# Monthly recognised-revenue totals (USD) for the 8 seeded months, oldest first.
# A gentle upward drift so the walk-forward backtest produces a meaningful MAPE.
_MONTHLY_TOTALS = [
    Decimal("24000"),
    Decimal("26000"),
    Decimal("23000"),
    Decimal("30000"),
    Decimal("34000"),
    Decimal("36000"),
    Decimal("40000"),
    Decimal("38000"),
]


def _first_of_month(offset_months_back: int) -> date:
    today = date.today()
    total = today.year * 12 + (today.month - 1) - offset_months_back
    return date(total // 12, total % 12 + 1, 1)


async def seed_revenue_history(tenant_id: uuid.UUID) -> dict[str, int]:
    """Backfill 8 months of APPROVED invoices for the tenant (idempotent).

    Returns counts (``invoices``, ``lines``) created, or ``skipped`` = 1 when
    the tenant already meets the MIN history floor.
    """
    async with async_session_factory() as session:
        existing_months = await session.scalar(
            select(
                func.count(distinct(func.date_trunc("month", ErpInvoiceModel.invoice_date)))
            ).where(
                ErpInvoiceModel.tenant_id == tenant_id,
                ErpInvoiceModel.status == InvoiceStatus.APPROVED,
            )
        )
        if existing_months and existing_months >= MIN_HISTORY_MONTHS:
            logger.info(
                "seed.revenue_history.skip.ready",
                tenant_id=str(tenant_id),
                months=existing_months,
            )
            return {"skipped": 1}

        customers = (
            (
                await session.execute(
                    select(ErpCrmCustomerModel)
                    .where(
                        ErpCrmCustomerModel.tenant_id == tenant_id,
                        ErpCrmCustomerModel.is_active.is_(True),
                    )
                    .order_by(ErpCrmCustomerModel.customer_code)
                )
            )
            .scalars()
            .all()
        )
        if not customers:
            raise RuntimeError(
                f"No active customers found for tenant {tenant_id}; seed CRM data first."
            )

        revenue = (
            await session.execute(
                select(ErpChartOfAccountModel).where(
                    ErpChartOfAccountModel.tenant_id == tenant_id,
                    ErpChartOfAccountModel.code == _REVENUE_ACCOUNT_CODE,
                )
            )
        ).scalar_one_or_none()
        if revenue is None:
            raise RuntimeError(
                f"Revenue account {_REVENUE_ACCOUNT_CODE} not found for tenant {tenant_id}."
            )

        existing = set(
            (
                await session.execute(
                    select(ErpInvoiceModel.invoice_number).where(
                        ErpInvoiceModel.tenant_id == tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )

        invoices = 0
        lines = 0
        for month_offset in range(len(_MONTHLY_TOTALS), 0, -1):
            month = _first_of_month(month_offset)
            total = _MONTHLY_TOTALS[len(_MONTHLY_TOTALS) - month_offset]
            for seq in (1, 2):
                number = f"INV-HIST-{month.year:04d}-{month.month:02d}-{seq:02d}"
                if number in existing:
                    logger.info("seed.revenue_history.skip.exists", number=number)
                    continue

                amount = (total / 2) if seq == 1 else (total - total / 2)
                invoice_date = month + timedelta(days=3 if seq == 1 else 18)
                approved_at = datetime.combine(
                    invoice_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                )
                customer = customers[(invoices + seq) % len(customers)]
                inv = ErpInvoiceModel(
                    tenant_id=tenant_id,
                    invoice_number=number,
                    customer_id=customer.id,
                    invoice_date=invoice_date,
                    due_date=invoice_date + timedelta(days=30),
                    status=InvoiceStatus.APPROVED,
                    total=amount.quantize(Decimal("0.01")),
                    currency="USD",
                    exchange_rate=Decimal("1"),
                    source="manual",
                    source_ref=None,
                    approved_at=approved_at,
                )
                session.add(inv)
                await session.flush()

                session.add(
                    ErpInvoiceLineModel(
                        tenant_id=tenant_id,
                        invoice_id=inv.id,
                        line_no=1,
                        description=f"Revenue history backfill ({month:%b %Y})",
                        account_id=revenue.id,
                        quantity=Decimal("1"),
                        unit_price=inv.total,
                        amount=inv.total,
                    )
                )
                invoices += 1
                lines += 1
                logger.info(
                    "seed.revenue_history.created",
                    number=number,
                    date=str(invoice_date),
                    total=str(inv.total),
                )

        await session.commit()
        return {"invoices": invoices, "lines": lines}
