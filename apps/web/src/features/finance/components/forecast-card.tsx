"use client";

import { useCallback, useEffect, useState } from "react";
import { Info, Loader2, RefreshCw, TrendingUp } from "lucide-react";
import {
    Area,
    Bar,
    BarChart,
    CartesianGrid,
    ComposedChart,
    Line,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/http";
import {
    getRevenueForecast,
    refreshRevenueForecast,
    type RevenueForecast,
} from "@/lib/api/finance-api";
import { sweepDealHealth } from "@/lib/api/crm-ai-api";
import { formatMoney } from "@/lib/finance/format";
import { WidgetCard } from "@/features/finance/components/automation-widgets";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; forecast: RevenueForecast };

const PREDICTED_COLOR = "#0ea5e9";
const BAND_COLOR = "#0ea5e9";
const BASELINE_COLOR = "#64748b";
const ACTUAL_COLOR = "#f59e0b";

const chartPanel = "rounded-xl border border-border/70 bg-muted/30 p-3 sm:p-4";

function monthLabel(value: string): string {
    const date = new Date(`${value}T00:00:00`);
    return date.toLocaleDateString(undefined, {
        month: "short",
        year: "2-digit",
    });
}

function dateLabel(value: string): string {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
    });
}

// Deal-health band styling, mirroring the ai-agent health engine's green /
// yellow / red output. Unassessed deals render in a neutral colour.
const HEALTH_DOT: Record<string, { className: string; label: string }> = {
    green: { className: "bg-emerald-500", label: "Healthy" },
    yellow: { className: "bg-yellow-500", label: "At risk" },
    red: { className: "bg-red-500", label: "Critical" },
};

const HEALTH_NEUTRAL = {
    className: "bg-muted-foreground/50",
    label: "Not assessed",
};

function healthOf(health: string | null): { className: string; label: string } {
    return health ? (HEALTH_DOT[health] ?? HEALTH_NEUTRAL) : HEALTH_NEUTRAL;
}

const axisTick = {
    fontSize: 11,
    fill: "var(--muted-foreground)",
    fontFamily: "var(--font-sans)",
};

const compactMoneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
});

function compactMoney(value: number): string {
    return compactMoneyFormatter.format(value);
}

function LegendChip({
    swatch,
    color,
    label,
}: {
    swatch: "dot" | "dash" | "band";
    color: string;
    label: string;
}) {
    return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {swatch === "dot" ? (
                <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: color }}
                />
            ) : swatch === "dash" ? (
                <span
                    aria-hidden="true"
                    className="h-0.5 w-3.5"
                    style={{
                        background: `repeating-linear-gradient(90deg, ${color} 0 3px, transparent 3px 5px)`,
                    }}
                />
            ) : (
                <span
                    aria-hidden="true"
                    className="h-2 w-3.5 rounded-[2px]"
                    style={{ background: color }}
                />
            )}
            {label}
        </span>
    );
}

function ChartTooltipContent({
    active,
    payload,
    label,
}: {
    active: boolean;
    payload?: ReadonlyArray<{
        name?: string;
        value?: number | [number, number];
        color?: string;
        payload?: { baseline?: number | null; pipeline?: number | null };
    }>;
    label?: string;
}) {
    if (!active || !payload || payload.length === 0) return null;
    const datum = payload[0]?.payload;
    const hasBreakdown = datum?.baseline != null && datum?.pipeline != null;
    const predictedEntry = payload.find((entry) => entry.name === "Forecast");
    return (
        <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
            {label ? (
                <p className="mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {label}
                </p>
            ) : null}
            <ul className="space-y-1">
                {payload.map((entry, index) => (
                    <li key={index} className="flex items-center gap-2 text-sm">
                        <span
                            aria-hidden="true"
                            className="size-2 shrink-0 rounded-full"
                            style={{
                                backgroundColor:
                                    entry.color ?? "var(--chart-1)",
                            }}
                        />
                        <span className="text-muted-foreground">
                            {entry.name}
                        </span>
                        <span className="ml-auto pl-3 font-semibold tabular-nums text-foreground">
                            {Array.isArray(entry.value)
                                ? `${formatMoney(entry.value[0])} – ${formatMoney(entry.value[1])}`
                                : formatMoney(entry.value ?? 0)}
                        </span>
                    </li>
                ))}
            </ul>
            {hasBreakdown ? (
                <p className="mt-2 border-t border-border/60 pt-1.5 text-xs tabular-nums text-muted-foreground">
                    {formatMoney(datum!.baseline!)} usual revenue
                    {datum!.pipeline! > 0 ? (
                        <> + {formatMoney(datum!.pipeline!)} deals closing</>
                    ) : null}{" "}
                    = {formatMoney((predictedEntry?.value as number) ?? 0)}
                </p>
            ) : null}
        </div>
    );
}

