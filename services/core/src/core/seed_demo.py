"""Demo data seeding for Finance, HR, Payroll, and Sales modules.

10+ rows per entity for realistic demo/local workspaces.
Idempotent: skips if tenant already has data. Use ``--force`` to clear and reseed.

Usage:
    core seed-demo --tenant-id <UUID>
    core seed-demo --tenant-id <UUID> --force
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select, text

from core.db.session import async_session_factory
from core.domain.value_objects import (
    AccountType,
    CreditCheckResult,
    CrmEntityType,
    CrmTimelineEventType,
    EntryStatus,
    InvoiceStatus,
    OrderStatus,
    PaymentStatus,
    StockMovementType,
)
from core.features.crm.models.customer import ErpCrmCustomerModel
from core.features.crm.models.timeline_event import ErpCrmTimelineEventModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("core.seed.demo")


def _ago(days: float) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _opening_balance_rows(
    stock_levels: tuple[dict[str, object], ...],
    stock_movements: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Balancing ledger rows that back every seeded opening stock level.

    Stock levels are seeded as opening balances; core recomputes
    ``qty_on_hand`` as the sum of all non-reservation/release movements, so
    each level must be reconciled with a balancing movement entry or the
    AI-agent ledger-mismatch rule fires on demo data. Returns one row per
    level whose movement sum differs from ``on_hand`` (receipt when the
    balance is positive, issue when negative).
    """
    reservation_types = {"reservation", "release"}
    ledger_sum: dict[tuple[int, int], Decimal] = {}
    for mrow in stock_movements:
        if getattr(mrow["type"], "value", mrow["type"]) in reservation_types:
            continue
        key = (int(str(mrow["prod"])), int(str(mrow["wh"])))
        ledger_sum[key] = ledger_sum.get(key, Decimal(0)) + Decimal(str(mrow["qty"]))

    balance: list[dict[str, object]] = []
    for srow in stock_levels:
        prod_idx = int(str(srow["prod"]))
        wh_idx = int(str(srow["wh"]))
        delta = Decimal(str(srow["on_hand"])) - ledger_sum.get((prod_idx, wh_idx), Decimal(0))
        if delta == 0:
            continue
        balance.append(
            {
                "prod": prod_idx,
                "wh": wh_idx,
                "type": (StockMovementType.RECEIPT if delta > 0 else StockMovementType.ISSUE),
                "qty": delta,
            }
        )
    return balance


def _today() -> date:
    return date.today()


def _date_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def _date_ahead(days: int) -> date:
    return date.today() + timedelta(days=days)


# ═══════════════════════════════════════════════════════════════════════════
# HR DATA
# ═══════════════════════════════════════════════════════════════════════════

DEPARTMENT_ROWS: tuple[dict[str, object], ...] = (
    {"name": "Engineering", "is_active": True},
    {"name": "Product", "is_active": True},
    {"name": "Sales", "is_active": True},
    {"name": "Finance", "is_active": True},
    {"name": "Human Resources", "is_active": True},
    {"name": "Marketing", "is_active": True},
    {"name": "Operations", "is_active": True},
)

EMPLOYEE_ROWS: tuple[dict[str, object], ...] = (
    {
        "num": "EMP-0001",
        "first": "Alice",
        "last": "Johnson",
        "email": "alice.johnson@skyrict.com",
        "phone": "+1 415 555 0101",
        "dept": 0,
        "title": "Senior Software Engineer",
        "status": "active",
        "hire_days_ago": 730,
    },
    {
        "num": "EMP-0002",
        "first": "Bob",
        "last": "Williams",
        "email": "bob.williams@skyrict.com",
        "phone": "+1 415 555 0102",
        "dept": 0,
        "title": "Staff Engineer",
        "status": "active",
        "hire_days_ago": 1095,
    },
    {
        "num": "EMP-0003",
        "first": "Carol",
        "last": "Martinez",
        "email": "carol.martinez@skyrict.com",
        "phone": "+1 415 555 0103",
        "dept": 1,
        "title": "Product Manager",
        "status": "active",
        "hire_days_ago": 540,
    },
    {
        "num": "EMP-0004",
        "first": "David",
        "last": "Brown",
        "email": "david.brown@skyrict.com",
        "phone": "+1 415 555 0104",
        "dept": 2,
        "title": "Sales Director",
        "status": "active",
        "hire_days_ago": 900,
    },
    {
        "num": "EMP-0005",
        "first": "Emma",
        "last": "Davis",
        "email": "emma.davis@skyrict.com",
        "phone": "+1 415 555 0105",
        "dept": 3,
        "title": "Finance Manager",
        "status": "active",
        "hire_days_ago": 660,
    },
    {
        "num": "EMP-0006",
        "first": "Frank",
        "last": "Garcia",
        "email": "frank.garcia@skyrict.com",
        "phone": "+1 415 555 0106",
        "dept": 4,
        "title": "HR Business Partner",
        "status": "active",
        "hire_days_ago": 480,
    },
    {
        "num": "EMP-0007",
        "first": "Grace",
        "last": "Rodriguez",
        "email": "grace.rodriguez@skyrict.com",
        "phone": "+1 415 555 0107",
        "dept": 0,
        "title": "QA Engineer",
        "status": "on_leave",
        "hire_days_ago": 365,
    },
    {
        "num": "EMP-0008",
        "first": "Henry",
        "last": "Wilson",
        "email": "henry.wilson@skyrict.com",
        "phone": "+1 415 555 0108",
        "dept": 5,
        "title": "Marketing Manager",
        "status": "active",
        "hire_days_ago": 420,
    },
    {
        "num": "EMP-0009",
        "first": "Ivy",
        "last": "Anderson",
        "email": "ivy.anderson@skyrict.com",
        "phone": "+1 415 555 0109",
        "dept": 6,
        "title": "Operations Lead",
        "status": "active",
        "hire_days_ago": 300,
    },
    {
        "num": "EMP-0010",
        "first": "Jack",
        "last": "Thomas",
        "email": "jack.thomas@skyrict.com",
        "phone": "+1 415 555 0110",
        "dept": 2,
        "title": "Account Executive",
        "status": "active",
        "hire_days_ago": 240,
    },
    {
        "num": "EMP-0011",
        "first": "Karen",
        "last": "Jackson",
        "email": "karen.jackson@skyrict.com",
        "phone": "+1 415 555 0111",
        "dept": 0,
        "title": "DevOps Engineer",
        "status": "active",
        "hire_days_ago": 180,
    },
    {
        "num": "EMP-0012",
        "first": "Leo",
        "last": "White",
        "email": "leo.white@skyrict.com",
        "phone": "+1 415 555 0112",
        "dept": 1,
        "title": "UX Designer",
        "status": "active",
        "hire_days_ago": 120,
    },
    {
        "num": "EMP-0013",
        "first": "Mia",
        "last": "Harris",
        "email": "mia.harris@skyrict.com",
        "phone": "+1 415 555 0113",
        "dept": 3,
        "title": "Staff Accountant",
        "status": "active",
        "hire_days_ago": 90,
    },
    {
        "num": "EMP-0014",
        "first": "Noah",
        "last": "Clark",
        "email": "noah.clark@skyrict.com",
        "phone": "+1 415 555 0114",
        "dept": 2,
        "title": "Sales Representative",
        "status": "terminated",
        "hire_days_ago": 500,
        "term_days_ago": 30,
    },
    {
        "num": "EMP-0015",
        "first": "Olivia",
        "last": "Lewis",
        "email": "olivia.lewis@skyrict.com",
        "phone": "+1 415 555 0115",
        "dept": 5,
        "title": "Content Strategist",
        "status": "active",
        "hire_days_ago": 60,
    },
)

LEAVE_REQUEST_ROWS: tuple[dict[str, object], ...] = (
    {
        "emp": 0,
        "type": "annual",
        "start_days": -10,
        "end_days": -7,
        "days": 4,
        "status": "approved",
        "reason": "Family vacation",
    },
    {
        "emp": 2,
        "type": "annual",
        "start_days": -5,
        "end_days": -3,
        "days": 3,
        "status": "approved",
        "reason": "Personal trip",
    },
    {
        "emp": 3,
        "type": "sick",
        "start_days": -2,
        "end_days": -2,
        "days": 1,
        "status": "approved",
        "reason": "Feeling unwell",
    },
    {
        "emp": 7,
        "type": "annual",
        "start_days": 5,
        "end_days": 7,
        "days": 3,
        "status": "pending",
        "reason": "Long weekend trip",
    },
    {
        "emp": 8,
        "type": "sick",
        "start_days": -1,
        "end_days": -1,
        "days": 1,
        "status": "approved",
        "reason": "Doctor appointment",
    },
    {
        "emp": 10,
        "type": "annual",
        "start_days": 10,
        "end_days": 14,
        "days": 5,
        "status": "pending",
        "reason": "Conference attendance",
    },
    {
        "emp": 11,
        "type": "unpaid",
        "start_days": 15,
        "end_days": 20,
        "days": 6,
        "status": "pending",
        "reason": "Personal sabbatical",
    },
    {
        "emp": 4,
        "type": "annual",
        "start_days": -20,
        "end_days": -18,
        "days": 3,
        "status": "approved",
        "reason": "Year-end break",
    },
    {
        "emp": 9,
        "type": "sick",
        "start_days": -15,
        "end_days": -14,
        "days": 2,
        "status": "approved",
        "reason": "Flu recovery",
    },
    {
        "emp": 1,
        "type": "annual",
        "start_days": 20,
        "end_days": 24,
        "days": 5,
        "status": "rejected",
        "reason": "Overlap with sprint deadline",
    },
    {
        "emp": 12,
        "type": "annual",
        "start_days": -30,
        "end_days": -28,
        "days": 3,
        "status": "approved",
        "reason": "Moving to new apartment",
    },
)

