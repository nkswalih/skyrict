"use client";

import { ErrorPanel } from "@/components/ui/error-panel";
import { Spinner } from "@/components/ui/spinner";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
    ArrowRight,
    CheckCircle2,
    CreditCard,
    ShieldCheck,
} from "lucide-react";

import {
    clearWizardSession,
    loadWizardSession,
    type WizardSession,
} from "@/features/onboarding/wizard-session";
import type {
    BillingCurrency,
    BillingInterval,
    BillingPlan,
    BillingPlanId,
} from "@/lib/api/billing-api";
import { getSignupPlans } from "@/lib/api/auth-api";
import { describeLoadError } from "@/lib/api/error-messages";
import {
    formatPriceForCurrency,
    resolvePlanPrice,
} from "@/features/billing/billing-utils";
import { AuthButton } from "@/lib/auth/AuthButton";
import { deriveApex } from "@/lib/auth/apex";

const PLAN_IDS: ReadonlySet<string> = new Set<BillingPlanId>([
    "starter",
    "professional",
    "business",
    "enterprise",
]);
const INTERVALS: ReadonlySet<string> = new Set<BillingInterval>([
    "month",
    "year",
]);
const CURRENCIES: ReadonlySet<string> = new Set<BillingCurrency>([
    "usd",
    "inr",
    "gbp",
    "eur",
]);

function isComplete(
    session: Partial<WizardSession> | null,
): session is WizardSession {
    return Boolean(
        session &&
        session.email &&
        session.vt &&
        session.tenantId &&
        session.slug &&
        session.plan &&
        session.interval,
    );
}

/** Build the tenant-specific sign-in URL (same convention as the old org step). */
function signinTarget(slug: string, email: string): string {
    const { protocol, hostname, port } = window.location;
    const apex = deriveApex(hostname);
    return `${protocol}//${slug}.signin.${apex}${port ? `:${port}` : ""}/signin?email=${encodeURIComponent(email)}`;
}

