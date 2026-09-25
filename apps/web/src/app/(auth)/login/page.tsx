import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { LoginForm } from "@/features/auth/login-form";
import { callBackend, hostSurface } from "@/lib/server/auth";

export const metadata: Metadata = {
    title: "Sign in",
    description: "Sign in to your Skyrict workspace.",
};

const SIGNIN_HOST_RE = /^([a-z0-9-]+)\.signin\.(localhost|skyrict\.in)$/;

export default async function LoginPage({
    searchParams,
}: {
    searchParams: Promise<{
        email?: string;
        error?: string;
        accepted?: string;
    }>;
}) {
    const params = await searchParams;
    const email = params.email?.trim() ?? "";
    const error = params.error?.trim() ?? "";
    const accepted = params.accepted === "1";

    // --- Tenant existence guard ---------------------------------------------------
    // When a user visits {slug}.signin.localhost but that tenant no longer exists
    // in the database (e.g. after a data reset), redirect them to the signup page
    // instead of showing a login form that can never succeed.
    const headerStore = await headers();
    const host = headerStore.get("host") ?? "";
    const { surface, slug } = hostSurface(host);

    if (surface === "signin" && slug) {
        let shouldRedirectToSignup = false;
        try {
            const result = await callBackend("/auth/signup/check-slug", {
                method: "POST",
                body: { slug },
            });
            // `available: true` means no tenant with this slug exists → send to signup.
            shouldRedirectToSignup = Boolean(
                result.ok && result.data?.available,
            );
        } catch {
            // Backend unreachable or unexpected error - fall through and show the
            // login form.  The user will see a credential error if they try to sign
            // in, which is acceptable as a degraded experience.
        }

        if (shouldRedirectToSignup) {
            const value = host.trim().toLowerCase().replace(/:\d+$/, "");
            const match = SIGNIN_HOST_RE.exec(value);
            const apex = match?.[2] ?? "localhost";
            const portPart = host.includes(":")
                ? `:${host.split(":").pop()}`
                : "";
            const protocol = apex === "localhost" ? "http" : "https";
            redirect(`${protocol}://signup.${apex}${portPart}/signup`);
        }
    }

    return (
        <div className="space-y-8">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                    Welcome back
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Sign in to Skyrict
                </h1>
                <p className="text-sm text-muted-foreground">
                    Enter your credentials to access your workspace.
                </p>
            </div>

            <LoginForm
                initialEmail={email}
                initialError={error}
                accepted={accepted}
            />
        </div>
    );
}
