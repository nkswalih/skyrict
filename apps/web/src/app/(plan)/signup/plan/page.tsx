import type { Metadata } from "next";
import Link from "next/link";

import { PlanStep } from "@/features/onboarding/plan-step";
import { AuthButton } from "@/lib/auth/AuthButton";
import { resolvePricingContext } from "@/lib/server/geo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
    title: "Choose a plan",
    description: "Step 4 of 7 - pick the plan that fits your business.",
};

export default async function PlanPage({
    searchParams,
}: {
    searchParams: Promise<{
        email?: string;
        vt?: string;
        tenantId?: string;
        slug?: string;
    }>;
}) {
    const [params, pricing] = await Promise.all([
        searchParams,
        resolvePricingContext(),
    ]);
    const email = params.email?.trim();
    const vt = params.vt?.trim();
    const tenantId = params.tenantId?.trim();
    const slug = params.slug?.trim();

    if (!email || !vt) {
        return (
            <div className="space-y-4 text-center">
                <div className="space-y-2">
                    <h1 className="font-display text-2xl font-semibold text-foreground">
                        Session expired
                    </h1>
                    <p className="text-sm text-muted-foreground">
                        Your onboarding session is missing. Restart the flow to
                        continue.
                    </p>
                </div>
                <Link href="/signup" className="block">
                    <AuthButton className="size-10 justify-self-end w-full" variant="brand" size="icon-lg">Start over</AuthButton>
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <div className="space-y-1.5 text-center">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-foreground">
                    Step 4 of 7 · Plan
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Choose your plan
                </h1>
                <p className="text-sm text-muted-foreground">
                    Start free and upgrade as your business grows. You can
                    change plans anytime.
                </p>
            </div>

            <PlanStep
                email={email}
                vt={vt}
                tenantId={tenantId}
                slug={slug}
                initialCurrency={pricing.currency}
                initialCountry={pricing.country}
                marketAvailable={pricing.available}
            />
        </div>
    );
}
