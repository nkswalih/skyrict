"use client";

import * as Sentry from "@sentry/nextjs";
import Link from "next/link";
import { useEffect } from "react";
import { AlertCircle, ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";

interface RouteErrorProps {
    error: Error & { digest?: string };
    reset: () => void;
    /** Where "Back" lands. Defaults to /dashboard. */
    backHref?: string;
}

/**
 * Shared fallback for per-segment `error.tsx` boundaries. `reset()` re-renders
 * the segment from scratch, which remounts client children - their mount
 * effects re-run and the failing fetch is genuinely retried. The shell chrome
 * (parent layout) stays mounted, so the user lands on a real page.
 */
export function RouteError({
    error,
    reset,
    backHref = "/",
}: RouteErrorProps) {
    useEffect(() => {
        Sentry.captureException(error);
    }, [error]);

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
                Something went wrong loading this page.
            </p>
            {error.digest ? (
                <p className="mt-1 text-xs text-muted-foreground">
                    Error ID: {error.digest}
                </p>
            ) : null}
            <div className="mt-4 flex items-center gap-2">
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => reset()}
                >
                    Try again
                </Button>
                <Button asChild variant="ghost" size="sm">
                    <Link href={backHref}>
                        <ArrowLeft aria-hidden="true" className="size-4" />
                        Back to dashboard
                    </Link>
                </Button>
            </div>
        </div>
    );
}