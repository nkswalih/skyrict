import {
    Activity,
    AlertTriangle,
    ArrowLeftRight,
    BadgeDollarSign,
    BarChart3,
    BellRing,
    Blocks,
    BookOpen,
    Building2,
    Calendar,
    CalendarClock,
    CalendarDays,
    ClipboardCheck,
    Coins,
    Contact,
    ContactRound,
    LayoutDashboard,
    Layers,
    NotebookPen,
    Package,
    Plug,
    Receipt,
    ReceiptText,
    Search,
    ScrollText,
    ShieldCheck,
    ShieldAlert,
    ShoppingCart,
    SlidersHorizontal,
    Sparkles,
    TrendingDown,
    TrendingUp,
    UserPlus,
    UserRound,
    Users,
    Wallet,
    Warehouse,
    type LucideIcon,
} from "lucide-react";

export interface NavItem {
    href: string;
    label: string;
    icon: LucideIcon;
    /** Permission key that gates this item (absent = always visible inside its world). */
    permission?: string;
    soon?: boolean;
    tour?: string;
    /** Match only the exact href, never child paths (e.g. module overviews). */
    exact?: boolean;
    /** Sub-navigation rendered as indented rows under a collapsible toggle row. */
    children?: NavItem[];
}

export interface NavGroup {
    label: string;
    items: NavItem[];
    /** Collapsible groups render their label as a toggle that opens the indented sub-items. */
    collapsible?: boolean;
}

/** Workspace sidebar (non-module pages). Modules are entered from the Overview launchpad. */
export const workspaceNavGroups: NavGroup[] = [
    {
        label: "Workspace",
        items: [
            {
                href: "/dashboard",
                label: "Overview",
                icon: LayoutDashboard,
                tour: "nav-overview",
            },
        ],
    },
    {
        label: "Manage",
        items: [
            {
                href: "/dashboard/roles",
                label: "Roles",
                icon: ShieldCheck,
                permission: "roles:read",
                tour: "nav-roles",
            },
            {
                href: "/dashboard/integrations",
                label: "Integrations",
                icon: Plug,
                soon: true,
                tour: "nav-integrations",
            },
        ],
    },
];

export const workspaceAccountItems: NavItem[] = [
    {
        href: "/dashboard/invite",
        label: "Invite team",
        icon: UserPlus,
        permission: "invitations:send",
        tour: "nav-invite",
    },
    {
        href: "/dashboard/members",
        label: "Members",
        icon: Users,
        permission: "users:read",
        tour: "nav-members",
    },
    {
        href: "/dashboard/settings",
        label: "Settings",
        icon: SlidersHorizontal,
        tour: "nav-settings",
    },
];

