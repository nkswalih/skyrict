import type { Metadata } from "next";
import Link from "next/link";

import { DocsShell } from "@/components/docs/docs-shell";

export const metadata: Metadata = {
    // The docs hostname is the canonical public origin for the /docs tree on
    // every surface that serves it (docs.skyrict.in, Vercel deployment
    // fallback, web.skyrict.in). Resolving relative URLs against it makes the
    // emitted canonical/OG links point at https://docs.skyrict.in/... even on
    // the fallback hosts.
    metadataBase: new URL("https://docs.skyrict.in"),
    title: {
        default: "Docs",
        template: "%s · Docs",
    },
    description:
        "Guides for connecting operations, reading live signals, and running your business with Skyrict.",
    robots: {
        index: true,
        follow: true,
    },
    alternates: {
        // Docs-surface root: on the canonical host the browser URL is
        // docs.skyrict.in/ (no /docs prefix).
        canonical: "/",
    },
};

export default function DocsLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="flex min-h-dvh flex-col bg-background text-foreground">
            <DocsShell>{children}</DocsShell>

            <footer className="border-t border-border/70">
                <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-6 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                    <p>
                        © 2026 Skyrict. Open source on{" "}
                        <Link
                            href="https://github.com/nkswalih/skyrict"
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-foreground underline-offset-4 hover:underline"
                        >
                            GitHub
                        </Link>
                        .
                    </p>
                    <div className="flex items-center gap-4">
                        <Link
                            href="https://github.com/nkswalih/skyrict/issues"
                            target="_blank"
                            rel="noreferrer"
                            className="underline-offset-4 hover:text-foreground hover:underline"
                        >
                            Contact support
                        </Link>
                        <Link
                            href="/terms"
                            className="underline-offset-4 hover:text-foreground hover:underline"
                        >
                            Terms
                        </Link>
                        <Link
                            href="/privacy"
                            className="underline-offset-4 hover:text-foreground hover:underline"
                        >
                            Privacy
                        </Link>
                    </div>
                </div>
            </footer>
        </div>
    );
}