"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, PenLine, Receipt, Wallet } from "lucide-react";
import {
    Bar,
    BarChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
} from "recharts";

import {
    RecentActivityList,
    type ActivityItem,
} from "@/components/dashboard/shared/recent-activity-list";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import {
    StatusBreakdown,
    type BreakdownSegment,
} from "@/components/dashboard/shared/status-breakdown";
import { L3NarrativeCard } from "@/components/dashboard/erp/hr/l3-narrative-card";
import { Button } from "@/components/ui/button";
import { CardSkeleton, StatCardSkeleton } from "@/components/ui/page-skeletons";
import { ApiError } from "@/lib/api/http";
import {
    getPayrollSettings,
    listPayrollRuns,
    type PayrollRunStatus,
} from "@/lib/api/payroll-api";
import {
    formatDate,
    formatDateTime,
    formatListCount,
    formatMoney,
} from "@/lib/format";

type PageStatus =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; data: OverviewData };

interface OverviewData {
    runs: string;
    draft: string;
    paid: string;
    latestRun: string;
    latestHint: string;
    latestHref?: string;
    breakdown: BreakdownSegment[];
    breakdownTotal: number;
    recentRuns: ActivityItem[];
    currency: string;
    costTrend: { key: string; label: string; amount: number }[];
}

/** Bar/dot colors for the runs-by-status summary, matching StatusBadge hues. */
const STATUS_BAR: Record<PayrollRunStatus, string> = {
    draft: "bg-slate-400",
    computed: "bg-sky-500",
    approved: "bg-amber-500",
    paid: "bg-emerald-500",
    void: "bg-red-500",
};

const STATUS_ORDER: PayrollRunStatus[] = [
    "draft",
    "computed",
    "approved",
    "paid",
    "void",
];

function capitalize(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1);
}

