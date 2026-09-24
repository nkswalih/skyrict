"use client";

import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ErrorStateProps {
    message: string;
    onRetry?: () => void;
}

/**
 * Failure state for API errors (network, timeout, 5xx). Distinct from the
 * empty state - an error is never rendered as "no rows".
 */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
    return (
        <div
            role="alert"
            className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-10 text-center"
        >
            <AlertCircle
                aria-hidden="true"
                className="size-5 shrink-0 text-destructive"
            />
            <p className="mt-3 text-sm font-medium text-foreground">
                {message}
            </p>
            {onRetry ? (
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={onRetry}
                >
                    Try again
                </Button>
            ) : null}
        </div>
    );
}
