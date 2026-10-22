import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";
import { Button } from "@/components/ui/button";

const trustFacts = [
    {
        title: "Workspace isolation",
        body: "Each account runs in its own tenant. Records never cross workspaces.",
    },
    {
        title: "Roles and permissions",
        body: "Owner, admin, and member roles gate every surface and report.",
    },
    {
        title: "Multi-factor authentication",
        body: "TOTP on every account, with one-time backup codes.",
    },
    {
        title: "Open source",
        body: "The codebase is public, so the security model can be checked.",
    },
];

function Trust() {
    return (
        <section
            id="trust"
            aria-labelledby="trust-heading"
            className="scroll-mt-24 border-t border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1120px] px-6 py-20 sm:py-24 lg:py-28">
                <RevealSection>
                    <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start lg:gap-16">
                        <div>
                            <h2
                                id="trust-heading"
                                className="font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl lg:text-[2.9rem]"
                            >
                                Built for real
                                <br />
                                operations.
                            </h2>
                            <p className="mt-5 max-w-md text-base leading-relaxed text-marketing-muted">
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

                        <ul className="grid border-t border-marketing-line/80 sm:grid-cols-2">
                            {trustFacts.map(({ title, body }) => (
                                <li
                                    key={title}
                                    className="border-b border-marketing-line/80 py-5 sm:odd:border-r sm:odd:pr-6 sm:even:pl-6"
                                >
                                    <h3 className="font-display text-sm font-semibold text-marketing-ink">
                                        {title}
                                    </h3>
                                    <p className="mt-1 text-sm leading-relaxed text-marketing-muted">
                                        {body}
                                    </p>
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