type BreakdownPoint = NonNullable<RevenueForecast["points"]>[number] & {
    baseline: number;
    pipeline: number;
};

function breakdownPoints(forecast: RevenueForecast | null): BreakdownPoint[] {
    return (forecast?.points ?? []).filter(
        (point): point is BreakdownPoint =>
            point.baseline != null && point.pipeline != null,
    );
}

function biggestMonth(forecast: RevenueForecast | null): BreakdownPoint | null {
    const points = breakdownPoints(forecast);
    if (points.length === 0) return null;
    return points.reduce((best, point) =>
        point.predicted > best.predicted ? point : best,
    );
}

function biggestMonthCallout(forecast: RevenueForecast | null): string | null {
    const biggest = biggestMonth(forecast);
    if (!biggest || biggest.pipeline === 0) return null;
    return `${monthLabel(biggest.month)} is your biggest month: we expect ${formatMoney(biggest.predicted)}, and ${formatMoney(biggest.pipeline)} of that comes from deals expected to close that month.`;
}

function IngredientCard({
    swatchClass,
    title,
    children,
}: {
    swatchClass: string;
    title: string;
    children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-border/70 bg-muted/30 p-4">
            <div className="mb-1.5 flex items-center gap-2">
                <span aria-hidden="true" className={swatchClass} />
                <h4 className="font-display text-sm font-semibold text-foreground">
                    {title}
                </h4>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
                {children}
            </p>
        </div>
    );
}

