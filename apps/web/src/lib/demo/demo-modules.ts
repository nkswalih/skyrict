import type { DemoState } from "@/lib/demo/demo-store";

export type DemoCell =
  | string
  | { text: string; variant?: "outline" | "secondary" | "destructive" };

export interface DemoColumn {
  key: string;
  label: string;
  align?: "right";
}

export interface DemoRow {
  id: string;
  cells: Record<string, DemoCell>;
}

export interface DemoModuleSpec {
  title: string;
  description: string;
  columns: DemoColumn[];
  rows: DemoRow[];
  emptyMessage: string;
  /** Renders a filter box over every cell when present. */
  searchPlaceholder?: string;
  footnote?: string;
}

function money(value: number): string {
  return `₹${value.toLocaleString()}`;
}

function badge(
  text: string,
  variant: "outline" | "secondary" | "destructive" = "outline",
): DemoCell {
  return { text, variant };
}

function row(id: string, cells: Record<string, DemoCell>): DemoRow {
  return { id, cells };
}

function employeeName(state: DemoState, index: number): string {
  const employee = state.employees[index];
  return employee
    ? `${employee.firstName} ${employee.lastName}`
    : `Employee ${index + 1}`;
}

/**
 * Seeded record views for every sidebar route that used to fall through to the
 * generic "Module Records" placeholder. Everything is derived from the visitor's
 * demo state where possible, so edits made elsewhere in the walkthrough show up
 * here too.
 */
