"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, CreditCard, ExternalLink } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/sonner";
import { hasPermission, useModuleAccess } from "@/lib/access/modules";
import {
    createCheckoutSession,
    createPortalSession,
    getBillingSubscription,
    listBillingPlans,
    type BillingInterval,
    type BillingPlan,
    type BillingPlanId,
    type BillingSubscription,
} from "@/lib/api/billing-api";
import { apiErrorMessage, onApiError } from "@/lib/api/error-toast";
import {
    formatPriceCents,
    purchasablePlans,
    subscriptionStatusLabel,
    trialCountdownLabel,
} from "@/features/billing/billing-utils";
import { cn } from "@/lib/utils";

const BILLING_MANAGE = "billing.manage";

function PlanCardSkeleton() {
    return (
        <section className="rounded-xl border border-border bg-card p-4">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="mt-3 h-8 w-24" />
            <Skeleton className="mt-4 h-4 w-full" />
            <Skeleton className="mt-2 h-4 w-3/4" />
            <Skeleton className="mt-5 h-9 w-full" />
        </section>
    );
}

interface PlanCardProps {
    plan: BillingPlan;
    interval: BillingInterval;
    isCurrent: boolean;
    canCheckout: boolean;
    pending: boolean;
    onCheckout: (planId: BillingPlanId, interval: BillingInterval) => void;
}

function PlanCard({
    plan,
    interval,
    isCurrent,
    canCheckout,
    pending,
    onCheckout,
}: PlanCardProps) {
    const price =
        interval === "year" ? plan.annual_price_cents : plan.monthly_price_cents;
    const features = [
        plan.features.max_users === null
            ? "Unlimited users"
            : `${plan.features.max_users} users`,
        plan.features.ai_credits_monthly === null
            ? "Custom AI credits"
            : `${plan.features.ai_credits_monthly.toLocaleString()} AI credits / month`,
        plan.features.max_agents === null
            ? "Unlimited agents"
            : `${plan.features.max_agents} agents`,
    ];

    return (
        <section
            aria-label={`${plan.display_name} plan`}
            className={cn(
                "flex flex-col rounded-xl border bg-card p-4",
                isCurrent ? "border-primary/50" : "border-border",
            )}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <h3 className="font-display text-sm font-semibold text-foreground">
                        {plan.display_name}
                    </h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                        {plan.features.modules.length > 0
                            ? plan.features.modules.join(" · ")
                            : "Core suite"}
                    </p>
                </div>
                {isCurrent ? (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                        Current
                    </span>
                ) : null}
            </div>

            <div className="mt-3 flex flex-wrap items-baseline gap-x-1.5">
                <span className="font-display text-2xl font-semibold text-foreground">
                    {formatPriceCents(price)}
                </span>
                {price !== null && price > 0 ? (
                    <span className="text-xs text-muted-foreground">
                        / month
                        {interval === "year" ? ", billed yearly" : ""}
                    </span>
                ) : null}
            </div>

            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
                {features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                        <Check
                            aria-hidden="true"
                            className="mt-0.5 size-3.5 shrink-0 text-primary"
                        />
                        <span>{feature}</span>
                    </li>
                ))}
            </ul>

            <div className="mt-5 flex flex-1 items-end">
                {isCurrent ? (
                    <Button variant="outline" disabled className="w-full">
                        Current plan
                    </Button>
                ) : plan.id === "enterprise" ? (
                    <Button variant="outline" asChild className="w-full">
                        <a href="mailto:sales@skyrict.in?subject=Enterprise plan">
                            Contact sales
                        </a>
                    </Button>
                ) : canCheckout ? (
                    <Button
                        onClick={() => onCheckout(plan.id as BillingPlanId, interval)}
                        disabled={pending}
                        className="w-full"
                    >
                        {pending ? "Preparing checkout…" : `Choose ${plan.display_name}`}
                    </Button>
                ) : (
                    <Button variant="outline" disabled className="w-full">
                        Requires workspace owner
                    </Button>
                )}
            </div>
        </section>
    );
}

/**
 * Plans and billing (SKY-36). Any member can view the catalog and their
 * workspace's subscription; checkout and portal actions are owner-only
 * (backend enforces `billing.manage` + `tenant_owner` too).
 */
