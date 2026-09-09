"""Phase-1 report definition seeds (RPT-DATA-001, M-RPT §Reporting view).

The single canonical source for the Phase-1 report pack: migration 0036 seeds
every existing tenant from these definitions, and ``core.seed`` applies the
same pack when a new tenant is provisioned. There is deliberately exactly one
copy of each definition here - neither the migration nor the provisioning
hook maintains its own list.

Every seed carries its SQL text (the dataset query), the whitelist of bind
parameters the query is allowed to use, and the permission key that gates the
endpoint serving it. The SQL must satisfy :func:`validate_read_only_sql` -
the seed catalog test and both call sites enforce that before anything is
persisted.

The 12 reports mirror ``docs/architecture/erp-phase1.md`` §M-RPT exactly:

  Financial  - pnl_by_period, ar_aging, cash_received
  Sales/CRM  - pipeline_value_by_stage, orders_by_period, top_customers
  Inventory  - stock_on_hand_vs_reorder, movement_by_type, slow_movers
  HR         - headcount_by_department, leave_usage, payroll_cost_by_period

Column names reference the real ERP tables (``erp_*``) and their tenant
composite keys, so a report is always tenant-filtered and joins never cross
tenants.

NL-builder semantics (RPT-AI-001, SKY-80): every seed carries ``dataset``,
``dimensions`` and ``measures`` - the selectable vocabulary the LLM may choose
from when interpreting a natural-language request. These are pure metadata
(no schema column): the catalog is the whitelist, and the API surface exposes
them so the AI agent never invents datasets, grouping dimensions, or numeric
measures that the reviewed templates do not provide.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.core.permissions import ERP_REPORTS_READ


@dataclass(frozen=True, slots=True)
class ReportDefinitionSeed:
    """One report definition to seed for every tenant.

    ``params`` is the allow-list of ``:name`` bind parameters the query may
    use (every bind in ``sql`` must be listed here; unused declarations are
    a catalog error caught by the seed test).

    ``dataset``, ``dimensions`` and ``measures`` are the NL report builder's
    selectable vocabulary (RPT-AI-001, SKY-80) - the only datasets, grouping
    dimensions, and numeric measures an LLM may pick for this report. They
    mirror the query's output columns so validation can never accept a
    dimension/measure the template does not actually produce.
    """

    slug: str
    title: str
    module: str
    description: str
    sql: str
    params: tuple[str, ...]
    dataset: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    permission_key: str = ERP_REPORTS_READ
    version: int = 1


PHASE_1_REPORT_SEEDS: tuple[ReportDefinitionSeed, ...] = (
    # ------------------------------------------------------------------ #
    # Financial                                                          #
    # ------------------------------------------------------------------ #
    ReportDefinitionSeed(
        slug="pnl_by_period",
        title="P&L by period",
        module="finance",
        description=(
            "Profit and loss grouped by revenue/expense account for posted "
            "journal entries in the selected period."
        ),
        sql="""
