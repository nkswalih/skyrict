"use client";
import { Logo } from "@/components/brand/logo";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";

import { TurnstileWidget } from "@/components/onboarding/turnstile-widget";
import {
    canProceed,
    resolveRiskGate,
    type RiskGateMode,
} from "@/components/onboarding/risk-gate";
import { env } from "@/config/env";
import { cn } from "@/lib/utils";

/**
 * The anti-bot gate in front of self-service sign-up.
 *
 * One rule governs this component: it must never report a verification that
 * did not happen.
 *
 * A Turnstile token being issued is NOT a verification. Cloudflare checks the
 * browser and hands back a token; the server exchanges that token for a verdict
 * at sign-up time. So this component may say "checking", and it may let the user
 * through to the form once a token exists - but it must not claim the user is
 * verified, because at this point nobody has verified anything.
 *
 * The previous implementation had a checkbox that called a hardcoded stub
 * returning `{ status: "ok" }` and flipped itself to "Verified" without a single
 * network call, so the user was told they had passed a check that never ran.
 * See docs/runbooks/pre-release-audit-2026-09.md finding 23.
 */
function RiskChallenge({
    demoCaptcha = false,
    onValidChange,
    onShowChange,
    onTokenChange,
}: {
    demoCaptcha?: boolean;
    /** True once a challenge token exists and is ready to submit. */
    onValidChange?: (valid: boolean) => void;
    onShowChange?: (visible: boolean) => void;
    onTokenChange?: (token: string | null) => void;
}) {
    const [show, setShow] = useState(false);
    const [token, setToken] = useState<string | null>(null);

    // The policy lives in risk-gate.ts so it can be tested without a DOM; this
    // component is only its renderer. See that file for why the client is never
    // entitled to claim a verification.
    const mode: RiskGateMode = resolveRiskGate({
        turnstileSiteKey: env.turnstileSiteKey,
        demoCaptcha,
    });

    // The honeypot. A real, off-screen, name="website" input that a human never
    // sees and a bot fills in. Kept in every branch - it is the one defence
    // that still works when the challenge provider is missing.
    const honeypot = (
        <input
            aria-hidden="true"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            className="absolute -left-[9999px] h-0 w-0"
        />
    );

    useEffect(() => {
        // No round trip. The previous implementation asked assessRisk() whether
        // a captcha was required, but that was a stub that always answered yes,
        // so the request bought nothing and could only ever disagree with the
        // server.
        //
        // Reports only the mode-derived decision. Every token-driven change
        // goes through handleToken, which is the single source for those - two
        // paths reporting validity would be able to contradict each other.
        // canProceed(mode, null) is the answer with no token in hand: a
        // challenge is not satisfied, an unavailable gate is not satisfied, and
        // a gate that does not apply does not obstruct anything.
        const visible = mode !== "hidden";
        setShow(visible);
        onShowChange?.(visible);
        onValidChange?.(canProceed(mode, null));
    }, [mode, onShowChange, onValidChange]);

    function handleToken(next: string | null) {
        setToken(next);
        onTokenChange?.(next);
        // canProceed, not `Boolean(next)`: in the unavailable mode a stray token
        // must not open a closed gate.
        onValidChange?.(canProceed(mode, next));
    }

    if (!show) {
        return <div aria-hidden="true" className="hidden">{honeypot}</div>;
    }

    // --- Provider configured: the managed challenge -------------------------
    if (mode === "challenge") {
        const done = Boolean(token);

        return (
            <div
                aria-hidden={done}
                inert={done}
                className={cn(
                    "fixed inset-0 z-50 flex items-center justify-center bg-card transition-opacity duration-300",
                    done ? "pointer-events-none opacity-0" : "opacity-100",
                )}
            >
                <div className="mx-auto flex w-full max-w-sm flex-col items-center gap-6 px-6 py-10 text-center">
                    <div className="flex flex-col items-center gap-2">
                        <Logo className="text-foreground" />
                        <h2 className="font-display text-xl font-semibold text-foreground">
                            One quick check
                        </h2>
                        {/* Truthful on both counts: a check IS running, and it
                            has not finished yet. The old copy - "Verifying you
                            are human" - asserted an outcome the client cannot
                            know and has not earned. */}
                        <p className="text-sm text-muted-foreground">
                            Confirm you&apos;re human so we can keep automated
                            sign-ups out.
                        </p>
                    </div>
                    <TurnstileWidget
                        siteKey={env.turnstileSiteKey}
                        onTokenChange={handleToken}
                    />
                    <p className="text-xs text-muted-foreground">
                        Your answers are checked when you submit, not just in
                        your browser.
                    </p>
                </div>
            </div>
        );
    }

    // --- No provider configured: say so, and do not let anyone through -------
    // The deployment is misconfigured. Rendering a control that looks like a
    // gate but passes everyone is strictly worse than refusing: it hides the
    // fault from the user and from the operator, and it leaves the sign-up
    // endpoint to reject every attempt with an opaque 4xx. Say what is wrong.
    return (
        <div
            role="alert"
            className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 shadow-sm"
        >
            <div className="flex items-start gap-3">
                <div className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md border border-destructive/40 bg-card">
                    <ShieldAlert
                        aria-hidden="true"
                        className="size-5 text-destructive"
                    />
                </div>
                <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">
                        Sign-up is unavailable
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        No CAPTCHA provider is configured for this environment,
                        so sign-up is closed rather than left unprotected. An
                        administrator needs to set the Turnstile site key. We are
                        not showing a check that would not actually be enforced.
                    </p>
                </div>
            </div>
            {honeypot}
        </div>
    );
}

export { RiskChallenge };