function ForecastExplainerDialog({
    forecast,
}: {
    forecast: RevenueForecast | null;
}) {
    const points = breakdownPoints(forecast);
    const biggest = points.reduce<BreakdownPoint | null>(
        (best, point) =>
            !best || point.pipeline > best.pipeline ? point : best,
        null,
    );
    const [selectedMonth, setSelectedMonth] = useState<string | null>(null);

    const active =
        points.find((point) => point.month === selectedMonth) ??
        biggest ??
        points[0] ??
        null;
    const activeDeals = active?.deals ?? [];
    const dealsTotal = activeDeals.reduce(
        (sum, deal) => sum + (deal.adjusted ?? 0),
        0,
    );

    const mape =
        forecast?.backtest_mape != null ? Number(forecast.backtest_mape) : null;
    const sigma = forecast?.sigma != null ? Number(forecast.sigma) : null;

    return (
        <Dialog>
            <DialogTrigger asChild>
                <Button
                    variant="outline"
                    size="sm"
                    aria-label="How is this forecast made"
                >
                    <Info aria-hidden="true" className="mr-1.5 size-3.5" />
                    How is this forecast made?
                </Button>
            </DialogTrigger>
            <DialogContent className="flex max-h-[85dvh] overflow-hidden flex-col sm:max-w-xl">
                <DialogHeader>
                    <DialogTitle>How this forecast works</DialogTitle>
                    <DialogDescription>
                        What the number means and how it was calculated — in
                        plain language.
                    </DialogDescription>
                </DialogHeader>

                <div className="min-h-0 space-y-4 overflow-y-auto p-1 pr-3 pt-1">
                    <div className="grid gap-3 sm:grid-cols-2">
                        <IngredientCard
                            swatchClass="h-0.5 w-6 rounded-full bg-slate-500"
                            title="Your usual revenue"
                        >
                            What you typically earn in a month, worked out from
                            your last 24 months of approved invoices. Big months
                            and slow months from past years are carried forward.
                            This is the grey dashed line.
                        </IngredientCard>
                        <IngredientCard
                            swatchClass="size-2 rounded-full bg-sky-500"
                            title="Deals expected to close (the “pipeline”)"
                        >
                            Deals your team is still working on — before they’ve
                            been won or lost. Each deal counts at its chance of
                            closing: a $100,000 deal with a 60% chance adds
                            $60,000. An AI health check watches each deal — a
                            green deal counts in full, while a yellow or red
                            deal is counted at a reduced value. Deals without an
                            amount or a closing date are left out.
                        </IngredientCard>
                    </div>

                    {active ? (
                        <div className="rounded-xl border border-border/70 p-4">
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                                <h4 className="font-display text-sm font-semibold text-foreground">
                                    So the {monthLabel(active.month)} forecast
                                    is
                                </h4>
                                <select
                                    value={active.month}
                                    onChange={(event) =>
                                        setSelectedMonth(event.target.value)
                                    }
                                    aria-label="Choose a month"
                                    className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground"
                                >
                                    {points.map((point) => (
                                        <option
                                            key={point.month}
                                            value={point.month}
                                        >
                                            {monthLabel(point.month)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="space-y-1.5 text-sm tabular-nums">
                                <div className="flex items-center justify-between gap-3">
                                    <span className="text-muted-foreground">
                                        Your usual revenue
                                    </span>
                                    <span className="font-semibold text-foreground">
                                        {formatMoney(active.baseline)}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between gap-3">
                                    <span className="text-muted-foreground">
                                        + Deals expected to close
                                    </span>
                                    <span className="font-semibold text-foreground">
                                        {active.pipeline > 0
                                            ? `+ ${formatMoney(active.pipeline)}`
                                            : "None expected"}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between gap-3 border-t border-border/70 pt-1.5">
                                    <span className="font-medium text-foreground">
                                        = Forecast
                                    </span>
                                    <span className="font-semibold text-sky-600 dark:text-sky-400">
                                        {formatMoney(active.predicted)}
                                    </span>
                                </div>
                            </div>
                            {activeDeals.length > 0 ? (
                                <div className="mt-3 border-t border-border/70 pt-3">
                                    <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                                        <h5 className="text-xs font-semibold text-foreground uppercase">
                                            Which deals, and when
                                        </h5>
                                        <span className="text-[11px] text-muted-foreground">
                                            Yellow/red deals count at a reduced
                                            value
                                        </span>
                                    </div>
                                    <ul className="space-y-2">
                                        {activeDeals.map((deal) => {
                                            const health = healthOf(
                                                deal.health,
                                            );
                                            const scored = deal.factor !== 1;
                                            return (
                                                <li
                                                    key={deal.id}
                                                    className="flex items-baseline gap-3 text-sm"
                                                >
                                                    <span
                                                        aria-hidden="true"
                                                        title={health.label}
                                                        className={`mt-1.5 size-2 shrink-0 rounded-full ${health.className}`}
                                                    />
                                                    <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                                                        <span className="min-w-0">
                                                            <span className="block truncate font-medium text-foreground">
                                                                {deal.name}
                                                            </span>
                                                            <span className="block text-xs text-muted-foreground">
                                                                Expected{" "}
                                                                {dateLabel(
                                                                    deal.expected_close_date,
                                                                )}{" "}
                                                                ·{" "}
                                                                {deal.amount !=
                                                                null
                                                                    ? formatMoney(
                                                                          deal.amount,
                                                                      )
                                                                    : "—"}{" "}
                                                                ×{" "}
                                                                {
                                                                    deal.probability
                                                                }
                                                                %
                                                                {scored
                                                                    ? ` · counted at ${(
                                                                          deal.factor *
                                                                          100
                                                                      ).toFixed(
                                                                          0,
                                                                      )}%`
                                                                    : ""}
                                                            </span>
                                                        </span>
                                                        <span className="shrink-0 font-semibold text-foreground tabular-nums">
                                                            +
                                                            {formatMoney(
                                                                deal.adjusted,
                                                            )}
                                                        </span>
                                                    </span>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                    <p className="mt-2 text-xs text-muted-foreground">
                                        These {activeDeals.length} deals add up
                                        to +{formatMoney(dealsTotal)}.
                                    </p>
                                </div>
                            ) : null}
                        </div>
                    ) : null}

                    {sigma != null ? (
                        <div className="rounded-xl border border-border/70 p-4">
                            <h4 className="mb-1.5 font-display text-sm font-semibold text-foreground">
                                How much can you trust it?
                            </h4>
                            <p className="text-sm leading-relaxed text-muted-foreground">
                                We checked the model against your past months.
                                It was usually within ±
                                {formatMoney(Math.abs(sigma))} of the real
                                number — that’s the grey band around the line.
                                The average miss was about{" "}
                                {mape != null ? mape.toFixed(0) : "—"}%. That’s
                                normal for revenue forecasts.
                            </p>
                        </div>
                    ) : null}

                    <div>
                        <h4 className="mb-2 font-display text-sm font-semibold text-foreground">
                            Month by month
                        </h4>
                        <div className="overflow-hidden rounded-lg border border-border/70">
                            <table className="w-full text-right text-sm tabular-nums">
                                <thead className="sticky top-0 bg-muted text-xs text-muted-foreground uppercase">
                                    <tr>
                                        <th className="px-3 py-2 text-left font-medium">
                                            Month
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Usual revenue
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Deals closing
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Forecast
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {points.map((point) => (
                                        <tr
                                            key={point.month}
                                            className="border-t border-border/50"
                                        >
                                            <td className="px-3 py-1.5 text-left font-medium text-foreground">
                                                {monthLabel(point.month)}
                                                {point.pipeline > 0 ? (
                                                    <span className="ml-2 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600 uppercase dark:text-sky-400">
                                                        deals
                                                    </span>
                                                ) : null}
                                            </td>
                                            <td className="px-3 py-1.5 text-muted-foreground">
                                                {formatMoney(point.baseline)}
                                            </td>
                                            <td
                                                className={
                                                    point.pipeline > 0
                                                        ? "px-3 py-1.5 font-semibold text-foreground"
                                                        : "px-3 py-1.5 text-muted-foreground"
                                                }
                                            >
                                                {point.pipeline > 0
                                                    ? `+ ${formatMoney(point.pipeline)}`
                                                    : "—"}
                                            </td>
                                            <td className="px-3 py-1.5 font-semibold text-foreground">
                                                {formatMoney(point.predicted)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

// Deal-health markers on the card itself, aggregated across the horizon. The
// counts come from the per-deal health ratings the backend attaches to each
// forecast month; without them (old backend payload) the strip stays hidden.
const HEALTH_BAND_COLOR: Record<string, string> = {
    green: "#22c55e",
    yellow: "#eab308",
    red: "#ef4444",
};

function dealHealthSummary(forecast: RevenueForecast | null): {
    total: number;
    healthy: number;
    atRisk: number;
    critical: number;
    unassessed: number;
} {
    const summary = {
        total: 0,
        healthy: 0,
        atRisk: 0,
        critical: 0,
        unassessed: 0,
    };
    for (const point of forecast?.points ?? []) {
        for (const deal of point.deals ?? []) {
            summary.total += 1;
            if (deal.health === "green") summary.healthy += 1;
            else if (deal.health === "yellow") summary.atRisk += 1;
            else if (deal.health === "red") summary.critical += 1;
            else summary.unassessed += 1;
        }
    }
    return summary;
}

function DealHealthStrip({
    forecast,
    checker,
}: {
    forecast: RevenueForecast | null;
    checker?: () => Promise<void>;
}) {
    const health = dealHealthSummary(forecast);
    const [checking, setChecking] = useState(false);
    const [checkError, setCheckError] = useState<string | null>(null);
    if (health.total === 0) return null;

    const runCheck = async () => {
        setChecking(true);
        setCheckError(null);
        try {
            await checker?.();
        } catch (error) {
            setCheckError(
                error instanceof ApiError
                    ? error.message
                    : "Could not check deals.",
            );
        } finally {
            setChecking(false);
        }
    };

    return (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Deal health</span>
            <LegendChip
                swatch="dot"
                color={HEALTH_BAND_COLOR.green}
                label={`${health.healthy} healthy`}
            />
            {health.atRisk > 0 ? (
                <LegendChip
                    swatch="dot"
                    color={HEALTH_BAND_COLOR.yellow}
                    label={`${health.atRisk} at risk`}
                />
            ) : null}
            {health.critical > 0 ? (
                <LegendChip
                    swatch="dot"
                    color={HEALTH_BAND_COLOR.red}
                    label={`${health.critical} critical`}
                />
            ) : null}
            {health.unassessed > 0 ? (
                <LegendChip
                    swatch="dot"
                    color="var(--muted-foreground)"
                    label={`${health.unassessed} not checked`}
                />
            ) : null}
            <span>Flagged deals count at a reduced value</span>
            {checker ? (
                <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto h-6 px-2 text-xs"
                    onClick={() => void runCheck()}
                    disabled={checking}
                    aria-label="Check deal health now"
                >
                    {checking ? (
                        <Loader2
                            aria-hidden="true"
                            className="mr-1 size-3 animate-spin"
                        />
                    ) : (
                        <RefreshCw aria-hidden="true" className="mr-1 size-3" />
                    )}
                    Check deals
                </Button>
            ) : null}
            {checkError ? (
                <span className="basis-full text-destructive">
                    {checkError}
                </span>
            ) : null}
        </div>
    );
}

function AccuracySummary({ forecast }: { forecast: RevenueForecast | null }) {
    const mape =
        forecast?.backtest_mape != null ? Number(forecast.backtest_mape) : null;
    const sigma = forecast?.sigma != null ? Number(forecast.sigma) : null;
    if (mape === null || sigma === null) {
        return (
            <p className="text-xs text-muted-foreground">
                Accuracy not yet known — the forecast needs at least 4 months of
                history before we can score it.
            </p>
        );
    }
    return (
        <div className="mb-4 flex flex-wrap items-center gap-x-8 gap-y-1 border-y border-border/60 py-2">
            <div>
                <div className="text-xs text-muted-foreground">
                    Forecast accuracy
                </div>
                <div className="text-sm font-semibold text-foreground">
                    {mape.toFixed(1)}%
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                        average miss vs history
                    </span>
                </div>
            </div>
            <div>
                <div className="text-xs text-muted-foreground">
                    Typical error
                </div>
                <div className="text-sm font-semibold text-foreground">
                    ±{formatMoney(sigma)}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                        how far off past forecasts were
                    </span>
                </div>
            </div>
            {forecast?.pipeline_value != null ? (
                <div>
                    <div className="text-xs text-muted-foreground">
                        Deals expected to close
                    </div>
                    <div className="text-sm font-semibold text-foreground">
                        +{formatMoney(forecast.pipeline_value)}
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                            across the next 12 months
                        </span>
                    </div>
                </div>
            ) : null}
        </div>
    );
}

export function RevenueForecastCard({ canRefresh }: { canRefresh: boolean }) {
    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const forecast = await getRevenueForecast();
            setStatus({ state: "ready", forecast });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not load the revenue forecast.",
            });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const refresh = useCallback(async () => {
        if (refreshing) return;
        setRefreshing(true);
        try {
            const forecast = await refreshRevenueForecast();
            setStatus({ state: "ready", forecast });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not refresh the forecast.",
            });
        } finally {
            setRefreshing(false);
        }
    }, [refreshing]);

    const forecast = status.state === "ready" ? status.forecast : null;
    const data = (forecast?.points ?? []).map((point) => ({
        label: monthLabel(point.month),
        predicted: point.predicted,
        baseline: point.baseline,
        pipeline: point.pipeline,
        band:
            point.lower_bound !== null && point.upper_bound !== null
                ? ([point.lower_bound, point.upper_bound] as [number, number])
                : null,
    }));
    const hasDecomposition = data.some((point) => point.baseline != null);
    const historyData = (forecast?.history ?? []).map((point) => ({
        label: monthLabel(point.month),
        actual: point.actual,
    }));

    return (
        <WidgetCard
            title="Revenue forecast"
            icon={<TrendingUp aria-hidden="true" className="size-4" />}
            hint={
                forecast
                    ? `${forecast.model_version} · next ${forecast.points.length} month${forecast.points.length === 1 ? "" : "s"}`
                    : "Forecast from approved invoice history"
            }
            action={
                <div className="flex items-center gap-1">
                    <ForecastExplainerDialog forecast={forecast} />
                    {canRefresh ? (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void refresh()}
                            disabled={refreshing}
                            aria-label="Refresh revenue forecast"
                        >
                            {refreshing ? (
                                <Loader2
                                    aria-hidden="true"
                                    className="mr-1.5 size-3.5 animate-spin"
                                />
                            ) : (
                                <RefreshCw
                                    aria-hidden="true"
                                    className="mr-1.5 size-3.5"
                                />
                            )}
                            Refresh
                        </Button>
                    ) : null}
                </div>
            }
        >
            {status.state === "error" ? (
                <p className="text-sm text-destructive">{status.message}</p>
            ) : status.state === "loading" ? (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                    Loading forecast…
                </div>
            ) : data.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    Not enough history to forecast yet — the model needs at
                    least 3 months of approved invoices. Record invoices, then
                    refresh to generate a forecast.
                </p>
            ) : (
                <>
                    <AccuracySummary forecast={forecast} />
                    <DealHealthStrip
                        forecast={forecast}
                        checker={async () => {
                            await sweepDealHealth();
                            await load();
                        }}
                    />
                    {biggestMonthCallout(forecast) ? (
                        <p className="mb-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm font-medium leading-relaxed text-foreground">
                            {biggestMonthCallout(forecast)}
                        </p>
                    ) : null}
                    <div className={chartPanel}>
                        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                            <LegendChip
                                swatch="dot"
                                color={PREDICTED_COLOR}
                                label="Forecast"
                            />
                            {hasDecomposition ? (
                                <LegendChip
                                    swatch="dash"
                                    color={BASELINE_COLOR}
                                    label="Usual revenue"
                                />
                            ) : null}
                            <LegendChip
                                swatch="band"
                                color="color-mix(in srgb, #0ea5e9 22%, transparent)"
                                label="Expected range"
                            />
                        </div>
                        <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart
                                    data={data}
                                    margin={{
                                        top: 4,
                                        right: 4,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <defs>
                                        <linearGradient
                                            id="forecastBand"
                                            x1="0"
                                            y1="0"
                                            x2="0"
                                            y2="1"
                                        >
                                            <stop
                                                offset="0%"
                                                stopColor={BAND_COLOR}
                                                stopOpacity={0.24}
                                            />
                                            <stop
                                                offset="100%"
                                                stopColor={BAND_COLOR}
                                                stopOpacity={0.04}
                                            />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid
                                        stroke="var(--border)"
                                        strokeOpacity={0.6}
                                        vertical={false}
                                    />
                                    <XAxis
                                        dataKey="label"
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickMargin={8}
                                        interval="preserveStartEnd"
                                    />
                                    <YAxis
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickFormatter={compactMoney}
                                        domain={[0, "auto"]}
                                        width={52}
                                    />
                                    <Tooltip
                                        cursor={{
                                            stroke: "var(--border)",
                                            strokeOpacity: 0.9,
                                        }}
                                        content={({
                                            active,
                                            payload,
                                            label,
                                        }) => (
                                            <ChartTooltipContent
                                                active={Boolean(active)}
                                                payload={
                                                    payload as ReadonlyArray<{
                                                        name?: string;
                                                        value?:
                                                            | number
                                                            | [number, number];
                                                        color?: string;
                                                    }>
                                                }
                                                label={
                                                    label as string | undefined
                                                }
                                            />
                                        )}
                                    />
                                    <Area
                                        dataKey="band"
                                        name="Expected range"
                                        stroke="none"
                                        fill="url(#forecastBand)"
                                        activeDot={false}
                                        legendType="none"
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="predicted"
                                        name="Forecast"
                                        stroke={PREDICTED_COLOR}
                                        strokeWidth={2.5}
                                        dot={false}
                                        activeDot={{
                                            r: 4,
                                            strokeWidth: 2,
                                            stroke: "var(--card)",
                                        }}
                                        legendType="none"
                                    />
                                    {hasDecomposition ? (
                                        <Line
                                            type="monotone"
                                            dataKey="baseline"
                                            name="Usual revenue"
                                            stroke={BASELINE_COLOR}
                                            strokeWidth={1.5}
                                            strokeDasharray="4 4"
                                            dot={false}
                                            activeDot={false}
                                            legendType="none"
                                        />
                                    ) : null}
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                        Forecast = usual revenue + deals expected to close · the
                        grey band is the expected range.
                    </p>
                </>
            )}
            {historyData.length > 0 ? (
                <div className="mt-6">
                    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                        <h4 className="font-display text-sm font-semibold text-foreground">
                            Revenue history
                        </h4>
                        <p className="text-xs text-muted-foreground">
                            Actual money earned by month (approved invoices) —
                            this is what the forecast above is based on
                        </p>
                    </div>
                    <div className={chartPanel}>
                        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                            <LegendChip
                                swatch="dot"
                                color={ACTUAL_COLOR}
                                label="Actual revenue"
                            />
                        </div>
                        <div className="h-48">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={historyData}
                                    margin={{
                                        top: 4,
                                        right: 4,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <CartesianGrid
                                        stroke="var(--border)"
                                        strokeOpacity={0.6}
                                        vertical={false}
                                    />
                                    <XAxis
                                        dataKey="label"
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickMargin={8}
                                        interval="preserveStartEnd"
                                    />
                                    <YAxis
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickFormatter={compactMoney}
                                        domain={[0, "auto"]}
                                        width={52}
                                    />
                                    <Tooltip
                                        cursor={{
                                            fill: "var(--card)",
                                            fillOpacity: 0.55,
                                        }}
                                        content={({
                                            active,
                                            payload,
                                            label,
                                        }) => (
                                            <ChartTooltipContent
                                                active={Boolean(active)}
                                                payload={
                                                    payload as ReadonlyArray<{
                                                        name?: string;
                                                        value?:
                                                            | number
                                                            | [number, number];
                                                        color?: string;
                                                    }>
                                                }
                                                label={
                                                    label as string | undefined
                                                }
                                            />
                                        )}
                                    />
                                    <Bar
                                        dataKey="actual"
                                        name="Actual"
                                        fill={ACTUAL_COLOR}
                                        fillOpacity={0.9}
                                        radius={[4, 4, 0, 0]}
                                        maxBarSize={36}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            ) : null}
        </WidgetCard>
    );
}
