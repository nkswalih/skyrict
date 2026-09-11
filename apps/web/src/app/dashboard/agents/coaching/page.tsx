"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Inbox, Loader2, RefreshCw, X } from "lucide-react";

import { AgentsHeader } from "@/components/dashboard/agents/agents-header";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { hasPermission, useModuleAccess } from "@/lib/access/modules";
import {
    listCoachingSuggestions,
    reviewCoachingSuggestion,
    type CoachingSuggestionItem,
    type CoachingReviewDecision,
} from "@/lib/api/coaching-api";

const STATUS_LABELS: Record<CoachingSuggestionItem["status"], string> = {
    pending: "Pending",
    viewed: "Viewed",
    accepted: "Accepted",
    dismissed: "Dismissed",
};

function isActionable(status: CoachingSuggestionItem["status"]): boolean {
    return status === "pending" || status === "viewed";
}

function shortId(id: string | null): string | null {
    return id ? id.slice(0, 8) : null;
}

function CoachingSuggestionCard({
    suggestion,
    canReview,
    busy,
    reviewError,
    onReview,
}: {
    suggestion: CoachingSuggestionItem;
    canReview: boolean;
    busy: boolean;
    reviewError: string | null;
    onReview: (
        suggestion: CoachingSuggestionItem,
        decision: CoachingReviewDecision,
    ) => void;
}) {
    const actionable = isActionable(suggestion.status);
    const repId = shortId(suggestion.rep_user_id);
    const opportunityId = shortId(suggestion.opportunity_id);
    const leadId = shortId(suggestion.lead_id);

    return (
        <article className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-medium text-foreground">
                            {suggestion.title}
                        </h3>
                        <Badge variant="secondary">
                            {suggestion.suggestion_type}
                        </Badge>
                        <Badge
                            variant={actionable ? "default" : "outline"}
                        >
                            {STATUS_LABELS[suggestion.status]}
                        </Badge>
                    </div>
                    <p className="mt-1.5 text-sm text-muted-foreground">
                        {suggestion.body}
                    </p>
                    <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
                        {repId ? (
                            <div>
                                Rep{" "}
                                <span className="font-mono">{repId}</span>
                            </div>
                        ) : null}
                        {opportunityId ? (
                            <div>
                                Opportunity{" "}
                                <span className="font-mono">
                                    {opportunityId}
                                </span>
                            </div>
                        ) : null}
                        {leadId ? (
                            <div>
                                Lead{" "}
                                <span className="font-mono">{leadId}</span>
                            </div>
                        ) : null}
                        <div>
                            Created{" "}
                            <time dateTime={suggestion.created_at}>
                                {new Date(
                                    suggestion.created_at,
                                ).toLocaleDateString()}
                            </time>
                        </div>
                    </dl>
                </div>
                {suggestion.reviewed_at ? (
                    <p className="shrink-0 text-xs text-muted-foreground">
                        Reviewed{" "}
                        <time dateTime={suggestion.reviewed_at}>
                            {new Date(
                                suggestion.reviewed_at,
                            ).toLocaleDateString()}
                        </time>
                    </p>
                ) : null}
            </div>

            {reviewError ? (
                <p className="mt-3 text-xs text-destructive">
                    {reviewError}
                </p>
            ) : null}

            {actionable ? (
                <div className="mt-3 flex items-center gap-2">
                    <Button
                        size="sm"
                        disabled={busy || !canReview}
                        onClick={() =>
                            onReview(suggestion, "accepted")
                        }
                    >
                        {busy ? (
                            <Loader2
                                aria-hidden="true"
                                className="size-3.5 animate-spin"
                            />
                        ) : (
                            <Check aria-hidden="true" className="size-3.5" />
                        )}
                        Accept
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        disabled={busy || !canReview}
                        onClick={() =>
                            onReview(suggestion, "dismissed")
                        }
                    >
                        <X aria-hidden="true" className="size-3.5" />
                        Dismiss
                    </Button>
                    {!canReview ? (
                        <p className="text-xs text-muted-foreground">
                            Review permission required to act on suggestions.
                        </p>
                    ) : null}
                </div>
            ) : null}
        </article>
    );
}

/** Manager queue: pending coaching suggestions with accept/dismiss actions. */
function CoachingQueuePanel() {
    const { permissions } = useModuleAccess();
    const [suggestions, setSuggestions] = useState<
        CoachingSuggestionItem[] | null
    >(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [busyId, setBusyId] = useState<string | null>(null);
    const [reviewError, setReviewError] = useState<string | null>(null);

    const canReview = hasPermission(permissions, "erp.ai.coaching.review");

    const load = useCallback(() => {
        setLoadError(null);
        setSuggestions(null);
        listCoachingSuggestions()
            .then((response) => setSuggestions(response.data))
            .catch((error: unknown) => {
                setSuggestions([]);
                setLoadError(
                    error instanceof Error
                        ? error.message
                        : "Could not load the coaching queue.",
                );
            });
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const handleReview = useCallback(
        (
            suggestion: CoachingSuggestionItem,
            decision: CoachingReviewDecision,
        ) => {
            setBusyId(suggestion.id);
            setReviewError(null);
            reviewCoachingSuggestion(suggestion.id, decision)
                .then((updated) => {
                    setSuggestions((previous) =>
                        (previous ?? []).map((item) =>
                            item.id === updated.id ? updated : item,
                        ),
                    );
                })
                .catch((error: unknown) => {
                    setReviewError(
                        error instanceof Error
                            ? error.message
                            : "Could not save the review.",
                    );
                })
                .finally(() => setBusyId(null));
        },
        [],
    );

    return (
        <div className="mx-auto max-w-3xl space-y-4">
            <div className="flex items-center justify-between gap-4">
                <div>
                    <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                        Manager queue
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Accept or dismiss AI coaching suggestions raised for
                        your sales reps.
                    </p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={load}
                    disabled={suggestions === null}
                >
                    <RefreshCw
                        aria-hidden="true"
                        className="size-3.5"
                    />
                    Refresh
                </Button>
            </div>

            {suggestions === null ? (
                /* Loading state - the queue shape is stable enough to skeleton. */
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
            ) : suggestions.length === 0 ? (
                <div className="rounded-xl border border-border bg-card p-10 text-center">
                    <Inbox
                        aria-hidden="true"
                        className="mx-auto size-8 text-muted-foreground/60"
                    />
                    <p className="mt-3 text-sm font-medium text-foreground">
                        Nothing in the queue
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                        New coaching suggestions will appear here once the
                        Sales Coach flags them.
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {suggestions.map((suggestion) => (
                        <CoachingSuggestionCard
                            key={suggestion.id}
                            suggestion={suggestion}
                            canReview={canReview}
                            busy={busyId === suggestion.id}
                            reviewError={reviewError}
                            onReview={handleReview}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

export default function CoachingPage() {
    return (
        <RequirePermission permission="erp.ai.coaching.read">
            <div className="flex h-full flex-col overflow-hidden">
                <AgentsHeader title="Sales Coach" />
                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
                    <CoachingQueuePanel />
                </div>
            </div>
        </RequirePermission>
    );
}