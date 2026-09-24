"use client";
import { AiGlyph } from "@/components/brand/logo";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useState } from "react";
import {
    CheckCircle2,
    Clock,
    Inbox,
    RefreshCw,
    XCircle,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { TableSkeleton } from "@/components/ui/page-skeletons";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
    decideApproval,
    getApprovalInstance,
    listApprovalInbox,
    type ApprovalDecision,
    type ApprovalDecisionResult,
    type ApprovalInboxItem,
    type ApprovalInstance,
    type ApprovalSuggestion,
} from "@/lib/api/approval-api";
import { apiErrorMessage, onApiError } from "@/lib/api/error-toast";

type InboxState =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; items: ApprovalInboxItem[]; notice: string | null };

const whenFormat = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
});

function formatWhen(value: string | null): string {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "—" : whenFormat.format(parsed);
}

const STEP_STATUS_LABELS: Record<string, string> = {
    pending: "Pending",
    escalated: "Escalated",
    approved: "Approved",
    rejected: "Rejected",
};

function StepStatusBadge({ status }: { status: string }) {
    const label = STEP_STATUS_LABELS[status] ?? status;
    if (status === "approved") {
        return (
            <Badge variant="default">
                <CheckCircle2 aria-hidden="true" />
                {label}
            </Badge>
        );
    }
    if (status === "rejected") {
        return (
            <Badge variant="destructive">
                <XCircle aria-hidden="true" />
                {label}
            </Badge>
        );
    }
    if (status === "escalated") {
        return (
            <Badge variant="outline">
                <Clock aria-hidden="true" />
                {label}
            </Badge>
        );
    }
    return <Badge variant="secondary">{label}</Badge>;
}

function SuggestionChip({ suggestion }: { suggestion: ApprovalSuggestion }) {
    if (!suggestion.recommendation) return null;
    return (
        <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-xs font-medium text-primary">
            <AiGlyph aria-hidden="true" className="size-3 shrink-0" />
            <span className="truncate">{suggestion.recommendation}</span>
        </span>
    );
}

/* ---------------------------------------------------------------------------
 * Review dialog: full instance detail + decision controls
 * ------------------------------------------------------------------------- */

interface ReviewDialogProps {
    instanceId: string;
    onClose: () => void;
    onDecided: (result: ApprovalDecisionResult) => void;
}

type DetailState =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; instance: ApprovalInstance };

