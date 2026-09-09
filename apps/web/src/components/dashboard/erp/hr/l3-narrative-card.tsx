"use client";

import { useCallback, useEffect, useState } from "react";
import { Info, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    getL3Narrative,
    refreshL3Narrative,
    type L3Narrative,
    type L3NarrativeKind,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type CardStatus =
    | { state: "loading" }
    | { state: "blocked"; message: string }
    | { state: "error"; message: string }
    | { state: "ready"; narrative: L3Narrative };

const KIND_LABEL: Record<L3NarrativeKind, string> = {
    payroll_cost: "Payroll cost narrative",
    leave_pay_correlation: "Leave · pay correlation",
    compliance_digest: "Weekly compliance digest",
};

export function L3NarrativeCard({
    kind,
    className,
    label,
    accessibilityLabel,
}: {
    kind: L3NarrativeKind;
    className?: string;
    /** Defaults to a kind-specific label; override for a distinct editorial voice. */
    label?: string;
    accessibilityLabel?: string;
}) {
    const [status, setStatus] = useState<CardStatus>({ state: "loading" });
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const narrative = await getL3Narrative(kind);
            setStatus({ state: "ready", narrative });
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setStatus({
                    state: "blocked",
                    message:
                        "L3 narratives need the erp.hr.ai.management permission — keep the page for the data you can see.",
                });
            } else {
                setStatus({
                    state: "error",
                    message:
                        error instanceof ApiError
                            ? error.message
                            : "L3 narrative could not be loaded.",
                });
            }
        }
    }, [kind]);

    const handleRefresh = useCallback(async () => {
        setBusy(true);
        try {
            const narrative = await refreshL3Narrative(kind);
            setStatus({ state: "ready", narrative });
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setStatus({
                    state: "blocked",
                    message:
                        "L3 narratives need the erp.hr.ai.management permission — keep the page for the data you can see.",
                });
            } else {
                setStatus({
                    state: "error",
                    message:
                        error instanceof ApiError
                            ? error.message
                            : "L3 narrative could not be refreshed.",
                });
            }
        } finally {
            setBusy(false);
        }
    }, [kind]);

    useEffect(() => {
        void load();
    }, [load]);

    const heading = label ?? KIND_LABEL[kind];

    if (status.state === "loading") {
        return (
            <section
                aria-label={accessibilityLabel ?? heading}
                className={cn(
                    "rounded-xl border border-border bg-card p-5",
                    className,
                )}
            >
                <div className="space-y-3">
                    <div className="h-4 w-56 animate-pulse rounded bg-muted" />
                    <div className="h-10 w-full animate-pulse rounded bg-muted" />
                    <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
                </div>
            </section>
        );
    }

    if (status.state === "blocked" || status.state === "error") {
        return (
            <section
                aria-label={accessibilityLabel ?? heading}
                className={cn(
                    "flex items-start justify-between gap-4 rounded-xl border border-destructive/20 bg-destructive/5 p-4",
                    className,
                )}
            >
                <div className="flex min-w-0 items-start gap-2">
                    <TriangleAlert
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-destructive"
                    />
                    <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{heading}</p>
                        <p className="text-xs text-muted-foreground">{status.message}</p>
                    </div>
                </div>
                {status.state === "error" ? (
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void load()}
                    >
                        Retry
                    </Button>
                ) : null}
            </section>
        );
    }

    const { narrative } = status;
    const figures = Object.entries(narrative.figures);
    const abstained = narrative.status === "abstained";

    return (
        <section
            aria-label={accessibilityLabel ?? heading}
            className={cn(
                "rounded-xl border border-indigo-500/20 bg-card p-5",
                className,
            )}
        >
            <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                    {heading}
                </h2>
                <Badge
                    variant="outline"
                    className="border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-400"
                >
                    <Sparkles aria-hidden="true" className="size-3" />
                    L3 AI
                </Badge>
                {narrative.source ? (
                    <Badge variant="secondary" className="capitalize">
                        {narrative.source}
                    </Badge>
                ) : null}
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-7 gap-1.5 px-2 text-xs"
                    disabled={busy}
                    onClick={() => void handleRefresh()}
                >
                    <RefreshCw
                        aria-hidden="true"
                        className={cn("size-3.5", busy && "animate-spin")}
                    />
                    {busy ? "Recomputed" : "Refresh"}
                </Button>
            </div>

            {narrative.title && !abstained ? (
                <p className="mt-3 text-base font-medium text-foreground">
                    {narrative.title}
                </p>
            ) : (
                <p className="mt-3 text-sm text-muted-foreground">
                    {abstained
                        ? "No narrative this period — the underlying data was too thin or out of date."
                        : "No narrative yet for this period."}
                </p>
            )}

            {narrative.summary ? (
                <p className="mt-1 text-sm text-muted-foreground">
                    {narrative.summary}
                </p>
            ) : null}

            {narrative.points.length > 0 ? (
                <ul className="mt-3 space-y-1.5">
                    {narrative.points.map((point, index) => (
                        <li
                            key={index}
                            className="flex items-start gap-2 text-sm text-foreground"
                        >
                            <span
                                aria-hidden="true"
                                className="mt-1.5 size-1.5 shrink-0 rounded-full bg-indigo-500"
                            />
                            {point}
                        </li>
                    ))}
                </ul>
            ) : null}

            {figures.length > 0 ? (
                <dl className="mt-4 flex flex-wrap gap-2">
                    {figures.map(([key, value]) => (
                        <div
                            key={key}
                            className="rounded-full border border-border bg-muted/50 px-3 py-1 text-xs"
                        >
                            <dt className="inline text-muted-foreground">{key}: </dt>
                            <dd className="inline font-medium tabular-nums text-foreground">
                                {value}
                            </dd>
                        </div>
                    ))}
                </dl>
            ) : null}

            {narrative.caveat ? (
                <p className="mt-4 flex items-start gap-1.5 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                    {narrative.caveat}
                </p>
            ) : null}

            {narrative.generatedAt || narrative.asOf ? (
                <p className="mt-3 text-xs text-muted-foreground">
                    As of {formatDateTime(narrative.asOf)}
                    {narrative.generatedAt
                        ? ` · rendered ${formatDateTime(narrative.generatedAt)}`
                        : ""}
                    {narrative.modelUsed ? ` · ${narrative.modelUsed}` : ""}
                </p>
            ) : null}
        </section>
    );
}