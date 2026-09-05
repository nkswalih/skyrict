"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Activity,
    AlertTriangle,
    ArrowLeftRight,
    BellRing,
    BarChart3,
    Calendar,
    LayoutDashboard,
    Layers,
    Package,
    ShoppingCart,
    Warehouse,
    type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const INVENTORY_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
    {
        href: "/dashboard/erp/inventory",
        label: "Overview",
        icon: LayoutDashboard,
    },
    {
        href: "/dashboard/erp/inventory/products",
        label: "Products",
        icon: Package,
    },
    {
        href: "/dashboard/erp/inventory/warehouses",
        label: "Warehouses",
        icon: Warehouse,
    },
    { href: "/dashboard/erp/inventory/stock", label: "Stock", icon: Layers },
    {
        href: "/dashboard/erp/inventory/movements",
        label: "Movements",
        icon: ArrowLeftRight,
    },
    {
        href: "/dashboard/erp/inventory/alerts",
        label: "Alerts",
        icon: BellRing,
    },
    {
        href: "/dashboard/erp/inventory/suggestions",
        label: "AI Suggestions",
        icon: ShoppingCart,
    },
    {
        href: "/dashboard/erp/inventory/anomalies",
        label: "Anomalies",
        icon: AlertTriangle,
    },
    {
        href: "/dashboard/erp/inventory/forecast",
        label: "Forecast",
        icon: Calendar,
    },
    {
        href: "/dashboard/erp/inventory/abc",
        label: "ABC",
        icon: BarChart3,
    },
    {
        href: "/dashboard/erp/inventory/health",
        label: "Health",
        icon: Activity,
    },
];

export function InventoryNav() {
    const pathname = usePathname();

    return (
        <nav
            aria-label="Inventory sections"
            className="flex flex-wrap items-center gap-1.5"
        >
            {INVENTORY_ITEMS.map((item) => {
                const Icon = item.icon;
                const active =
                    item.href === "/dashboard/erp/inventory"
                        ? pathname === item.href
                        : pathname === item.href ||
                          pathname.startsWith(`${item.href}/`);
                return (
                    <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                            "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                            active
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        )}
                    >
                        <Icon aria-hidden="true" className="size-4" />
                        {item.label}
                    </Link>
                );
            })}
        </nav>
    );
}
