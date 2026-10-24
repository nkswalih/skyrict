// TEMP-PREVIEW: brand panel commented out to preview the auth page without the
// left content side. Restore by uncommenting the two lines below.
// import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import type { Metadata } from "next";

import { Logo } from "@/components/brand/logo";

export const metadata: Metadata = {
    robots: {
        index: false,
        follow: false,
    },
};

export default function AuthLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="relative grid min-h-dvh bg-card lg:h-dvh lg:grid-rows-1 lg:overflow-hidden">
            {/* TEMP-PREVIEW: left brand panel hidden. Restore by uncommenting.
      <div className="min-h-0 overflow-hidden">
        <AuthBrandPanel />
      </div>
      */}

            <main className="flex min-h-0 flex-col px-6 py-10 lg:overflow-y-auto">
                <div className="mt-8 flex justify-center">
                    <Logo mark="rounded" className="text-foreground" />
                </div>

                <div className="mx-auto my-auto flex w-full max-w-sm flex-col py-10">
                    {children}
                </div>
            </main>
        </div>
    );
}
