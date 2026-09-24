"use client";

import { Spinner } from "@/components/ui/spinner";
import { useEffect, useRef, useState } from "react";

type TurnstileApi = {
    render: (
        el: HTMLElement,
        options: {
            sitekey: string;
            theme?: "light" | "dark" | "auto";
            callback?: (token: string) => void;
            "expired-callback"?: () => void;
            "error-callback"?: () => void;
        },
    ) => string;
    reset: (widgetId: string) => void;
    remove: (widgetId: string) => void;
};

declare global {
    interface Window {
        turnstile?: TurnstileApi;
    }
}

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js";
const SCRIPT_ATTR = "data-skyrict-turnstile";

let scriptPromise: Promise<TurnstileApi> | undefined;

function loadTurnstile(): Promise<TurnstileApi> {
    if (window.turnstile) return Promise.resolve(window.turnstile);
    if (scriptPromise) return scriptPromise;

    scriptPromise = new Promise<TurnstileApi>((resolve, reject) => {
        const existing = document.querySelector(`script[${SCRIPT_ATTR}]`);
        if (existing) {
            existing.remove();
        }
        const script = document.createElement("script");
        script.src = `${SCRIPT_SRC}?render=explicit`;
        script.async = true;
        script.defer = true;
        script.setAttribute(SCRIPT_ATTR, "true");
        script.onload = () => {
            const deadline = Date.now() + 10_000;
            const poll = () => {
                if (window.turnstile) {
                    resolve(window.turnstile);
                } else if (Date.now() > deadline) {
                    reject(new Error("Turnstile failed to initialize"));
                } else {
                    setTimeout(poll, 50);
                }
            };
            poll();
        };
        script.onerror = () => reject(new Error("Failed to load Turnstile"));
        document.head.appendChild(script);
    });

    return scriptPromise;
}

function TurnstileWidget({
    siteKey,
    onTokenChange,
}: {
    siteKey: string;
    onTokenChange: (token: string | null) => void;
}) {
    const containerRef = useRef<HTMLDivElement>(null);
    const widgetIdRef = useRef<string | undefined>(undefined);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string>();

    // Hold the latest callback in a ref so the widget renders exactly once per
    // siteKey. Parent re-renders (e.g. typing in the email field) recreate the
    // inline onTokenChange arrow; without this the effect would tear down and
    // re-render the Turnstile iframe on every keystroke, resetting the token.
    const onTokenChangeRef = useRef(onTokenChange);
    onTokenChangeRef.current = onTokenChange;

    useEffect(() => {
        let cancelled = false;
        let widgetId: string | undefined;

        loadTurnstile()
            .then((api) => {
                if (cancelled || !containerRef.current) return;
                widgetId = api.render(containerRef.current, {
                    sitekey: siteKey,
                    theme: "auto",
                    callback: (token) => onTokenChangeRef.current(token),
                    "expired-callback": () => onTokenChangeRef.current(null),
                    "error-callback": () => onTokenChangeRef.current(null),
                });
                widgetIdRef.current = widgetId;
                setLoading(false);
            })
            .catch((err: unknown) => {
                if (cancelled) return;
                setLoading(false);
                setError(
                    err instanceof Error
                        ? err.message
                        : "Turnstile unavailable",
                );
            });

        return () => {
            cancelled = true;
            if (widgetId && window.turnstile) {
                window.turnstile.remove(widgetId);
            }
        };
    }, [siteKey]);

    if (error) {
        return (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                {error}
            </div>
        );
    }

    return (
        <div className="relative mx-auto w-fit max-[348px]:scale-[0.9]">
            {loading ? (
                <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5">
                    <Spinner
                        aria-hidden="true"
                        className="size-5 text-muted-foreground"
                    />
                    <span className="text-sm font-medium">
                        Checking your browser...
                    </span>
                </div>
            ) : null}
            {/* Never use display:none on the render target: Turnstile fails to
          initialize (shows its error/"Troubleshoot" state) when rendered
          into a hidden element. The spinner row above covers the loading
          window, and the container expands once the widget iframe lands. */}
            <div ref={containerRef} />
            <input
                aria-hidden="true"
                name="website"
                tabIndex={-1}
                autoComplete="off"
                className="absolute -left-[9999px] h-0 w-0"
            />
        </div>
    );
}

export { TurnstileWidget };
