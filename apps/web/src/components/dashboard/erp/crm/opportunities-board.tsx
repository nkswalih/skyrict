"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    ArrowRight,
    Columns3,
    GripVertical,
    MoreHorizontal,
    TrendingUp,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { ErrorState } from "@/components/dashboard/erp/error-state";
import { EmptyState } from "@/components/dashboard/erp/empty-state";
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
import { Textarea } from "@/components/ui/textarea";
import { useModuleAccess } from "@/lib/access/modules";
import {
    changeOpportunityStage,
    listOpportunities,
    type Opportunity,
    type OpportunityStage,
} from "@/lib/api/crm-api";
import { ApiError } from "@/lib/api/http";
import {
    isTerminalStage,
    nextStages,
    PIPELINE_STAGES,
} from "@/lib/erp/actions";
import { formatDate, formatMoney } from "@/lib/erp/money";
import {
    opportunityStageBadgeClass,
    OPPORTUNITY_STAGE_LABELS,
} from "@/lib/erp/labels";
import { cn } from "@/lib/utils";

type PageStatus =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; opportunities: Opportunity[]; notice?: string };

function opportunityName(opportunity: Opportunity): string {
    return opportunity.name || "Unnamed opportunity";
}

export function OpportunitiesBoard() {
    const router = useRouter();
    const { permissions } = useModuleAccess();
    const canWrite =
        permissions.includes("*") || permissions.includes("erp.crm.write");

    const [status, setStatus] = useState<PageStatus>({ state: "loading" });
    const [pending, setPending] = useState<{
        id: string;
        stage: OpportunityStage;
    } | null>(null);
    const [confirming, setConfirming] = useState<{
        opportunity: Opportunity;
        action: "move" | "won" | "lost";
        stage: OpportunityStage;
    } | null>(null);
    const [lostReason, setLostReason] = useState("");
    const [draggingId, setDraggingId] = useState<string | null>(null);
    const [dragOverStage, setDragOverStage] = useState<OpportunityStage | null>(
        null,
    );
    const [menuFor, setMenuFor] = useState<string | null>(null);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const result = await listOpportunities({ limit: 100 });
            setStatus({ state: "ready", opportunities: result.data });
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load opportunities.";
            setStatus({ state: "error", message });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const grouped = useMemo(() => {
        if (status.state !== "ready")
            return new Map<OpportunityStage, Opportunity[]>();
        const map = new Map<OpportunityStage, Opportunity[]>();
        for (const stage of PIPELINE_STAGES) map.set(stage, []);
        for (const opportunity of status.opportunities) {
            map.get(opportunity.stage)?.push(opportunity);
        }
        return map;
    }, [status]);

    /**
     * Move a deal and trust the response.
     *
     * The stage-change endpoint returns the persisted opportunity, so the
     * board applies that row instead of re-reading the pipeline. The re-read
     * used to race the write's commit and could settle the board on the
     * PREVIOUS stage - the card visibly snapping back to its old column and
     * staying there, which reads as a move that silently failed - and it
     * flashed the entire board through a loading state on every drag.
     */
    async function runMove(
        opportunity: Opportunity,
        stage: OpportunityStage,
        lostReason?: string,
    ) {
        setPending({ id: opportunity.id, stage });
        // Where this card sat before the move, so a failure can put it back.
        const previousStage = opportunity.stage;
        try {
            const { opportunity: moved } = await changeOpportunityStage(
                opportunity.id,
                stage,
                lostReason,
            );
            setStatus((current) =>
                current.state === "ready"
                    ? {
                          ...current,
                          opportunities: current.opportunities.map((item) =>
                              item.id === moved.id ? moved : item,
                          ),
                      }
                    : current,
            );
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not move the opportunity.";
            // The drag path flipped the card optimistically, so a failure has
            // to undo it - leaving a card in a column the server never
            // accepted is a lie the user has to notice and undo by hand.
            setStatus((current) =>
                current.state === "ready"
                    ? {
                          ...current,
                          notice: message,
                          opportunities: current.opportunities.map((item) =>
                              item.id === opportunity.id
                                  ? { ...item, stage: previousStage }
                                  : item,
                          ),
                      }
                    : current,
            );
        } finally {
            setPending(null);
        }
    }

    /**
     * Optimistic drag-drop move: flip the card locally first, then persist.
     * The server stays authoritative - on any failure we reload so the board
     * reverts to the real pipeline state and the error is surfaced above.
     */
    async function onDropTo(stage: OpportunityStage) {
        const dragged = draggingId
            ? status.state === "ready"
                ? (status.opportunities.find(
                      (item) => item.id === draggingId,
                  ) ?? null)
                : null
            : null;
        setDragOverStage(null);
        setDraggingId(null);
        if (
            !dragged ||
            !canWrite ||
            isTerminalStage(stage) ||
            dragged.stage === stage
        )
            return;
        setStatus((current) =>
            current.state === "ready"
                ? {
                      ...current,
                      opportunities: current.opportunities.map((item) =>
                          item.id === dragged.id ? { ...item, stage } : item,
                      ),
                  }
                : current,
        );
        await runMove(dragged, stage);
    }

    function onConfirm() {
        if (!confirming) return;
        const { opportunity, stage, action } = confirming;
        const reason = action === "lost" ? lostReason.trim() : "";
        setConfirming(null);
        setLostReason("");
        void runMove(opportunity, stage, reason || undefined);
    }

    if (status.state === "loading") {
        return (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
                {PIPELINE_STAGES.map((stage) => (
                    <div key={stage} className="space-y-3">
                        <div className="h-8 w-28 rounded-lg bg-muted/70" />
                        <div className="h-36 rounded-xl border border-border bg-card" />
                        <div className="h-36 rounded-xl border border-border bg-card" />
                    </div>
                ))}
            </div>
        );
    }

    if (status.state === "error") {
        return (
            <ErrorState message={status.message} onRetry={() => void load()} />
        );
    }

    return (
        <div className="space-y-4">
            {status.notice ? (
                <div
                    role="alert"
                    className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm font-medium text-destructive"
                >
                    {status.notice}
                </div>
            ) : null}

            {status.opportunities.length === 0 ? (
                <EmptyState
                    icon={TrendingUp}
                    title="Your pipeline is empty"
                    description="Qualify a lead and it lands here at the prospecting stage, ready to move forward."
                />
            ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
                    {PIPELINE_STAGES.map((stage) => {
                        const opportunities = grouped.get(stage) ?? [];
                        const isDropTarget =
                            canWrite && !isTerminalStage(stage);
                        const over = dragOverStage === stage;
                        return (
                            <section
                                key={stage}
                                aria-label={OPPORTUNITY_STAGE_LABELS[stage]}
                                className={cn(
                                    "min-w-0 rounded-xl transition-colors",
                                    isDropTarget &&
                                        over &&
                                        "bg-primary/5 ring-2 ring-primary/30",
                                )}
                                onDragOver={(event) => {
                                    if (!isDropTarget || !draggingId) return;
                                    event.preventDefault();
                                    event.dataTransfer.dropEffect = "move";
                                    setDragOverStage(stage);
                                }}
                                onDragLeave={() => {
                                    if (dragOverStage === stage)
                                        setDragOverStage(null);
                                }}
                                onDrop={(event) => {
                                    if (!isDropTarget) return;
                                    event.preventDefault();
                                    void onDropTo(stage);
                                }}
                            >
                                <header className="mb-3 flex items-center justify-between gap-2 px-1">
                                    <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                                        <Columns3
                                            aria-hidden="true"
                                            className="size-3.5 text-muted-foreground"
                                        />
                                        {OPPORTUNITY_STAGE_LABELS[stage]}
                                    </h2>
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
                                        {opportunities.length}
                                    </span>
                                </header>
                                <div className="space-y-3">
                                    {opportunities.map((opportunity) => (
                                        <OpportunityCard
                                            key={opportunity.id}
                                            opportunity={opportunity}
                                            canWrite={canWrite}
                                            pending={pending}
                                            draggable={
                                                canWrite &&
                                                !isTerminalStage(
                                                    opportunity.stage,
                                                )
                                            }
                                            dragging={
                                                draggingId === opportunity.id
                                            }
                                            menuOpen={
                                                menuFor === opportunity.id
                                            }
                                            onDragStart={() => {
                                                setDraggingId(opportunity.id);
                                                setMenuFor(null);
                                            }}
                                            onDragEnd={() => {
                                                setDraggingId(null);
                                                setDragOverStage(null);
                                            }}
                                            onOpenMenu={() =>
                                                setMenuFor(opportunity.id)
                                            }
                                            onCloseMenu={() => setMenuFor(null)}
                                            onMove={(nextStage) =>
                                                setConfirming({
                                                    opportunity,
                                                    action:
                                                        nextStage === "won"
                                                            ? "won"
                                                            : nextStage === "lost"
                                                              ? "lost"
                                                              : "move",
                                                    stage: nextStage,
                                                })
                                            }
                                            onWon={() =>
                                                setConfirming({
                                                    opportunity,
                                                    action: "won",
                                                    stage: "won",
                                                })
                                            }
                                            onLost={() => {
                                                setLostReason("");
                                                setConfirming({
                                                    opportunity,
                                                    action: "lost",
                                                    stage: "lost",
                                                });
                                            }}
                                            onOpen={() =>
                                                router.push(
                                                    `/erp/crm/opportunities/${opportunity.id}`,
                                                )
                                            }
                                        />
                                    ))}
                                </div>
                            </section>
                        );
                    })}
                </div>
            )}

            {/* Confirm dialog for stage moves and the won/lost terminal transitions. */}
            <Dialog
                open={confirming !== null}
                onOpenChange={(open) => !open && setConfirming(null)}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {confirming?.action === "lost"
                                ? "Mark as lost?"
                                : confirming?.action === "won"
                                  ? "Mark as won?"
                                  : `Move to ${confirming ? OPPORTUNITY_STAGE_LABELS[confirming.stage] : ""}?`}
                        </DialogTitle>
                        <DialogDescription>
                            {confirming?.action === "won"
                                ? "The customer will be created from this opportunity in the CRM."
                                : confirming?.action === "lost"
                                  ? "The pipeline closes and the opportunity can no longer move."
                                  : `The opportunity moves forward to the ${confirming ? OPPORTUNITY_STAGE_LABELS[confirming.stage] : ""} stage.`}
                        </DialogDescription>
                    </DialogHeader>

                    {confirming?.action === "lost" ? (
                        <div className="space-y-1.5">
                            <label
                                htmlFor="lost-reason"
                                className="text-sm font-medium text-foreground"
                            >
                                Lost reason
                            </label>
                            <Textarea
                                id="lost-reason"
                                value={lostReason}
                                onChange={(event) =>
                                    setLostReason(event.target.value)
                                }
                                placeholder="e.g. went with a competitor"
                                maxLength={500}
                                disabled={pending !== null}
                            />
                        </div>
                    ) : null}

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setConfirming(null)}
                            disabled={pending !== null}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            variant={
                                confirming?.action === "lost"
                                    ? "destructive"
                                    : "default"
                            }
                            onClick={onConfirm}
                            disabled={pending !== null}
                        >
                            {pending !== null ? (
                                <Spinner
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            ) : null}
                            {confirming?.action === "lost"
                                ? "Mark lost"
                                : confirming?.action === "won"
                                  ? "Mark won"
                                  : "Move forward"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

function OpportunityCard({
    opportunity,
    canWrite,
    pending,
    draggable,
    dragging,
    menuOpen,
    onDragStart,
    onDragEnd,
    onOpenMenu,
    onCloseMenu,
    onMove,
    onWon,
    onLost,
    onOpen,
}: {
    opportunity: Opportunity;
    canWrite: boolean;
    pending: { id: string; stage: OpportunityStage } | null;
    draggable: boolean;
    dragging: boolean;
    menuOpen: boolean;
    onDragStart: () => void;
    onDragEnd: () => void;
    onOpenMenu: () => void;
    onCloseMenu: () => void;
    onMove: (stage: OpportunityStage) => void;
    onWon: () => void;
    onLost: () => void;
    onOpen: () => void;
}) {
    const isBusy = pending?.id === opportunity.id;
    const stages = nextStages(opportunity.stage);
    const terminal = isTerminalStage(opportunity.stage);
    const menuAnchor = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!menuOpen) return;
        function onPointerDown(event: MouseEvent | TouchEvent) {
            if (
                menuAnchor.current &&
                !menuAnchor.current.contains(event.target as Node)
            ) {
                onCloseMenu();
            }
        }
        document.addEventListener("mousedown", onPointerDown);
        document.addEventListener("touchstart", onPointerDown);
        return () => {
            document.removeEventListener("mousedown", onPointerDown);
            document.removeEventListener("touchstart", onPointerDown);
        };
    }, [menuOpen, onCloseMenu]);

    return (
        <article
            ref={menuAnchor}
            draggable={draggable}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onClick={(event) => {
                if (menuOpen) return;
                if ((event.target as HTMLElement).closest("button")) return;
                onOpen();
            }}
            className={cn(
                "relative rounded-xl border border-border bg-card p-3 transition-shadow hover:shadow-sm",
                opportunity.stage === "won" && "border-emerald-500/30",
                opportunity.stage === "lost" && "border-border opacity-80",
                draggable && "cursor-grab active:cursor-grabbing",
                dragging && "opacity-40",
            )}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <h3 className="truncate text-sm font-medium text-foreground">
                        {opportunityName(opportunity)}
                    </h3>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                        {opportunity.leadId
                            ? "From qualified lead"
                            : "Manual opportunity"}
                    </p>
                </div>
                {canWrite ? (
                    <div className="flex shrink-0 items-center gap-0.5">
                        {draggable ? (
                            <GripVertical
                                aria-hidden="true"
                                className="size-3.5 text-muted-foreground/60"
                            />
                        ) : null}
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            aria-label={`Move ${opportunityName(opportunity)} to another stage`}
                            onClick={(event) => {
                                event.stopPropagation();
                                if (menuOpen) onCloseMenu();
                                else onOpenMenu();
                            }}
                        >
                            <MoreHorizontal
                                aria-hidden="true"
                                className="size-3.5 text-muted-foreground"
                            />
                        </Button>
                    </div>
                ) : null}
            </div>

            {menuOpen ? (
                <div className="absolute top-10 right-3 z-20 min-w-44 overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10">
                    <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
                        Move to stage
                    </p>
                    {stages.length === 0 ? (
                        <p className="px-2 py-1.5 text-sm text-muted-foreground">
                            {terminal
                                ? "This deal is closed."
                                : "No moves available."}
                        </p>
                    ) : (
                        stages.map((stage) => (
                            <button
                                key={stage}
                                type="button"
                                disabled={pending !== null}
                                onClick={() => {
                                    onCloseMenu();
                                    if (stage === "won") onWon();
                                    else if (stage === "lost") onLost();
                                    else onMove(stage);
                                }}
                                className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                            >
                                {OPPORTUNITY_STAGE_LABELS[stage]}
                                {isBusy && pending?.stage === stage ? (
                                    <Spinner
                                        aria-hidden="true"
                                        className="size-3"
                                    />
                                ) : null}
                            </button>
                        ))
                    )}
                </div>
            ) : null}

            <div className="mt-3 space-y-1">
                <p className="min-w-0 font-display text-base font-semibold text-foreground tabular-nums">
                    {formatMoney(opportunity.amount, opportunity.currency)}
                </p>
                <Badge
                    variant="outline"
                    className={opportunityStageBadgeClass(opportunity.stage)}
                >
                    {OPPORTUNITY_STAGE_LABELS[opportunity.stage]}
                </Badge>
            </div>

            <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
                <div className="flex items-center justify-between gap-2">
                    <dt className="min-w-0">Probability</dt>
                    <dd className="min-w-0 text-right font-medium text-foreground tabular-nums">
                        {opportunity.probability}%
                    </dd>
                </div>
                <div className="flex items-center justify-between gap-2">
                    <dt className="min-w-0">Expected close</dt>
                    <dd className="min-w-0 text-right font-medium text-foreground">
                        {formatDate(opportunity.expectedCloseDate)}
                    </dd>
                </div>
            </dl>

            {canWrite && !terminal && stages.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1">
                    {stages.map((stage) => (
                        <Button
                            key={stage}
                            type="button"
                            variant="outline"
                            size="xs"
                            disabled={pending !== null}
                            onClick={() => onMove(stage)}
                        >
                            {isBusy && pending?.stage === stage ? (
                                <Spinner
                                    aria-hidden="true"
                                    className="size-3"
                                />
                            ) : (
                                <ArrowRight
                                    aria-hidden="true"
                                    className="size-3"
                                />
                            )}
                            {OPPORTUNITY_STAGE_LABELS[stage]}
                        </Button>
                    ))}
                </div>
            ) : canWrite && terminal ? (
                <div className="mt-3 h-6" aria-hidden="true" />
            ) : null}
        </article>
    );
}
