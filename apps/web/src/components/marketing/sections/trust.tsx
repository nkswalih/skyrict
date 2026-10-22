import {
    Cable,
    FileCode2,
    Fingerprint,
    Lock,
    MailCheck,
    ShieldCheck,
    type LucideIcon,
} from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";
import { Button } from "@/components/ui/button";

const trustFacts: {
    icon: LucideIcon;
    title: string;
    body: string;
}[] = [
    {
        icon: Lock,
        title: "Workspace isolation",
        body: "Each account runs in its own workspace. Data never crosses tenants.",
    },
    {
        icon: ShieldCheck,
        title: "Roles and permissions",
        body: "Owner, admin, and member roles gate every surface and report.",
    },
    {
        icon: Fingerprint,
        title: "Multi-factor authentication",
        body: "TOTP codes plus one-time backup codes on every account.",
    },
    {
        icon: MailCheck,
        title: "Email verification",
        body: "Accounts stay limited until the address is confirmed.",
    },
    {
        icon: Cable,
        title: "Connected source systems",
        body: "Skyrict reads your real operational sources instead of asking for a copy.",
    },
    {
        icon: FileCode2,
        title: "Open source",
        body: "The full codebase is public, so claims can be checked in the code.",
    },
];

function Trust() {
    return (
        <section id="trust" className="scroll-mt-20 border-t border-border/40">
            <div className="mx-auto w-full max-w-6xl px-6 py-20 sm:py-28">
                <RevealSection>
                    <div className="grid gap-12 lg:grid-cols-[1fr_1.3fr] lg:items-start">
                        <div>
                            <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                                Built for real operations.
                            </h2>
                            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                                Scoped by design, not by accident. Tenant
                                isolation, roles, MFA, and email verification on
                                every account, and the source is public so the
                                defaults can be checked.
                            </p>
                            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                                <Button variant="brand" size="pill" asChild>
                                    <Link href="/docs/security/multi-factor-authentication">
                                        Read the security guide
                                    </Link>
                                </Button>
                                <Button variant="ghost" asChild>
                                    <Link
                                        href="https://github.com/nkswalih/skyrict"
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        Read the source on GitHub
                                    </Link>
                                </Button>
                            </div>
                        </div>
                        <ul className="divide-y divide-border/60 rounded-xl border border-border/70 bg-card">
                            {trustFacts.map(({ icon: Icon, title, body }) => (
                                <li
                                    key={title}
                                    className="flex items-start gap-4 px-5 py-4"
                                >
                                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-primary/25 bg-primary/10 text-primary">
                                        <Icon
                                            aria-hidden="true"
                                            className="size-4"
                                        />
                                    </span>
                                    <div>
                                        <h3 className="font-display text-sm font-semibold text-foreground">
                                            {title}
                                        </h3>
                                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                                            {body}
                                        </p>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Trust };
