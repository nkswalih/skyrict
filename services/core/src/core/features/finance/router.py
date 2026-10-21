"""Finance API routes - thin wrappers over :class:`FinanceService`.

Authorization uses the ``erp.finance.*`` keys resolved at request time:
``read`` for reads, ``write`` for mutations, ``approve`` for the money-moment
actions (post entry / approve invoice / close period). Responses use the
standard ``skyrict_common`` envelope; list endpoints are offset/limit paged
(``total`` reflects the returned page in v1).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import (
    get_finance_service,
    get_tenant_id,
    require_ingest_m2m_or_permission,
    require_permission,
)
from core.db.session import commit_writes, get_db
from core.domain.value_objects import SUPPORTED_CURRENCIES
from core.features.finance.schemas import (
    AccountCreateRequest,
    AccountResponse,
    ArAgingResponse,
    BalanceSheetResponse,
    ExchangeRateResponse,
    ExchangeRateWriteRequest,
    FiscalPeriodCreateRequest,
    FiscalPeriodResponse,
    FxContextResponse,
    InvoiceCreateRequest,
    InvoiceResponse,
    JournalEntryCreateRequest,
    JournalEntryResponse,
    PaymentApplyRequest,
    PaymentResponse,
    ProfitAndLossResponse,
    TrialBalanceResponse,
)
from core.features.finance.service import (
    FinanceService,
    InvoiceLineInput,
    JournalLineInput,
)
from skyrict_common.schemas import ListResponse, PaginationMeta, ResponseEnvelope

router = APIRouter(prefix="/finance", tags=["finance"])

# Module-level permission guards (B008: no calls in argument defaults).
require_finance_read = require_permission("erp.finance.read")
require_finance_write = require_permission("erp.finance.write")
require_finance_approve = require_permission("erp.finance.approve")
require_fx_read = require_permission("core.fx.read")
require_fx_write = require_permission("core.fx.write")
# The invoice list additionally accepts ai-agent's m2m ingest secret
# (CORE_AI_INGEST_TOKEN) so ``finance reindex`` can pull line history; every
# other route stays JWT-only (same posture as inventory catalog reads).
require_invoice_read_m2m = require_ingest_m2m_or_permission("erp.finance.read")


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


def _user_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["user_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------


@router.post("/accounts", response_model=ResponseEnvelope[AccountResponse], status_code=201)
async def create_account(
    body: AccountCreateRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AccountResponse]:
    account = await svc.create_account(
        tenant_id=_tenant_id(current_user),
        code=body.code,
        name=body.name,
        account_type=body.account_type,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=AccountResponse.model_validate(account))


@router.get("/accounts", response_model=ResponseEnvelope[list[AccountResponse]])
async def list_accounts(
    include_inactive: bool = False,
    current_user: dict[str, Any] = Depends(require_invoice_read_m2m),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[list[AccountResponse]]:
    accounts = await svc.list_accounts(_tenant_id(current_user), include_inactive=include_inactive)
    return ResponseEnvelope(data=[AccountResponse.model_validate(a) for a in accounts])


@router.delete("/accounts/{account_id}", response_model=ResponseEnvelope[AccountResponse])
async def deactivate_account(
    account_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AccountResponse]:
    account = await svc.deactivate_account(_tenant_id(current_user), account_id)
    await commit_writes(db)
    return ResponseEnvelope(data=AccountResponse.model_validate(account))


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------


@router.post(
    "/journal-entries", response_model=ResponseEnvelope[JournalEntryResponse], status_code=201
)
async def create_journal_entry(
    body: JournalEntryCreateRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[JournalEntryResponse]:
    entry = await svc.create_manual_entry(
        tenant_id=_tenant_id(current_user),
        entry_date=body.entry_date,
        memo=body.memo,
        lines=[
            JournalLineInput(account_code=line.account_code, debit=line.debit, credit=line.credit)
            for line in body.lines
        ],
    )
    await commit_writes(db)
    return ResponseEnvelope(data=JournalEntryResponse.model_validate(entry))


@router.get("/journal-entries", response_model=ListResponse[JournalEntryResponse])
async def list_journal_entries(
    status: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    offset: int = 0,
    limit: int = 50,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ListResponse[JournalEntryResponse]:
    entries = await svc.list_journal_entries(
        _tenant_id(current_user),
        status=_parse_entry_status(status),
        from_date=from_date,
        to_date=to_date,
        offset=offset,
        limit=limit,
    )
    total = await svc.count_journal_entries(
        _tenant_id(current_user),
        status=_parse_entry_status(status),
        from_date=from_date,
        to_date=to_date,
    )
    return ListResponse(
        data=[JournalEntryResponse.model_validate(e) for e in entries],
        meta=PaginationMeta.create(
            total=total, page=(offset // limit) + 1 if limit else 1, page_size=limit
        ),
    )


@router.get("/journal-entries/{entry_id}", response_model=ResponseEnvelope[JournalEntryResponse])
async def get_journal_entry(
    entry_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[JournalEntryResponse]:
    entry = await svc.get_journal_entry(_tenant_id(current_user), entry_id)
    return ResponseEnvelope(data=JournalEntryResponse.model_validate(entry))


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=ResponseEnvelope[JournalEntryResponse],
)
async def post_journal_entry(
    entry_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_approve),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[JournalEntryResponse]:
    entry = await svc.post_journal_entry(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        entry_id=entry_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=JournalEntryResponse.model_validate(entry))


@router.post(
    "/journal-entries/{entry_id}/void",
    response_model=ResponseEnvelope[JournalEntryResponse],
)
async def void_journal_entry(
    entry_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[JournalEntryResponse]:
    entry = await svc.void_journal_entry(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        entry_id=entry_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=JournalEntryResponse.model_validate(entry))


# ---------------------------------------------------------------------------
# Fiscal periods
# ---------------------------------------------------------------------------


@router.post(
    "/fiscal-periods", response_model=ResponseEnvelope[FiscalPeriodResponse], status_code=201
)
async def create_fiscal_period(
    body: FiscalPeriodCreateRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[FiscalPeriodResponse]:
    period = await svc.create_fiscal_period(
        tenant_id=_tenant_id(current_user),
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=FiscalPeriodResponse.model_validate(period))


@router.get("/fiscal-periods", response_model=ResponseEnvelope[list[FiscalPeriodResponse]])
async def list_fiscal_periods(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[list[FiscalPeriodResponse]]:
    periods = await svc.list_fiscal_periods(_tenant_id(current_user))
    return ResponseEnvelope(data=[FiscalPeriodResponse.model_validate(p) for p in periods])


@router.post(
    "/fiscal-periods/{period_id}/close",
    response_model=ResponseEnvelope[FiscalPeriodResponse],
)
async def close_fiscal_period(
    period_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_approve),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[FiscalPeriodResponse]:
    period = await svc.close_fiscal_period(_tenant_id(current_user), period_id)
    await commit_writes(db)
    return ResponseEnvelope(data=FiscalPeriodResponse.model_validate(period))


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


@router.post("/invoices", response_model=ResponseEnvelope[InvoiceResponse], status_code=201)
async def create_invoice(
    body: InvoiceCreateRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[InvoiceResponse]:
    invoice = await svc.create_manual_invoice(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        customer_id=body.customer_id,
        invoice_date=body.invoice_date,
        due_date=body.due_date,
        currency=body.currency,
        lines=[
            InvoiceLineInput(
                description=line.description,
                account_code=line.account_code,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
            for line in body.lines
        ],
    )
    await commit_writes(db)
    return ResponseEnvelope(data=InvoiceResponse.model_validate(invoice))


@router.get("/invoices", response_model=ListResponse[InvoiceResponse])
async def list_invoices(
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
    _: dict[str, object] = Depends(require_invoice_read_m2m),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    svc: FinanceService = Depends(get_finance_service),
) -> ListResponse[InvoiceResponse]:
    invoices, customer_names = await svc.list_invoices_with_customer_names(
        tenant_id,
        status=_parse_invoice_status(status),
        offset=offset,
        limit=limit,
    )
    order_numbers = await svc.resolve_source_order_numbers(invoices, tenant_id)
    data = []
    for inv in invoices:
        resp = InvoiceResponse.model_validate(inv)
        resp.customer_name = customer_names.get(inv.customer_id)
        resp.source_order_number = order_numbers.get(inv.source_ref) if inv.source_ref else None
        data.append(resp)
    total = await svc.count_invoices(tenant_id, status=_parse_invoice_status(status))
    return ListResponse(
        data=data,
        meta=PaginationMeta.create(
            total=total, page=(offset // limit) + 1 if limit else 1, page_size=limit
        ),
    )


@router.get("/invoices/{invoice_id}", response_model=ResponseEnvelope[InvoiceResponse])
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[InvoiceResponse]:
    tenant_id = _tenant_id(current_user)
    invoice, customer_name = await svc.get_invoice_with_customer_name(tenant_id, invoice_id)
    resp = InvoiceResponse.model_validate(invoice)
    resp.customer_name = customer_name
    order_numbers = await svc.resolve_source_order_numbers([invoice], tenant_id)
    resp.source_order_number = order_numbers.get(invoice.source_ref) if invoice.source_ref else None
    return ResponseEnvelope(data=resp)


@router.post("/invoices/{invoice_id}/issue", response_model=ResponseEnvelope[InvoiceResponse])
async def issue_invoice(
    invoice_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[InvoiceResponse]:
    invoice = await svc.issue_invoice(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        invoice_id=invoice_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=InvoiceResponse.model_validate(invoice))


@router.post(
    "/invoices/{invoice_id}/approve",
    response_model=ResponseEnvelope[InvoiceResponse],
)
async def approve_invoice(
    invoice_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_approve),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[InvoiceResponse]:
    invoice = await svc.approve_invoice(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        invoice_id=invoice_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=InvoiceResponse.model_validate(invoice))


@router.post("/invoices/{invoice_id}/void", response_model=ResponseEnvelope[InvoiceResponse])
async def void_invoice(
    invoice_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[InvoiceResponse]:
    invoice = await svc.void_invoice(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        invoice_id=invoice_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=InvoiceResponse.model_validate(invoice))


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=ResponseEnvelope[PaymentResponse],
    status_code=201,
)
async def apply_payment(
    invoice_id: uuid.UUID,
    body: PaymentApplyRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[PaymentResponse]:
    payment = await svc.apply_payment(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        invoice_id=invoice_id,
        amount=body.amount,
        method=body.method,
        paid_at=body.paid_at,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=PaymentResponse.model_validate(payment))


@router.get("/payments/{payment_id}", response_model=ResponseEnvelope[PaymentResponse])
async def get_payment(
    payment_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[PaymentResponse]:
    payment = await svc.get_payment(_tenant_id(current_user), payment_id)
    return ResponseEnvelope(data=PaymentResponse.model_validate(payment))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/reports/trial-balance", response_model=ResponseEnvelope[TrialBalanceResponse])
async def get_trial_balance(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[TrialBalanceResponse]:
    report = await svc.trial_balance(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=TrialBalanceResponse.model_validate(report))


@router.get("/reports/profit-and-loss", response_model=ResponseEnvelope[ProfitAndLossResponse])
async def get_profit_and_loss(
    from_date: date,
    to_date: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[ProfitAndLossResponse]:
    report = await svc.profit_and_loss(_tenant_id(current_user), from_date, to_date)
    return ResponseEnvelope(data=ProfitAndLossResponse.model_validate(report))


@router.get("/reports/balance-sheet", response_model=ResponseEnvelope[BalanceSheetResponse])
async def get_balance_sheet(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[BalanceSheetResponse]:
    report = await svc.balance_sheet(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=BalanceSheetResponse.model_validate(report))


@router.get("/reports/ar-aging", response_model=ResponseEnvelope[ArAgingResponse])
async def get_ar_aging(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[ArAgingResponse]:
    report = await svc.ar_aging(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=ArAgingResponse.model_validate(report))


# ---------------------------------------------------------------------------
# FX rates (SKY-67 C2)
# ---------------------------------------------------------------------------


@router.get("/fx/context", response_model=ResponseEnvelope[FxContextResponse])
async def get_fx_context(
    current_user: dict[str, Any] = Depends(require_fx_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[FxContextResponse]:
    tenant_id = _tenant_id(current_user)
    return ResponseEnvelope(
        data=FxContextResponse(
            default_currency=await svc.default_currency(tenant_id),
            currencies=sorted(SUPPORTED_CURRENCIES),
        )
    )


@router.get("/fx/rates", response_model=ListResponse[ExchangeRateResponse])
async def list_fx_rates(
    currency: str | None = Query(default=None, max_length=3),
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    current_user: dict[str, Any] = Depends(require_fx_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ListResponse[ExchangeRateResponse]:
    rates = await svc.list_exchange_rates(_tenant_id(current_user), currency=currency)
    page = rates[offset : offset + limit]
    return ListResponse(
        data=[ExchangeRateResponse.model_validate(rate) for rate in page],
        meta=PaginationMeta.create(
            total=len(rates), page=(offset // limit) + 1 if limit else 1, page_size=limit
        ),
    )


@router.get(
    "/fx/rates/{quote_currency}",
    response_model=ResponseEnvelope[ExchangeRateResponse],
)
async def get_fx_rate(
    quote_currency: str,
    on: date = Query(default_factory=date.today),
    current_user: dict[str, Any] = Depends(require_fx_read),
    svc: FinanceService = Depends(get_finance_service),
) -> ResponseEnvelope[ExchangeRateResponse]:
    rate = await svc.exchange_rate_to_default(
        _tenant_id(current_user), quote_currency=quote_currency, on_date=on
    )
    return ResponseEnvelope(data=ExchangeRateResponse.model_validate(rate))


@router.put("/fx/rates", response_model=ResponseEnvelope[ExchangeRateResponse])
async def put_fx_rate(
    body: ExchangeRateWriteRequest,
    current_user: dict[str, Any] = Depends(require_fx_write),
    svc: FinanceService = Depends(get_finance_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[ExchangeRateResponse]:
    rate = await svc.set_exchange_rate(
        _tenant_id(current_user),
        base_currency=body.base_currency,
        quote_currency=body.quote_currency,
        effective_date=body.effective_date,
        rate=body.rate,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=ExchangeRateResponse.model_validate(rate))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_entry_status(value: str | None) -> Any:
    if value is None:
        return None
    from core.domain.value_objects import EntryStatus

    return EntryStatus(value)


def _parse_invoice_status(value: str | None) -> Any:
    if value is None:
        return None
    from core.domain.value_objects import InvoiceStatus

    return InvoiceStatus(value)
