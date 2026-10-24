import type { Metadata } from "next";
import Link from "next/link";

import { SecurityStep } from "@/features/onboarding/security-step";
import { AuthButton } from "@/lib/auth/AuthButton";

export const metadata: Metadata = {
    title: "Secure your account",
    description: "Step 3 of 7 - choose a strong password.",
};

export default async function SecurityPage({
    searchParams,
}: {
    searchParams: Promise<{ email?: string; vt?: string }>;
}) {
    const params = await searchParams;
    const email = params.email?.trim();
    const vt = params.vt?.trim();

    if (!email || !vt) {
        return (
            <div className="space-y-4 text-center">
                <div className="space-y-2">
                    <h1 className="font-display text-2xl font-semibold text-foreground">
                        Session expired
                    </h1>
                    <p className="text-sm text-muted-foreground">
                        Your verification session is missing. Restart the flow
                        to continue.
                    </p>
                </div>
                <Link href="/signup" className="block">
                    <AuthButton className="size-10 justify-self-end w-full" variant="brand" size="icon-lg">Start over</AuthButton>
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-foreground">
                    Step 3 of 7 · Security
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Protect your account
                </h1>
                <p className="text-sm text-muted-foreground">
                    Use at least 12 characters with uppercase, lowercase, a
                    number, and a special character.
                </p>
            </div>

            <SecurityStep email={email} vt={vt} />
        </div>
    );
}
