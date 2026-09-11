"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
    ArrowRight,
    FileWarning,
    RefreshCw,
} from "lucide-react";

import { AgentsHeader } from "@/components/dashboard/agents/agents-header";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
    listGuardianReports,
    type GuardianReportItem,
} from "@/lib/api/guardian-api";

const STATUS_LABELS: Record<GuardianReportItem["status"], string> = {
    generated: "Generated",
    reviewed: "Reviewed",
    archived: "Archived",
};

function formatWeekRange(
    start: string,
    end: string,
): string {
    const startDate = new Date(start);
    const endDate = new Date(end);
    return `${startDate.toLocaleDateString()} - ${endDate.toLocaleDateString()}`;
}

function ReportCard({ report }: { report: GuardianReportItem }) {
    const isGenerated = report.status === "generated";

    return (
        <Link
            href={`/dashboard/agents/guardian/${report.id}`}
            className="block rounded-xl border border-border bg-card transition-colors hover:border-primary/50 hover:bg-card/70"
        >
            <div className="flex items-start justify-between gap-4 p-4">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-medium text-foreground">
                            Weekly integrity report
                        </h3>
                        <Badge
                            variant={isGenerated ? "default" : "outline"}
                        >
                            {STATUS_LABELS[report.status]}
                        </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                        {formatWeekRange(
                            report.report_week_start,
                            report.report_week_end,
                        )}
                    </p>
                    <p className="mt-2 line-clamp-2 text-sm text-foreground">
                        {report.summary}
                    </p>
                    <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
                        <div>
                            {report.total_events_scanned} events scanned
                        </div>
                        <div
                            className={cn(
                                report.flagged_count > 0 &&
                                    "font-medium text-destructive",
                            )}
                        >
                            {report.flagged_count} flagged
                        </div>
                        <div>
                            Generated{" "}
                            <time dateTime={report.generated_at}>
                                {new Date(
                                    report.generated_at,
                                ).toLocaleDateString()}
                            </time>
                        </div>
                    </dl>
                </div>
                <ArrowRight
                    aria-hidden="true"
                    className="mt-1 size-4 shrink-0 text-muted-foreground"
                />
            </div>
        </Link>
    );
}

/** Weekly Audit Guardian report list; each report links to its detail view. */
function GuardianReportsPanel() {
    const [reports, setReports] = useState<GuardianReportItem[] | null>(
        null,
    );
    const [loadError, setLoadError] = useState<string | null>(null);

    const load = useCallback(() => {
        setLoadError(null);
        setReports(null);
        listGuardianReports()
            .then((response) => setReports(response.data))
            .catch((error: unknown) => {
                setReports([]);
                setLoadError(
                    error instanceof Error
                        ? error.message
                        : "Could not load the audit reports.",
                );
            });
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <div className="mx-auto max-w-3xl space-y-4">
            <div className="flex items-center justify-between gap-4">
                <div>
                    <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                        Weekly reports
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Audit Guardian flags unusual access and action patterns
                        in the weekly integrity sweep. Open a report to
                        investigate flagged events and their evidence links.
                    </p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={load}
                    disabled={reports === null}
                >
                    <RefreshCw
                        aria-hidden="true"
                        className="size-3.5"
                    />
                    Refresh
                </Button>
            </div>

            {reports === null ? (
                <div className="space-y-3" aria-hidden="true">
                    {[0, 1, 2].map((row) => (
                        <Skeleton
                            key={row}
                            className="h-32 w-full rounded-xl"
                        />
                    ))}
                </div>
            ) : loadError ? (
                <div className="rounded-xl border border-border bg-card p-6 text-center">
                    <p className="text-sm text-destructive">{loadError}</p>
                    <Button className="mt-4" size="sm" onClick={load}>
                        Retry
                    </Button>
                </div>
            ) : reports.length === 0 ? (
                <div className="rounded-xl border border-border bg-card p-10 text-center">
                    <FileWarning
                        aria-hidden="true"
                        className="mx-auto size-8 text-muted-foreground/60"
                    />
                    <p className="mt-3 text-sm font-medium text-foreground">
                        No reports yet
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                        The first weekly integrity report will appear after
                        the Audit Guardian sweep runs.
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {reports.map((report) => (
                        <ReportCard key={report.id} report={report} />
                    ))}
                </div>
            )}
        </div>
    );
}

export default function GuardianReportsPage() {
    return (
        <RequirePermission permission="erp.ai.guardian.read">
            <div className="flex h-full flex-col overflow-hidden">
                <AgentsHeader title="Audit Guardian" />
                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
                    <GuardianReportsPanel />
                </div>
            </div>
        </RequirePermission>
    );
}