function ReviewStep({
    email,
    vt,
    tenantId,
    slug,
    plan,
    interval,
    currency,
    checkout,
}: {
    email?: string;
    vt?: string;
    tenantId?: string;
    slug?: string;
    plan?: string;
    interval?: string;
    currency?: string;
    checkout?: string;
}) {
    const [plans, setPlans] = useState<BillingPlan[]>([]);
    const [loadingPlans, setLoadingPlans] = useState(true);
    const [loadError, setLoadError] = useState<unknown>(null);

    const session = useMemo(() => {
        const raw = loadWizardSession();
        return {
            email: email ?? raw?.email,
            vt: vt ?? raw?.vt,
            tenantId: tenantId ?? raw?.tenantId,
            slug: slug ?? raw?.slug,
            plan: (plan && PLAN_IDS.has(plan) ? plan : raw?.plan) as
                BillingPlanId | undefined,
            interval: (interval && INTERVALS.has(interval)
                ? interval
                : raw?.interval) as BillingInterval | undefined,
            currency: (currency && CURRENCIES.has(currency)
                ? currency
                : (raw?.currency ?? "usd")) as BillingCurrency,
        };
        // Only re-run when the URL-provided values change; the sessionStorage
        // read happens once per mount.
    }, [email, vt, tenantId, slug, plan, interval, currency]);

    const contextComplete = isComplete(session);

    useEffect(() => {
        let cancelled = false;
        getSignupPlans()
            .then((catalog) => {
                if (!cancelled) setPlans(catalog);
            })
            .catch((error: unknown) => {
                if (cancelled) return;
                setLoadError(error);
            })
            .finally(() => {
                if (!cancelled) setLoadingPlans(false);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const selectedId = session.plan ?? "starter";
    const selectedInterval = session.interval ?? "month";
    const selectedPlan = plans.find((p) => p.id === selectedId);
    const resolved = selectedPlan
        ? resolvePlanPrice(selectedPlan, session.currency, selectedInterval)
        : null;
    const price = resolved?.cents ?? null;
    const isPaid = price !== null && price > 0;

    if (!contextComplete) {
        return (
            <div className="space-y-4 text-center">
                <div className="space-y-2">
                    <h2 className="font-display text-xl font-semibold text-foreground">
                        Session expired
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Your onboarding session is missing. Restart the flow to
                        continue.
                    </p>
                </div>
                <AuthButton
                    className="w-full"
                    onClick={() => {
                        clearWizardSession();
                        window.location.assign("/signup");
                    }}
                >
                    Start over
                </AuthButton>
            </div>
        );
    }

    const charged = checkout === "success" && isPaid;

    return (
        <div className="space-y-5">
            {charged ? (
                <div className="flex items-start gap-2.5 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5">
                    <CheckCircle2
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-primary"
                    />
                    <div>
                        <p className="text-sm font-medium text-foreground">
                            Payment received
                        </p>
                        <p className="text-xs text-muted-foreground">
                            Your {selectedPlan?.display_name ?? "plan"} is on
                            its way. The subscription activates once Stripe
                            confirms the payment.
                        </p>
                    </div>
                </div>
            ) : null}

            <div className="rounded-xl border border-border bg-card p-4">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                    Review
                </p>
                <dl className="mt-3 space-y-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                        <dt className="text-muted-foreground">Workspace</dt>
                        <dd className="font-medium text-foreground">
                            {session.slug}
                        </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                        <dt className="text-muted-foreground">Plan</dt>
                        <dd className="font-medium text-foreground">
                            {selectedPlan?.display_name ?? "Starter"}
                        </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                        <dt className="text-muted-foreground">Billing</dt>
                        <dd className="font-medium text-foreground">
                            {formatPriceForCurrency(price, session.currency)} /
                            month
                            {resolved?.billedInUsd
                                ? " · charged in USD"
                                : ""} ·{" "}
                            {selectedInterval === "year" ? "annual" : "monthly"}
                        </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                        <dt className="text-muted-foreground">Payment</dt>
                        <dd className="font-medium text-foreground">
                            {isPaid
                                ? charged
                                    ? "Complete"
                                    : "Pending"
                                : "No payment required"}
                        </dd>
                    </div>
                </dl>

                {!isPaid ? (
                    <p className="mt-3 text-xs text-muted-foreground">
                        {selectedId === "enterprise"
                            ? "Enterprise pricing is quoted individually - the Skyrict team will reach out."
                            : "Starter is free forever. Upgrade anytime from your billing settings."}
                    </p>
                ) : null}
            </div>

            {loadingPlans ? (
                <div className="flex items-center justify-center py-6">
                    <Spinner
                        aria-hidden="true"
                        className="size-5 text-primary"
                    />
                    <span className="sr-only">Loading plan details</span>
                </div>
            ) : loadError ? (
                <ErrorPanel
                    {...describeLoadError(loadError, {
                        title: "Plan details are temporarily unavailable",
                        retryableMessage:
                            "We couldn't load your plan details right now. Please try again in a moment.",
                    })}
                />
            ) : (
                <div className="space-y-3">
                    <AuthButton
                        type="button"
                        className="w-full"
                        onClick={() =>
                            window.location.assign(
                                signinTarget(session.slug, session.email),
                            )
                        }
                    >
                        Enter my workspace
                        <ArrowRight aria-hidden="true" className="size-4" />
                    </AuthButton>

                    {isPaid && !charged ? (
                        <Link
                            href={`/signup/billing?${new URLSearchParams({
                                plan: session.plan,
                                interval: session.interval,
                                currency: session.currency,
                            }).toString()}`}
                            className="flex w-full items-center justify-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/50"
                        >
                            <CreditCard aria-hidden="true" className="size-4" />
                            Complete billing
                        </Link>
                    ) : null}

                    <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
                        <ShieldCheck aria-hidden="true" className="size-3.5" />
                        Your data is protected with encryption and MFA.
                    </p>
                </div>
            )}
        </div>
    );
}

export { ReviewStep };
