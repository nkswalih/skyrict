"use client";

import { Spinner } from "@/components/ui/spinner";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, CheckCheck, X } from "lucide-react";

import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    formatPriceForCurrency,
    resolvePlanPrice,
} from "@/features/billing/billing-utils";
import type {
    BillingCurrency,
    BillingInterval,
    BillingPlan,
    BillingPlanId,
} from "@/lib/api/billing-api";
import { ApiError, getSignupPlans } from "@/lib/api/auth-api";
import { BETA_MARKET_LABEL } from "@/lib/billing/currency";
import { AuthButton } from "@/lib/auth/AuthButton";
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

/**
 * Tiered "included" emphasis: flagship rows/modules render a double-tick
 * (CheckCheck) to signal stronger inclusion. Starter stays single-tick,
 * Professional gets a minimal set, Business more, Enterprise everything.
 */
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

/** Tabular feature matrix: grouped sections with per-plan cells. */
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

/** Highlight the mid-tier paid plan, the way AWS/Linear mark their popular tier. */
function isPopularPlan(plan: BillingPlan): boolean {
    return plan.id === "professional";
}

function PlanModuleChips({
    plan,
    max = 3,
    compact = false,
}: {
    plan: BillingPlan;
    max?: number;
    compact?: boolean;
}) {
    const modules = plan.features.modules;
    const shown = modules.slice(0, max);
    const rest = modules.length - shown.length;

    return (
        <ul
            className={cn(
                "flex flex-wrap gap-1",
                compact ? "gap-1" : "gap-1.5",
            )}
        >
            {shown.map((module) => (
                <li
                    key={module}
                    className={cn(
                        "rounded-md border border-border bg-background font-mono text-muted-foreground",
                        compact
                            ? "px-1.5 py-0.5 text-[10px]"
                            : "px-2 py-1 text-[11px]",
                    )}
                >
                    {module}
                </li>
            ))}
            {rest > 0 ? (
                <li
                    className={cn(
                        "rounded-md border border-border bg-background text-muted-foreground",
                        compact
                            ? "px-1.5 py-0.5 text-[10px]"
                            : "px-2 py-1 text-[11px]",
                    )}
                >
                    +{rest} more
                </li>
            ) : null}
        </ul>
    );
}

function PlanCard({
    plan,
    billing,
    currency,
    selected,
    onSelect,
}: {
    plan: BillingPlan;
    billing: BillingInterval;
    currency: BillingCurrency;
    selected: boolean;
    onSelect: () => void;
}) {
    const resolved = resolvePlanPrice(plan, currency, billing);
    const price = resolved.cents;
    const isPaid = price !== null && price > 0;
    const popular = isPopularPlan(plan);
    const isEnterprise = plan.id === "enterprise";
    const limitRows = planLimitRows(plan);

    const ctaLabel = selected
        ? isEnterprise
            ? "Contact sales"
            : "Selected"
        : "Get started";

    const ctaClass =
        "flex w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/30";

    return (
        <div
            className={cn(
                "relative flex flex-col rounded-xl border bg-card p-4 transition-all",
                selected
                    ? "border-primary shadow-[0_0_0_1px] shadow-primary/20"
                    : "border-border hover:border-primary/50",
            )}
        >
            {popular ? (
                <span className="absolute -top-2.5 left-4 rounded-full bg-primary px-2.5 py-0.5 text-[11px] font-semibold text-primary-foreground">
                    Most popular
                </span>
            ) : null}

            <button
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={onSelect}
                className="flex flex-1 flex-col text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/30 rounded-lg"
            >
                <span className="flex items-center justify-between gap-2">
                    <span className="font-display text-sm font-semibold text-foreground">
                        {plan.display_name}
                    </span>
                    <span
                        aria-hidden="true"
                        className={cn(
                            "flex size-4 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                            selected
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-border",
                        )}
                    >
                        {selected ? (
                            <Check aria-hidden="true" className="size-2.5" />
                        ) : null}
                    </span>
                </span>

                <span className="mt-2 flex flex-wrap items-baseline gap-x-1.5">
                    <span className="font-display text-3xl font-semibold tracking-tight text-foreground">
                        {formatPriceForCurrency(
                            resolved.cents,
                            resolved.currency,
                        )}
                    </span>
                    {isPaid ? (
                        <span className="text-xs text-muted-foreground">
                            / month
                        </span>
                    ) : null}
                </span>

                <span className="mt-0.5 text-[11px] text-muted-foreground">
                    {isPaid
                        ? billing === "year"
                            ? resolved.billedInUsd
                                ? "billed yearly · charged in USD"
                                : "billed yearly"
                            : resolved.billedInUsd
                              ? "billed monthly · charged in USD"
                              : "billed monthly"
                        : plan.id === "enterprise"
                          ? "custom contract, invoiced"
                          : "free forever"}
                </span>

                <ul className="mt-3 space-y-1.5 text-xs text-muted-foreground">
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

                <span className="mt-3 block">
                    <PlanModuleChips plan={plan} compact />
                </span>
            </button>

            <div className="mt-auto flex flex-col gap-1.5 pt-4">
                <PlanDetailsDialog
                    plan={plan}
                    billing={billing}
                    currency={currency}
                    onSelect={onSelect}
                />

                {isEnterprise && selected ? (
                    <a
                        href="mailto:sales@skyrict.in?subject=Enterprise plan"
                        className={cn(
                            ctaClass,
                            "border-primary bg-primary text-primary-foreground",
                        )}
                    >
                        {ctaLabel}
                    </a>
                ) : (
                    <button
                        type="button"
                        aria-pressed={selected}
                        onClick={onSelect}
                        className={cn(
                            ctaClass,
                            selected
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
                        )}
                    >
                        {selected ? (
                            <Check aria-hidden="true" className="size-4" />
                        ) : null}
                        {ctaLabel}
                    </button>
                )}
            </div>
        </div>
    );
}

