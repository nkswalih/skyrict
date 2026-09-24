"use client";

import { Spinner } from "@/components/ui/spinner";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
    ArrowLeft,
    CheckCircle2,
    CreditCard,
} from "lucide-react";

import {
    clearWizardSession,
    loadWizardSession,
    saveWizardSession,
    type WizardSession,
} from "@/features/onboarding/wizard-session";
import type {
    BillingCurrency,
    BillingInterval,
    BillingPlan,
    BillingPlanId,
} from "@/lib/api/billing-api";
import {
    ApiError,
    createSignupCheckoutSession,
    getSignupPlans,
} from "@/lib/api/auth-api";
import {
    formatPriceForCurrency,
    resolvePlanPrice,
} from "@/features/billing/billing-utils";
import {
    SUPPORTED_CURRENCIES,
} from "@/lib/billing/currency";
import { AuthButton } from "@/lib/auth/AuthButton";

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
// The wizard's currency rides the Stripe redirect URL; validate against the
// beta allowlist (checkout itself is rejected server-side for pending/non-
// allowlisted currencies, so this is routing hygiene, not a gate).
const CURRENCIES: ReadonlySet<string> = new Set<BillingCurrency>(
    SUPPORTED_CURRENCIES,
);

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

function BillingStep({
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
    const router = useRouter();
    const [plans, setPlans] = useState<BillingPlan[]>([]);
    const [loadingPlans, setLoadingPlans] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState("");

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
                setLoadError(
                    error instanceof ApiError
                        ? error.message
                        : "Could not load plan details. Try again.",
                );
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

    const isEnterprise = selectedId === "enterprise";
    const isPaid = price !== null && price > 0;

    async function handleCheckout() {
        if (!isComplete(session)) return;
        setCreating(true);
        setCreateError("");
        try {
            const checkoutSession = await createSignupCheckoutSession({
                email: session.email,
                verificationToken: session.vt,
                tenantId: session.tenantId,
                planId: session.plan,
                interval: session.interval,
                currency: session.currency,
            });
            saveWizardSession({
                email: session.email,
                vt: session.vt,
                tenantId: session.tenantId,
                slug: session.slug,
                plan: session.plan,
                interval: session.interval,
                currency: session.currency,
            });
            window.location.assign(checkoutSession.url);
        } catch (error: unknown) {
            setCreateError(
                error instanceof ApiError
                    ? error.message
                    : "Could not start checkout. Try again.",
            );
            setCreating(false);
        }
    }

    function handleStarterContinue() {
        if (!isComplete(session)) return;
        const next = new URLSearchParams({
            plan: session.plan as string,
            interval: session.interval as string,
            currency: session.currency,
        });
        router.push(`/signup/review?${next.toString()}`);
    }

    function handleChangePlan() {
        if (!isComplete(session)) return;
        const next = new URLSearchParams({
            email: session.email,
            vt: session.vt,
            tenantId: session.tenantId,
            slug: session.slug,
        });
        router.push(`/signup/plan?${next.toString()}`);
    }

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
                        router.push("/signup");
                    }}
                >
                    Start over
                </AuthButton>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {checkout === "cancelled" ? (
                <div className="flex items-start gap-2.5 rounded-lg border border-border bg-muted/40 px-3 py-2.5">
                    <CheckCircle2
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    />
                    <div>
                        <p className="text-sm font-medium text-foreground">
                            Payment cancelled
                        </p>
                        <p className="text-xs text-muted-foreground">
                            No charge was made. You can retry checkout or
                            continue with the free Starter plan.
                        </p>
                    </div>
                </div>
            ) : null}

            {loadingPlans ? (
                <div className="flex items-center justify-center py-10">
                    <Spinner
                        aria-hidden="true"
                        className="size-5 text-primary"
                    />
                    <span className="sr-only">Loading plan details</span>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="rounded-xl border border-border bg-card p-4">
                        <div className="flex items-center justify-between gap-3">
                            <div>
                                <p className="font-display text-sm font-semibold text-foreground">
                                    {selectedPlan?.display_name ?? "Starter"}{" "}
                                    plan
                                </p>
                                <p className="mt-0.5 text-xs text-muted-foreground">
                                    Billed{" "}
                                    {selectedInterval === "year"
                                        ? "annually"
                                        : "monthly"}
                                    {selectedPlan && resolved ? (
                                        <span>
                                            {" · "}
                                            {formatPriceForCurrency(
                                                resolved.cents,
                                                resolved.currency,
                                            )}{" "}
                                            / month
                                            {resolved.billedInUsd
                                                ? " · charged in USD"
                                                : null}
                                        </span>
                                    ) : null}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={handleChangePlan}
                                className="text-sm font-medium text-primary underline-offset-4 hover:underline outline-none"
                            >
                                Change plan
                            </button>
                        </div>
                        {selectedPlan?.features.modules.length ? (
                            <ul className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                                {selectedPlan.features.modules.map((module) => (
                                    <li
                                        key={module}
                                        className="flex items-start gap-1.5 text-xs text-muted-foreground"
                                    >
                                        <CheckCircle2
                                            aria-hidden="true"
                                            className="mt-0.5 size-3 shrink-0 text-primary"
                                        />
                                        {module}
                                    </li>
                                ))}
                            </ul>
                        ) : null}
                    </div>

                    {loadError ? (
                        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                            {loadError}
                        </p>
                    ) : null}

                    {isEnterprise ? (
                        <div className="space-y-3">
                            <p className="text-sm text-muted-foreground">
                                Enterprise plans are quoted individually so our
                                team can tailor SSO, data integrations, and
                                support to your organization.
                            </p>
                            <a
                                href="mailto:sales@skyrict.in?subject=Enterprise plan"
                                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-3 focus-visible:ring-ring/30 outline-none"
                            >
                                <CreditCard
                                    aria-hidden="true"
                                    className="size-4"
                                />
                                Contact the Skyrict team
                            </a>
                        </div>
                    ) : isPaid && resolved ? (
                        <div className="space-y-3">
                            <AuthButton
                                type="button"
                                loading={creating}
                                className="w-full"
                                onClick={handleCheckout}
                            >
                                Pay with card ·{" "}
                                {formatPriceForCurrency(
                                    resolved.cents,
                                    resolved.currency,
                                )}{" "}
                                / month
                            </AuthButton>
                            {createError ? (
                                <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                                    {createError}
                                </p>
                            ) : null}
                            <p className="text-center text-xs text-muted-foreground">
                                Secured by Stripe. You won&apos;t be charged
                                until you complete payment.
                            </p>
                        </div>
                    ) : (
                        <AuthButton
                            type="button"
                            className="w-full"
                            onClick={handleStarterContinue}
                        >
                            Continue for free
                        </AuthButton>
                    )}
                </div>
            )}

            <button
                type="button"
                onClick={() =>
                    router.push(
                        `/signup/plan?${new URLSearchParams({ email: session.email, vt: session.vt, tenantId: session.tenantId, slug: session.slug }).toString()}`,
                    )
                }
                className="flex items-center justify-center gap-1.5 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline outline-none"
            >
                <ArrowLeft aria-hidden="true" className="size-3.5" />
                Back to plan
            </button>
        </div>
    );
}

export { BillingStep };
