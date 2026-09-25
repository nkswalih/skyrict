"use client";

import { AlertCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

interface ErrorPanelProps {
    /** Short headline, e.g. "Plans are temporarily unavailable". */
    title: string;
    /** One or two calm sentences the user can act on. */
    message: string;
    /** Show a Retry control. Only for safe re-runs (list/data loads). */
    onRetry?: () => void;
    /** Retry label; defaults to "Retry". */
    retryLabel?: string;
    /** Optional secondary action next to Retry (e.g. a nav link). */
    secondary?: ReactNode;
}

/**
 * Shared failure presentation for data-loading surfaces (marketing pricing,
 * the signup wizard, dashboard widgets). Announces via `role="alert"` so
 * screen readers surface the failure without requiring focus, and renders a
 * text + icon layout that never depends on color alone.
 *
 * Mutations must NOT pass `onRetry` - re-running a POST could double-create a
 * record; mutation failures get a message-only toast via `onApiError` instead.
 */
export function ErrorPanel({
    title,
    message,
    onRetry,
    retryLabel = "Retry",
    secondary,
}: ErrorPanelProps) {
    return (
        <div role="alert" className="mx-auto w-full max-w-lg space-y-3">
            <div className="space-y-1 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
                <div className="flex items-start gap-2">
                    <AlertCircle
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-destructive"
                    />
                    <h2 className="text-sm font-semibold text-destructive">
                        {title}
                    </h2>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                    {message}
                </p>
            </div>
            {onRetry || secondary ? (
                <div className="flex flex-wrap items-center justify-center gap-2">
                    {onRetry ? (
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={onRetry}
                        >
                            {retryLabel}
                        </Button>
                    ) : null}
                    {secondary}
                </div>
            ) : null}
        </div>
    );
}