export function PlansPage() {
    const searchParams = useSearchParams();
    const { status: accessStatus, roles, permissions } = useModuleAccess();
    const [subscription, setSubscription] = useState<BillingSubscription | null>(null);
    const [plans, setPlans] = useState<BillingPlan[] | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [interval, setInterval] = useState<BillingInterval>("year");
    const [pendingCheckout, setPendingCheckout] = useState<string | null>(null);
    const [portalPending, setPortalPending] = useState(false);
    const [actionError, setActionError] = useState<string | null>(null);
    const notifiedCheckout = useRef<string | null>(null);

    // Mirror the backend gate exactly: billing.manage PLUS the owner role.
    // organization_admin holds billing.manage but not tenant_owner, so a
    // non-owner must never see action buttons that would 403.
    const canManageBilling =
        accessStatus === "ready" &&
        roles.includes("tenant_owner") &&
        hasPermission(permissions, BILLING_MANAGE);

    const load = useCallback(() => {
        setLoadError(null);
        void Promise.all([getBillingSubscription(), listBillingPlans()])
            .then(([nextSubscription, nextPlans]) => {
                setSubscription(nextSubscription);
                setPlans(nextPlans);
            })
            .catch((error: unknown) => setLoadError(apiErrorMessage(error)));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Stripe redirects back to this page with ?checkout=success|cancelled.
    useEffect(() => {
        const state = searchParams.get("checkout");
        if (!state || notifiedCheckout.current === state) return;
        notifiedCheckout.current = state;
        if (state === "success") {
            toast.success("Subscription updated", {
                description: "Your new plan is active. Welcome aboard.",
            });
        } else if (state === "cancelled") {
            toast.info("Checkout cancelled", {
                description: "You can upgrade any time from this page.",
            });
        }
        // Strip the query param so a later visit (no new checkout) does not
        // replay the toast from stale URL state.
        const url = new URL(window.location.href);
        url.searchParams.delete("checkout");
        window.history.replaceState(null, "", url.toString());
    }, [searchParams]);

    async function handleCheckout(planId: BillingPlanId, billingInterval: BillingInterval) {
        setActionError(null);
        setPendingCheckout(`${planId}:${billingInterval}`);
        try {
            const session = await createCheckoutSession(planId, billingInterval);
            window.location.assign(session.url);
        } catch (error) {
            setActionError(apiErrorMessage(error));
            onApiError(error, { description: "The checkout session could not be started." });
            setPendingCheckout(null);
        }
    }

    async function handlePortal() {
        setActionError(null);
        setPortalPending(true);
        try {
            const session = await createPortalSession();
            window.location.assign(session.url);
        } catch (error) {
            setActionError(apiErrorMessage(error));
            onApiError(error, { description: "The billing portal could not be opened." });
            setPortalPending(false);
        }
    }

    const loading = subscription === null || plans === null;
    const currentPlan =
        subscription === null
            ? null
            : plans?.find((plan) => plan.id === subscription.plan_id) ?? null;

    return (
        <div className="space-y-6 pb-8">
            <PageHeader
                title="Plans"
                description="Choose the plan that fits your workspace. Prices are per workspace - all seats included."
                icon={CreditCard}
            />

            {loadError ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                    {loadError}
                    <button
                        type="button"
                        onClick={load}
                        className="ml-3 font-medium underline underline-offset-4"
                    >
                        Try again
                    </button>
                </div>
            ) : null}

            {actionError ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                    {actionError}
                </div>
            ) : null}

            {loading ? (
                <>
                    <section className="rounded-xl border border-border bg-card p-4">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="mt-3 h-8 w-32" />
                        <Skeleton className="mt-3 h-4 w-64" />
                    </section>
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        <PlanCardSkeleton />
                        <PlanCardSkeleton />
                        <PlanCardSkeleton />
                        <PlanCardSkeleton />
                    </div>
                </>
            ) : (
                <>
                    <section className="rounded-xl border border-border bg-card p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="min-w-0">
                                <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                                    Current plan
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                                        {subscriptionStatusLabel(
                                            subscription.subscription_status,
                                        )}
                                    </span>
                                </h2>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    {subscription.subscription_status === "trialing" ? (
                                        <>
                                            {currentPlan
                                                ? `${currentPlan.display_name} trial - ${trialCountdownLabel(subscription.days_remaining)}.`
                                                : `Trial active - ${trialCountdownLabel(subscription.days_remaining)}.`}
                                        </>
                                    ) : (
                                        <>
                                            {currentPlan
                                                ? `${currentPlan.display_name} plan`
                                                : "Free plan"}
                                            {subscription.billing_email
                                                ? ` · billed to ${subscription.billing_email}`
                                                : ""}
                                        </>
                                    )}
                                </p>
                            </div>
                            {canManageBilling ? (
                                <Button
                                    variant="outline"
                                    onClick={handlePortal}
                                    disabled={portalPending}
                                >
                                    <ExternalLink
                                        aria-hidden="true"
                                        className="size-4"
                                    />
                                    {portalPending
                                        ? "Opening portal…"
                                        : "Manage billing"}
                                </Button>
                            ) : null}
                        </div>
                    </section>

                    <div className="flex items-center gap-2">
                        <div
                            role="group"
                            aria-label="Billing interval"
                            className="inline-flex rounded-lg border border-border bg-card p-0.5"
                        >
                            <button
                                type="button"
                                onClick={() => setInterval("month")}
                                aria-pressed={interval === "month"}
                                className={cn(
                                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                                    interval === "month"
                                        ? "bg-primary text-primary-foreground"
                                        : "text-muted-foreground hover:text-foreground",
                                )}
                            >
                                Monthly
                            </button>
                            <button
                                type="button"
                                onClick={() => setInterval("year")}
                                aria-pressed={interval === "year"}
                                className={cn(
                                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                                    interval === "year"
                                        ? "bg-primary text-primary-foreground"
                                        : "text-muted-foreground hover:text-foreground",
                                )}
                            >
                                Annual
                            </button>
                        </div>
                        <span className="text-xs text-muted-foreground">
                            {interval === "year" ? "Save ~17% · billed yearly" : "Billed monthly"}
                        </span>
                    </div>

                    {!canManageBilling ? (
                        <p className="text-sm text-muted-foreground">
                            Only the workspace owner can change the plan or open
                            billing. Ask your owner to sign in if you need an
                            upgrade.
                        </p>
                    ) : null}

                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        {plans.map((plan) => (
                            <PlanCard
                                key={plan.id}
                                plan={plan}
                                interval={interval}
                                isCurrent={subscription.plan_id === plan.id}
                                canCheckout={
                                    canManageBilling &&
                                    purchasablePlans(plans).some(
                                        (p) => p.id === plan.id,
                                    )
                                }
                                pending={
                                    pendingCheckout === `${plan.id}:${interval}`
                                }
                                onCheckout={handleCheckout}
                            />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
