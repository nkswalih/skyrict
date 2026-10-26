import type { Metadata } from "next";

import { BillingStep } from "@/features/onboarding/billing-step";

export const metadata: Metadata = {
    title: "Billing",
    description: "Step 6 of 7 - set up payment for your plan.",
};

export default async function BillingPage({
    searchParams,
}: {
    searchParams: Promise<{
        email?: string;
        vt?: string;
        tenantId?: string;
        slug?: string;
        plan?: string;
        interval?: string;
        currency?: string;
        checkout?: string;
    }>;
}) {
    const params = await searchParams;

    return (
        <div className="space-y-6">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-foreground">
                    Step 6 of 7 · Billing
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Set up billing
                </h1>
                <p className="text-sm text-muted-foreground">
                    {params.checkout === "cancelled"
                        ? "Payment was not completed. Choose how you&apos;d like to continue."
                        : "Add a payment method only if you pick a paid plan - Starter stays free."}
                </p>
            </div>

            <BillingStep
                email={params.email?.trim()}
                vt={params.vt?.trim()}
                tenantId={params.tenantId?.trim()}
                slug={params.slug?.trim()}
                plan={params.plan?.trim()}
                interval={params.interval?.trim()}
                currency={params.currency?.trim()}
                checkout={params.checkout?.trim()}
            />
        </div>
    );
}