SELECT coa.code,
       coa.name AS account_name,
       coa.account_type,
       SUM(jl.debit) AS total_debit,
       SUM(jl.credit) AS total_credit
  FROM erp_journal_lines jl
  JOIN erp_journal_entries je ON je.tenant_id = jl.tenant_id AND je.id = jl.entry_id
  JOIN erp_chart_of_accounts coa ON coa.tenant_id = jl.tenant_id AND coa.id = jl.account_id
 WHERE jl.tenant_id = :tenant_id
   AND je.status = 'posted'
   AND coa.account_type IN ('revenue', 'expense')
   AND je.entry_date BETWEEN :from_date AND :to_date
 GROUP BY coa.code, coa.name, coa.account_type
 ORDER BY coa.account_type, coa.code
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="profit and loss journal entries",
        dimensions=("account code", "account name", "account type"),
        measures=("total debit", "total credit"),
    ),
    ReportDefinitionSeed(
        slug="ar_aging",
        title="Accounts receivable aging",
        module="finance",
        description=(
            "Open invoices bucketed by days past due (current, 1-30, 31-60, "
            "61-90, 90+) with outstanding balance after applied payments."
        ),
        sql="""
SELECT i.invoice_number,
       i.invoice_date,
       i.due_date,
       i.total,
       COALESCE(SUM(p.amount), 0) AS paid_total,
       i.total - COALESCE(SUM(p.amount), 0) AS outstanding,
       CASE
         WHEN i.due_date < DATE(:as_of_date) - INTERVAL '90 days' THEN '90+'
         WHEN i.due_date < DATE(:as_of_date) - INTERVAL '60 days' THEN '61-90'
         WHEN i.due_date < DATE(:as_of_date) - INTERVAL '30 days' THEN '31-60'
         WHEN i.due_date < DATE(:as_of_date) THEN '1-30'
         ELSE 'current'
       END AS aging_bucket
  FROM erp_invoices i
  LEFT JOIN erp_payments p
         ON p.tenant_id = i.tenant_id
        AND p.invoice_id = i.id
        AND p.status = 'applied'
 WHERE i.tenant_id = :tenant_id
   AND i.status IN ('issued', 'approved')
GROUP BY i.invoice_number, i.invoice_date, i.due_date, i.total
  ORDER BY i.due_date, i.invoice_number
""".strip(),
        params=("tenant_id", "as_of_date"),
        dataset="open invoices",
        dimensions=("invoice number", "aging bucket"),
        measures=("invoice total", "paid total", "outstanding balance"),
        version=2,
    ),
    ReportDefinitionSeed(
        slug="cash_received",
        title="Cash received",
        module="finance",
        description="Applied payments by day and method within the selected period.",
        sql="""
SELECT DATE(p.paid_at) AS payment_date,
       p.method AS payment_method,
       COUNT(*) AS payment_count,
       SUM(p.amount) AS total_received
  FROM erp_payments p
 WHERE p.tenant_id = :tenant_id
   AND p.status = 'applied'
   AND DATE(p.paid_at) BETWEEN :from_date AND :to_date
 GROUP BY DATE(p.paid_at), p.method
 ORDER BY payment_date, p.method
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="applied payments",
        dimensions=("payment date", "payment method"),
        measures=("payment count", "total received"),
    ),
    # ------------------------------------------------------------------ #
    # Sales / CRM                                                         #
    # ------------------------------------------------------------------ #
    ReportDefinitionSeed(
        slug="pipeline_value_by_stage",
        title="Pipeline value by stage",
        module="sales",
        description="Open CRM opportunities grouped by pipeline stage with counts and value.",
        sql="""
SELECT stage,
       COUNT(*) AS opportunity_count,
       COALESCE(SUM(amount), 0) AS pipeline_value
  FROM erp_crm_opportunities
 WHERE tenant_id = :tenant_id
   AND stage NOT IN ('won', 'lost')
 GROUP BY stage
 ORDER BY pipeline_value DESC
""".strip(),
        params=("tenant_id",),
        dataset="open crm opportunities",
        dimensions=("stage",),
        measures=("opportunity count", "pipeline value"),
    ),
    ReportDefinitionSeed(
        slug="orders_by_period",
        title="Sales orders by period",
        module="sales",
        description="Confirmed and fulfilled sales orders by day within the selected period.",
        sql="""
SELECT DATE(created_at) AS order_date,
       COUNT(*) AS order_count,
       COALESCE(SUM(total), 0) AS order_value
  FROM erp_sales_orders
 WHERE tenant_id = :tenant_id
   AND status IN ('confirmed', 'fulfilled')
   AND DATE(created_at) BETWEEN :from_date AND :to_date
 GROUP BY DATE(created_at)
 ORDER BY order_date
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="sales orders",
        dimensions=("order date",),
        measures=("order count", "order value"),
    ),
    ReportDefinitionSeed(
        slug="top_customers",
        title="Top customers",
        module="sales",
        description="Top 10 customers by lifetime value of confirmed and fulfilled orders.",
        sql="""
SELECT c.customer_code,
       c.name AS customer_name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total), 0) AS lifetime_value
  FROM erp_crm_customers c
  LEFT JOIN erp_sales_orders o
         ON o.tenant_id = c.tenant_id
        AND o.customer_id = c.id
        AND o.status IN ('confirmed', 'fulfilled')
 WHERE c.tenant_id = :tenant_id
   AND c.is_active = TRUE
GROUP BY c.customer_code, c.name
  ORDER BY lifetime_value DESC
  LIMIT 10
""".strip(),
        params=("tenant_id",),
        dataset="customers with confirmed and fulfilled orders",
        dimensions=("customer code", "customer name"),
        measures=("order count", "lifetime value"),
        version=2,
    ),
    # ------------------------------------------------------------------ #
    # Inventory                                                           #
    # ------------------------------------------------------------------ #
    ReportDefinitionSeed(
        slug="stock_on_hand_vs_reorder",
        title="Stock on hand vs reorder point",
        module="inventory",
        description="Active products at or below their reorder point with the gap.",
        sql="""
SELECT p.sku,
       p.name AS product_name,
       COALESCE(sl.qty_on_hand, 0) AS qty_on_hand,
       p.reorder_point,
       p.reorder_point - COALESCE(sl.qty_on_hand, 0) AS gap_to_reorder
  FROM erp_products p
  LEFT JOIN erp_stock_levels sl
         ON sl.tenant_id = p.tenant_id
        AND sl.product_id = p.id
WHERE p.tenant_id = :tenant_id
   AND p.is_active = TRUE
   AND COALESCE(sl.qty_on_hand, 0) < p.reorder_point
  ORDER BY gap_to_reorder DESC
""".strip(),
        params=("tenant_id",),
        dataset="products at or below their reorder point",
        dimensions=("sku", "product name"),
        measures=("qty on hand", "reorder point", "gap to reorder"),
        version=2,
    ),
    ReportDefinitionSeed(
        slug="movement_by_type",
        title="Stock movement by type",
        module="inventory",
        description="Stock movements grouped by movement type within the selected period.",
        sql="""
SELECT movement_type,
       COUNT(*) AS movement_count,
       SUM(qty) AS net_qty
  FROM erp_stock_movements
 WHERE tenant_id = :tenant_id
   AND DATE(created_at) BETWEEN :from_date AND :to_date
 GROUP BY movement_type
 ORDER BY movement_count DESC
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="stock movements",
        dimensions=("movement type",),
        measures=("movement count", "net qty"),
    ),
    ReportDefinitionSeed(
        slug="slow_movers",
        title="Slow-moving stock",
        module="inventory",
        description="Active products with zero movements in the selected period.",
        sql="""
SELECT p.sku,
       p.name AS product_name,
       COALESCE(sl.qty_on_hand, 0) AS qty_on_hand,
       COALESCE(mv.movement_count, 0) AS movement_count
  FROM erp_products p
  LEFT JOIN erp_stock_levels sl
         ON sl.tenant_id = p.tenant_id
        AND sl.product_id = p.id
  LEFT JOIN (
        SELECT tenant_id, product_id, COUNT(*) AS movement_count
          FROM erp_stock_movements
         WHERE tenant_id = :tenant_id
           AND DATE(created_at) BETWEEN :from_date AND :to_date
         GROUP BY tenant_id, product_id
       ) mv
         ON mv.tenant_id = p.tenant_id
        AND mv.product_id = p.id
WHERE p.tenant_id = :tenant_id
   AND p.is_active = TRUE
   AND COALESCE(mv.movement_count, 0) = 0
  ORDER BY p.sku
  LIMIT 10
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="products with no stock movements",
        dimensions=("sku", "product name"),
        measures=("qty on hand", "movement count"),
        version=2,
    ),
    # ------------------------------------------------------------------ #
    # HR                                                                  #
    # ------------------------------------------------------------------ #
    ReportDefinitionSeed(
        slug="headcount_by_department",
        title="Headcount by department",
        module="hr",
        description="Current (non-terminated) employees grouped by department.",
        sql="""
SELECT d.name AS department_name,
       COUNT(e.id) AS headcount
  FROM erp_departments d
  LEFT JOIN erp_employees e
         ON e.tenant_id = d.tenant_id
        AND e.department_id = d.id
        AND e.employment_status <> 'terminated'
 WHERE d.tenant_id = :tenant_id
 GROUP BY d.name
 ORDER BY headcount DESC
""".strip(),
        params=("tenant_id",),
        dataset="current employees",
        dimensions=("department name",),
        measures=("headcount",),
    ),
    ReportDefinitionSeed(
        slug="leave_usage",
        title="Leave usage",
        module="hr",
        description="Approved leave requests by type within the selected period.",
        sql="""
SELECT lt.code AS leave_type_code,
       lt.name AS leave_type_name,
       COALESCE(SUM(lm.qty), 0) AS days_used,
       COUNT(lm.id) AS request_count
  FROM erp_leave_movements lm
  JOIN erp_leave_types lt
    ON lt.tenant_id = lm.tenant_id
   AND lt.code = lm.leave_type
 WHERE lm.tenant_id = :tenant_id
   AND lm.ref_type = 'leave_request'
   AND DATE(lm.occurred_at) BETWEEN :from_date AND :to_date
GROUP BY lt.code, lt.name
  ORDER BY days_used DESC
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="approved leave requests",
        dimensions=("leave type code", "leave type name"),
        measures=("days used", "request count"),
        version=2,
    ),
    ReportDefinitionSeed(
        slug="payroll_cost_by_period",
        title="Payroll cost by period",
        module="hr",
        description="Gross/deductions/net totals per non-void payroll run in the period.",
        sql="""
SELECT pr.period_start,
       pr.period_end,
       pr.run_code,
       COUNT(pe.id) AS employee_count,
       COALESCE(SUM(pe.gross), 0) AS total_gross,
       COALESCE(SUM(pe.deductions), 0) AS total_deductions,
       COALESCE(SUM(pe.net), 0) AS total_net
  FROM erp_payroll_runs pr
  LEFT JOIN erp_payroll_entries pe
         ON pe.tenant_id = pr.tenant_id
        AND pe.run_id = pr.id
 WHERE pr.tenant_id = :tenant_id
   AND pr.status IN ('computed', 'approved', 'paid')
   AND pr.period_start BETWEEN :from_date AND :to_date
GROUP BY pr.period_start, pr.period_end, pr.run_code
  ORDER BY pr.period_start, pr.run_code
""".strip(),
        params=("tenant_id", "from_date", "to_date"),
        dataset="payroll runs",
        dimensions=("period start", "period end", "run code"),
        measures=("employee count", "total gross", "total deductions", "total net"),
        version=2,
    ),
)


def is_seed_stale(seed: ReportDefinitionSeed, *, version: int, sql: str) -> bool:
    """Return whether a stored definition lags the canonical seed.

    A stored definition is stale when its version is older than the seed's or
    when its stored SQL differs from the canonical seed after normalizing
    whitespace (the two write paths historically collapsed whitespace, so a
    whitespace-only difference must NOT count as drift).

    This is the single drift signal the migration and the provisioning hook
    share - both must classify "in sync" the same way so re-runs are stable
    and never rewrite identical rows.
    """
    if version < seed.version:
        return True
    return normalize_sql(sql) != normalize_sql(seed.sql)


def normalize_sql(sql: str) -> str:
    """Collapse whitespace for content comparison (whitespace != drift)."""
    return " ".join(sql.split())


def find_seed_by_slug(slug: str) -> ReportDefinitionSeed | None:
    """Return the canonical seed for a slug, or None when not a whitelisted report.

    The NL report builder (RPT-AI-001, SKY-80) only ever persists a new
    definition whose SQL is EXACTLY one of these whitelisted templates - the
    create path resolves the template by this lookup so no arbitrary or
    AI-generated SQL can reach the database.
    """
    for seed in PHASE_1_REPORT_SEEDS:
        if seed.slug == slug:
            return seed
    return None


def find_seed_for_sql(sql: str) -> ReportDefinitionSeed | None:
    """Return the canonical seed whose SQL matches *sql* (whitespace-insensitive).

    Stored rows may collapse whitespace (the legacy write paths did), so the
    match normalizes both sides. Saved reports created by the NL builder carry
    the user's own slug but their SQL is byte-for-byte one of the whitelisted
    templates, so the API surface can enrich a user-created definition with
    the template's dataset/dimensions/measures semantics by matching on SQL
    content when the slug does not resolve.
    """
    target = normalize_sql(sql)
    for seed in PHASE_1_REPORT_SEEDS:
        if normalize_sql(seed.sql) == target:
            return seed
    return None


__all__ = [
    "PHASE_1_REPORT_SEEDS",
    "ReportDefinitionSeed",
    "find_seed_by_slug",
    "find_seed_for_sql",
    "is_seed_stale",
    "normalize_sql",
]
