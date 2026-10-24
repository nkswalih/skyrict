import type { Metadata } from "next";
import Link from "next/link";

import { VerifyStep } from "@/features/onboarding/verify-step";
import { AuthButton } from "@/lib/auth/AuthButton";

export const metadata: Metadata = {
    title: "Verify your email",
    description: "Step 2 of 7 - confirm your email address.",
};

export default async function VerifyPage({
    searchParams,
}: {
    searchParams: Promise<{ email?: string }>;
}) {
    const params = await searchParams;
    const email = params.email?.trim();

    if (!email) {
        return (
            <div className="space-y-4 text-center">
                <div className="space-y-2">
                    <h1 className="font-display text-2xl font-semibold text-foreground">
                        Let&apos;s start from the top
                    </h1>
                    <p className="text-sm text-muted-foreground">
                        Head back to step 1 to enter your work email.
                    </p>
                </div>
                <Link href="/signup" className="block">
                    <AuthButton className="size-10 justify-self-end w-full" variant="brand" size="icon-lg">
                        Back to account details
                    </AuthButton>
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-foreground">
                    Step 2 of 7 · Verification
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Check your inbox
                </h1>
                <p className="text-sm text-muted-foreground">
                    We sent a 6-digit code to confirm it&apos;s really you.
                </p>
            </div>

            <VerifyStep email={email} />
        </div>
    );
}
