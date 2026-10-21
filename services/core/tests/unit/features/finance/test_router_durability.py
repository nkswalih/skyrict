"""Finance write routes must commit before they return.

``get_db`` commits in the dependency teardown, which runs at the tail of the
request; a route that returns first lets the client's immediate re-read race
the commit (see ``core.db.session.commit_writes``). The API durability suite
covers the behaviour end to end; this guards the handler contract so a future
refactor cannot silently drop ``commit_writes`` from a money-mutating route.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

from core.features.finance import automation, router
from core.features.finance.schemas import (
    InvoiceCreateRequest,
    InvoiceLineRequest,
    JournalEntryCreateRequest,
    JournalLineRequest,
    PaymentApplyRequest,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_USER = {"tenant_id": uuid.uuid4(), "user_id": uuid.uuid4()}


def _journal_entry_body() -> JournalEntryCreateRequest:
    return JournalEntryCreateRequest(
        entry_date=date.today(),
        memo="durability",
        lines=[
            JournalLineRequest(account_code="1200", debit=Decimal("1.00")),
            JournalLineRequest(account_code="4000", credit=Decimal("1.00")),
        ],
    )


def _invoice_body() -> InvoiceCreateRequest:
    return InvoiceCreateRequest(
        customer_id=uuid.uuid4(),
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        lines=[
            InvoiceLineRequest(
                description="durability",
                account_code="4000",
                quantity=Decimal("1"),
                unit_price=Decimal("1.00"),
            )
        ],
    )


def _payment_body() -> PaymentApplyRequest:
    return PaymentApplyRequest(
        amount=Decimal("1.00"),
        method="bank_transfer",
        paid_at=datetime.now(UTC),
    )


async def _assert_commits(
    module: Any,
    handler: Callable[..., Awaitable[Any]],
    kwargs: dict[str, Any],
    response_symbol: str,
) -> None:
    db = AsyncMock()
    svc = AsyncMock()
    with (
        patch.object(module, response_symbol) as response,
        patch.object(module, "commit_writes", new_callable=AsyncMock) as commit,
    ):
        response.model_validate.return_value = object()
        await handler(**kwargs, current_user=_USER, svc=svc, db=db)
    commit.assert_awaited_once_with(db)


async def test_create_journal_entry_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.create_journal_entry,
        {"body": _journal_entry_body()},
        "JournalEntryResponse",
    )


async def test_post_journal_entry_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.post_journal_entry,
        {"entry_id": uuid.uuid4()},
        "JournalEntryResponse",
    )


async def test_reverse_journal_entry_commits_before_returning() -> None:
    await _assert_commits(
        automation,
        automation.reverse_journal_entry,
        {"entry_id": uuid.uuid4()},
        "JournalEntryResponse",
    )


async def test_create_invoice_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.create_invoice,
        {"body": _invoice_body()},
        "InvoiceResponse",
    )


async def test_issue_invoice_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.issue_invoice,
        {"invoice_id": uuid.uuid4()},
        "InvoiceResponse",
    )


async def test_approve_invoice_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.approve_invoice,
        {"invoice_id": uuid.uuid4()},
        "InvoiceResponse",
    )


async def test_apply_payment_commits_before_returning() -> None:
    await _assert_commits(
        router,
        router.apply_payment,
        {"invoice_id": uuid.uuid4(), "body": _payment_body()},
        "PaymentResponse",
    )
