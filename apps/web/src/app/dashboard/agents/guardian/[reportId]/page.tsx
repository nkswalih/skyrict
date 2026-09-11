"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
    ArrowLeft,
    CheckCircle2,
    Loader2,
    ShieldAlert,
} from "lucide-react";

import { AgentsHeader } from "@/components/dashboard/agents/agents-header";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { hasPermission, useModuleAccess } from "@/lib/access/modules";
import {
    getGuardianReport,
    reviewGuardianReport,
    type GuardianEventItem,
    type GuardianEventSeverity,
    type GuardianReportDetailResponse,
} from "@/lib/api/guardian-api";

const STATUS_LABELS: Record<GuardianReportDetailResponse["status"], string> =
    {
        generated: "Generated",
        reviewed: "Reviewed",
        archived: "Archived",
    };

function severityVariant(
    severity: GuardianEventSeverity,
): "destructive" | "secondary" | "outline" {
    if (severity === "high" || severity === "critical") return "destructive";
    if (severity === "medium") return "secondary";
    return "outline";
}

function formatWeekRange(start: string, end: string): string {
    return `${new Date(start).toLocaleDateString()} - ${new Date(
        end,
    ).toLocaleDateString()}`;
}

/**
 * Render one evidence payload as a definition list. Only http(s) strings
 * become links - everything else renders as inline text so an unexpected
 * value can never become a navigable (and potentially unsafe) href.
 */
function EvidenceList({
    evidence,
}: {
    evidence: Record<string, unknown>;
}) {
    const entries = Object.entries(evidence);
    if (entries.length === 0) {
        return (
            <p className="text-xs text-muted-foreground">
                No additional evidence.
            </p>
        );
    }
    return (
        <dl className="grid gap-x-6 gap-y-1 text-xs">
            {entries.map(([key, value]) => {
                const isUrl =
                    typeof value === "string" &&
                    /^https?:\/\//.test(value);
                const display =
                    typeof value === "string"
                        ? value
                        : JSON.stringify(value);
                return (
                    <div key={key} className="flex gap-2">
                        <dt className="shrink-0 font-medium text-muted-foreground">
                            {key}
                        </dt>
                        <dd className="min-w-0 truncate text-foreground">
                            {isUrl ? (
                                <a
                                    href={value as string}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-primary underline-offset-4 hover:underline"
                                >
                                    {display}
                                </a>
                            ) : (
                                display
                            )}
                        </dd>
                    </div>
                );
            })}
        </dl>
    );
}

function FlaggedEventCard({
    event,
}: {
    event: GuardianEventItem;
}) {
    return (
        <article className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={severityVariant(event.severity)}>
                            {event.severity}
                        </Badge>
                        <span className="text-sm font-medium text-foreground">
                            {event.event_action}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground/80">
                            {event.source_table}
                        </span>
                    </div>
                    <p className="mt-1.5 text-sm text-foreground">
                        {event.reason}
                    </p>
                    <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
                        <div>
                            Source{" "}
                            <span className="font-mono">
                                {event.source_id.slice(0, 8)}
                            </span>
                        </div>
                        <div>
                            Flagged{" "}
                            <time dateTime={event.flagged_at}>
                                {new Date(
                                    event.flagged_at,
                                ).toLocaleString()}
                            </time>
                        </div>
                    </dl>
                </div>
            </div>
            <div className="mt-3 border-t border-border pt-3">
                <p className="mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
                    Evidence
                </p>
                <EvidenceList evidence={event.evidence} />
            </div>
        </article>
    );
}