function ReviewDialog({ instanceId, onClose, onDecided }: ReviewDialogProps) {
    const [detail, setDetail] = useState<DetailState>({ state: "loading" });
    const [reason, setReason] = useState("");
    const [submitting, setSubmitting] = useState<ApprovalDecision | null>(null);
    const [submitError, setSubmitError] = useState<string | null>(null);

    const load = useCallback(() => {
        setDetail({ state: "loading" });
        getApprovalInstance(instanceId)
            .then((instance) => setDetail({ state: "ready", instance }))
            .catch((error: unknown) =>
                setDetail({ state: "error", message: apiErrorMessage(error) }),
            );
    }, [instanceId]);

    useEffect(load, [load]);

    async function handleDecide(decision: ApprovalDecision): Promise<void> {
        if (detail.state !== "ready" || submitting) return;
        setSubmitting(decision);
        setSubmitError(null);
        try {
            const trimmed = reason.trim();
            const result = await decideApproval(
                instanceId,
                decision,
                trimmed === "" ? undefined : trimmed,
            );
            onDecided(result);
        } catch (error: unknown) {
            setSubmitError(apiErrorMessage(error));
            onApiError(error);
        } finally {
            setSubmitting(null);
        }
    }

    const currentStep =
        detail.state === "ready"
            ? detail.instance.steps.find(
                  (step) =>
                      step.step_index === detail.instance.current_step_index,
              )
            : undefined;

    return (
        <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
                {detail.state === "loading" ? (
                    <div className="space-y-4 py-4">
                        <div className="h-4 w-1/3 animate-pulse rounded-full bg-muted" />
                        <div className="h-20 animate-pulse rounded-xl bg-muted/60" />
                        <div className="h-32 animate-pulse rounded-xl bg-muted/60" />
                    </div>
                ) : null}

                {detail.state === "error" ? (
                    <div className="py-6 text-center">
                        <p className="text-sm font-medium text-destructive">
                            {detail.message}
                        </p>
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            onClick={load}
                        >
                            <RefreshCw aria-hidden="true" />
                            Retry
                        </Button>
                    </div>
                ) : null}

                {detail.state === "ready" ? (
                    <>
                        <DialogHeader>
                            <DialogTitle>
                                {detail.instance.resource_label} review
                            </DialogTitle>
                            <DialogDescription>
                                {detail.instance.resource_type} · step{" "}
                                {currentStep?.step_key ?? "—"} · submitted{" "}
                                {formatWhen(detail.instance.submitted_at)}
                            </DialogDescription>
                        </DialogHeader>

                        {detail.instance.suggestion ? (
                            <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
                                <div className="flex items-center gap-1.5 text-sm font-medium text-primary">
                                    <AiGlyph
                                        aria-hidden="true"
                                        className="size-4"
                                    />
                                    AI routing suggestion
                                </div>
                                <p className="mt-1.5 text-sm text-foreground">
                                    {detail.instance.suggestion.recommendation ??
                                        "No recommendation"}
                                </p>
                                {detail.instance.suggestion.confidence ? (
                                    <p className="mt-0.5 text-xs text-muted-foreground">
                                        Confidence:{" "}
                                        {detail.instance.suggestion.confidence}
                                    </p>
                                ) : null}
                                {detail.instance.suggestion.reasoning ? (
                                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                                        {detail.instance.suggestion.reasoning}
                                    </p>
                                ) : null}
                                <p className="mt-2 text-xs text-muted-foreground">
                                    Advisory only — this never bypasses a manual
                                    review.
                                </p>
                            </div>
                        ) : null}

                        <div className="space-y-3">
                            <h3 className="font-display text-sm font-semibold text-foreground">
                                Steps
                            </h3>
                            {detail.instance.steps.map((step) => (
                                <div
                                    key={step.step_index}
                                    className={cn(
                                        "rounded-xl border border-border bg-card p-4",
                                        step.step_index ===
                                            detail.instance.current_step_index &&
                                            step.status === "pending" &&
                                            "border-primary/40",
                                    )}
                                >
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="flex items-center gap-2">
                                            <span className="flex size-6 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                                                {step.step_index + 1}
                                            </span>
                                            <span className="text-sm font-medium text-foreground">
                                                {step.step_key}
                                            </span>
                                        </div>
                                        <StepStatusBadge status={step.status} />
                                    </div>
                                    <p className="mt-2 text-xs text-muted-foreground">
                                        {step.assignee_kind}:{" "}
                                        {step.assignee_value}
                                    </p>
                                    {step.decided_at ? (
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            Decided {formatWhen(step.decided_at)}
                                        </p>
                                    ) : null}
                                    {step.sla_due_at ? (
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            SLA due {formatWhen(step.sla_due_at)}
                                        </p>
                                    ) : null}
                                </div>
                            ))}
                        </div>

                        {detail.instance.transitions.length > 0 ? (
                            <div className="space-y-2">
                                <h3 className="font-display text-sm font-semibold text-foreground">
                                    Audit trail
                                </h3>
                                <ol className="space-y-2">
                                    {detail.instance.transitions.map(
                                        (transition, index) => (
                                            <li
                                                key={index}
                                                className="flex items-start justify-between gap-3 rounded-lg border border-border/60 px-3 py-2"
                                            >
                                                <div className="min-w-0">
                                                    <p className="text-xs font-medium text-foreground">
                                                        {transition.new_state}
                                                        {transition.step_key
                                                            ? ` · ${transition.step_key}`
                                                            : ""}
                                                    </p>
                                                    {transition.reason ? (
                                                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                                                            {transition.reason}
                                                        </p>
                                                    ) : null}
                                                </div>
                                                <span className="shrink-0 text-xs text-muted-foreground">
                                                    {formatWhen(
                                                        transition.occurred_at,
                                                    )}
                                                </span>
                                            </li>
                                        ),
                                    )}
                                </ol>
                            </div>
                        ) : null}

                        <div className="space-y-2">
                            <Label htmlFor="approval-reason">
                                Note (optional)
                            </Label>
                            <Textarea
                                id="approval-reason"
                                value={reason}
                                onChange={(event) => setReason(event.target.value)}
                                placeholder="Add context for the audit trail…"
                                maxLength={1000}
                                rows={3}
                            />
                        </div>

                        {submitError ? (
                            <p className="text-sm font-medium text-destructive">
                                {submitError}
                            </p>
                        ) : null}

                        <DialogFooter className="gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={submitting !== null}
                                onClick={onClose}
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                variant="secondary"
                                disabled={submitting !== null}
                                onClick={() => void handleDecide("request_changes")}
                            >
                                {submitting === "request_changes" ? (
                                    <Spinner
                                        aria-hidden="true"
                                    />
                                ) : null}
                                Request changes
                            </Button>
                            <Button
                                type="button"
                                variant="destructive"
                                disabled={submitting !== null}
                                onClick={() => void handleDecide("reject")}
                            >
                                {submitting === "reject" ? (
                                    <Spinner
                                        aria-hidden="true"
                                    />
                                ) : null}
                                Reject
                            </Button>
                            <Button
                                type="button"
                                disabled={submitting !== null}
                                onClick={() => void handleDecide("approve")}
                            >
                                {submitting === "approve" ? (
                                    <Spinner
                                        aria-hidden="true"
                                    />
                                ) : null}
                                Approve
                            </Button>
                        </DialogFooter>
                    </>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}

/* ---------------------------------------------------------------------------
 * Inbox page
 * ------------------------------------------------------------------------- */

export function ApprovalsInbox() {
    const [inbox, setInbox] = useState<InboxState>({ state: "loading" });
    const [reviewingId, setReviewingId] = useState<string | null>(null);

    const load = useCallback(() => {
        setInbox({ state: "loading" });
        listApprovalInbox()
            .then((items) =>
                setInbox({ state: "ready", items, notice: null }),
            )
            .catch((error: unknown) =>
                setInbox({ state: "error", message: apiErrorMessage(error) }),
            );
    }, []);

    useEffect(load, [load]);

    const handleDecided = useCallback(
        (result: ApprovalDecisionResult) => {
            setReviewingId(null);
            if (inbox.state === "ready") {
                setInbox({
                    state: "ready",
                    items: inbox.items.filter(
                        (item) =>
                            item.instance_id !== result.instance_id,
                    ),
                    notice: `Step ${result.step_key} recorded · ${
                        result.instance_completed
                            ? "workflow completed"
                            : "workflow continued"
                    }`,
                });
            }
        },
        [inbox],
    );

    return (
        <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6">
            <PageHeader
                title="Approvals"
                description="Requests routed to you for review — AI suggestions are shown for context."
                icon={Inbox}
            />

            {inbox.state === "loading" ? <TableSkeleton rows={6} /> : null}

            {inbox.state === "error" ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-12 text-center">
                    <p className="text-sm font-medium text-destructive">
                        {inbox.message}
                    </p>
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={load}
                    >
                        <RefreshCw aria-hidden="true" />
                        Try again
                    </Button>
                </div>
            ) : null}

            {inbox.state === "ready" ? (
                <div className="overflow-hidden rounded-2xl border border-border bg-card">
                    {inbox.notice ? (
                        <div className="flex items-center gap-2 border-b border-border/60 bg-primary/5 px-4 py-3 text-sm text-primary">
                            <CheckCircle2
                                aria-hidden="true"
                                className="size-4"
                            />
                            {inbox.notice}
                        </div>
                    ) : null}
                    {inbox.items.length === 0 ? (
                        <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
                            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                                <Inbox aria-hidden="true" className="size-5" />
                            </div>
                            <h3 className="mt-3 font-display text-sm font-semibold text-foreground">
                                Inbox zero
                            </h3>
                            <p className="mt-1 max-w-60 text-xs leading-relaxed text-muted-foreground">
                                Nothing is waiting on you right now.
                            </p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead>
                                    <tr className="border-b border-border bg-muted/40 text-xs text-muted-foreground">
                                        <th
                                            scope="col"
                                            className="px-4 py-3 font-medium"
                                        >
                                            Item
                                        </th>
                                        <th
                                            scope="col"
                                            className="px-4 py-3 font-medium"
                                        >
                                            Step
                                        </th>
                                        <th
                                            scope="col"
                                            className="px-4 py-3 font-medium"
                                        >
                                            Submitted
                                        </th>
                                        <th
                                            scope="col"
                                            className="px-4 py-3 font-medium"
                                        >
                                            SLA due
                                        </th>
                                        <th
                                            scope="col"
                                            className="px-4 py-3 font-medium"
                                        >
                                            AI suggestion
                                        </th>
                                        <th
                                            scope="col"
                                            className="px-4 py-3 text-right font-medium"
                                        >
                                            <span className="sr-only">
                                                Actions
                                            </span>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {inbox.items.map((item) => (
                                        <tr
                                            key={item.instance_id}
                                            className="border-b border-border/60 last:border-0 hover:bg-muted/30"
                                        >
                                            <td className="px-4 py-3.5">
                                                <p className="font-medium text-foreground">
                                                    {item.resource_label}
                                                </p>
                                                <p className="mt-0.5 text-xs text-muted-foreground">
                                                    {item.status}
                                                </p>
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <p className="text-foreground">
                                                    {item.step_key}
                                                </p>
                                                <p className="mt-0.5 text-xs text-muted-foreground">
                                                    {item.delegated_from
                                                        ? `delegated from ${item.delegated_from.slice(0, 8)}`
                                                        : item.eligible_as}
                                                </p>
                                            </td>
                                            <td className="px-4 py-3.5 text-muted-foreground">
                                                {formatWhen(item.submitted_at)}
                                            </td>
                                            <td className="px-4 py-3.5 text-muted-foreground">
                                                {formatWhen(item.sla_due_at)}
                                            </td>
                                            <td className="px-4 py-3.5">
                                                {item.suggestion ? (
                                                    <SuggestionChip
                                                        suggestion={
                                                            item.suggestion
                                                        }
                                                    />
                                                ) : (
                                                    <span className="text-xs text-muted-foreground">
                                                        —
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3.5 text-right">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() =>
                                                        setReviewingId(
                                                            item.instance_id,
                                                        )
                                                    }
                                                >
                                                    Review
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            ) : null}

            {reviewingId ? (
                <ReviewDialog
                    instanceId={reviewingId}
                    onClose={() => setReviewingId(null)}
                    onDecided={handleDecided}
                />
            ) : null}
        </div>
    );
}