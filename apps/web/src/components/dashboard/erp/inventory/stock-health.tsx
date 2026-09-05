"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { InventoryEmpty } from "@/components/dashboard/erp/inventory/inventory-empty";
import { hasPermission, useModuleAccess } from "@/lib/access/modules";
import { ApiError } from "@/lib/api/http";
import {
    formatDate,
    formatMoney,
    getStockHealthSummary,
    listDeadStock,
    listMovementTrends,
    listSlowMovers,
    type DeadStockItem,
    type MovementTrendPoint,
    type SlowMoverItem,
    type StockHealthSummary,
} from "@/lib/api/inventory-api";
import { Activity, PackageX, TrendingDown, TrendingUp } from "lucide-react";

import {
    Bar,
    BarChart,
    CartesianGrid,
    Legend,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready" };

interface HealthData {
    summary: StockHealthSummary;
    trends: MovementTrendPoint[];
    deadStock: DeadStockItem[];
    slowMovers: SlowMoverItem[];
}

const COST_PERMISSION = "erp.inventory.cost";

function trendLabel(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "—";
    return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function StockHealthOverview() {
    const { status: accessStatus, permissions } = useModuleAccess();
    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [data, setData] = useState<HealthData | null>(null);
    const [tab, setTab] = useState<"dead" | "slow">("dead");

    const showCost = hasPermission(permissions, COST_PERMISSION);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const [summary, trends, deadRes, slowRes] = await Promise.all([
                getStockHealthSummary(),
                listMovementTrends({ weeks: 13 }),
                listDeadStock({ days: 90 }),
                listSlowMovers({ windowDays: 180 }),
            ]);
            setData({
                summary,
                trends: trends.data,
                deadStock: deadRes.data,
                slowMovers: slowRes.data,
            });
            setStatus({ state: "ready" });
        } catch (err) {
            const msg = err instanceof ApiError ? err.message : "Could not load stock health.";
            setStatus({ state: "error", message: msg });
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    if (status.state === "loading") {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (status.state === "error") {
        return <p className="text-sm text-destructive py-8 text-center">{status.message}</p>;
    }

    const { summary, trends, deadStock, slowMovers } = data as HealthData;
    const chartData = trends.map((point) => ({
        week: trendLabel(point.periodStart),
        Receipts: parseFloat(point.receipts),
        Issues: parseFloat(point.issues),
        Adjustments: parseFloat(point.adjustments),
    }));

    const statCards = [
        {
            label: "Total SKUs",
            value: summary.totalSkuCount.toLocaleString(),
            icon: Activity,
        },
        {
            label: "Low stock",
            value: summary.lowStockCount.toLocaleString(),
            icon: TrendingDown,
        },
        {
            label: "Dead stock",
            value: summary.deadStockCount.toLocaleString(),
            icon: PackageX,
        },
        {
            label: "Slow movers",
            value: summary.slowMoverCount.toLocaleString(),
            icon: TrendingUp,
        },
    ];

    return (
        <div className="space-y-8">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {statCards.map((card) => {
                    const Icon = card.icon;
                    return (
                        <div
                            key={card.label}
                            className="rounded-xl border border-border bg-card p-5 space-y-2"
                        >
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Icon aria-hidden="true" className="size-4" />
                                {card.label}
                            </div>
                            <p className="text-2xl font-semibold tabular-nums text-foreground">
                                {card.value}
                            </p>
                        </div>
                    );
                })}
            </div>

            {showCost && summary.tiedUpCapital != null && (
                <div className="rounded-xl border border-border bg-card p-5 flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                        Capital tied up in dead stock
                    </p>
                    <p className="text-lg font-semibold tabular-nums text-foreground">
                        {formatMoney(summary.tiedUpCapital)}
                    </p>
                </div>
            )}

            <section className="space-y-3">
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    Movement Trends
                </h2>
                {chartData.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                        No movement data available yet.
                    </p>
                ) : (
                    <div className="rounded-xl border border-border bg-card p-4 h-72">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData}>
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    stroke="var(--border)"
                                />
                                <XAxis
                                    dataKey="week"
                                    tick={{ fontSize: 12 }}
                                    stroke="var(--muted-foreground)"
                                />
                                <YAxis
                                    tick={{ fontSize: 12 }}
                                    stroke="var(--muted-foreground)"
                                    allowDecimals={false}
                                />
                                <Tooltip />
                                <Legend />
                                <Bar
                                    dataKey="Receipts"
                                    stackId="movement"
                                    fill="var(--primary)"
                                />
                                <Bar
                                    dataKey="Issues"
                                    stackId="movement"
                                    fill="#f59e0b"
                                />
                                <Bar
                                    dataKey="Adjustments"
                                    stackId="movement"
                                    fill="#8b5cf6"
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                )}
            </section>

            <section className="space-y-3">
                <div className="flex items-center justify-between flex-wrap gap-3">
                    <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                        At-Risk Items
                    </h2>
                    <div className="flex gap-1.5">
                        {(
                            [
                                ["dead", "Dead stock"],
                                ["slow", "Slow movers"],
                            ] as const
                        ).map(([key, label]) => (
                            <button
                                key={key}
                                onClick={() => setTab(key)}
                                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                                    tab === key
                                        ? "bg-primary text-primary-foreground"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                {tab === "dead" &&
                    (deadStock.length === 0 ? (
                        <InventoryEmpty
                            title="No dead stock"
                            description="No products with on-hand stock but no outbound movement in the trailing window."
                            icon={PackageX}
                        />
                    ) : (
                        <StockTable
                            showCost={showCost && accessStatus === "ready"}
                            costEmpty={
                                accessStatus === "ready" && !showCost
                                    ? "Requires erp.inventory.cost"
                                    : "—"
                            }
                            rows={deadStock.map((item) => ({
                                key: item.productId,
                                name: item.name,
                                sku: item.sku,
                                qty: item.qtyOnHand,
                                last: item.lastOutboundAt,
                                cost: item.costPrice,
                                extra:
                                    item.tiedUpValue != null
                                        ? formatMoney(item.tiedUpValue)
                                        : "",
                                extraLabel: "Tied up",
                            }))}
                        />
                    ))}

                {tab === "slow" &&
                    (slowMovers.length === 0 ? (
                        <InventoryEmpty
                            title="No slow movers"
                            description="No bottom-quartile turnover items in the trailing window."
                            icon={TrendingUp}
                        />
                    ) : (
                        <StockTable
                            showCost={showCost && accessStatus === "ready"}
                            costEmpty={
                                accessStatus === "ready" && !showCost
                                    ? "Requires erp.inventory.cost"
                                    : "—"
                            }
                            rows={slowMovers.map((item) => ({
                                key: item.productId,
                                name: item.name,
                                sku: item.sku,
                                qty: item.qtyOnHand,
                                last: item.lastOutboundAt,
                                cost: item.carryingCost,
                                extra: item.turnoverRatio,
                                extraLabel: "Turnover",
                                badge: item.suggestMarkdown ? "Markdown" : null,
                            }))}
                        />
                    ))}
            </section>
        </div>
    );
}

interface StockRow {
    key: string;
    name: string;
    sku: string;
    qty: string;
    last: string | null;
    cost: [string, string] | null;
    extra: string;
    extraLabel: string;
    badge?: string | null;
}

function StockTable({
    rows,
    showCost,
    costEmpty,
}: {
    rows: StockRow[];
    showCost: boolean;
    costEmpty: string;
}) {
    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead>
                        <tr className="border-b border-border bg-muted/40">
                            <th
                                scope="col"
                                className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                Product
                            </th>
                            <th
                                scope="col"
                                className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                SKU
                            </th>
                            <th
                                scope="col"
                                className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                Qty on hand
                            </th>
                            <th
                                scope="col"
                                className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                {rows[0]?.extraLabel ?? "Value"}
                            </th>
                            {showCost && (
                                <th
                                    scope="col"
                                    className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                >
                                    Cost
                                </th>
                            )}
                            <th
                                scope="col"
                                className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                Last outbound
                            </th>
                            <th
                                scope="col"
                                className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                            >
                                Advice
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row) => (
                            <tr
                                key={row.key}
                                className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30"
                            >
                                <td className="px-4 py-3 font-medium text-foreground">
                                    {row.name}
                                </td>
                                <td className="px-4 py-3 text-muted-foreground">
                                    {row.sku}
                                </td>
                                <td className="px-4 py-3 text-right tabular-nums text-foreground">
                                    {row.qty}
                                </td>
                                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                                    {row.extra}
                                </td>
                                {showCost && (
                                    <td className="px-4 py-3 text-right tabular-nums text-foreground">
                                        {row.cost ? formatMoney(row.cost) : costEmpty}
                                    </td>
                                )}
                                <td className="px-4 py-3 text-muted-foreground">
                                    {formatDate(row.last)}
                                </td>
                                <td className="px-4 py-3">
                                    {row.badge ? (
                                        <Badge
                                            variant="outline"
                                            className="text-xs ring-1 bg-amber-500/10 text-amber-700 ring-amber-500/30"
                                        >
                                            {row.badge}
                                        </Badge>
                                    ) : (
                                        <span className="text-muted-foreground">—</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