/** One weekly report: flagged events, evidence links, and mark-as-reviewed. */
function GuardianReportDetail({
    reportId,
}: {
    reportId: string;
}) {
    const { permissions } = useModuleAccess();
    const [report, setReport] = useState<GuardianReportDetailResponse | null>(
        null,
    );
    const [loading, setLoading] = useState(true);
    const [missing, setMissing] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [reviewing, setReviewing] = useState(false);
    const [reviewError, setReviewError] = useState<string | null>(null);

    const canReview = hasPermission(permissions, "erp.ai.guardian.review");

    const load = useCallback(() => {
        setLoading(true);
        setLoadError(null);
        getGuardianReport(reportId)
            .then((data) => setReport(data))
            .catch((error: unknown) => {
                if (error instanceof Error && error.message === "Report not found") {
                    setMissing(true);
                } else {
                    setLoadError(
                        error instanceof Error
                            ? error.message
                            : "Could not load this report.",
                    );
                }
            })
            .finally(() => setLoading(false));
    }, [reportId]);

    useEffect(() => {
        load();
    }, [load]);

    const handleReview = useCallback(() => {
        if (!report) return;
        setReviewing(true);
        setReviewError(null);
        reviewGuardianReport(report.id)
            .then((updated) => {
                setReport((previous) =>
                    previous ? { ...previous, status: updated.status } : previous,
                );
            })
            .catch((error: unknown) => {
                setReviewError(
                    error instanceof Error
                        ? error.message
                        : "Could not mark the report as reviewed.",
                );
            })
            .finally(() => setReviewing(false));
    }, [report]);

    if (missing) {
        return (
            <GuardianHeader>
                <div className="rounded-xl border border-border bg-card p-10 text-center">
                    <ShieldAlert
                        aria-hidden="true"
                        className="mx-auto size-8 text-muted-foreground/60"
                    />
                    <p className="mt-3 text-sm font-medium text-foreground">
                        Report not found
                    </p>
                    <Button className="mt-4" size="sm" asChild>
                        <Link href="/dashboard/agents/guardian">
                            <ArrowLeft aria-hidden="true" className="size-3.5" />
                            Back to reports
                        </Link>
                    </Button>
                </div>
            </GuardianHeader>
        );
    }

    return (
        <GuardianHeader>
            {loading ? (
                <div className="flex items-center justify-center py-24">
                    <Loader2
                        aria-hidden="true"
                        className="size-6 animate-spin text-muted-foreground"
                    />
                </div>
            ) : loadError ? (
                <div className="rounded-xl border border-border bg-card p-6 text-center">
                    <p className="text-sm text-destructive">{loadError}</p>
                    <Button className="mt-4" size="sm" onClick={load}>
                        Retry
                    </Button>
                </div>
            ) : report ? (
                <div className="mx-auto max-w-3xl space-y-4">
                    <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-card p-4">
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                                    Weekly integrity report
                                </h2>
                                <Badge
                                    variant={
                                        report.status === "generated"
                                            ? "default"
                                            : "outline"
                                    }
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
                            <p className="mt-2 text-sm text-foreground">
                                {report.summary}
                            </p>
                            <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
                                <div>
                                    {report.total_events_scanned} events
                                    scanned
                                </div>
                                <div className="font-medium text-destructive">
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
                        {report.status === "generated" ? (
                            <div className="shrink-0">
                                <Button
                                    size="sm"
                                    onClick={handleReview}
                                    disabled={reviewing || !canReview}
                                >
                                    {reviewing ? (
                                        <Loader2
                                            aria-hidden="true"
                                            className="size-3.5 animate-spin"
                                        />
                                    ) : (
                                        <CheckCircle2
                                            aria-hidden="true"
                                            className="size-3.5"
                                        />
                                    )}
                                    Mark as reviewed
                                </Button>
                                {!canReview ? (
                                    <p className="mt-1.5 text-right text-xs text-muted-foreground">
                                        Review permission required.
                                    </p>
                                ) : null}
                            </div>
                        ) : null}
                        {reviewError ? (
                            <p className="text-xs text-destructive">
                                {reviewError}
                            </p>
                        ) : null}
                    </div>

                    <div className="space-y-3">
                        {report.events.length === 0 ? (
                            <div className="rounded-xl border border-border bg-card p-8 text-center">
                                <p className="text-sm font-medium text-foreground">
                                    No flagged events
                                </p>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    Every scanned action fell within expected
                                    patterns this week.
                                </p>
                            </div>
                        ) : (
                            report.events.map((event) => (
                                <FlaggedEventCard
                                    key={event.id}
                                    event={event}
                                />
                            ))
                        )}
                    </div>
                </div>
            ) : null}
        </GuardianHeader>
    );
}

/** Shared chrome: agents header + a back link to the report list. */
function GuardianHeader({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="flex h-full flex-col overflow-hidden">
            <AgentsHeader title="Audit Guardian" />
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
                <Link
                    href="/dashboard/agents/guardian"
                    className="mb-4 flex w-fit items-center gap-2 rounded-lg text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                    <ArrowLeft aria-hidden="true" className="size-4" />
                    All reports
                </Link>
                {children}
            </div>
        </div>
    );
}

export default function GuardianReportPage({
    params,
}: {
    params: Promise<{ reportId: string }>;
}) {
    const [reportId, setReportId] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        void params.then(({ reportId: id }) => {
            if (!cancelled) setReportId(id);
        });
        return () => {
            cancelled = true;
        };
    }, [params]);

    if (!reportId) {
        return (
            <RequirePermission permission="erp.ai.guardian.read">
                <GuardianHeader>
                    <div className="flex items-center justify-center py-24">
                        <Loader2
                            aria-hidden="true"
                            className="size-6 animate-spin text-muted-foreground"
                        />
                    </div>
                </GuardianHeader>
            </RequirePermission>
        );
    }

    return (
        <RequirePermission permission="erp.ai.guardian.read">
            <GuardianReportDetail reportId={reportId} />
        </RequirePermission>
    );
}