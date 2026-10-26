export const knownTitles: Record<string, string> = {
    "/dashboard": "Overview",
    "/dashboard/members": "Members",
    "/dashboard/invite": "Invite member",
    "/dashboard/agents": "AI Agents",
    "/dashboard/erp": "Business Operations",
    "/dashboard/intelligence": "Market Intelligence",
    "/dashboard/settings": "Settings",
    "/dashboard/settings/notifications": "Notification preferences",
    "/dashboard/settings/billing": "Plans & billing",
    "/dashboard/integrations": "Integrations",
};

const idPattern =
    /^(?:\d+|[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}|[\da-f]{8,})$/i;

/**
 * Short, page-level titles for the public demo. The demo reuses the ERP nav and
 * screens, but it is not a workspace route: without this map the generic
 * resolver treats `/demo/erp/...` as `/dashboard/demo/...` and renders
 * "Overview · Demo · Erp · CRM · Leads" in the top bar.
 */
const DEMO_TITLES: Record<string, string> = {
    "/demo": "Interactive Demo",
    "/demo/erp": "Business Operations",
    "/demo/erp/crm/overview": "CRM Overview",
    "/demo/erp/inventory": "Inventory Overview",
    "/demo/erp/inventory/overview": "Inventory Overview",
    "/demo/erp/hr": "People & Employees",
    "/demo/erp/hr/overview": "People & Employees",
    "/demo/erp/hr/employees": "People & Employees",
    "/demo/erp/finance": "Finance Overview",
    "/demo/erp/finance/overview": "Finance Overview",
    "/demo/erp/payroll": "Payroll Runs",
    "/demo/erp/payroll/runs": "Payroll Runs",
    "/demo/erp/orders": "Sales Orders",
    "/demo/erp/sales": "Sales Orders",
    "/demo/erp/documents": "Documents",
    "/demo/erp/documents/list": "All Documents",
    "/demo/erp/reports": "Reports",
    "/demo/erp/profile": "Profile",
    "/demo/erp/settings": "Profile & settings",
    "/demo/erp/settings/appearance": "Appearance",
    "/demo/erp/settings/workspace": "Workspace preferences",
    "/demo/erp/settings/notifications": "Notification preferences",
    "/demo/erp/settings/billing": "Plans & billing",
    "/demo/erp/settings/security": "Security & access",
    "/demo/erp/settings/integrations": "Integrations",
};

const DEMO_ACRONYMS = new Set(["ai", "abc", "crm", "erp", "hr", "sku"]);

function demoHumanize(segment: string): string {
    return segment
        .split("-")
        .filter(Boolean)
        .map((part) =>
            DEMO_ACRONYMS.has(part.toLowerCase())
                ? part.toUpperCase()
                : `${part.charAt(0).toUpperCase()}${part.slice(1)}`,
        )
        .join(" ");
}

function resolveDemoTitle(pathname: string): string {
    const clean = pathname.replace(/\/+$/, "") || "/demo";
    if (DEMO_TITLES[clean]) return DEMO_TITLES[clean];

    const segments = clean.split("/").filter(Boolean).slice(2);
    const last = segments[segments.length - 1];
    if (!last) return "Business Operations";

    if (
        segments[0] === "crm" &&
        segments[1] === "leads" &&
        segments.length > 2
    ) {
        return "Lead Detail";
    }
    if (last === "overview" && segments.length > 1) {
        return `${demoHumanize(segments[segments.length - 2])} Overview`;
    }
    return demoHumanize(last);
}

function humanize(segment: string): string {
    return segment
        .replace(/[-_]+/g, " ")
        .replace(/([a-z\d])([A-Z])/g, "$1 $2")
        .replace(/\b\w/g, (char) => char.toUpperCase())
        .trim();
}

/** Resolve a page title from any workspace route, known or not. */
export function resolvePageTitle(pathname: string): string {
    if (pathname === "/demo" || pathname.startsWith("/demo/")) {
        return resolveDemoTitle(pathname);
    }

    const normalized =
        pathname === "/"
            ? "/dashboard"
            : pathname.startsWith("/dashboard")
              ? pathname
              : `/dashboard${pathname}`;
    if (knownTitles[normalized]) return knownTitles[normalized];

    const segments = normalized.split("/").filter(Boolean);
    const parent = Object.keys(knownTitles)
        .filter((key) => normalized.startsWith(`${key}/`))
        .sort((a, b) => b.length - a.length)[0];

    const rest = parent
        ? segments
              .slice(parent.split("/").filter(Boolean).length)
              .filter((segment) => !idPattern.test(segment))
              .map(humanize)
        : [];

    if (parent && rest.length > 0)
        return `${knownTitles[parent]} · ${rest.join(" · ")}`;

    const last = [...segments]
        .reverse()
        .find((segment) => !idPattern.test(segment));
    return last ? humanize(last) : "Dashboard";
}