export const erpNavGroups: NavGroup[] = [
    {
        label: "Operations",
        items: [
            {
                href: "/dashboard/erp",
                label: "Dashboard",
                icon: LayoutDashboard,
                exact: true,
            },
            {
                href: "/dashboard/erp/crm",
                label: "CRM",
                icon: Contact,
                permission: "erp.crm.read",
                exact: true,
                children: [
                    {
                        href: "/dashboard/erp/crm/overview",
                        label: "Overview",
                        icon: LayoutDashboard,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/leads",
                        label: "Leads",
                        icon: Contact,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/opportunities",
                        label: "Opportunities",
                        icon: TrendingUp,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/customers",
                        label: "Customers",
                        icon: Users,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/contacts",
                        label: "Contacts",
                        icon: ContactRound,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/activities",
                        label: "Activities",
                        icon: CalendarClock,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/ai",
                        label: "AI Insights",
                        icon: Sparkles,
                        permission: "erp.crm.read",
                    },
                    {
                        href: "/dashboard/erp/crm/search",
                        label: "Search",
                        icon: Search,
                        permission: "erp.crm.read",
                    },
                ],
            },
            {
                href: "/dashboard/erp/orders",
                label: "Orders",
                icon: ShoppingCart,
                permission: "erp.sales.read",
            },
            {
                href: "/dashboard/erp/inventory",
                label: "Inventory",
                icon: Package,
                permission: "erp.inventory.read",
                exact: true,
                children: [
                    {
                        href: "/dashboard/erp/inventory/products",
                        label: "Products",
                        icon: Package,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/warehouses",
                        label: "Warehouses",
                        icon: Warehouse,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/stock",
                        label: "Stock",
                        icon: Layers,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/movements",
                        label: "Movements",
                        icon: ArrowLeftRight,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/alerts",
                        label: "Alerts",
                        icon: BellRing,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/suggestions",
                        label: "AI Suggestions",
                        icon: ShoppingCart,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/anomalies",
                        label: "Anomalies",
                        icon: AlertTriangle,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/forecast",
                        label: "Forecast",
                        icon: Calendar,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/abc",
                        label: "ABC Classification",
                        icon: BarChart3,
                        permission: "erp.inventory.read",
                    },
                    {
                        href: "/dashboard/erp/inventory/health",
                        label: "Stock Health",
                        icon: Activity,
                        permission: "erp.inventory.read",
                    },
                ],
            },
            {
                href: "/dashboard/erp/hr",
                label: "HR",
                icon: Blocks,
                permission: "erp.hr.read",
                exact: true,
                children: [
                    {
                        href: "/dashboard/erp/hr/employees",
                        label: "Employees",
                        icon: UserRound,
                        permission: "erp.hr.read",
                    },
                    {
                        href: "/dashboard/erp/hr/departments",
                        label: "Departments",
                        icon: Building2,
                        permission: "erp.hr.read",
                    },
                    {
                        href: "/dashboard/erp/hr/leave",
                        label: "Leave",
                        icon: CalendarDays,
                        permission: "erp.hr.read",
                    },
                    {
                        href: "/dashboard/erp/hr/attendance",
                        label: "Attendance",
                        icon: CalendarClock,
                        permission: "erp.hr.read",
                    },
                    {
                        href: "/dashboard/erp/hr/data-quality",
                        label: "Data quality",
                        icon: ClipboardCheck,
                        permission: "erp.hr.read",
                    },
                    {
                        href: "/dashboard/erp/hr/ai-alerts",
                        label: "AI alerts",
                        icon: ShieldAlert,
                        permission: "erp.hr.ai.read",
                    },
                    {
                        href: "/dashboard/erp/hr/attrition",
                        label: "Attrition",
                        icon: TrendingDown,
                        permission: "erp.hr.ai.read",
                    },
                    {
                        href: "/dashboard/erp/hr/compliance",
                        label: "Compliance",
                        icon: ShieldCheck,
                        permission: "erp.hr.ai.read",
                    },
                ],
            },
            {
                href: "/dashboard/erp/finance",
                label: "Finance",
                icon: Wallet,
                permission: "erp.finance.read",
                exact: true,
                children: [
                    {
                        href: "/dashboard/erp/finance/accounts",
                        label: "Accounts",
                        icon: BookOpen,
                        permission: "erp.finance.read",
                    },
                    {
                        href: "/dashboard/erp/finance/journal-entries",
                        label: "Journal Entries",
                        icon: NotebookPen,
                        permission: "erp.finance.read",
                    },
                    {
                        href: "/dashboard/erp/finance/fiscal-periods",
                        label: "Fiscal Periods",
                        icon: CalendarDays,
                        permission: "erp.finance.read",
                    },
                    {
                        href: "/dashboard/erp/finance/invoices",
                        label: "Invoices",
                        icon: ReceiptText,
                        permission: "erp.finance.read",
                    },
                    {
                        href: "/dashboard/erp/finance/statements",
                        label: "Statements",
                        icon: BarChart3,
                        permission: "erp.finance.read",
                    },
                    {
                        href: "/dashboard/erp/finance/audit-log",
                        label: "Audit Log",
                        icon: ScrollText,
                        permission: "erp.finance.read",
                    },
                ],
            },
            {
                href: "/dashboard/erp/payroll",
                label: "Payroll",
                icon: Receipt,
                permission: "erp.payroll.read",
                exact: true,
                children: [
                    {
                        href: "/dashboard/erp/payroll/runs",
                        label: "Runs",
                        icon: BadgeDollarSign,
                        permission: "erp.payroll.read",
                    },
                    {
                        href: "/dashboard/erp/payroll/reviews",
                        label: "Reviews",
                        icon: ClipboardCheck,
                        permission: "erp.payroll.approve",
                    },
                    {
                        href: "/dashboard/erp/payroll/compensation",
                        label: "Compensation",
                        icon: Coins,
                        permission: "erp.payroll.read",
                    },
                    {
                        href: "/dashboard/erp/payroll/settings",
                        label: "Settings",
                        icon: SlidersHorizontal,
                        permission: "erp.payroll.read",
                    },
                    {
                        href: "/dashboard/erp/payroll/automation",
                        label: "Automation",
                        icon: CalendarClock,
                        permission: "erp.payroll.ai.read",
                    },
                    {
                        href: "/dashboard/erp/payroll/anomalies",
                        label: "Payroll anomalies",
                        icon: AlertTriangle,
                        permission: "erp.payroll.ai.read",
                    },
                ],
            },
            {
                href: "/dashboard/erp/reports",
                label: "Reports",
                icon: BarChart3,
            },
        ],
    },
];

/** Keep only nav items whose permission the user holds (wildcard grants all). */
export function filterNavItemsByPermissions(
    items: NavItem[],
    permissions: string[],
): NavItem[] {
    const allowed = new Set(permissions);
    const result: NavItem[] = [];
    for (const item of items) {
        if (
            item.permission &&
            !allowed.has("*") &&
            !allowed.has(item.permission)
        ) {
            continue;
        }
        if (item.children) {
            const children = filterNavItemsByPermissions(
                item.children,
                permissions,
            );
            if (children.length === 0) continue;
            result.push({ ...item, children });
        } else {
            result.push(item);
        }
    }
    return result;
}

/** Filter nav groups, dropping groups that end up empty. */
export function filterNavGroupsByPermissions(
    groups: NavGroup[],
    permissions: string[],
): NavGroup[] {
    const result: NavGroup[] = [];
    for (const group of groups) {
        const items = filterNavItemsByPermissions(group.items, permissions);
        if (items.length > 0) result.push({ ...group, items });
    }
    return result;
}
