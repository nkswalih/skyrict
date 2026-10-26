import type { Metadata } from "next";
import Link from "next/link";

import { OrganizationStep } from "@/features/onboarding/organization-step";
import { AuthButton } from "@/lib/auth/AuthButton";

export const metadata: Metadata = {
    title: "Your organization",
    description: "Step 5 of 7 - connect your business details.",
};

export default async function OrganizationPage({
    searchParams,
}: {
    searchParams: Promise<{
        email?: string;
        vt?: string;
        plan?: string;
        interval?: string;
        currency?: string;
    }>;
}) {
    const params = await searchParams;
    const email = params.email?.trim();
    const vt = params.vt?.trim();
    const plan = params.plan?.trim();
    const interval = params.interval?.trim();
    const currency = params.currency?.trim();

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
                <Link href="/signup" prefetch={false} className="block">
                    <AuthButton className="size-10 justify-self-end w-full" variant="brand" size="icon-lg">Start over</AuthButton>
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-foreground">
                    Step 5 of 7 · Organization
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Tell us about your business
                </h1>
                <p className="text-sm text-muted-foreground">
                    We&apos;ll wire this into your workspace so agents know the
                    context.
                </p>
            </div>

            <OrganizationStep
                email={email}
                vt={vt}
                plan={plan}
                interval={interval}
                currency={currency}
            />
        </div>
    );
}
