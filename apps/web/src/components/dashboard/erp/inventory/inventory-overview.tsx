"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    ArrowLeftRight,
    ArrowRight,
    BellRing,
    Layers,
    Package,
    Warehouse,
    type LucideIcon,
} from "lucide-react";

import { AiChatPanel } from "@/components/dashboard/erp/inventory/ai-chat-panel";
import { InventoryError } from "@/components/dashboard/erp/inventory/inventory-banners";
import { Badge } from "@/components/ui/badge";
import { StatCardSkeleton } from "@/components/ui/page-skeletons";
import { ApiError } from "@/lib/api/http";
import {
    listAlerts,
    listProducts,
    listWarehouses,
    type Alert,
} from "@/lib/api/inventory-api";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | {
          state: "ready";
          products: number;
          warehouses: number;
          alerts: number;
          recentAlerts: Alert[];
      };

const QUICK_LINKS: {
    href: string;
    title: string;
    description: string;
    icon: LucideIcon;
}[] = [
    {
        href: "/dashboard/erp/inventory/products",
        title: "Products",
        description: "Catalog of what you track stock for.",
        icon: Package,
    },
    {
        href: "/dashboard/erp/inventory/warehouses",
        title: "Warehouses",
        description: "Where stock lives.",
        icon: Warehouse,
    },
    {
        href: "/dashboard/erp/inventory/stock",
        title: "Stock levels",
        description: "Current on-hand and reserved counts.",
        icon: Layers,
    },
    {
        href: "/dashboard/erp/inventory/movements",
        title: "Movements",
        description: "The immutable stock ledger.",
        icon: ArrowLeftRight,
    },
    {
        href: "/dashboard/erp/inventory/alerts",
        title: "Reorder alerts",
        description: "Products at or below their reorder point.",
        icon: BellRing,
    },
];

function KpiCard({
    label,
    value,
    tone,
}: {
    label: string;
    value: string;
    tone?: "danger";
}) {
    return (
        <div className="rounded-xl border border-border bg-card p-5">
            <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                {label}
            </p>
            <p
                className={
                    tone === "danger"
                        ? "mt-2 font-display text-2xl font-semibold tracking-tight text-destructive"
                        : "mt-2 font-display text-2xl font-semibold tracking-tight text-foreground"
                }
            >
                {value}
            </p>
        </div>
    );
}

export function InventoryOverview() {
    const [status, setStatus] = useState<Status>({ state: "loading" });

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [products, warehouses, alerts] = await Promise.all([
                    listProducts({ page: 1, pageSize: 1 }),
                    listWarehouses({ page: 1, pageSize: 1 }),
                    listAlerts({ page: 1, pageSize: 4 }),
                ]);
                if (cancelled) return;
                setStatus({
                    state: "ready",
                    products: products.meta.total,
                    warehouses: warehouses.meta.total,
                    alerts: alerts.meta.total,
                    recentAlerts: alerts.data,
                });
            } catch (error) {
                if (cancelled) return;
                const message =
                    error instanceof ApiError
                        ? error.message
                        : "Could not load inventory.";
                setStatus({ state: "error", message });
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    if (status.state === "loading") {
        return (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
            </div>
        );
    }

    if (status.state === "error") {
        return <InventoryError message={status.message} />;
    }

    const { products, warehouses, alerts, recentAlerts } = status;

    return (
        <div className="space-y-8">
            <section className="space-y-4">
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    At a glance
                </h2>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <KpiCard label="Products" value={String(products)} />
                    <KpiCard label="Warehouses" value={String(warehouses)} />
                    <KpiCard
                        label="Low stock"
                        value={String(alerts)}
                        tone={alerts > 0 ? "danger" : undefined}
                    />
                </div>
            </section>

            <AiChatPanel />

            {recentAlerts.length > 0 ? (
                <section className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                            Needs attention
                        </h2>
                        <Link
                            href="/dashboard/erp/inventory/alerts"
                            className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                        >
                            View all
                            <ArrowRight aria-hidden="true" className="size-4" />
                        </Link>
                    </div>
                    <div className="overflow-hidden rounded-xl border border-border bg-card">
                        <ul className="divide-y divide-border/60">
                            {recentAlerts.map((alert) => (
                                <li
                                    key={`${alert.productId}-${alert.warehouseId}`}
                                    className="flex items-center justify-between gap-3 px-4 py-3"
                                >
                                    <div className="min-w-0">
                                        <p className="truncate text-sm font-medium text-foreground">
                                            {alert.name}
                                            <span className="ml-2 font-mono text-xs text-muted-foreground">
                                                {alert.sku}
                                            </span>
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            {alert.qtyOnHand} on hand · reorder
                                            at {alert.reorderPoint}
                                        </p>
                                    </div>
                                    <Badge
                                        variant="outline"
                                        className="shrink-0 bg-destructive/10 text-destructive ring-1 ring-destructive/30"
                                    >
                                        Below reorder
                                    </Badge>
                                </li>
                            ))}
                        </ul>
                    </div>
                </section>
            ) : null}

            <section className="space-y-4">
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    Sections
                </h2>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {QUICK_LINKS.map((link) => {
                        const Icon = link.icon;
                        return (
                            <Link
                                key={link.href}
                                href={link.href}
                                className="group relative flex flex-col rounded-xl border border-border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-muted/40 active:translate-y-0"
                            >
                                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
                                    <Icon
                                        aria-hidden="true"
                                        className="size-5"
                                    />
                                </div>
                                <h3 className="mt-4 font-display text-base font-semibold text-foreground">
                                    {link.title}
                                </h3>
                                <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">
                                    {link.description}
                                </p>
                                <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary">
                                    Open
                                    <ArrowRight
                                        aria-hidden="true"
                                        className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
                                    />
                                </span>
                            </Link>
                        );
                    })}
                </div>
            </section>
        </div>
    );
}
