import type { Metadata } from "next";

import { ReviewStep } from "@/features/onboarding/review-step";

export const metadata: Metadata = {
    title: "Review your setup",
    description: "Step 7 of 7 - confirm your workspace and plan.",
};

export default async function ReviewPage({
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
                    Step 7 of 7 · Review
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    You&apos;re almost there
                </h1>
                <p className="text-sm text-muted-foreground">
                    {params.checkout === "success"
                        ? "Payment received - confirm the details and enter your workspace."
                        : "Confirm your details and finish onboarding."}
                </p>
            </div>

            <ReviewStep
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
