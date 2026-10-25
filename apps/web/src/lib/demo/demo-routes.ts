/**
 * Route allowlist for the public demo.
 *
 * The catch-all route used to render a generic "Module Records" page for ANY
 * slug, so a typo (`/demo/erp/does-not-exist`) looked like a real module and
 * returned HTTP 200. The server layout validates against this list and calls
 * `notFound()` for anything else.
 *
 * `AI_ROUTES` is the single source of truth for AI-gated screens. The previous
 * substring check (`routePath.includes("ai")`) both misclassified unrelated
 * future paths and missed real AI nav rows such as `inventory/abc` and
 * `hr/attrition` (all gated by `erp.ai.*` permissions in sidebar-config).
 */

export const DEMO_HOME = "/demo/erp";

/** Paths under `/demo/erp` implemented by bespoke screens. */
const BESPOKE_ROUTES = [
    "crm",
    "crm/overview",
    "crm/leads",
    "crm/opportunities",
    "crm/customers",
    "inventory",
    "inventory/overview",
    "inventory/products",
    "inventory/stock",
    "finance",
    "finance/overview",
    "finance/invoices",
    "orders",
    "sales",
    "hr",
    "hr/overview",
    "hr/employees",
    "payroll",
    "payroll/runs",
    "profile",
    "settings",
    "settings/appearance",
    "settings/workspace",
    "settings/notifications",
    "settings/billing",
    "settings/security",
    "settings/integrations",
] as const;

/** AI-gated previews (gate rendered, no AI stack called). */
export const DEMO_AI_ROUTES = new Set<string>([
    "crm/ai",
    "inventory/suggestions",
    "inventory/anomalies",
    "inventory/forecast",
    "inventory/abc",
    "hr/ai-alerts",
    "hr/attrition",
    "hr/planning",
    "hr/compliance",
    "hr/correlation",
    "finance/ai-docs",
    "payroll/automation",
    "payroll/anomalies",
]);

/** Remaining sidebar modules rendered from seeded demo data. */
export const DEMO_MODULE_ROUTES = new Set<string>([
    "crm/contacts",
    "crm/activities",
    "crm/search",
    "inventory/warehouses",
    "inventory/movements",
    "inventory/alerts",
    "inventory/health",
    "hr/departments",
    "hr/leave",
    "hr/attendance",
    "hr/data-quality",
    "finance/accounts",
    "finance/journal-entries",
    "finance/fiscal-periods",
    "finance/statements",
    "finance/controls",
    "finance/audit-log",
    "finance/settings",
    "payroll/reviews",
    "payroll/compensation",
    "payroll/settings",
    "documents",
    "documents/list",
    "reports",
]);

const LEAD_DETAIL = /^crm\/leads\/[A-Za-z0-9][A-Za-z0-9_-]*$/;

const ALLOWED = new Set<string>([
    ...BESPOKE_ROUTES,
    ...DEMO_AI_ROUTES,
    ...DEMO_MODULE_ROUTES,
]);

export function isDemoErpRoute(routePath: string): boolean {
    return ALLOWED.has(routePath) || LEAD_DETAIL.test(routePath);
}

export function isDemoAiRoute(routePath: string): boolean {
    return DEMO_AI_ROUTES.has(routePath);
}