# Malaysian public holidays for the demo tenant (org-wide; 8.2.1 input data).
# Dates are illustrative — demo config, not an authoritative calendar.
HOLIDAY_ROWS: tuple[dict[str, object], ...] = (
    {"date": "2026-01-01", "name": "New Year's Day"},
    {"date": "2026-02-17", "name": "Chinese New Year"},
    {"date": "2026-03-20", "name": "Hari Raya Aidilfitri"},
    {"date": "2026-05-01", "name": "Labour Day"},
    {"date": "2026-05-31", "name": "Wesak Day"},
    {"date": "2026-06-01", "name": "Yang di-Pertuan Agong's Birthday"},
    {"date": "2026-08-31", "name": "National Day"},
    {"date": "2026-09-16", "name": "Malaysia Day"},
    {"date": "2026-12-25", "name": "Christmas Day"},
)

# Department-scoped blackout for the Finance team's year-end close (8.2.4).
# Referenced by department index into DEPARTMENT_ROWS (3 = Finance).
BLACKOUT_ROWS: tuple[dict[str, object], ...] = (
    {
        "dept_idx": 3,
        "start": "2026-12-20",
        "end": "2026-12-31",
        "reason": "Year-end financial close",
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# FINANCE DATA
# ═══════════════════════════════════════════════════════════════════════════

ACCOUNT_ROWS: tuple[dict[str, object], ...] = (
    {"code": "1200", "name": "Cash", "type": AccountType.ASSET},
    {"code": "1100", "name": "Accounts Receivable", "type": AccountType.ASSET},
    {"code": "1300", "name": "Inventory Asset", "type": AccountType.ASSET},
    {"code": "1500", "name": "Office Equipment", "type": AccountType.ASSET},
    {"code": "2110", "name": "Accounts Payable", "type": AccountType.LIABILITY},
    {"code": "2010", "name": "Accrued Salaries", "type": AccountType.LIABILITY},
    {"code": "2020", "name": "Tax Payable", "type": AccountType.LIABILITY},
    {"code": "3000", "name": "Owner's Equity", "type": AccountType.EQUITY},
    {"code": "3010", "name": "Retained Earnings", "type": AccountType.EQUITY},
    {"code": "4000", "name": "Sales Revenue", "type": AccountType.REVENUE},
    {"code": "4010", "name": "Service Revenue", "type": AccountType.REVENUE},
    {"code": "4020", "name": "Interest Income", "type": AccountType.REVENUE},
    {"code": "5000", "name": "Cost of Goods Sold", "type": AccountType.EXPENSE},
    {"code": "5010", "name": "Salaries Expense", "type": AccountType.EXPENSE},
    {"code": "5020", "name": "Rent Expense", "type": AccountType.EXPENSE},
    {"code": "5030", "name": "Utilities Expense", "type": AccountType.EXPENSE},
    {"code": "5040", "name": "Marketing Expense", "type": AccountType.EXPENSE},
    {"code": "5050", "name": "Office Supplies", "type": AccountType.EXPENSE},
    {"code": "5060", "name": "Depreciation Expense", "type": AccountType.EXPENSE},
    {"code": "5070", "name": "Insurance Expense", "type": AccountType.EXPENSE},
)

FISCAL_PERIOD_ROWS: tuple[dict[str, object], ...] = (
    {"name": "Q1 2026", "start": "2026-01-01", "end": "2026-03-31", "closed": True},
    {"name": "Q2 2026", "start": "2026-04-01", "end": "2026-06-30", "closed": True},
    {"name": "Q3 2026", "start": "2026-07-01", "end": "2026-09-30", "closed": False},
    {"name": "Q4 2026", "start": "2026-10-01", "end": "2026-12-31", "closed": False},
)

# Journal entries: (memo, source, source_ref, status, entry_days_ago, lines: [(account_idx, debit, credit)])
JOURNAL_ENTRY_ROWS: tuple[dict[str, object], ...] = (
    {
        "memo": "Opening balance — cash injection",
        "source": "manual",
        "source_ref": "JE-0001",
        "status": EntryStatus.POSTED,
        "days_ago": 90,
        "lines": [(0, Decimal("500000"), None), (8, None, Decimal("500000"))],
    },
    {
        "memo": "January rent payment",
        "source": "manual",
        "source_ref": "JE-0002",
        "status": EntryStatus.POSTED,
        "days_ago": 80,
        "lines": [(14, Decimal("12000"), None), (0, None, Decimal("12000"))],
    },
    {
        "memo": "February rent payment",
        "source": "manual",
        "source_ref": "JE-0003",
        "status": EntryStatus.POSTED,
        "days_ago": 50,
        "lines": [(14, Decimal("12000"), None), (0, None, Decimal("12000"))],
    },
    {
        "memo": "January payroll — Engineering",
        "source": "payroll",
        "source_ref": "PR-2026-01",
        "status": EntryStatus.POSTED,
        "days_ago": 75,
        "lines": [(13, Decimal("45000"), None), (5, None, Decimal("45000"))],
    },
    {
        "memo": "February payroll — Engineering",
        "source": "payroll",
        "source_ref": "PR-2026-02",
        "status": EntryStatus.POSTED,
        "days_ago": 45,
        "lines": [(13, Decimal("45000"), None), (5, None, Decimal("45000"))],
    },
    {
        "memo": "March payroll — Engineering",
        "source": "payroll",
        "source_ref": "PR-2026-03",
        "status": EntryStatus.POSTED,
        "days_ago": 15,
        "lines": [(13, Decimal("47500"), None), (5, None, Decimal("47500"))],
    },
    {
        "memo": "Cloud infrastructure — Q1",
        "source": "manual",
        "source_ref": "JE-0006",
        "status": EntryStatus.POSTED,
        "days_ago": 40,
        "lines": [(15, Decimal("8500"), None), (0, None, Decimal("8500"))],
    },
    {
        "memo": "Marketing campaign — Spring launch",
        "source": "manual",
        "source_ref": "JE-0007",
        "status": EntryStatus.POSTED,
        "days_ago": 35,
        "lines": [(16, Decimal("15000"), None), (0, None, Decimal("15000"))],
    },
    {
        "memo": "Software license purchase",
        "source": "manual",
        "source_ref": "JE-0008",
        "status": EntryStatus.POSTED,
        "days_ago": 25,
        "lines": [(17, Decimal("3200"), None), (0, None, Decimal("3200"))],
    },
    {
        "memo": "Service revenue — client project",
        "source": "invoice",
        "source_ref": "INV-0001",
        "status": EntryStatus.POSTED,
        "days_ago": 20,
        "lines": [(0, Decimal("25000"), None), (10, None, Decimal("25000"))],
    },
    {
        "memo": "Equipment depreciation — Q1",
        "source": "manual",
        "source_ref": "JE-0010",
        "status": EntryStatus.POSTED,
        "days_ago": 10,
        "lines": [(18, Decimal("2500"), None), (3, None, Decimal("2500"))],
    },
    {
        "memo": "Office supplies purchase",
        "source": "manual",
        "source_ref": "JE-0011",
        "status": EntryStatus.DRAFT,
        "days_ago": 3,
        "lines": [(17, Decimal("890"), None), (0, None, Decimal("890"))],
    },
    {
        "memo": "Interest income — savings account",
        "source": "manual",
        "source_ref": "JE-0012",
        "status": EntryStatus.POSTED,
        "days_ago": 5,
        "lines": [(0, Decimal("320"), None), (11, None, Decimal("320"))],
    },
    {
        "memo": "COGS — SO-0001 Enterprise ERP License",
        "source": "cogs",
        "source_ref": "SO-0001",
        "status": EntryStatus.POSTED,
        "days_ago": 60,
        "lines": [(12, Decimal("5000"), None), (2, None, Decimal("5000"))],
    },
    {
        "memo": "COGS — SO-0002 CRM + HR + Training",
        "source": "cogs",
        "source_ref": "SO-0002",
        "status": EntryStatus.POSTED,
        "days_ago": 45,
        "lines": [(12, Decimal("3200"), None), (2, None, Decimal("3200"))],
    },
    {
        "memo": "COGS — SO-0006 Data Migration Package",
        "source": "cogs",
        "source_ref": "SO-0006",
        "status": EntryStatus.POSTED,
        "days_ago": 50,
        "lines": [(12, Decimal("2000"), None), (2, None, Decimal("2000"))],
    },
    {
        "memo": "COGS — SO-0010 HR Module Add-on",
        "source": "cogs",
        "source_ref": "SO-0010",
        "status": EntryStatus.POSTED,
        "days_ago": 55,
        "lines": [(12, Decimal("1200"), None), (2, None, Decimal("1200"))],
    },
)

# Invoices: (number, customer_name_idx, invoice_days_ago, due_days_ahead, status, total, lines)
INVOICE_ROWS: tuple[dict[str, object], ...] = (
    {
        "number": "INV-0001",
        "days_ago": 30,
        "due_ahead": 15,
        "status": InvoiceStatus.PAID,
        "total": Decimal("25000"),
        "source": "sales_order",
        "source_ref": "SO-0001",
        "lines": [
            {
                "desc": "ERP integration consulting",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("20000"),
            },
            {
                "desc": "Project management fees",
                "account_idx": 10,
                "qty": 10,
                "price": Decimal("500"),
            },
        ],
    },
    {
        "number": "INV-0002",
        "days_ago": 25,
        "due_ahead": 20,
        "status": InvoiceStatus.APPROVED,
        "total": Decimal("18500"),
        "source": "sales_order",
        "source_ref": "SO-0002",
        "lines": [
            {
                "desc": "Custom module development",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("15000"),
            },
            {"desc": "Testing and QA", "account_idx": 10, "qty": 5, "price": Decimal("700")},
        ],
    },
    {
        "number": "INV-0003",
        "days_ago": 20,
        "due_ahead": 25,
        "status": InvoiceStatus.ISSUED,
        "total": Decimal("42000"),
        "lines": [
            {
                "desc": "Annual SaaS subscription",
                "account_idx": 10,
                "qty": 12,
                "price": Decimal("3000"),
            },
            {
                "desc": "Premium support package",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("6000"),
            },
        ],
    },
    {
        "number": "INV-0004",
        "days_ago": 15,
        "due_ahead": 30,
        "status": InvoiceStatus.ISSUED,
        "total": Decimal("8750"),
        "lines": [
            {
                "desc": "Staff training workshop",
                "account_idx": 10,
                "qty": 5,
                "price": Decimal("1500"),
            },
            {"desc": "Training materials", "account_idx": 10, "qty": 5, "price": Decimal("250")},
        ],
    },
    {
        "number": "INV-0005",
        "days_ago": 10,
        "due_ahead": 35,
        "status": InvoiceStatus.DRAFT,
        "total": Decimal("67200"),
        "lines": [
            {
                "desc": "Enterprise platform license",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("60000"),
            },
            {
                "desc": "Implementation services",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("7200"),
            },
        ],
    },
    {
        "number": "INV-0006",
        "days_ago": 8,
        "due_ahead": 37,
        "status": InvoiceStatus.DRAFT,
        "total": Decimal("5400"),
        "lines": [
            {
                "desc": "Data migration services",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("5400"),
            },
        ],
    },
    {
        "number": "INV-0007",
        "days_ago": 5,
        "due_ahead": 40,
        "status": InvoiceStatus.ISSUED,
        "total": Decimal("31800"),
        "lines": [
            {"desc": "CRM module setup", "account_idx": 10, "qty": 1, "price": Decimal("18000")},
            {
                "desc": "Custom report development",
                "account_idx": 10,
                "qty": 6,
                "price": Decimal("2300"),
            },
        ],
    },
    {
        "number": "INV-0008",
        "days_ago": 3,
        "due_ahead": 42,
        "status": InvoiceStatus.DRAFT,
        "total": Decimal("12000"),
        "lines": [
            {
                "desc": "Inventory management consulting",
                "account_idx": 10,
                "qty": 20,
                "price": Decimal("600"),
            },
        ],
    },
    {
        "number": "INV-0009",
        "days_ago": 2,
        "due_ahead": 43,
        "status": InvoiceStatus.ISSUED,
        "total": Decimal("15600"),
        "lines": [
            {
                "desc": "Payroll module configuration",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("9600"),
            },
            {"desc": "Integration testing", "account_idx": 10, "qty": 8, "price": Decimal("750")},
        ],
    },
    {
        "number": "INV-0010",
        "days_ago": 1,
        "due_ahead": 44,
        "status": InvoiceStatus.APPROVED,
        "total": Decimal("44500"),
        "lines": [
            {
                "desc": "Full-stack ERP deployment",
                "account_idx": 10,
                "qty": 1,
                "price": Decimal("40000"),
            },
            {
                "desc": "Post-launch support (3 months)",
                "account_idx": 10,
                "qty": 3,
                "price": Decimal("1500"),
            },
        ],
    },
    {
        "number": "INV-0011",
        "days_ago": 60,
        "due_ahead": -30,
        "status": InvoiceStatus.PAID,
        "total": Decimal("9800"),
        "lines": [
            {"desc": "Bug fix retainer", "account_idx": 10, "qty": 1, "price": Decimal("9800")},
        ],
    },
    {
        "number": "INV-0012",
        "days_ago": 45,
        "due_ahead": -15,
        "status": InvoiceStatus.PAID,
        "total": Decimal("22400"),
        "lines": [
            {"desc": "API gateway setup", "account_idx": 10, "qty": 1, "price": Decimal("14400")},
            {"desc": "Security audit", "account_idx": 10, "qty": 1, "price": Decimal("8000")},
        ],
    },
)

PAYMENT_ROWS: tuple[dict[str, object], ...] = (
    {
        "invoice_idx": 0,
        "number": "PAY-0001",
        "amount": Decimal("25000"),
        "method": "bank_transfer",
        "days_ago": 18,
    },
    {
        "invoice_idx": 10,
        "number": "PAY-0002",
        "amount": Decimal("9800"),
        "method": "bank_transfer",
        "days_ago": 42,
    },
    {
        "invoice_idx": 11,
        "number": "PAY-0003",
        "amount": Decimal("22400"),
        "method": "credit_card",
        "days_ago": 30,
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# PAYROLL DATA
# ═══════════════════════════════════════════════════════════════════════════

COMPENSATION_ROWS: tuple[dict[str, object], ...] = (
    {"emp": 0, "monthly": Decimal("9500"), "currency": "USD", "effective_days_ago": 700},
    {"emp": 1, "monthly": Decimal("11500"), "currency": "USD", "effective_days_ago": 1000},
    {"emp": 2, "monthly": Decimal("8800"), "currency": "USD", "effective_days_ago": 500},
    {"emp": 3, "monthly": Decimal("10200"), "currency": "USD", "effective_days_ago": 850},
    {"emp": 4, "monthly": Decimal("9800"), "currency": "USD", "effective_days_ago": 630},
    {"emp": 5, "monthly": Decimal("7500"), "currency": "USD", "effective_days_ago": 450},
    {"emp": 6, "monthly": Decimal("7200"), "currency": "USD", "effective_days_ago": 340},
    {"emp": 7, "monthly": Decimal("8100"), "currency": "USD", "effective_days_ago": 400},
    {"emp": 8, "monthly": Decimal("7800"), "currency": "USD", "effective_days_ago": 280},
    {"emp": 9, "monthly": Decimal("6500"), "currency": "USD", "effective_days_ago": 220},
    {"emp": 10, "monthly": Decimal("8900"), "currency": "USD", "effective_days_ago": 160},
    {"emp": 11, "monthly": Decimal("7600"), "currency": "USD", "effective_days_ago": 100},
    {"emp": 12, "monthly": Decimal("6800"), "currency": "USD", "effective_days_ago": 80},
    {"emp": 14, "monthly": Decimal("7100"), "currency": "USD", "effective_days_ago": 50},
)

# Payroll runs: (code, period_start, period_end, status, computed_days_ago)
PAYROLL_RUN_ROWS: tuple[dict[str, object], ...] = (
    {
        "code": "PR-2026-01",
        "start": "2026-01-01",
        "end": "2026-01-31",
        "status": "paid",
        "days_ago": 75,
    },
    {
        "code": "PR-2026-02",
        "start": "2026-02-01",
        "end": "2026-02-28",
        "status": "paid",
        "days_ago": 45,
    },
    {
        "code": "PR-2026-03",
        "start": "2026-03-01",
        "end": "2026-03-31",
        "status": "approved",
        "days_ago": 15,
    },
    {
        "code": "PR-2026-04",
        "start": "2026-04-01",
        "end": "2026-04-30",
        "status": "computed",
        "days_ago": 2,
    },
    {
        "code": "PR-2026-05",
        "start": "2026-05-01",
        "end": "2026-05-31",
        "status": "draft",
        "days_ago": 0,
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# SALES DATA
# ═══════════════════════════════════════════════════════════════════════════

# Products (seeded if not present)
PRODUCT_ROWS: tuple[dict[str, object], ...] = (
    {
        "sku": "PROD-001",
        "name": "Enterprise ERP License",
        "category": "Software",
        "unit": "license",
        "cost": Decimal("5000"),
        "sell": Decimal("25000"),
        "reorder": Decimal("5"),
    },
    {
        "sku": "PROD-002",
        "name": "CRM Module Add-on",
        "category": "Software",
        "unit": "license",
        "cost": Decimal("1500"),
        "sell": Decimal("8000"),
        "reorder": Decimal("3"),
    },
    {
        "sku": "PROD-003",
        "name": "HR Module Add-on",
        "category": "Software",
        "unit": "license",
        "cost": Decimal("1200"),
        "sell": Decimal("6500"),
        "reorder": Decimal("3"),
    },
    {
        "sku": "PROD-004",
        "name": "Implementation Service",
        "category": "Services",
        "unit": "hour",
        "cost": Decimal("75"),
        "sell": Decimal("200"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-005",
        "name": "Training Workshop",
        "category": "Services",
        "unit": "session",
        "cost": Decimal("500"),
        "sell": Decimal("1500"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-006",
        "name": "Premium Support Plan",
        "category": "Services",
        "unit": "month",
        "cost": Decimal("800"),
        "sell": Decimal("2500"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-007",
        "name": "Data Migration Package",
        "category": "Services",
        "unit": "package",
        "cost": Decimal("2000"),
        "sell": Decimal("5400"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-008",
        "name": "Custom Report Development",
        "category": "Services",
        "unit": "report",
        "cost": Decimal("600"),
        "sell": Decimal("2300"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-009",
        "name": "API Gateway Setup",
        "category": "Infrastructure",
        "unit": "setup",
        "cost": Decimal("3000"),
        "sell": Decimal("14400"),
        "reorder": Decimal("2"),
    },
    {
        "sku": "PROD-010",
        "name": "Security Audit",
        "category": "Services",
        "unit": "audit",
        "cost": Decimal("2500"),
        "sell": Decimal("8000"),
        "reorder": Decimal("0"),
    },
    {
        "sku": "PROD-011",
        "name": "Cloud Hosting (Annual)",
        "category": "Infrastructure",
        "unit": "year",
        "cost": Decimal("4800"),
        "sell": Decimal("12000"),
        "reorder": Decimal("10"),
    },
    {
        "sku": "PROD-012",
        "name": "Analytics Dashboard",
        "category": "Software",
        "unit": "license",
        "cost": Decimal("1000"),
        "sell": Decimal("4500"),
        "reorder": Decimal("5"),
    },
)

# Sales orders: (order_number, status, subtotal, discount, tax, total, days_ago, lines)
SALES_ORDER_ROWS: tuple[dict[str, object], ...] = (
    {
        "number": "SO-0001",
        "status": OrderStatus.FULFILLED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("25000"),
        "discount": Decimal("0"),
        "tax": Decimal("2500"),
        "total": Decimal("27500"),
        "days_ago": 60,
        "lines": [
            {
                "prod": 0,
                "name": "Enterprise ERP License",
                "sku": "PROD-001",
                "qty": 1,
                "price": Decimal("25000"),
                "disc": Decimal("0"),
                "tax": Decimal("2500"),
                "total": Decimal("27500"),
            }
        ],
    },
    {
        "number": "SO-0002",
        "status": OrderStatus.FULFILLED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("16000"),
        "discount": Decimal("500"),
        "tax": Decimal("1550"),
        "total": Decimal("17050"),
        "days_ago": 45,
        "lines": [
            {
                "prod": 1,
                "name": "CRM Module Add-on",
                "sku": "PROD-002",
                "qty": 1,
                "price": Decimal("8000"),
                "disc": Decimal("0"),
                "tax": Decimal("800"),
                "total": Decimal("8800"),
            },
            {
                "prod": 2,
                "name": "HR Module Add-on",
                "sku": "PROD-003",
                "qty": 1,
                "price": Decimal("6500"),
                "disc": Decimal("0"),
                "tax": Decimal("650"),
                "total": Decimal("7150"),
            },
            {
                "prod": 4,
                "name": "Training Workshop",
                "sku": "PROD-005",
                "qty": 1,
                "price": Decimal("1500"),
                "disc": Decimal("500"),
                "tax": Decimal("100"),
                "total": Decimal("1100"),
            },
        ],
    },
    {
        "number": "SO-0003",
        "status": OrderStatus.CONFIRMED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("42000"),
        "discount": Decimal("2000"),
        "tax": Decimal("4000"),
        "total": Decimal("44000"),
        "days_ago": 30,
        "lines": [
            {
                "prod": 0,
                "name": "Enterprise ERP License",
                "sku": "PROD-001",
                "qty": 1,
                "price": Decimal("25000"),
                "disc": Decimal("2000"),
                "tax": Decimal("2300"),
                "total": Decimal("25300"),
            },
            {
                "prod": 5,
                "name": "Premium Support Plan",
                "sku": "PROD-006",
                "qty": 6,
                "price": Decimal("2500"),
                "disc": Decimal("0"),
                "tax": Decimal("1500"),
                "total": Decimal("16500"),
            },
            {
                "prod": 3,
                "name": "Implementation Service",
                "sku": "PROD-004",
                "qty": 11,
                "price": Decimal("200"),
                "disc": Decimal("0"),
                "tax": Decimal("220"),
                "total": Decimal("2420"),
            },
        ],
    },
    {
        "number": "SO-0004",
        "status": OrderStatus.DRAFT,
        "credit": CreditCheckResult.PENDING,
        "subtotal": Decimal("8700"),
        "discount": Decimal("0"),
        "tax": Decimal("870"),
        "total": Decimal("9570"),
        "days_ago": 10,
        "lines": [
            {
                "prod": 11,
                "name": "Analytics Dashboard",
                "sku": "PROD-012",
                "qty": 1,
                "price": Decimal("4500"),
                "disc": Decimal("0"),
                "tax": Decimal("450"),
                "total": Decimal("4950"),
            },
            {
                "prod": 7,
                "name": "Custom Report Development",
                "sku": "PROD-008",
                "qty": 2,
                "price": Decimal("2300"),
                "disc": Decimal("0"),
                "tax": Decimal("460"),
                "total": Decimal("5060"),
            },
        ],
    },
    {
        "number": "SO-0005",
        "status": OrderStatus.CONFIRMED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("19800"),
        "discount": Decimal("1000"),
        "tax": Decimal("1880"),
        "total": Decimal("20680"),
        "days_ago": 25,
        "lines": [
            {
                "prod": 8,
                "name": "API Gateway Setup",
                "sku": "PROD-009",
                "qty": 1,
                "price": Decimal("14400"),
                "disc": Decimal("1000"),
                "tax": Decimal("1340"),
                "total": Decimal("14740"),
            },
            {
                "prod": 9,
                "name": "Security Audit",
                "sku": "PROD-010",
                "qty": 1,
                "price": Decimal("8000"),
                "disc": Decimal("0"),
                "tax": Decimal("800"),
                "total": Decimal("8800"),
            },
        ],
    },
    {
        "number": "SO-0006",
        "status": OrderStatus.FULFILLED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("5400"),
        "discount": Decimal("0"),
        "tax": Decimal("540"),
        "total": Decimal("5940"),
        "days_ago": 50,
        "lines": [
            {
                "prod": 6,
                "name": "Data Migration Package",
                "sku": "PROD-007",
                "qty": 1,
                "price": Decimal("5400"),
                "disc": Decimal("0"),
                "tax": Decimal("540"),
                "total": Decimal("5940"),
            }
        ],
    },
    {
        "number": "SO-0007",
        "status": OrderStatus.DRAFT,
        "credit": CreditCheckResult.PENDING,
        "subtotal": Decimal("36000"),
        "discount": Decimal("3000"),
        "tax": Decimal("3300"),
        "total": Decimal("36300"),
        "days_ago": 5,
        "lines": [
            {
                "prod": 0,
                "name": "Enterprise ERP License",
                "sku": "PROD-001",
                "qty": 1,
                "price": Decimal("25000"),
                "disc": Decimal("3000"),
                "tax": Decimal("2200"),
                "total": Decimal("24200"),
            },
            {
                "prod": 10,
                "name": "Cloud Hosting (Annual)",
                "sku": "PROD-011",
                "qty": 1,
                "price": Decimal("12000"),
                "disc": Decimal("0"),
                "tax": Decimal("1200"),
                "total": Decimal("13200"),
            },
        ],
    },
    {
        "number": "SO-0008",
        "status": OrderStatus.CANCELLED,
        "credit": CreditCheckResult.FAILED,
        "subtotal": Decimal("8000"),
        "discount": Decimal("0"),
        "tax": Decimal("800"),
        "total": Decimal("8800"),
        "days_ago": 40,
        "lines": [
            {
                "prod": 1,
                "name": "CRM Module Add-on",
                "sku": "PROD-002",
                "qty": 1,
                "price": Decimal("8000"),
                "disc": Decimal("0"),
                "tax": Decimal("800"),
                "total": Decimal("8800"),
            }
        ],
    },
    {
        "number": "SO-0009",
        "status": OrderStatus.CONFIRMED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("14500"),
        "discount": Decimal("500"),
        "tax": Decimal("1400"),
        "total": Decimal("15400"),
        "days_ago": 18,
        "lines": [
            {
                "prod": 5,
                "name": "Premium Support Plan",
                "sku": "PROD-006",
                "qty": 3,
                "price": Decimal("2500"),
                "disc": Decimal("500"),
                "tax": Decimal("600"),
                "total": Decimal("7600"),
            },
            {
                "prod": 4,
                "name": "Training Workshop",
                "sku": "PROD-005",
                "qty": 2,
                "price": Decimal("1500"),
                "disc": Decimal("0"),
                "tax": Decimal("300"),
                "total": Decimal("3300"),
            },
            {
                "prod": 3,
                "name": "Implementation Service",
                "sku": "PROD-004",
                "qty": 18,
                "price": Decimal("200"),
                "disc": Decimal("0"),
                "tax": Decimal("500"),
                "total": Decimal("4500"),
            },
        ],
    },
    {
        "number": "SO-0010",
        "status": OrderStatus.FULFILLED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("6500"),
        "discount": Decimal("0"),
        "tax": Decimal("650"),
        "total": Decimal("7150"),
        "days_ago": 55,
        "lines": [
            {
                "prod": 2,
                "name": "HR Module Add-on",
                "sku": "PROD-003",
                "qty": 1,
                "price": Decimal("6500"),
                "disc": Decimal("0"),
                "tax": Decimal("650"),
                "total": Decimal("7150"),
            },
        ],
    },
    {
        "number": "SO-0011",
        "status": OrderStatus.DRAFT,
        "credit": CreditCheckResult.PENDING,
        "subtotal": Decimal("29500"),
        "discount": Decimal("1500"),
        "tax": Decimal("2800"),
        "total": Decimal("30800"),
        "days_ago": 3,
        "lines": [
            {
                "prod": 0,
                "name": "Enterprise ERP License",
                "sku": "PROD-001",
                "qty": 1,
                "price": Decimal("25000"),
                "disc": Decimal("1500"),
                "tax": Decimal("2350"),
                "total": Decimal("25850"),
            },
            {
                "prod": 7,
                "name": "Custom Report Development",
                "sku": "PROD-008",
                "qty": 2,
                "price": Decimal("2300"),
                "disc": Decimal("0"),
                "tax": Decimal("460"),
                "total": Decimal("5060"),
            },
        ],
    },
    {
        "number": "SO-0012",
        "status": OrderStatus.CONFIRMED,
        "credit": CreditCheckResult.PASSED,
        "subtotal": Decimal("52000"),
        "discount": Decimal("5000"),
        "tax": Decimal("4700"),
        "total": Decimal("51700"),
        "days_ago": 12,
        "lines": [
            {
                "prod": 0,
                "name": "Enterprise ERP License",
                "sku": "PROD-001",
                "qty": 2,
                "price": Decimal("25000"),
                "disc": Decimal("5000"),
                "tax": Decimal("4500"),
                "total": Decimal("44500"),
            },
            {
                "prod": 6,
                "name": "Data Migration Package",
                "sku": "PROD-007",
                "qty": 1,
                "price": Decimal("5400"),
                "disc": Decimal("0"),
                "tax": Decimal("540"),
                "total": Decimal("5940"),
            },
            {
                "prod": 4,
                "name": "Training Workshop",
                "sku": "PROD-005",
                "qty": 1,
                "price": Decimal("1500"),
                "disc": Decimal("0"),
                "tax": Decimal("150"),
                "total": Decimal("1650"),
            },
        ],
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY DATA
# ═══════════════════════════════════════════════════════════════════════════

WAREHOUSE_ROWS: tuple[dict[str, object], ...] = (
    {"name": "Main Distribution Center", "location": "Riyadh Industrial City", "is_active": True},
    {"name": "East Region Hub", "location": "Dammam, Eastern Province", "is_active": True},
    {"name": "West Region Hub", "location": "Jeddah, Western Province", "is_active": True},
    {"name": "Central Warehouse", "location": "Riyadh, Al Kharj Road", "is_active": True},
    {"name": "Overflow Storage", "location": "Khobar, Eastern Province", "is_active": True},
)

# Stock levels: (product_idx, warehouse_idx, on_hand, reserved)
# Some products below reorder to trigger alerts: PROD-002 (reorder 3, qty 1),
# PROD-009 (reorder 2, qty 1), PROD-012 (reorder 5, qty 2).
STOCK_LEVEL_ROWS: tuple[dict[str, object], ...] = (
    # Warehouse 0: Main DC — primary stock
    {"prod": 0, "wh": 0, "on_hand": Decimal("12"), "reserved": Decimal("2")},
    {"prod": 1, "wh": 0, "on_hand": Decimal("1"), "reserved": Decimal("0")},
    {"prod": 2, "wh": 0, "on_hand": Decimal("8"), "reserved": Decimal("1")},
    {"prod": 9, "wh": 0, "on_hand": Decimal("5"), "reserved": Decimal("0")},
    {"prod": 10, "wh": 0, "on_hand": Decimal("20"), "reserved": Decimal("3")},
    {"prod": 11, "wh": 0, "on_hand": Decimal("2"), "reserved": Decimal("0")},
    # Warehouse 1: East Region Hub
    {"prod": 0, "wh": 1, "on_hand": Decimal("6"), "reserved": Decimal("1")},
    {"prod": 2, "wh": 1, "on_hand": Decimal("4"), "reserved": Decimal("0")},
    {"prod": 10, "wh": 1, "on_hand": Decimal("15"), "reserved": Decimal("2")},
    # Warehouse 2: West Region Hub
    {"prod": 1, "wh": 2, "on_hand": Decimal("3"), "reserved": Decimal("0")},
    {"prod": 8, "wh": 2, "on_hand": Decimal("1"), "reserved": Decimal("0")},
    {"prod": 9, "wh": 2, "on_hand": Decimal("3"), "reserved": Decimal("1")},
    # Warehouse 3: Central Warehouse
    {"prod": 0, "wh": 3, "on_hand": Decimal("4"), "reserved": Decimal("0")},
    {"prod": 11, "wh": 3, "on_hand": Decimal("6"), "reserved": Decimal("1")},
    {"prod": 10, "wh": 3, "on_hand": Decimal("8"), "reserved": Decimal("0")},
    # Warehouse 4: Overflow Storage (sparse)
    {"prod": 2, "wh": 4, "on_hand": Decimal("2"), "reserved": Decimal("0")},
    {"prod": 10, "wh": 4, "on_hand": Decimal("5"), "reserved": Decimal("0")},
)

# Stock movements: immutable ledger entries
# (product_idx, warehouse_idx, movement_type, qty, ref_type, ref_id, days_ago)
STOCK_MOVEMENT_ROWS: tuple[dict[str, object], ...] = (
    # Initial receipts at Main DC
    {
        "prod": 0,
        "wh": 0,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("15"),
        "ref": "purchase_order",
        "ref_id": "PO-0001",
        "days": 90,
    },
    {
        "prod": 1,
        "wh": 0,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("5"),
        "ref": "purchase_order",
        "ref_id": "PO-0002",
        "days": 90,
    },
    {
        "prod": 2,
        "wh": 0,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("10"),
        "ref": "purchase_order",
        "ref_id": "PO-0003",
        "days": 85,
    },
    {
        "prod": 10,
        "wh": 0,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("25"),
        "ref": "purchase_order",
        "ref_id": "PO-0004",
        "days": 80,
    },
    {
        "prod": 11,
        "wh": 0,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("8"),
        "ref": "purchase_order",
        "ref_id": "PO-0005",
        "days": 75,
    },
    # Issues to sales orders
    {
        "prod": 0,
        "wh": 0,
        "type": StockMovementType.ISSUE,
        "qty": Decimal("-2"),
        "ref": "sales_order",
        "ref_id": "SO-0001",
        "days": 60,
    },
    {
        "prod": 0,
        "wh": 1,
        "type": StockMovementType.ISSUE,
        "qty": Decimal("-1"),
        "ref": "sales_order",
        "ref_id": "SO-0003",
        "days": 30,
    },
    {
        "prod": 2,
        "wh": 0,
        "type": StockMovementType.ISSUE,
        "qty": Decimal("-1"),
        "ref": "sales_order",
        "ref_id": "SO-0002",
        "days": 45,
    },
    {
        "prod": 10,
        "wh": 0,
        "type": StockMovementType.ISSUE,
        "qty": Decimal("-3"),
        "ref": "sales_order",
        "ref_id": "SO-0005",
        "days": 25,
    },
    # Transfers between warehouses
    {
        "prod": 10,
        "wh": 0,
        "type": StockMovementType.TRANSFER,
        "qty": Decimal("-7"),
        "ref": "transfer",
        "ref_id": "TRF-0001",
        "days": 50,
    },
    {
        "prod": 10,
        "wh": 1,
        "type": StockMovementType.TRANSFER,
        "qty": Decimal("7"),
        "ref": "transfer",
        "ref_id": "TRF-0001",
        "days": 50,
    },
    {
        "prod": 0,
        "wh": 0,
        "type": StockMovementType.TRANSFER,
        "qty": Decimal("-2"),
        "ref": "transfer",
        "ref_id": "TRF-0002",
        "days": 40,
    },
    {
        "prod": 0,
        "wh": 3,
        "type": StockMovementType.TRANSFER,
        "qty": Decimal("2"),
        "ref": "transfer",
        "ref_id": "TRF-0002",
        "days": 40,
    },
    # Reservations for confirmed orders
    {
        "prod": 0,
        "wh": 0,
        "type": StockMovementType.RESERVATION,
        "qty": Decimal("-2"),
        "ref": "sales_order",
        "ref_id": "SO-0003",
        "days": 30,
    },
    {
        "prod": 0,
        "wh": 1,
        "type": StockMovementType.RESERVATION,
        "qty": Decimal("-1"),
        "ref": "sales_order",
        "ref_id": "SO-0009",
        "days": 18,
    },
    {
        "prod": 2,
        "wh": 0,
        "type": StockMovementType.RESERVATION,
        "qty": Decimal("-1"),
        "ref": "sales_order",
        "ref_id": "SO-0010",
        "days": 55,
    },
    {
        "prod": 10,
        "wh": 0,
        "type": StockMovementType.RESERVATION,
        "qty": Decimal("-3"),
        "ref": "sales_order",
        "ref_id": "SO-0012",
        "days": 12,
    },
    # Adjustments
    {
        "prod": 8,
        "wh": 2,
        "type": StockMovementType.ADJUSTMENT,
        "qty": Decimal("1"),
        "ref": "adjustment",
        "ref_id": "ADJ-0001",
        "days": 20,
    },
    {
        "prod": 11,
        "wh": 3,
        "type": StockMovementType.RECEIPT,
        "qty": Decimal("4"),
        "ref": "purchase_order",
        "ref_id": "PO-0006",
        "days": 15,
    },
    # Release cancelled order reservation
    {
        "prod": 1,
        "wh": 0,
        "type": StockMovementType.RELEASE,
        "qty": Decimal("1"),
        "ref": "sales_order",
        "ref_id": "SO-0008",
        "days": 40,
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# Seeding engine
# ═══════════════════════════════════════════════════════════════════════════


async def _resolve_owner_id(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    row = (
        await session.execute(
            text(
                "SELECT id FROM users WHERE tenant_id = :tid AND is_active = true ORDER BY created_at ASC LIMIT 1"
            ),
            {"tid": tenant_id},
        )
    ).scalar_one_or_none()
    return row if row is None else uuid.UUID(str(row))


async def seed_demo_data(tenant_id: uuid.UUID, *, force: bool = False) -> dict[str, int]:
    """Seed demo data for all ERP modules. Idempotent unless force=True."""
    from core.features.ai_hr.models.leave_anomaly import LeaveAnomalyModel
    from core.features.ai_hr.models.leave_blackout_period import AiHrLeaveBlackoutPeriodModel
    from core.features.ai_hr.models.public_holiday import AiHrPublicHolidayModel
    from core.features.ai_hr.models.utilization_alert import (
        UtilizationAlertModel,
        UtilizationAlertType,
    )
    from core.features.finance.models.chart_of_account import ErpChartOfAccountModel
    from core.features.finance.models.fiscal_period import ErpFiscalPeriodModel
    from core.features.finance.models.invoice import ErpInvoiceModel
    from core.features.finance.models.invoice_line import ErpInvoiceLineModel
    from core.features.finance.models.journal_entry import ErpJournalEntryModel
    from core.features.finance.models.journal_line import ErpJournalLineModel
    from core.features.finance.models.payment import ErpPaymentModel
    from core.features.hr.models.attendance_record import AttendanceRecordModel
    from core.features.hr.models.department import DepartmentModel
    from core.features.hr.models.employee import EmployeeModel
    from core.features.hr.models.leave_balance import LeaveBalanceModel
    from core.features.hr.models.leave_movement import LeaveMovementModel
    from core.features.hr.models.leave_request import LeaveRequestModel
    from core.features.inventory.models.product import ErpProductModel
    from core.features.inventory.models.stock_level import ErpStockLevelModel
    from core.features.inventory.models.stock_movement import ErpStockMovementModel
    from core.features.inventory.models.warehouse import ErpWarehouseModel
    from core.features.payroll.models.compensation import CompensationModel
    from core.features.payroll.models.payroll_entry import PayrollEntryModel
    from core.features.payroll.models.payroll_run import PayrollRunModel, PayrollRunStatus
    from core.features.sales.models.order import ErpSalesOrderModel
    from core.features.sales.models.order_line import ErpSalesOrderLineModel

    async with async_session_factory() as session:
        if force:
            # Nullify circular FK (departments.manager_employee_id -> erp_employees)
            # before bulk-delete so DELETE erp_employees isn't blocked.
            await session.execute(
                text(
                    "UPDATE erp_departments SET manager_employee_id = NULL WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
            # erp_leave_movements carries an append-only guard trigger
            # (migration 0013); disable it just for this teardown so the
            # tenant can be wiped. ALTER TABLE is transactional in Postgres,
            # so a failed teardown rolls the disable back with everything else.
            await session.execute(
                text(
                    "ALTER TABLE erp_leave_movements DISABLE TRIGGER erp_leave_movements_append_only"
                )
            )
            for model in (
                ErpSalesOrderLineModel,
                ErpSalesOrderModel,
                ErpStockMovementModel,
                ErpStockLevelModel,
                ErpWarehouseModel,
                ErpProductModel,
                PayrollEntryModel,
                PayrollRunModel,
                CompensationModel,
                ErpPaymentModel,
                ErpInvoiceLineModel,
                ErpInvoiceModel,
                ErpJournalLineModel,
                ErpJournalEntryModel,
                ErpFiscalPeriodModel,
                ErpChartOfAccountModel,
                AttendanceRecordModel,
                LeaveMovementModel,
                LeaveRequestModel,
                LeaveBalanceModel,
                AiHrLeaveBlackoutPeriodModel,
                AiHrPublicHolidayModel,
                UtilizationAlertModel,
                LeaveAnomalyModel,
                EmployeeModel,
                DepartmentModel,
            ):
                await session.execute(
                    delete(model.__table__).where(model.__table__.c.tenant_id == tenant_id)  # type: ignore[arg-type]
                )
            await session.execute(
                text(
                    "ALTER TABLE erp_leave_movements ENABLE TRIGGER erp_leave_movements_append_only"
                )
            )
            await session.commit()
            logger.info("seed.demo.cleared", tenant_id=str(tenant_id))

        existing_depts = (
            await session.execute(
                select(func.count())
                .select_from(DepartmentModel)
                .where(DepartmentModel.tenant_id == tenant_id)
            )
        ).scalar_one()
        if existing_depts and not force:
            logger.info(
                "seed.demo.skip", tenant_id=str(tenant_id), reason="already has departments"
            )
            return {"skipped": int(existing_depts)}

        owner_id = await _resolve_owner_id(session, tenant_id)
        counts: dict[str, int] = {}

        # ── DEPARTMENTS ──────────────────────────────────────────────
        dept_ids: list[uuid.UUID] = []
        for row in DEPARTMENT_ROWS:
            dept = DepartmentModel(
                tenant_id=tenant_id,
                name=row["name"],
                is_active=row["is_active"],
            )
            session.add(dept)
            await session.flush()
            dept_ids.append(dept.id)
        counts["departments"] = len(dept_ids)

        # ── EMPLOYEES ────────────────────────────────────────────────
        emp_ids: list[uuid.UUID] = []
        for row in EMPLOYEE_ROWS:
            dept_idx = int(str(row["dept"]))
            term_date = None
            if row["status"] == "terminated":
                term_date = _date_ago(int(str(row.get("term_days_ago", 30))))
            emp = EmployeeModel(
                tenant_id=tenant_id,
                employee_number=row["num"],
                first_name=row["first"],
                last_name=row["last"],
                email=row["email"],
                phone=row["phone"],
                department_id=dept_ids[dept_idx],
                job_title=row["title"],
                employment_status=row["status"],
                hire_date=_date_ago(int(str(row["hire_days_ago"]))),
                termination_date=term_date,
            )
            session.add(emp)
            await session.flush()
            emp_ids.append(emp.id)
        counts["employees"] = len(emp_ids)

        # Update department managers
        depts_with_managers = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 5),
            (5, 7),
            (6, 8),
        ]
        for dept_idx, emp_idx in depts_with_managers:
            if dept_idx < len(dept_ids) and emp_idx < len(emp_ids):
                await session.execute(
                    text(
                        "UPDATE erp_departments SET manager_employee_id = :mid WHERE tenant_id = :tid AND id = :did"
                    ),
                    {"mid": emp_ids[emp_idx], "tid": tenant_id, "did": dept_ids[dept_idx]},
                )

        # ── LEAVE REQUESTS ───────────────────────────────────────────
        for row in LEAVE_REQUEST_ROWS:
            emp_idx = int(str(row["emp"]))
            lr = LeaveRequestModel(
                tenant_id=tenant_id,
                employee_id=emp_ids[emp_idx],
                leave_type=row["type"],
                start_date=_date_ago(-int(str(row["start_days"]))),
                end_date=_date_ago(-int(str(row["end_days"]))),
                days=int(str(row["days"])),
                status=row["status"],
                reason=row.get("reason"),
            )
            session.add(lr)
        # HR-AI-002 8.2.1 — LIVE short-notice fixture (demoted from a static
        # row because the fringe check only inspects start/end weekday): a
        # filed-today approved block that starts today (advance 0, still
        # within the trailing window) and ends on the NEXT Friday, so the
        # Monday/Friday fringe holds on ANY seed day. At 6-13 days it clears
        # 3x the Engineering median (2.0) and the live scan emits
        # short_notice_monday_friday (high) every time it rebuilds.
        _fri_ahead = ((4 - _today().weekday()) % 7) + 1
        if _fri_ahead < 6:
            _fri_ahead += 7
        session.add(
            LeaveRequestModel(
                tenant_id=tenant_id,
                employee_id=emp_ids[6],
                leave_type="annual",
                start_date=_today(),
                end_date=_date_ahead(_fri_ahead - 1),
                days=_fri_ahead,
                status="approved",
                reason="Summer holiday",
            )
        )
        counts["leave_requests"] = len(LEAVE_REQUEST_ROWS) + 1

        # ── LEAVE BALANCES ───────────────────────────────────────────
        for emp_idx in range(len(emp_ids)):
            for lt in ("annual", "sick"):
                used = 0
                if lt == "annual":
                    used = (emp_idx % 5) * 2
                bal = LeaveBalanceModel(
                    tenant_id=tenant_id,
                    employee_id=emp_ids[emp_idx],
                    leave_type=lt,
                    balance=Decimal(str(max(0, 20 - used))) if lt == "annual" else Decimal("10"),
                )
                session.add(bal)
        counts["leave_balances"] = len(emp_ids) * 2

        # ── AI PATTERN DATA (holidays + blackouts; 0024) ────────────
        for row in HOLIDAY_ROWS:
            session.add(
                AiHrPublicHolidayModel(
                    tenant_id=tenant_id,
                    calendar_date=date.fromisoformat(str(row["date"])),
                    name=str(row["name"]),
                )
            )
        for row in BLACKOUT_ROWS:
            session.add(
                AiHrLeaveBlackoutPeriodModel(
                    tenant_id=tenant_id,
                    start_date=date.fromisoformat(str(row["start"])),
                    end_date=date.fromisoformat(str(row["end"])),
                    department_id=dept_ids[int(str(row["dept_idx"]))],
                    reason=str(row["reason"]),
                )
            )
        counts["public_holidays"] = len(HOLIDAY_ROWS)
        counts["leave_blackout_periods"] = len(BLACKOUT_ROWS)

        # ── HR AI DEMO FINDINGS (8.1.4 forfeit alert) ────────────────
        # ONE PRE-COMPUTED fixture so the demo reproduces the Gherkin numbers
        # on ANY seed day: the real forfeit scan only fires within
        # FORFEIT_WINDOW_DAYS=60 of year-end, so most seed days (mid-year)
        # would otherwise show an empty alert inbox. It is written with
        # created_at = now so the lazy-on-read utilization scan is "fresh" and
        # serves the fixture instead of immediately rebuilding over it; the
        # next stale scan (refreshed every 1d) replaces it like generated rows
        # (and on year-end runs the real scan reproduces the same finding).
        #
        # The ANOMALY inbox is deliberately NOT pre-seeded: leaving the table
        # empty makes latest_generated_at = None, so the FIRST portal/admin
        # read runs the live leave-pattern scan. Engineering's filed-today
        # block above (starts today => advance 0, ends next Friday => Mon/Fri
        # fringe, 6-13 days => 3x the 2.0 median) makes short_notice and
        # leave_overuse deterministic on any seed day, and the scan re-emits
        # them on every rebuild — a genuine live computation path in the demo.
        session.add(
            UtilizationAlertModel(
                tenant_id=tenant_id,
                employee_id=emp_ids[1],
                alert_type=UtilizationAlertType.FORFEIT_RISK,
                severity="medium",
                balance_days=18,
                projected_forfeiture_days=18,
                days_remaining_in_year=55,
                evidence={
                    "leave_type": "annual",
                    "year": _today().year,
                    "forfeit_window_days": 60,
                },
                created_at=_ago(0.5),
            )
        )
        counts["ai_utilization_alerts"] = 1

        # ── ATTENDANCE (last 21 days; deterministic mix of statuses) ─
        # Cycle per employee/day: mostly on_time, some late, occasional
        # absent. pay_impact mirrors the service rule (on_time->full,
        # late->half, absent->none).
        att_cycle = (
            ("on_time", "full"),
            ("on_time", "full"),
            ("late", "half"),
            ("on_time", "full"),
            ("on_time", "full"),
            ("on_time", "full"),
            ("absent", "none"),
        )
        for emp_idx, emp_id in enumerate(emp_ids):
            for day_offset in range(21):
                status, pay_impact = att_cycle[(emp_idx + day_offset) % len(att_cycle)]
                session.add(
                    AttendanceRecordModel(
                        tenant_id=tenant_id,
                        employee_id=emp_id,
                        work_date=_date_ago(day_offset),
                        status=status,
                        pay_impact=pay_impact,
                    )
                )
        counts["attendance_records"] = len(emp_ids) * 21

        # ── CHART OF ACCOUNTS ────────────────────────────────────────
        account_ids: list[uuid.UUID] = []
        for row in ACCOUNT_ROWS:
            acct = ErpChartOfAccountModel(
                tenant_id=tenant_id,
                code=row["code"],
                name=row["name"],
                account_type=row["type"],
            )
            session.add(acct)
            await session.flush()
            account_ids.append(acct.id)
        counts["accounts"] = len(account_ids)

        # ── FISCAL PERIODS ───────────────────────────────────────────
        for row in FISCAL_PERIOD_ROWS:
            fp = ErpFiscalPeriodModel(
                tenant_id=tenant_id,
                name=row["name"],
                start_date=date.fromisoformat(str(row["start"])),
                end_date=date.fromisoformat(str(row["end"])),
                is_closed=row["closed"],
            )
            session.add(fp)
        counts["fiscal_periods"] = len(FISCAL_PERIOD_ROWS)

        # ── JOURNAL ENTRIES + LINES ──────────────────────────────────
        for row in JOURNAL_ENTRY_ROWS:
            je = ErpJournalEntryModel(
                tenant_id=tenant_id,
                entry_date=_date_ago(int(str(row["days_ago"]))),
                memo=row["memo"],
                status=row["status"],
                source=row["source"],
                source_ref=row["source_ref"],
                posted_by_user_id=owner_id if row["status"] == EntryStatus.POSTED else None,
                posted_at=_ago(float(str(row["days_ago"])))
                if row["status"] == EntryStatus.POSTED
                else None,
            )
            session.add(je)
            await session.flush()

            for acct_idx, debit, credit in row["lines"]:  # type: ignore[attr-defined]
                jl = ErpJournalLineModel(
                    tenant_id=tenant_id,
                    entry_id=je.id,
                    account_id=account_ids[acct_idx],
                    debit=debit,
                    credit=credit,
                    currency="USD",
                )
                session.add(jl)
        counts["journal_entries"] = len(JOURNAL_ENTRY_ROWS)

        # ── CRM CUSTOMERS (fetch existing) ───────────────────────────
        customer_ids: list[uuid.UUID] = [
            cid
            for (cid,) in (
                await session.execute(
                    select(ErpCrmCustomerModel.id)
                    .where(
                        ErpCrmCustomerModel.tenant_id == tenant_id,
                        ErpCrmCustomerModel.is_active.is_(True),
                    )
                    .order_by(ErpCrmCustomerModel.created_at)
                )
            ).all()
        ]
        if not customer_ids:
            logger.warning("seed.demo.no_customers", tenant_id=str(tenant_id))
            # Create a minimal placeholder customer so invoices are valid
            placeholder = ErpCrmCustomerModel(
                tenant_id=tenant_id,
                customer_code="CUS-DEMO",
                name="Demo Customer",
                email="demo@example.com",
            )
            session.add(placeholder)
            await session.flush()
            customer_ids = [placeholder.id]
        counts["crm_customers_found"] = len(customer_ids)

        # ── INVOICES + LINES ─────────────────────────────────────────
        invoice_ids: list[uuid.UUID] = []
        for idx, row in enumerate(INVOICE_ROWS):
            inv = ErpInvoiceModel(
                tenant_id=tenant_id,
                invoice_number=row["number"],
                customer_id=customer_ids[idx % len(customer_ids)],
                invoice_date=_date_ago(int(str(row["days_ago"]))),
                due_date=_date_ahead(int(str(row["due_ahead"]))),
                status=row["status"],
                total=row["total"],
                source=row.get("source", "manual"),
                source_ref=row.get("source_ref", row["number"]),
            )
            session.add(inv)
            await session.flush()
            invoice_ids.append(inv.id)

            for li, line in enumerate(row["lines"], 1):  # type: ignore[arg-type,var-annotated]
                il = ErpInvoiceLineModel(
                    tenant_id=tenant_id,
                    invoice_id=inv.id,
                    line_no=li,
                    description=line["desc"],
                    account_id=account_ids[int(line["account_idx"])],
                    quantity=line["qty"],
                    unit_price=line["price"],
                    amount=line["qty"] * line["price"],
                )
                session.add(il)
        counts["invoices"] = len(invoice_ids)

        # ── PAYMENTS ─────────────────────────────────────────────────
        for row in PAYMENT_ROWS:
            pay = ErpPaymentModel(
                tenant_id=tenant_id,
                payment_number=row["number"],
                invoice_id=invoice_ids[int(str(row["invoice_idx"]))],
                amount=row["amount"],
                method=row["method"],
                paid_at=_ago(float(str(row["days_ago"]))),
                status=PaymentStatus.APPLIED,
                source="manual",
                source_ref=row["number"],
            )
            session.add(pay)
        counts["payments"] = len(PAYMENT_ROWS)

        # ── CRM TIMELINE EVENTS (finance activity) ───────────────────
        timeline_count = 0
        for idx, inv_row in enumerate(INVOICE_ROWS):
            if inv_row["status"] in (InvoiceStatus.APPROVED, InvoiceStatus.PAID):
                evt = ErpCrmTimelineEventModel(
                    tenant_id=tenant_id,
                    entity_type=CrmEntityType.CUSTOMER,
                    entity_id=customer_ids[idx % len(customer_ids)],
                    event_type=CrmTimelineEventType.INVOICE_APPROVED,
                    title=f"Invoice {inv_row['number']} approved — ${inv_row['total']}",
                    actor_id=owner_id,
                    payload={"invoice_number": inv_row["number"], "amount": str(inv_row["total"])},
                )
                session.add(evt)
                timeline_count += 1
        for pay_row in PAYMENT_ROWS:
            inv_idx = int(str(pay_row["invoice_idx"]))
            evt = ErpCrmTimelineEventModel(
                tenant_id=tenant_id,
                entity_type=CrmEntityType.CUSTOMER,
                entity_id=customer_ids[inv_idx % len(customer_ids)],
                event_type=CrmTimelineEventType.PAYMENT_APPLIED,
                title=f"Payment {pay_row['number']} applied — ${pay_row['amount']}",
                actor_id=owner_id,
                payload={"payment_number": pay_row["number"], "amount": str(pay_row["amount"])},
            )
            session.add(evt)
            timeline_count += 1
        counts["crm_timeline_events"] = timeline_count

        # ── PRODUCTS ─────────────────────────────────────────────────
        product_ids: list[uuid.UUID] = []
        existing_products = {
            sku
            for (sku,) in (
                await session.execute(
                    select(ErpProductModel.sku).where(ErpProductModel.tenant_id == tenant_id)
                )
            ).all()
        }
        for row in PRODUCT_ROWS:
            if row["sku"] in existing_products:
                pid = (
                    await session.execute(
                        select(ErpProductModel.id).where(
                            ErpProductModel.tenant_id == tenant_id,
                            ErpProductModel.sku == row["sku"],
                        )
                    )
                ).scalar_one()
                product_ids.append(pid)
                continue
            prod = ErpProductModel(
                tenant_id=tenant_id,
                sku=row["sku"],
                name=row["name"],
                category=row.get("category"),
                unit=row.get("unit"),
                cost_price=row["cost"],
                sell_price=row["sell"],
                reorder_point=row.get("reorder", Decimal("0")),
            )
            session.add(prod)
            await session.flush()
            product_ids.append(prod.id)
        counts["products"] = len(product_ids)

        # ── COMPENSATION ─────────────────────────────────────────────
        for row in COMPENSATION_ROWS:
            emp_idx = int(str(row["emp"]))
            comp = CompensationModel(
                tenant_id=tenant_id,
                employee_id=emp_ids[emp_idx],
                monthly_salary=row["monthly"],
                currency=row["currency"],
                effective_from=_date_ago(int(str(row["effective_days_ago"]))),
                is_active=True,
            )
            session.add(comp)
        counts["compensation"] = len(COMPENSATION_ROWS)

        # ── PAYROLL RUNS + ENTRIES ───────────────────────────────────
        for run_row in PAYROLL_RUN_ROWS:
            run = PayrollRunModel(
                tenant_id=tenant_id,
                run_code=run_row["code"],
                period_start=date.fromisoformat(str(run_row["start"])),
                period_end=date.fromisoformat(str(run_row["end"])),
                status=PayrollRunStatus(str(run_row["status"])),
            )

            gross = Decimal("0")
            net = Decimal("0")

            if run_row["status"] in ("paid", "approved", "computed"):
                run.computed_at = _ago(float(str(run_row["days_ago"])))
                run.computed_by = owner_id
            if run_row["status"] in ("paid", "approved"):
                run.approved_at = _ago(float(str(run_row["days_ago"])) - 5)
                run.approved_by = owner_id
            if run_row["status"] == "paid":
                run.paid_at = _ago(float(str(run_row["days_ago"])) - 10)
                run.paid_by = owner_id

            session.add(run)
            await session.flush()

            if run_row["status"] in ("paid", "approved", "computed"):
                for emp_idx, comp_row in enumerate(COMPENSATION_ROWS):
                    if emp_idx >= len(emp_ids):
                        break
                    emp_status = EMPLOYEE_ROWS[emp_idx]["status"]
                    if emp_status == "terminated":
                        continue
                    base = Decimal(str(comp_row["monthly"]))
                    deductions = base * Decimal("0.15")
                    emp_gross = base
                    emp_net = base - deductions
                    gross += emp_gross
                    net += emp_net
                    entry = PayrollEntryModel(
                        tenant_id=tenant_id,
                        run_id=run.id,
                        employee_id=emp_ids[emp_idx],
                        base_salary=base,
                        pay_days=22,
                        gross=emp_gross,
                        deductions=deductions,
                        net=emp_net,
                    )
                    session.add(entry)

            run.total_gross = gross if gross > 0 else None
            run.total_net = net if net > 0 else None

        counts["payroll_runs"] = len(PAYROLL_RUN_ROWS)

        # ── SALES ORDERS + LINES ─────────────────────────────────────
        for idx, row in enumerate(SALES_ORDER_ROWS):
            so = ErpSalesOrderModel(
                tenant_id=tenant_id,
                order_number=row["number"],
                customer_id=customer_ids[idx % len(customer_ids)],
                status=row["status"],
                credit_check=row["credit"],
                subtotal=row["subtotal"],
                discount=row["discount"],
                tax=row["tax"],
                total=row["total"],
                currency_code="USD",
                confirmed_at=_ago(float(str(row["days_ago"])))
                if row["status"] in (OrderStatus.CONFIRMED, OrderStatus.FULFILLED)
                else None,
            )
            session.add(so)
            await session.flush()

            for line in row["lines"]:  # type: ignore[attr-defined]
                sol = ErpSalesOrderLineModel(
                    tenant_id=tenant_id,
                    order_id=so.id,
                    product_id=product_ids[int(line["prod"])],
                    product_name=line["name"],
                    sku=line["sku"],
                    quantity=line["qty"],
                    unit_price=line["price"],
                    discount=line["disc"],
                    tax=line["tax"],
                    line_total=line["total"],
                )
                session.add(sol)
        counts["sales_orders"] = len(SALES_ORDER_ROWS)

        # ── WAREHOUSES ──────────────────────────────────────────────
        wh_ids: list[uuid.UUID] = []
        for row in WAREHOUSE_ROWS:
            wh = ErpWarehouseModel(
                tenant_id=tenant_id,
                name=row["name"],
                location=row.get("location"),
                is_active=row["is_active"],
            )
            session.add(wh)
            await session.flush()
            wh_ids.append(wh.id)
        counts["warehouses"] = len(wh_ids)

        # ── UPDATE PRODUCT REORDER POINTS ────────────────────────────
        for idx, row in enumerate(PRODUCT_ROWS):
            reorder_val = row.get("reorder", Decimal("0"))
            if reorder_val:
                await session.execute(
                    text(
                        "UPDATE erp_products SET reorder_point = :rp "
                        "WHERE tenant_id = :tid AND id = :pid"
                    ),
                    {"rp": reorder_val, "tid": tenant_id, "pid": product_ids[idx]},
                )

        # ── STOCK LEVELS ────────────────────────────────────────────
        for row in STOCK_LEVEL_ROWS:
            sl = ErpStockLevelModel(
                tenant_id=tenant_id,
                product_id=product_ids[int(str(row["prod"]))],
                warehouse_id=wh_ids[int(str(row["wh"]))],
                qty_on_hand=row["on_hand"],
                qty_reserved=row["reserved"],
            )
            session.add(sl)
        counts["stock_levels"] = len(STOCK_LEVEL_ROWS)

        # ── STOCK MOVEMENTS ──────────────────────────────────────────
        for row in STOCK_MOVEMENT_ROWS:
            sm = ErpStockMovementModel(
                tenant_id=tenant_id,
                product_id=product_ids[int(str(row["prod"]))],
                warehouse_id=wh_ids[int(str(row["wh"]))],
                movement_type=row["type"],
                qty=row["qty"],
                ref_type=row["ref"],
                ref_id=row["ref_id"],
            )
            session.add(sm)
        counts["stock_movements"] = len(STOCK_MOVEMENT_ROWS)

        # ── OPENING-BALANCE RECONCILIATION ───────────────────────────
        # Stock levels above are opening balances; in production core
        # recomputes qty_on_hand as the sum of non-reservation/release
        # movements, so the demo ledger must back every level or the
        # ledger-mismatch anomaly rule fires on demo data. Add one
        # balancing entry per (product, warehouse) pair so the
        # non-reservation movement sum equals qty_on_hand. Entries are
        # backdated outside the AI agent's recent-window rules.
        opening_rows = _opening_balance_rows(STOCK_LEVEL_ROWS, STOCK_MOVEMENT_ROWS)
        for orow in opening_rows:
            session.add(
                ErpStockMovementModel(
                    tenant_id=tenant_id,
                    product_id=product_ids[int(str(orow["prod"]))],
                    warehouse_id=wh_ids[int(str(orow["wh"]))],
                    movement_type=orow["type"],
                    qty=orow["qty"],
                    ref_type="opening_balance",
                    ref_id=f"OPB-{orow['prod']:02d}-{orow['wh']}",
                    created_at=_ago(180),
                )
            )
        counts["stock_movements"] = len(STOCK_MOVEMENT_ROWS) + len(opening_rows)

        await session.commit()
        logger.info("seed.demo.complete", tenant_id=str(tenant_id), **counts)
        return counts
