"use client";

import { Fragment, useMemo, useEffect, useState } from "react";
import Link from "next/link";
import { Check, CheckCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/ui/error-panel";
import {
    formatPriceForCurrency,
    resolvePlanPrice,
} from "@/features/billing/billing-utils";
import { getSignupPlans } from "@/lib/api/auth-api";
import type {
    BillingCurrency,
    BillingInterval,
    BillingPlan,
} from "@/lib/api/billing-api";
import { describeLoadError } from "@/lib/api/error-messages";
import { BETA_MARKET_LABEL } from "@/lib/billing/currency";
import { cn } from "@/lib/utils";

function formatUsers(plan: BillingPlan): string {
    if (plan.features.max_users === null) return "Unlimited users";
    return plan.features.max_users === 1
        ? "1 user"
        : `Up to ${plan.features.max_users} users`;
}

function formatCredits(plan: BillingPlan): string {
    if (plan.features.ai_credits_monthly === null) return "Custom AI credits";
    return `${plan.features.ai_credits_monthly.toLocaleString()} AI credits / month`;
}

function formatAgents(plan: BillingPlan): string {
    if (plan.features.max_agents === null) return "Unlimited agents";
    return plan.features.max_agents === 1
        ? "1 agent"
        : `${plan.features.max_agents} agents`;
}

function planLimitRows(plan: BillingPlan): { label: string; value: string }[] {
    return [
        ...(plan.features.max_users !== null
            ? [{ label: "Users", value: formatUsers(plan) }]
            : []),
        { label: "AI credits", value: formatCredits(plan) },
        { label: "Agents", value: formatAgents(plan) },
    ];
}

/** Tiered "included" emphasis, matching the signup plan step. */
function isDoubleIncluded(plan: BillingPlan, token: string): boolean {
    const v = token.toLowerCase();
    switch (plan.id) {
        case "enterprise":
            return true;
        case "business":
            return /agents|credits|autopilot|permissions|api access|signal/.test(
                v,
            );
        case "professional":
            return /credits|all 5 signal/.test(v);
        default:
            return false;
    }
}

function formattedCreditBudgets(plan: BillingPlan): string {
    if (plan.features.ai_credits_monthly === null) return "Custom";
    return plan.features.ai_credits_monthly.toLocaleString();
}

type MatrixCell = string | boolean;

function hasModule(plan: BillingPlan, token: string): boolean {
    return plan.features.modules.some((module) =>
        module.toLowerCase().includes(token.toLowerCase()),
    );
}

/** Feature matrix rows; the catalog is authoritative, never hardcoded here. */
const COMPARISON_MATRIX: {
    section: string;
    rows: { label: string; value: (plan: BillingPlan) => MatrixCell }[];
}[] = [
    {
        section: "Usage limits",
        rows: [
            {
                label: "AI credits / month",
                value: formattedCreditBudgets,
            },
            { label: "AI agents", value: formatAgents },
            {
                label: "Market signal sources",
                value: (p) =>
                    hasModule(p, "all 5 signal")
                        ? "All 5"
                        : hasModule(p, "signal source")
                          ? "1"
                          : "None",
            },
        ],
    },
    {
        section: "AI & automation",
        rows: [
            {
                label: "Agent autopilot (auto-actions)",
                value: (p) => hasModule(p, "autopilot"),
            },
        ],
    },
    {
        section: "Security & compliance",
        rows: [
            {
                label: "Advanced role-based permissions",
                value: (p) => hasModule(p, "permissions"),
            },
            {
                label: "SSO / SAML",
                value: (p) => hasModule(p, "sso"),
            },
        ],
    },
    {
        section: "Integrations",
        rows: [
            {
                label: "Developer API access",
                value: (p) => hasModule(p, "api access"),
            },
            {
                label: "Custom data integrations",
                value: (p) => hasModule(p, "custom data"),
            },
        ],
    },
    {
        section: "Support & infrastructure",
        rows: [
            {
                label: "Dedicated infrastructure",
                value: (p) => hasModule(p, "dedicated"),
            },
        ],
    },
];

function isPopularPlan(plan: BillingPlan): boolean {
    return plan.id === "professional";
}

function moduleChips(plan: BillingPlan, max = 3) {
    const modules = plan.features.modules;
    const shown = modules.slice(0, max);
    const rest = modules.length - shown.length;
    return (
        <ul aria-label="Included modules" className="flex flex-wrap gap-1">
            {shown.map((module) => (
                <li
                    key={module}
                    className="rounded-md border border-border bg-background px-2 py-1 font-mono text-[11px] text-muted-foreground"
                >
                    {module}
                </li>
            ))}
            {rest > 0 ? (
                <li className="rounded-md border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground">
                    +{rest} more
                </li>
            ) : null}
        </ul>
    );
}

function planCta(plan: BillingPlan): { label: string; href: string } {
    switch (plan.id) {
        case "starter":
            return { label: "Start free", href: "/signup" };
        case "enterprise":
            return {
                label: "Contact sales",
                href: "mailto:sales@skyrict.in?subject=Enterprise plan",
            };
        default:
            return { label: "Start 14-day trial", href: "/signup" };
    }
}

function PlanCardSkeleton() {
    return (
        <div className="animate-pulse space-y-3 rounded-2xl border border-border bg-card p-5">
            <div className="h-4 w-24 rounded bg-muted" />
            <div className="h-9 w-28 rounded bg-muted" />
            <div className="h-3 w-40 rounded bg-muted" />
            <div className="space-y-2 pt-2">
                <div className="h-3 w-full rounded bg-muted" />
                <div className="h-3 w-3/4 rounded bg-muted" />
                <div className="h-3 w-2/3 rounded bg-muted" />
            </div>
            <div className="h-9 w-full rounded bg-muted pt-2" />
        </div>
    );
}

function PlanCard({
    plan,
    billing,
    currency,
    available,
}: {
    plan: BillingPlan;
    billing: BillingInterval;
    currency: BillingCurrency;
    available: boolean;
}) {
    const resolved = available
        ? resolvePlanPrice(plan, currency, billing)
        : null;
    const price = resolved?.cents ?? null;
    const isPaid = price !== null && price > 0;
    const popular = isPopularPlan(plan);
    const limitRows = planLimitRows(plan);
    const cta = planCta(plan);
    const externalCta =
        typeof cta.href === "string" && cta.href.startsWith("mailto:");

    return (
        <article
            className={cn(
                "relative flex h-full flex-col rounded-2xl border bg-card p-5 transition-all sm:p-6",
                popular
                    ? "border-primary shadow-[0_0_0_1px] shadow-primary/20"
                    : "border-border hover:border-primary/50",
            )}
        >
            {popular ? (
                <span className="absolute -top-2.5 left-5 rounded-full bg-primary px-2.5 py-0.5 text-[11px] font-semibold text-primary-foreground">
                    Most popular
                </span>
            ) : null}

            <h3 className="font-display text-sm font-semibold text-foreground">
                {plan.display_name}
            </h3>

            <div className="mt-2 flex flex-wrap items-baseline gap-x-1.5">
                <span className="font-display text-4xl font-semibold tracking-tight text-foreground">
                    {resolved
                        ? formatPriceForCurrency(price, resolved.currency)
                        : plan.id === "starter"
                          ? formatPriceForCurrency(0, currency)
                          : plan.id === "enterprise"
                            ? "Custom"
                            : "Per region"}
                </span>
                {isPaid ? (
                    <span className="text-xs text-muted-foreground">
                        / month
                    </span>
                ) : null}
            </div>
            <span className="mt-0.5 text-[11px] text-muted-foreground">
                {resolved
                    ? isPaid
                        ? billing === "year"
                            ? resolved.billedInUsd
                                ? "billed yearly · charged in USD"
                                : "billed yearly"
                            : resolved.billedInUsd
                              ? "billed monthly · charged in USD"
                              : "billed monthly"
                        : plan.id === "enterprise"
                          ? "custom contract, invoiced"
                          : "free forever"
                    : plan.id === "starter"
                      ? "free forever"
                      : plan.id === "enterprise"
                        ? "custom contract, invoiced"
                        : "payments are not open in your region yet"}
            </span>

            <ul className="mt-4 space-y-1.5 text-xs text-muted-foreground">
                {limitRows.map((row) => (
                    <li
                        key={row.label}
                        className="flex items-start gap-1.5"
                    >
                        {isDoubleIncluded(plan, row.label) ? (
                            <CheckCheck
                                aria-label="Included with emphasis"
                                className="mt-0.5 size-3 shrink-0 text-primary"
                            />
                        ) : (
                            <Check
                                aria-hidden="true"
                                className="mt-0.5 size-3 shrink-0 text-primary"
                            />
                        )}
                        <span>{row.value}</span>
                    </li>
                ))}
            </ul>

            <div className="mt-3">{moduleChips(plan)}</div>

            <div className="mt-auto pt-5">
                {externalCta ? (
                    <a
                        href={cta.href}
                        className={cn(
                            "flex w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
                            popular
                                ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
                                : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
                        )}
                    >
                        {cta.label}
                    </a>
                ) : (
                    <Button
                        size="lg"
                        variant={popular ? "default" : "outline"}
                        className="w-full"
                        asChild
                    >
                        <Link href={cta.href}>{cta.label}</Link>
                    </Button>
                )}
            </div>
        </article>
    );
}

function PricingTiers({
    currency,
    available,
}: {
    currency: BillingCurrency;
    /** False when the detected region is outside the beta or pricing pending. */
    available: boolean;
}) {
    const [billing, setBilling] = useState<BillingInterval>("month");
    const [plans, setPlans] = useState<BillingPlan[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<unknown>(null);
    const [retrying, setRetrying] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const load = () => {
            setLoading(true);
            setLoadError(null);
            getSignupPlans()
                .then((catalog) => {
                    if (cancelled) return;
                    setPlans(catalog);
                })
                .catch((error: unknown) => {
                    if (cancelled) return;
                    setLoadError(error);
                })
                .finally(() => {
                    if (!cancelled) setLoading(false);
                });
        };
        load();
        return () => {
            cancelled = true;
        };
    }, []);

    /** Retry is safe here: loading the catalog is a read-only GET. */
    async function handleRetry() {
        setRetrying(true);
        setLoadError(null);
        try {
            setPlans(await getSignupPlans());
        } catch (error) {
            setLoadError(error);
        } finally {
            setRetrying(false);
            setLoading(false);
        }
    }

    const loadPresentation = useMemo(
        () =>
            loadError
                ? describeLoadError(loadError, {
                      title: "Plans are temporarily unavailable",
                      retryableMessage:
                          "We couldn't load the latest plans right now. Take a moment and try again.",
                  })
                : null,
        [loadError],
    );

    return (
        <div className="space-y-10">
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3">
                <div className="flex items-center gap-3">
                    <div
                        role="group"
                        aria-label="Billing interval"
                        className="inline-flex rounded-lg border border-border bg-card p-0.5"
                    >
                        <button
                            type="button"
                            onClick={() => setBilling("month")}
                            aria-pressed={billing === "month"}
                            className={cn(
                                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                                billing === "month"
                                    ? "bg-primary text-primary-foreground"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            Monthly
                        </button>
                        <button
                            type="button"
                            onClick={() => setBilling("year")}
                            aria-pressed={billing === "year"}
                            className={cn(
                                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                                billing === "year"
                                    ? "bg-primary text-primary-foreground"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            Annual
                        </button>
                    </div>
                    <span className="text-xs text-muted-foreground">
                        {billing === "year"
                            ? "Save ~17% · billed yearly"
                            : "Billed monthly"}
                    </span>
                </div>
                <span className="text-xs text-muted-foreground">
                    Prices in {currency.toUpperCase()}, fixed per currency
                </span>
            </div>

            {!available ? (
                <div className="mx-auto w-full max-w-2xl space-y-2 rounded-2xl border border-border bg-card px-5 py-4 text-center">
                    <h2 className="font-display text-base font-semibold text-foreground">
                        Not yet available in your region
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Skyrict beta is currently available in{" "}
                        {BETA_MARKET_LABEL}. Create an account any time;
                        checkout opens in your region as the beta expands.
                    </p>
                </div>
            ) : null}

            {loading ? (
                <div
                    className="grid items-stretch gap-4 sm:grid-cols-2 lg:grid-cols-4"
                    aria-busy="true"
                >
                    <PlanCardSkeleton />
                    <PlanCardSkeleton />
                    <PlanCardSkeleton />
                    <PlanCardSkeleton />
                    <span className="sr-only">Loading pricing</span>
                </div>
            ) : loadError && loadPresentation ? (
                <ErrorPanel
                    title={loadPresentation.title}
                    message={loadPresentation.message}
                    onRetry={
                        loadPresentation.retryable ? handleRetry : undefined
                    }
                    retryLabel={retrying ? "Loading…" : "Retry"}
                    secondary={
                        <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="text-muted-foreground"
                        >
                            <Link href="/">Continue browsing</Link>
                        </Button>
                    }
                />
            ) : plans.length > 0 ? (
                <>
                    <div className="grid items-stretch gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        {plans.map((plan) => (
                            <PlanCard
                                key={plan.id}
                                plan={plan}
                                billing={billing}
                                currency={currency}
                                available={available}
                            />
                        ))}
                    </div>

                    <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-primary/40 bg-primary/5 px-3 py-2">
                        <Check className="size-4 text-primary" />
                        <span className="text-xs font-medium text-foreground">
                            14-day free trial on all paid plans · no credit card
                            required
                        </span>
                    </div>

                    <div className="overflow-hidden rounded-2xl border border-border bg-card">
                        <div className="overflow-x-auto">
                            <table className="w-full border-collapse text-left text-sm">
                                <caption className="px-5 pt-5 text-left font-display text-lg font-semibold text-foreground">
                                    Compare plans
                                </caption>
                                <thead>
                                    <tr>
                                        <th className="border-b border-border px-5 py-2 text-xs font-medium text-muted-foreground">
                                            Feature
                                        </th>
                                        {plans.map((plan) => (
                                            <th
                                                key={plan.id}
                                                scope="col"
                                                className={cn(
                                                    "border-b border-border px-3 py-2 text-center align-top text-xs font-medium",
                                                    isPopularPlan(plan)
                                                        ? "border-primary/40 bg-primary/5"
                                                        : "",
                                                )}
                                            >
                                                <span className="flex flex-col items-center gap-1">
                                                    {isPopularPlan(plan) ? (
                                                        <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                                                            Most popular
                                                        </span>
                                                    ) : null}
                                                    <span className="font-display text-sm font-semibold text-foreground">
                                                        {plan.display_name}
                                                    </span>
                                                </span>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td className="border-b border-border px-5 py-2 text-xs font-medium text-muted-foreground">
                                            Monthly price
                                        </td>
                                        {plans.map((plan) => {
                                            const m = available
                                                ? resolvePlanPrice(
                                                      plan,
                                                      currency,
                                                      "month",
                                                  )
                                                : null;
                                            return (
                                                <td
                                                    key={plan.id}
                                                    className={cn(
                                                        "border-b border-border px-3 py-2 text-center text-xs font-medium text-foreground",
                                                        isPopularPlan(plan)
                                                            ? "bg-primary/5"
                                                            : "",
                                                    )}
                                                >
                                                    {m
                                                        ? formatPriceForCurrency(
                                                              m.cents,
                                                              m.currency,
                                                          )
                                                        : "By region"}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                    <tr>
                                        <td className="border-b border-border px-5 py-2 text-xs font-medium text-muted-foreground">
                                            Annual, per month
                                        </td>
                                        {plans.map((plan) => {
                                            const a = available
                                                ? resolvePlanPrice(
                                                      plan,
                                                      currency,
                                                      "year",
                                                  )
                                                : null;
                                            return (
                                                <td
                                                    key={plan.id}
                                                    className={cn(
                                                        "border-b border-border px-3 py-2 text-center text-xs font-medium text-foreground",
                                                        isPopularPlan(plan)
                                                            ? "bg-primary/5"
                                                            : "",
                                                    )}
                                                >
                                                    {a
                                                        ? formatPriceForCurrency(
                                                              a.cents,
                                                              a.currency,
                                                          )
                                                        : "By region"}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                    {COMPARISON_MATRIX.map(
                                        ({ section, rows }) => (
                                            <Fragment key={section}>
                                                <tr>
                                                    <td
                                                        colSpan={plans.length + 1}
                                                        className="border-b border-border bg-muted/40 px-5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                                                    >
                                                        {section}
                                                    </td>
                                                </tr>
                                                {rows.map(({ label, value }) => (
                                                    <tr key={label}>
                                                        <td className="border-b border-border px-5 py-2 text-xs font-medium text-muted-foreground">
                                                            {label}
                                                        </td>
                                                        {plans.map((plan) => {
                                                            const cell = value(
                                                                plan,
                                                            );
                                                            return (
                                                                <td
                                                                    key={plan.id}
                                                                    className={cn(
                                                                        "border-b border-border px-3 py-2 text-center text-xs text-foreground",
                                                                        isPopularPlan(
                                                                            plan,
                                                                        )
                                                                            ? "bg-primary/5"
                                                                            : "",
                                                                    )}
                                                                >
                                                                    {typeof cell ===
                                                                    "boolean" ? (
                                                                        <span
                                                                            className={cn(
                                                                                "inline-flex items-center gap-1 text-xs font-medium",
                                                                                cell
                                                                                    ? "text-primary"
                                                                                    : "text-muted-foreground",
                                                                            )}
                                                                            aria-label={
                                                                                cell
                                                                                    ? isDoubleIncluded(
                                                                                          plan,
                                                                                          label,
                                                                                      )
                                                                                        ? "Included with emphasis"
                                                                                        : "Included"
                                                                                    : "Not included"
                                                                            }
                                                                        >
                                                                            {cell ? (
                                                                                isDoubleIncluded(
                                                                                    plan,
                                                                                    label,
                                                                                ) ? (
                                                                                    <CheckCheck className="size-4" />
                                                                                ) : (
                                                                                    <Check className="size-4" />
                                                                                )
                                                                            ) : (
                                                                                <X className="size-4" />
                                                                            )}
                                                                        </span>
                                                                    ) : (
                                                                        <span className="text-xs font-medium text-foreground">
                                                                            {cell}
                                                                        </span>
                                                                    )}
                                                                </td>
                                                            );
                                                        })}
                                                    </tr>
                                                ))}
                                            </Fragment>
                                        ),
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            ) : null}
        </div>
    );
}

export { PricingTiers };