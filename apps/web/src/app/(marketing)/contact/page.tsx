import { CircleCheck, GitBranch } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ContactForm } from "@/components/marketing/contact/contact-form";
import { RevealSection } from "@/components/marketing/reveal-section";
import { BreadcrumbJsonLd } from "@/components/seo/breadcrumb-json-ld";
import { contactEmail } from "@/config";

export const metadata: Metadata = {
    title: "Contact Sales",
    description:
        "Talk to Skyrict about your operations, a walkthrough, or a rollout. Bug reports belong in the public GitHub issue tracker.",
    alternates: {
        canonical: "/contact",
    },
};

const pointers = [
    "The systems you run today and what you want to improve",
    "Team size and the decisions you want covered",
    "A workflow or report that takes too long today",
];

export default function ContactPage() {
    return (
        <>
            <BreadcrumbJsonLd
                items={[
                    { name: "Home", path: "/" },
                    { name: "Contact Sales", path: "/contact" },
                ]}
            />
            <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                <div className="grid items-start gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
                    <RevealSection>
                        <div className="max-w-md">
                            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                                Contact
                            </p>
                            <h1 className="mt-4 font-display text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl">
                                Talk to us about your operations.
                            </h1>
                            <p className="mt-5 text-base leading-relaxed text-muted-foreground">
                                Tell us what you run, what you want to improve,
                                and where the work slows down. We reply from{" "}
                                <span className="font-mono text-sm text-foreground">
                                    {contactEmail}
                                </span>
                                .
                            </p>
                            <div className="mt-8 rounded-2xl border border-border bg-card p-6">
                                <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                    What to include
                                </p>
                                <ul className="mt-4 space-y-2.5">
                                    {pointers.map((pointer) => (
                                        <li
                                            key={pointer}
                                            className="flex items-start gap-2.5 text-sm leading-relaxed text-muted-foreground"
                                        >
                                            <CircleCheck
                                                aria-hidden="true"
                                                className="mt-0.5 size-4 shrink-0 text-primary/70"
                                            />
                                            {pointer}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                            <div className="mt-6 flex items-center gap-2.5 text-sm text-muted-foreground">
                                <GitBranch
                                    aria-hidden="true"
                                    className="size-4 shrink-0"
                                />
                                <span>
                                    Reporting a bug or a security issue? Use{" "}
                                    <Link
                                        href="https://github.com/nkswalih/skyrict/issues"
                                        target="_blank"
                                        rel="noreferrer"
                                        className="font-medium text-foreground underline decoration-border underline-offset-4 transition-colors hover:decoration-primary"
                                    >
                                        GitHub Issues
                                    </Link>
                                    .
                                </span>
                            </div>
                        </div>
                    </RevealSection>
                    <RevealSection delay={120}>
                        <ContactForm />
                    </RevealSection>
                </div>
            </section>
        </>
    );
}