export function getDemoModuleSpec(
  routePath: string,
  state: DemoState,
): DemoModuleSpec | null {
  const activeEmployees = state.employees.filter(
    (employee) => employee.employmentStatus === "active",
  );
  const payrollTotal = activeEmployees.reduce(
    (total, employee) => total + employee.monthlySalary,
    0,
  );
  const paidRevenue = state.invoices
    .filter((invoice) => invoice.status === "paid")
    .reduce((total, invoice) => total + invoice.amount, 0);
  const cogs = state.journalEntries
    .filter((entry) => entry.debitAccount.includes("Cost of Goods Sold"))
    .reduce((total, entry) => total + entry.amount, 0);

  switch (routePath) {
    case "crm/contacts":
      return {
        title: "Contacts",
        description: "Customer and prospect contacts across the demo book.",
        columns: [
          { key: "contact", label: "Contact" },
          { key: "account", label: "Account" },
          { key: "email", label: "Email" },
          { key: "phone", label: "Phone" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("contact-1", {
            contact: "Rahul Nair",
            account: "Vastraline Industries Ltd",
            email: "procurement@vastraline.demo",
            phone: "+91 22 4567 8900",
            status: badge("Active", "secondary"),
          }),
          row("contact-2", {
            contact: "Meera Joshi",
            account: "Apex Distribution Hub",
            email: "billing@apex-dist.demo",
            phone: "+91 22 2345 6789",
            status: badge("Active", "secondary"),
          }),
          row("contact-3", {
            contact: "Karan Rao",
            account: "Global TransLogix",
            email: "accounts@translogix.demo",
            phone: "+91 20 8901 2345",
            status: badge("Active", "secondary"),
          }),
          row("contact-4", {
            contact: "Ishita Bose",
            account: "Horizon Retailers",
            email: "ishita@horizon.demo",
            phone: "+91 94450 88990",
            status: badge("Prospect"),
          }),
        ],
        emptyMessage: "No contacts in the demo workspace yet.",
        footnote: "Read-only sample contacts. Customer records are editable in CRM.",
      };

    case "crm/activities":
      return {
        title: "Activities",
        description: "Calls, emails and follow-ups scheduled by the demo team.",
        columns: [
          { key: "activity", label: "Activity" },
          { key: "subject", label: "Subject" },
          { key: "owner", label: "Owner" },
          { key: "when", label: "When" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("activity-1", {
            activity: "Call",
            subject: "Qualify inbound logistics enquiry",
            owner: "Rohan Mehta",
            when: "Today · 10:30",
            status: badge("Due today", "destructive"),
          }),
          row("activity-2", {
            activity: "Email",
            subject: "Send ERP implementation scope",
            owner: "Rohan Mehta",
            when: "Today · 14:00",
            status: badge("Due today", "destructive"),
          }),
          row("activity-3", {
            activity: "Demo",
            subject: "Warehouse IoT walkthrough",
            owner: "Priya Sharma",
            when: "Tomorrow · 11:00",
            status: badge("Scheduled"),
          }),
          row("activity-4", {
            activity: "Follow-up",
            subject: "Procurement audit next steps",
            owner: "Arjun Patel",
            when: "28 Oct 2026",
            status: badge("Done", "secondary"),
          }),
        ],
        emptyMessage: "No activities scheduled.",
      };

    case "crm/search":
      return {
        title: "Search",
        description: "One search across leads, customers and open deals.",
        columns: [
          { key: "type", label: "Type" },
          { key: "name", label: "Name" },
          { key: "detail", label: "Detail" },
          { key: "status", label: "Status" },
        ],
        rows: [
          ...state.leads.map((lead) =>
            row(`search-lead-${lead.id}`, {
              type: badge("Lead"),
              name: lead.name,
              detail: `${lead.company} · ${lead.email}`,
              status: badge(lead.status),
            }),
          ),
          ...state.customers.map((customer) =>
            row(`search-customer-${customer.id}`, {
              type: badge("Customer"),
              name: customer.name,
              detail: `${customer.customerCode} · ${customer.email}`,
              status: badge(customer.isActive ? "Active" : "Inactive", "secondary"),
            }),
          ),
          ...state.opportunities.map((opportunity) =>
            row(`search-opportunity-${opportunity.id}`, {
              type: badge("Opportunity"),
              name: opportunity.name,
              detail: `${money(opportunity.amount)} · closes ${opportunity.expectedCloseDate}`,
              status: badge(opportunity.stage),
            }),
          ),
        ],
        emptyMessage: "No records match this search.",
        searchPlaceholder: "Search leads, customers and deals...",
      };

    case "inventory/warehouses": {
      const warehouses = new Map<string, typeof state.products>();
      for (const product of state.products) {
        warehouses.set(product.warehouse, [
          ...(warehouses.get(product.warehouse) ?? []),
          product,
        ]);
      }
      return {
        title: "Warehouses",
        description: "Stock distribution across the demo fulfilment network.",
        columns: [
          { key: "warehouse", label: "Warehouse" },
          { key: "skus", label: "SKUs", align: "right" },
          { key: "units", label: "Units on hand", align: "right" },
          { key: "alerts", label: "Reorder alerts", align: "right" },
        ],
        rows: [...warehouses.entries()].map(([warehouse, products]) => {
          const alerts = products.filter(
            (product) => product.qtyOnHand <= product.reorderPoint,
          ).length;
          return row(`warehouse-${warehouse}`, {
            warehouse,
            skus: String(products.length),
            units: String(
              products.reduce((total, product) => total + product.qtyOnHand, 0),
            ),
            alerts: badge(
              String(alerts),
              alerts > 0 ? "destructive" : "secondary",
            ),
          });
        }),
        emptyMessage: "No warehouses configured.",
      };
    }

    case "inventory/movements":
      return {
        title: "Stock Movements",
        description: "Receipts, issues and transfers posted against demo stock.",
        columns: [
          { key: "date", label: "Date" },
          { key: "reference", label: "Reference" },
          { key: "type", label: "Type" },
          { key: "product", label: "Product" },
          { key: "quantity", label: "Qty", align: "right" },
          { key: "warehouse", label: "Warehouse" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("movement-1", {
            date: "2026-10-24",
            reference: "GRN-2026-118",
            type: "Receipt",
            product: "Heavy Duty Conveyor Belt",
            quantity: "+12",
            warehouse: "Central DC",
            status: badge("Posted", "secondary"),
          }),
          row("movement-2", {
            date: "2026-10-23",
            reference: "SO-2026-089",
            type: "Issue",
            product: "Cast Iron Flange Bearings",
            quantity: "−40",
            warehouse: "West Hub",
            status: badge("Posted", "secondary"),
          }),
          row("movement-3", {
            date: "2026-10-22",
            reference: "TRF-2026-044",
            type: "Transfer",
            product: "Industrial Servo Motor 15kW",
            quantity: "3",
            warehouse: "East Warehouse → Central DC",
            status: badge("In transit"),
          }),
          row("movement-4", {
            date: "2026-10-21",
            reference: "ADJ-2026-009",
            type: "Adjustment",
            product: "Pneumatic Control Valve 2-inch",
            quantity: "−2",
            warehouse: "Central DC",
            status: badge("Posted", "secondary"),
          }),
        ],
        emptyMessage: "No stock movements recorded.",
      };

    case "inventory/alerts": {
      const lowStock = state.products.filter(
        (product) => product.qtyOnHand <= product.reorderPoint,
      );
      return {
        title: "Stock Alerts",
        description: "SKUs at or below their reorder threshold.",
        columns: [
          { key: "sku", label: "SKU" },
          { key: "product", label: "Product" },
          { key: "onHand", label: "On hand", align: "right" },
          { key: "reorderAt", label: "Reorder at", align: "right" },
          { key: "severity", label: "Severity" },
        ],
        rows: lowStock.map((product) =>
          row(`alert-${product.id}`, {
            sku: product.sku,
            product: product.name,
            onHand: String(product.qtyOnHand),
            reorderAt: String(product.reorderPoint),
            severity: badge(
              product.qtyOnHand === 0 ? "Out of stock" : "Reorder",
              "destructive",
            ),
          }),
        ),
        emptyMessage: "Every SKU is above its reorder threshold.",
      };
    }

    case "inventory/health":
      return {
        title: "Stock Health",
        description: "Availability status for every SKU in the demo catalog.",
        columns: [
          { key: "sku", label: "SKU" },
          { key: "product", label: "Product" },
          { key: "warehouse", label: "Warehouse" },
          { key: "onHand", label: "On hand", align: "right" },
          { key: "reorderAt", label: "Reorder at", align: "right" },
          { key: "status", label: "Health" },
        ],
        rows: state.products.map((product) => {
          const status =
            product.qtyOnHand === 0
              ? badge("Out of stock", "destructive")
              : product.qtyOnHand <= product.reorderPoint
                ? badge("Reorder", "destructive")
                : product.qtyOnHand <= product.reorderPoint * 2
                  ? badge("Watch")
                  : badge("Healthy", "secondary");
          return row(`health-${product.id}`, {
            sku: product.sku,
            product: product.name,
            warehouse: product.warehouse,
            onHand: String(product.qtyOnHand),
            reorderAt: String(product.reorderPoint),
            status,
          });
        }),
        emptyMessage: "No SKUs in the demo catalog.",
      };

    case "hr/departments": {
      const departments = new Map<string, typeof state.employees>();
      for (const employee of activeEmployees) {
        departments.set(employee.department, [
          ...(departments.get(employee.department) ?? []),
          employee,
        ]);
      }
      return {
        title: "Departments",
        description: "Headcount and monthly compensation by department.",
        columns: [
          { key: "department", label: "Department" },
          { key: "headcount", label: "Headcount", align: "right" },
          { key: "payroll", label: "Monthly payroll", align: "right" },
          { key: "share", label: "Share of roster", align: "right" },
        ],
        rows: [...departments.entries()].map(([department, employees]) => {
          const payroll = employees.reduce(
            (total, employee) => total + employee.monthlySalary,
            0,
          );
          return row(`department-${department}`, {
            department,
            headcount: String(employees.length),
            payroll: money(payroll),
            share: `${Math.round((employees.length / (activeEmployees.length || 1)) * 100)}%`,
          });
        }),
        emptyMessage: "No departments with active employees.",
      };
    }

    case "hr/leave":
      return {
        title: "Leave",
        description: "Open and approved leave requests for the demo roster.",
        columns: [
          { key: "employee", label: "Employee" },
          { key: "type", label: "Type" },
          { key: "from", label: "From" },
          { key: "to", label: "To" },
          { key: "days", label: "Days", align: "right" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("leave-1", {
            employee: employeeName(state, 0),
            type: "Annual",
            from: "02 Nov 2026",
            to: "06 Nov 2026",
            days: "5",
            status: badge("Approved", "secondary"),
          }),
          row("leave-2", {
            employee: employeeName(state, 2),
            type: "Sick",
            from: "27 Oct 2026",
            to: "27 Oct 2026",
            days: "1",
            status: badge("Pending"),
          }),
          row("leave-3", {
            employee: employeeName(state, 3),
            type: "Casual",
            from: "30 Oct 2026",
            to: "30 Oct 2026",
            days: "1",
            status: badge("Approved", "secondary"),
          }),
        ],
        emptyMessage: "No leave requests in this period.",
      };

    case "hr/attendance":
      return {
        title: "Attendance",
        description: "Current-month attendance summary for active employees.",
        columns: [
          { key: "employee", label: "Employee" },
          { key: "workingDays", label: "Working days", align: "right" },
          { key: "present", label: "Present", align: "right" },
          { key: "late", label: "Late", align: "right" },
          { key: "absent", label: "Absent", align: "right" },
          { key: "rate", label: "Attendance", align: "right" },
        ],
        rows: activeEmployees.map((employee, index) => {
          const present = [21, 20, 22, 19][index] ?? 20;
          const late = [1, 0, 0, 2][index] ?? 0;
          const absent = 22 - present;
          return row(`attendance-${employee.id}`, {
            employee: `${employee.firstName} ${employee.lastName}`,
            workingDays: "22",
            present: String(present),
            late: String(late),
            absent: String(absent),
            rate: `${Math.round((present / 22) * 100)}%`,
          });
        }),
        emptyMessage: "No active employees to report.",
      };

    case "hr/data-quality":
      return {
        title: "Data Quality",
        description: "Open people-data issues found by the demo quality scan.",
        columns: [
          { key: "issue", label: "Issue" },
          { key: "records", label: "Records", align: "right" },
          { key: "severity", label: "Severity" },
          { key: "owner", label: "Owner" },
        ],
        rows: [
          row("data-quality-1", {
            issue: "Missing tax identifier (PAN)",
            records: "2",
            severity: badge("High", "destructive"),
            owner: "People Ops",
          }),
          row("data-quality-2", {
            issue: "Bank account pending verification",
            records: "1",
            severity: badge("Medium"),
            owner: "Finance",
          }),
          row("data-quality-3", {
            issue: "Manager not assigned",
            records: "1",
            severity: badge("Low"),
            owner: "People Ops",
          }),
          row("data-quality-4", {
            issue: "Salary band older than 12 months",
            records: "3",
            severity: badge("Low"),
            owner: "Compensation",
          }),
        ],
        emptyMessage: "No data-quality issues found.",
      };

    case "finance/accounts":
      return {
        title: "Chart of Accounts",
        description: "Demo ledger accounts and their current balances.",
        columns: [
          { key: "code", label: "Code" },
          { key: "account", label: "Account" },
          { key: "type", label: "Type" },
          { key: "balance", label: "Balance", align: "right" },
        ],
        rows: [
          row("account-1100", {
            code: "1100",
            account: "Operating Cash",
            type: "Asset",
            balance: money(4850000),
          }),
          row("account-1200", {
            code: "1200",
            account: "Accounts Receivable",
            type: "Asset",
            balance: money(765000),
          }),
          row("account-1300", {
            code: "1300",
            account: "Inventory Asset",
            type: "Asset",
            balance: money(1245000),
          }),
          row("account-2010", {
            code: "2010",
            account: "Payroll Payable",
            type: "Liability",
            balance: money(payrollTotal),
          }),
          row("account-5000", {
            code: "5000",
            account: "Cost of Goods Sold",
            type: "Expense",
            balance: money(cogs),
          }),
          row("account-5010", {
            code: "5010",
            account: "Salaries Expense",
            type: "Expense",
            balance: money(payrollTotal),
          }),
        ],
        emptyMessage: "No accounts configured.",
      };

    case "finance/journal-entries":
      return {
        title: "Journal Entries",
        description: "Posted and draft general-ledger entries in the demo.",
        columns: [
          { key: "entry", label: "Entry #" },
          { key: "date", label: "Date" },
          { key: "description", label: "Description" },
          { key: "debit", label: "Debit" },
          { key: "credit", label: "Credit" },
          { key: "amount", label: "Amount", align: "right" },
          { key: "status", label: "Status" },
        ],
        rows: state.journalEntries.map((entry) =>
          row(`journal-${entry.id}`, {
            entry: entry.entryNumber,
            date: entry.date,
            description: entry.description,
            debit: entry.debitAccount,
            credit: entry.creditAccount,
            amount: money(entry.amount),
            status: badge(
              entry.status,
              entry.status === "posted" ? "secondary" : "outline",
            ),
          }),
        ),
        emptyMessage: "No journal entries in this period.",
      };

    case "finance/fiscal-periods":
      return {
        title: "Fiscal Periods",
        description: "Open and closed accounting periods for FY 2026–27.",
        columns: [
          { key: "period", label: "Period" },
          { key: "range", label: "Range" },
          { key: "status", label: "Status" },
          { key: "journals", label: "Journals", align: "right" },
        ],
        rows: [
          row("period-oct", {
            period: "Oct 2026",
            range: "01 Oct – 31 Oct 2026",
            status: badge("Open"),
            journals: String(state.journalEntries.length),
          }),
          row("period-sep", {
            period: "Sep 2026",
            range: "01 Sep – 30 Sep 2026",
            status: badge("Closed", "secondary"),
            journals: "14",
          }),
          row("period-aug", {
            period: "Aug 2026",
            range: "01 Aug – 31 Aug 2026",
            status: badge("Closed", "secondary"),
            journals: "11",
          }),
          row("period-jul", {
            period: "Jul 2026",
            range: "01 Jul – 31 Jul 2026",
            status: badge("Closed", "secondary"),
            journals: "16",
          }),
        ],
        emptyMessage: "No fiscal periods configured.",
      };

    case "finance/statements": {
      const grossProfit = paidRevenue - cogs;
      const operatingIncome = grossProfit - payrollTotal;
      return {
        title: "Financial Statements",
        description: "Profit and loss summary derived from the demo ledger.",
        columns: [
          { key: "line", label: "Line item" },
          { key: "category", label: "Category" },
          { key: "amount", label: "Amount", align: "right" },
        ],
        rows: [
          row("statement-revenue", {
            line: "Revenue received",
            category: "Income",
            amount: money(paidRevenue),
          }),
          row("statement-cogs", {
            line: "Cost of goods sold",
            category: "Expense",
            amount: money(cogs),
          }),
          row("statement-gross", {
            line: "Gross profit",
            category: "Subtotal",
            amount: money(grossProfit),
          }),
          row("statement-payroll", {
            line: "Payroll expense",
            category: "Expense",
            amount: money(payrollTotal),
          }),
          row("statement-operating", {
            line: "Operating income",
            category: "Subtotal",
            amount: money(operatingIncome),
          }),
        ],
        emptyMessage: "No ledger activity to summarise.",
        footnote:
          "Revenue uses paid invoices; COGS and payroll use posted journal entries.",
      };
    }

    case "finance/controls":
      return {
        title: "Planning & Policy",
        description: "Financial controls and policy checks in the demo workspace.",
        columns: [
          { key: "control", label: "Control" },
          { key: "policy", label: "Policy" },
          { key: "owner", label: "Owner" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("control-1", {
            control: "Segregation of duties",
            policy: "Journal preparer cannot approve",
            owner: "Controller",
            status: badge("Enforced", "secondary"),
          }),
          row("control-2", {
            control: "Journal approval threshold",
            policy: "Above ₹100,000 needs a second approver",
            owner: "Finance",
            status: badge("Enforced", "secondary"),
          }),
          row("control-3", {
            control: "Bank reconciliation",
            policy: "Completed within 2 business days",
            owner: "Treasury",
            status: badge("On track"),
          }),
          row("control-4", {
            control: "Expense policy attestation",
            policy: "Quarterly, all cost-centre owners",
            owner: "Finance Ops",
            status: badge("Due 31 Oct", "destructive"),
          }),
        ],
        emptyMessage: "No controls configured.",
      };

    case "finance/audit-log":
      return {
        title: "Audit Log",
        description: "Recent finance actions recorded in the demo workspace.",
        columns: [
          { key: "when", label: "When" },
          { key: "actor", label: "Actor" },
          { key: "action", label: "Action" },
          { key: "entity", label: "Entity" },
          { key: "status", label: "Result" },
        ],
        rows: [
          ...state.journalEntries.map((entry, index) =>
            row(`audit-journal-${entry.id}`, {
              when: `${entry.date} · 09:${String(12 + index).padStart(2, "0")}`,
              actor: "Arjun Patel",
              action: "Posted journal entry",
              entity: entry.entryNumber,
              status: badge("Success", "secondary"),
            }),
          ),
          row("audit-invoice", {
            when: "2026-10-20 · 16:04",
            actor: "System",
            action: "Marked invoice paid",
            entity: "INV-2026-043",
            status: badge("Success", "secondary"),
          }),
          row("audit-export", {
            when: "2026-10-19 · 11:42",
            actor: "Priya Sharma",
            action: "Exported AR aging report",
            entity: "Reports",
            status: badge("Success", "secondary"),
          }),
        ],
        emptyMessage: "No audit events in this period.",
      };

    case "finance/settings":
      return {
        title: "Finance Settings",
        description: "Demo accounting configuration (read-only).",
        columns: [
          { key: "setting", label: "Setting" },
          { key: "value", label: "Value" },
          { key: "scope", label: "Scope" },
        ],
        rows: [
          row("finance-setting-currency", {
            setting: "Base currency",
            value: "INR (₹)",
            scope: "Organisation",
          }),
          row("finance-setting-year", {
            setting: "Fiscal year start",
            value: "01 April",
            scope: "Organisation",
          }),
          row("finance-setting-method", {
            setting: "Inventory costing",
            value: "Weighted average",
            scope: "Inventory",
          }),
          row("finance-setting-approval", {
            setting: "Journal approval threshold",
            value: money(100000),
            scope: "General ledger",
          }),
          row("finance-setting-tax", {
            setting: "Default tax profile",
            value: "GST 18%",
            scope: "Sales & purchases",
          }),
        ],
        emptyMessage: "No finance settings configured.",
      };

    case "payroll/reviews":
      return {
        title: "Payroll Reviews",
        description: "Approval state for the latest demo payroll cycles.",
        columns: [
          { key: "run", label: "Run" },
          { key: "reviewer", label: "Reviewer" },
          { key: "submitted", label: "Submitted" },
          { key: "variance", label: "Variance", align: "right" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("payroll-review-1", {
            run: "PR-2026-10",
            reviewer: "Priya Sharma",
            submitted: "24 Oct 2026",
            variance: "0.0%",
            status: badge("Awaiting approval"),
          }),
          row("payroll-review-2", {
            run: "PR-2026-09",
            reviewer: "Priya Sharma",
            submitted: "24 Sep 2026",
            variance: "1.2%",
            status: badge("Approved", "secondary"),
          }),
          row("payroll-review-3", {
            run: "PR-2026-08",
            reviewer: "Arjun Patel",
            submitted: "24 Aug 2026",
            variance: "0.4%",
            status: badge("Approved", "secondary"),
          }),
        ],
        emptyMessage: "No payroll runs awaiting review.",
      };

    case "payroll/compensation":
      return {
        title: "Compensation",
        description: "Monthly and annualised compensation for the demo roster.",
        columns: [
          { key: "employee", label: "Employee" },
          { key: "department", label: "Department" },
          { key: "monthly", label: "Monthly", align: "right" },
          { key: "annual", label: "Annual CTC", align: "right" },
          { key: "effective", label: "Effective" },
        ],
        rows: activeEmployees.map((employee) =>
          row(`compensation-${employee.id}`, {
            employee: `${employee.firstName} ${employee.lastName}`,
            department: employee.department,
            monthly: money(employee.monthlySalary),
            annual: money(employee.monthlySalary * 12),
            effective: "01 Apr 2026",
          }),
        ),
        emptyMessage: "No active employees to compensate.",
      };

    case "payroll/settings":
      return {
        title: "Payroll Settings",
        description: "Demo payroll configuration (read-only).",
        columns: [
          { key: "setting", label: "Setting" },
          { key: "value", label: "Value" },
        ],
        rows: [
          row("payroll-setting-cycle", {
            setting: "Pay cycle",
            value: "Monthly · last working day",
          }),
          row("payroll-setting-cutoff", {
            setting: "Input cut-off",
            value: "20th of the pay month",
          }),
          row("payroll-setting-pf", {
            setting: "Provident fund",
            value: "12% employer + 12% employee",
          }),
          row("payroll-setting-tds", {
            setting: "TDS",
            value: "As per Indian income-tax slabs",
          }),
          row("payroll-setting-approval", {
            setting: "Approval chain",
            value: "People Ops → Finance → Founder",
          }),
        ],
        emptyMessage: "No payroll settings configured.",
      };

    case "documents":
    case "documents/list":
      return {
        title: routePath === "documents/list" ? "All Documents" : "Documents",
        description:
          routePath === "documents/list"
            ? "Every sample document attached to the demo workspace."
            : "Contracts, invoices and compliance files in the demo.",
        columns: [
          { key: "document", label: "Document" },
          { key: "type", label: "Type" },
          { key: "owner", label: "Owner" },
          { key: "updated", label: "Updated" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("document-1", {
            document: "Vastraline master services agreement",
            type: "Contract",
            owner: "Legal",
            updated: "18 Oct 2026",
            status: badge("Signed", "secondary"),
          }),
          row("document-2", {
            document: "INV-2026-043 · Apex Distribution",
            type: "Invoice",
            owner: "Finance",
            updated: "20 Oct 2026",
            status: badge("Paid", "secondary"),
          }),
          row("document-3", {
            document: "GST filing · September 2026",
            type: "Compliance",
            owner: "Finance",
            updated: "12 Oct 2026",
            status: badge("Filed", "secondary"),
          }),
          row("document-4", {
            document: "Warehouse safety audit",
            type: "Report",
            owner: "Operations",
            updated: "08 Oct 2026",
            status: badge("Draft"),
          }),
        ],
        emptyMessage: "No documents in the demo workspace.",
      };

    case "reports":
      return {
        title: "Reports",
        description: "Sample operational reports available in a live workspace.",
        columns: [
          { key: "report", label: "Report" },
          { key: "module", label: "Module" },
          { key: "schedule", label: "Schedule" },
          { key: "updated", label: "Last updated" },
          { key: "status", label: "Status" },
        ],
        rows: [
          row("report-1", {
            report: "Sales pipeline by stage",
            module: "CRM",
            schedule: "Weekly · Monday",
            updated: "24 Oct 2026",
            status: badge("Ready", "secondary"),
          }),
          row("report-2", {
            report: "Inventory reorder forecast",
            module: "Inventory",
            schedule: "Daily",
            updated: "25 Oct 2026",
            status: badge("Ready", "secondary"),
          }),
          row("report-3", {
            report: "Payroll variance",
            module: "Payroll",
            schedule: "Monthly",
            updated: "24 Oct 2026",
            status: badge("Ready", "secondary"),
          }),
          row("report-4", {
            report: "Cash-flow statement",
            module: "Finance",
            schedule: "Monthly",
            updated: "23 Oct 2026",
            status: badge("Ready", "secondary"),
          }),
        ],
        emptyMessage: "No reports available.",
      };

    default:
      return null;
  }
}