function PlanDetailsDialog({
    plan,
    billing,
    currency,
    onSelect,
}: {
    plan: BillingPlan;
    billing: BillingInterval;
    currency: BillingCurrency;
    onSelect: () => void;
}) {
    const resolved = resolvePlanPrice(plan, currency, billing);
    const price = resolved.cents;
    const isPaid = price !== null && price > 0;
    const popular = isPopularPlan(plan);
    const limitRows = planLimitRows(plan);

    return (
        <Dialog>
            <DialogTrigger className="w-full text-center text-xs font-medium text-primary underline-offset-4 hover:underline outline-none focus-visible:ring-3 focus-visible:ring-ring/30 rounded-md py-1">
                View full details
            </DialogTrigger>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {plan.display_name}
                        {popular ? (
                            <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-primary-foreground">
                                Most popular
                            </span>
                        ) : null}
                    </DialogTitle>
                    <DialogDescription className="sr-only">
                        Full details for the {plan.display_name} plan.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="font-display text-4xl font-semibold tracking-tight text-foreground">
                            {formatPriceForCurrency(
                                resolved.cents,
                                resolved.currency,
                            )}
                        </span>
                        {isPaid ? (
                            <span className="text-sm text-muted-foreground">
                                / month
                            </span>
                        ) : null}
                        <span className="w-full text-xs text-muted-foreground">
                            {isPaid
                                ? billing === "year"
                                    ? resolved.billedInUsd
                                        ? "Billed yearly. Annual price per month shown. Charged in USD."
                                        : "Billed yearly. Annual price per month shown."
                                    : resolved.billedInUsd
                                      ? "Billed monthly. Cancel anytime. Charged in USD."
                                      : "Billed monthly. Cancel anytime."
                                : plan.id === "enterprise"
                                  ? "Custom contract, invoiced annually."
                                  : "Free forever. No card required."}
                        </span>
                    </div>

                    <div className="overflow-hidden rounded-lg border border-border">
                        <dl className="divide-y divide-border text-sm">
                            {limitRows.map((row) => (
                                <div
                                    key={row.label}
                                    className="flex items-center justify-between gap-3 px-3 py-2"
                                >
                                    <dt className="text-xs font-medium text-muted-foreground">
                                        {row.label}
                                    </dt>
                                    <dd className="text-xs font-medium text-foreground">
                                        {row.value}
                                    </dd>
                                </div>
                            ))}
                        </dl>
                    </div>

                    <div className="space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">
                            Included modules
                        </p>
                        <ul className="space-y-1.5">
                            {plan.features.modules.map((module) => (
                                <li
                                    key={module}
                                    className="flex items-start gap-1.5 text-xs text-muted-foreground"
                                >
                                    {isDoubleIncluded(plan, module) ? (
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
                                    <span>{module}</span>
                                </li>
                            ))}
                        </ul>
                    </div>

                    <button
                        type="button"
                        onClick={onSelect}
                        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                    >
                        Get started with {plan.display_name}
                    </button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function CompareDialog({
    plans,
    currency,
    selected,
    onSelect,
}: {
    plans: BillingPlan[];
    currency: BillingCurrency;
    selected: BillingPlanId;
    onSelect: (planId: BillingPlanId) => void;
}) {
    return (
        <Dialog>
            <DialogTrigger className="text-sm font-medium text-primary underline-offset-4 hover:underline outline-none focus-visible:ring-3 focus-visible:ring-ring/30 rounded-md">
                Compare plans
            </DialogTrigger>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-4xl">
                <DialogHeader>
                    <DialogTitle>Compare plans</DialogTitle>
                    <DialogDescription>
                        All plans include the core Skyrict platform. Prices
                        shown in {currency.toUpperCase()}.
                    </DialogDescription>
                </DialogHeader>

                <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-sm">
                        <thead>
                            <tr>
                                <th className="border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
                                    Feature
                                </th>
                                {plans.map((plan) => {
                                    const isPlanSelected = selected === plan.id;
                                    const popular = isPopularPlan(plan);
                                    return (
                                        <th
                                            key={plan.id}
                                            className={cn(
                                                "border-b border-border px-3 py-2 text-center align-top",
                                                popular
                                                    ? "border-primary/40 bg-primary/5"
                                                    : "",
                                                isPlanSelected
                                                    ? "bg-primary/5"
                                                    : "",
                                            )}
                                        >
                                            <span className="flex flex-col items-center gap-1">
                                                {popular ? (
                                                    <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                                                        Most popular
                                                    </span>
                                                ) : null}
                                                <span className="font-display text-sm font-semibold text-foreground">
                                                    {plan.display_name}
                                                </span>
                                                {isPlanSelected ? (
                                                    <span className="text-[10px] font-medium text-primary">
                                                        Selected
                                                    </span>
                                                ) : null}
                                            </span>
                                        </th>
                                    );
                                })}
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td className="border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
                                    Monthly price
                                </td>
                                {plans.map((plan) => (
                                    <td
                                        key={plan.id}
                                        className={cn(
                                            "border-b border-border px-3 py-2 text-center text-xs font-medium text-foreground",
                                            isPopularPlan(plan)
                                                ? "bg-primary/5"
                                                : "",
                                        )}
                                    >
                                        {formatPriceForCurrency(
                                            resolvePlanPrice(
                                                plan,
                                                currency,
                                                "month",
                                            ).cents,
                                            resolvePlanPrice(
                                                plan,
                                                currency,
                                                "month",
                                            ).currency,
                                        )}
                                    </td>
                                ))}
                            </tr>
                            <tr>
                                <td className="border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
                                    Annual / mo
                                </td>
                                {plans.map((plan) => (
                                    <td
                                        key={plan.id}
                                        className={cn(
                                            "border-b border-border px-3 py-2 text-center text-xs font-medium text-foreground",
                                            isPopularPlan(plan)
                                                ? "bg-primary/5"
                                                : "",
                                        )}
                                    >
                                        {formatPriceForCurrency(
                                            resolvePlanPrice(
                                                plan,
                                                currency,
                                                "year",
                                            ).cents,
                                            resolvePlanPrice(
                                                plan,
                                                currency,
                                                "year",
                                            ).currency,
                                        )}
                                    </td>
                                ))}
                            </tr>
                            {COMPARISON_MATRIX.map(({ section, rows }) => (
                                <Fragment key={section}>
                                    <tr>
                                        <td
                                            colSpan={plans.length + 1}
                                            className="border-b border-border bg-muted/40 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                                        >
                                            {section}
                                        </td>
                                    </tr>
                                    {rows.map(({ label, value }) => (
                                        <tr key={label}>
                                            <td className="border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
                                                {label}
                                            </td>
                                            {plans.map((plan) => {
                                                const cell = value(plan);
                                                const popular =
                                                    isPopularPlan(plan);
                                                return (
                                                    <td
                                                        key={plan.id}
                                                        className={cn(
                                                            "border-b border-border px-3 py-2 text-center text-xs text-foreground",
                                                            popular
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
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="flex flex-wrap justify-end gap-2">
                    {plans.map((plan) => (
                        <button
                            key={plan.id}
                            type="button"
                            onClick={() => onSelect(plan.id as BillingPlanId)}
                            className={cn(
                                "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
                                selected === plan.id
                                    ? "border-primary bg-primary text-primary-foreground"
                                    : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
                            )}
                        >
                            Get started with {plan.display_name}
                        </button>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function PlanStep({
    email,
    vt,
    tenantId,
    slug,
    initialCurrency = "usd",
    initialCountry = null,
    marketAvailable = true,
}: {
    email: string;
    vt: string;
    tenantId?: string;
    slug?: string;
    initialCurrency?: BillingCurrency;
    initialCountry?: string | null;
    /** False when the resolved region is outside the beta (or pricing pending). */
    marketAvailable?: boolean;
}) {
    const router = useRouter();
    const [billing, setBilling] = useState<BillingInterval>("month");
    // Currency is 100% server-resolved (geo) — no manual override exists.
    const [currency] = useState<BillingCurrency>(initialCurrency);
    const [plans, setPlans] = useState<BillingPlan[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [selected, setSelected] = useState<BillingPlanId>("starter");

    useEffect(() => {
        let cancelled = false;
        getSignupPlans()
            .then((catalog) => {
                if (cancelled) return;
                setPlans(catalog);
                if (!catalog.some((plan) => plan.id === selected)) {
                    setSelected("starter");
                }
            })
            .catch((error: unknown) => {
                if (cancelled) return;
                setLoadError(
                    error instanceof ApiError
                        ? error.message
                        : "Could not load plans. Try again.",
                );
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
        // The default selection is stable; the catalog effect only runs once.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const selectedPlan = useMemo(
        () => plans.find((plan) => plan.id === selected),
        [plans, selected],
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-10">
                <Spinner
                    aria-hidden="true"
                    className="size-5 text-primary"
                />
                <span className="sr-only">Loading plans</span>
            </div>
        );
    }

    if (loadError) {
        return (
            <div className="space-y-4">
                <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    {loadError}
                </p>
                <AuthButton
                    type="button"
                    className="w-full"
                    onClick={() =>
                        router.push(
                            `/signup/security?${new URLSearchParams({ email, vt }).toString()}`,
                        )
                    }
                >
                    Back to security
                </AuthButton>
            </div>
        );
    }

    if (!marketAvailable) {
        // Beta region gate: no plan cards, no USD pricing shown as-if valid.
        // Checkout is additionally rejected server-side (defense in depth).
        return (
            <div className="mx-auto w-full max-w-lg space-y-4 text-center">
                <div className="space-y-2 rounded-lg border border-border bg-card px-4 py-5">
                    <h2 className="font-display text-lg font-semibold text-foreground">
                        Not yet available in your region
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Skyrict beta is currently available in{" "}
                        {BETA_MARKET_LABEL}. We&apos;re expanding soon — leave
                        your email and we&apos;ll notify you.
                    </p>
                </div>
                <AuthButton
                    type="button"
                    className="w-full"
                    onClick={() =>
                        router.push(
                            `/signup/security?${new URLSearchParams({ email, vt }).toString()}`,
                        )
                    }
                >
                    Back to security
                </AuthButton>
            </div>
        );
    }

    function handleContinue() {
        // If the URL already carries an org context, the tenant exists and we
        // are in the change-plan loop from Billing - go straight back there.
        // Otherwise the Plan step runs before organization creation, so the
        // chosen plan+interval travel in the URL to the Organization step.
        const next = new URLSearchParams({
            email,
            vt,
            plan: selected,
            interval: billing,
            currency,
        });
        if (tenantId && slug) {
            next.set("tenantId", tenantId);
            next.set("slug", slug);
        }
        router.push(
            tenantId && slug
                ? `/signup/billing?${next.toString()}`
                : `/signup/organization?${next.toString()}`,
        );
    }

    const isEnterprise = selected === "enterprise";

    return (
        <div className="space-y-5">
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
                <CompareDialog
                    plans={plans}
                    currency={currency}
                    selected={selected}
                    onSelect={(planId) => setSelected(planId)}
                />
            </div>

            <div
                className="grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-4"
                role="radiogroup"
                aria-label="Select a plan"
            >
                {plans.map((plan) => (
                    <PlanCard
                        key={plan.id}
                        plan={plan}
                        billing={billing}
                        currency={currency}
                        selected={selected === (plan.id as BillingPlanId)}
                        onSelect={() => setSelected(plan.id as BillingPlanId)}
                    />
                ))}
            </div>

            <div className="mx-auto w-full max-w-lg space-y-3">
                <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-primary/40 bg-primary/5 px-3 py-2">
                    <Check className="size-4 text-primary" />
                    <span className="text-xs font-medium text-foreground">
                        14-day free trial on all paid plans · no credit card
                        required
                    </span>
                </div>

                <p className="text-center text-xs text-muted-foreground">
                    {isEnterprise
                        ? initialCountry
                            ? `Custom pricing, SSO/SAML, and dedicated infrastructure. Region: ${initialCountry}.`
                            : "Custom pricing, SSO/SAML, and dedicated infrastructure."
                        : `Switch or cancel anytime. Prices shown in ${currency.toUpperCase()}.`}
                </p>

                <AuthButton
                    type="button"
                    className="w-full"
                    onClick={handleContinue}
                >
                    Continue with {selectedPlan?.display_name ?? "Starter"}
                </AuthButton>
            </div>
        </div>
    );
}

export { PlanStep };
