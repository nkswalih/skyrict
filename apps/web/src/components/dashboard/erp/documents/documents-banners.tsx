import { AlertCircle, CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";

/** Inline error banner - mirrors the existing ERP error card styling. */
export function DocumentsError({
    message,
    className,
}: {
    message: string;
    className?: string;
}) {
    return (
        <div
            role="alert"
            className={cn(
                "flex items-start gap-2 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground",
                className,
            )}
        >
            <AlertCircle
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-destructive"
            />
            <span>{message}</span>
        </div>
    );
}

/** Inline success banner for optimistic/mutation feedback. */
export function DocumentsSuccess({
    message,
    className,
}: {
    message: string;
    className?: string;
}) {
    return (
        <div
            role="status"
            aria-live="polite"
            className={cn(
                "flex items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-400",
                className,
            )}
        >
            <CheckCircle2
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0"
            />
            <span>{message}</span>
        </div>
    );
}