/** Bucket paid runs into a month-over-month net cost series (newest first in). */
function buildCostTrend(
    runs: { periodStart: string; totalNet: { amount: string } | null }[],
): { key: string; label: string; amount: number }[] {
    const byMonth = new Map<string, number>();
    for (const run of runs) {
        const amount = Number(run.totalNet?.amount ?? 0);
        if (!Number.isFinite(amount) || amount === 0) continue;
        const key = run.periodStart.slice(0, 7);
        byMonth.set(key, (byMonth.get(key) ?? 0) + amount);
    }
    return [...byMonth.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .slice(-12)
        .map(([key, amount]) => ({
            key,
            label: formatDate(`${key}-01`),
            amount: Math.round(amount * 100) / 100,
        }));
}

export function PayrollOverview() {
    const [status, setStatus] = useState<PageStatus>({ state: "loading" });

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const [
                runsResult,
                settings,
                draftResult,
                computedResult,
                approvedResult,
                paidResult,
                voidResult,
                trendResult,
            ] = await Promise.all([
                listPayrollRuns({ pageSize: 20 }),
                getPayrollSettings(),
                listPayrollRuns({ pageSize: 20, status: "draft" }),
                listPayrollRuns({ pageSize: 20, status: "computed" }),
                listPayrollRuns({ pageSize: 20, status: "approved" }),
                listPayrollRuns({ pageSize: 20, status: "paid" }),
                listPayrollRuns({ pageSize: 20, status: "void" }),
                listPayrollRuns({ pageSize: 100, status: "paid" }),
            ]);

            const runsByStatus: Record<PayrollRunStatus, number> = {
                draft: draftResult.meta.total,
                computed: computedResult.meta.total,
                approved: approvedResult.meta.total,
                paid: paidResult.meta.total,
                void: voidResult.meta.total,
            };

            const latestRun = runsResult.items[0] ?? null;
            const currency =
                latestRun?.totalNet?.currency ||
                settings?.defaultCurrency ||
                "USD";

            const breakdown: BreakdownSegment[] = STATUS_ORDER.map(
                (runStatus) => ({
                    label: capitalize(runStatus),
                    value: runsByStatus[runStatus],
                    colorClass: STATUS_BAR[runStatus],
                    href: `/dashboard/erp/payroll/runs?status=${runStatus}`,
                }),
            );

            const recentRuns: ActivityItem[] = runsResult.items
                .slice(0, 6)
                .map((run) => ({
                    key: run.id,
                    icon: <Receipt aria-hidden="true" className="size-4" />,
                    title: run.runCode,
                    meta: `${formatDate(run.periodStart)} – ${formatDate(run.periodEnd)}`,
                    status: run.status,
                    time: formatDateTime(run.createdAt),
                    href: `/dashboard/erp/payroll/runs/${run.id}`,
                }));

            setStatus({
                state: "ready",
                data: {
                    runs: formatListCount(runsResult.meta),
                    draft: formatListCount(draftResult.meta),
                    paid: formatListCount(paidResult.meta),
                    latestRun: latestRun
                        ? formatMoney(latestRun.totalNet?.amount, currency)
                        : "-",
                    latestHint: latestRun
                        ? `${latestRun.runCode} · ${formatDate(latestRun.periodStart)} – ${formatDate(latestRun.periodEnd)}`
                        : "No runs yet",
                    latestHref: latestRun
                        ? `/dashboard/erp/payroll/runs/${latestRun.id}`
                        : undefined,
                    breakdown,
                    breakdownTotal: STATUS_ORDER.reduce(
                        (sum, runStatus) => sum + runsByStatus[runStatus],
                        0,
                    ),
                    recentRuns,
                    currency,
                    costTrend: buildCostTrend(trendResult.items),
                },
            });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not load payroll overview.",
            });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    if (status.state === "loading") {
        return (
            <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                    <CardSkeleton className="h-64" />
                    <CardSkeleton className="h-64" />
                </div>
                <CardSkeleton className="h-80" />
            </div>
        );
    }

    if (status.state === "error") {
        return (
            <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
                <p className="text-sm font-medium text-destructive">
                    {status.message}
                </p>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => void load()}
                >
                    Try again
                </Button>
            </div>
        );
    }

    const { data } = status;

    return (
        <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                    icon={Receipt}
                    label="Payroll runs"
                    value={data.runs}
                    hint="Created in total"
                    href="/dashboard/erp/payroll/runs"
                />
                <StatCard
                    icon={PenLine}
                    label="Draft runs"
                    value={data.draft}
                    hint="Awaiting computation"
                    href="/dashboard/erp/payroll/runs?status=draft"
                />
                <StatCard
                    icon={BadgeCheck}
                    label="Paid runs"
                    value={data.paid}
                    hint="Completed"
                    href="/dashboard/erp/payroll/runs?status=paid"
                />
                <StatCard
                    icon={Wallet}
                    label="Latest run"
                    value={data.latestRun}
                    hint={data.latestHint}
                    href={data.latestHref}
                />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
                <StatusBreakdown
                    title="Runs by status"
                    segments={data.breakdown}
                    total={data.breakdownTotal}
                />
                <RecentActivityList
                    title="Recent runs"
                    items={data.recentRuns}
                    emptyMessage="No payroll runs yet start your first run."
                />
            </div>

            <section aria-label="Payroll cost trend" className="space-y-4">
                <div className="rounded-xl border border-border bg-card p-5">
                    <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                        Payroll cost trend
                    </h2>
                    <p className="text-xs text-muted-foreground">
                        Monthly total net across paid runs
                    </p>
                    {data.costTrend.length > 0 ? (
                        <div className="mt-4 h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={data.costTrend}
                                    margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                                >
                                    <XAxis
                                        dataKey="label"
                                        tick={{ fontSize: 12 }}
                                        stroke="var(--muted-foreground)"
                                        interval="preserveStartEnd"
                                    />
                                    <Tooltip
                                        cursor={{ fill: "var(--muted)" }}
                                        formatter={(value) =>
                                            formatMoney(Number(value), data.currency)
                                        }
                                    />
                                    <Bar
                                        dataKey="amount"
                                        fill="var(--primary)"
                                        radius={[4, 4, 0, 0]}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <p className="mt-3 text-sm text-muted-foreground">
                            No paid runs yet — the cost trend appears once a run is paid.
                        </p>
                    )}
                </div>

                <L3NarrativeCard
                    kind="payroll_cost"
                    accessibilityLabel="Payroll cost narrative"
                />
            </section>
        </div>
    );
}
