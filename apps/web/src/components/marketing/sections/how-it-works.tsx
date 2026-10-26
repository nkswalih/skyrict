import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";

const steps = [
    {
        title: "Set up the workspace",
        body: "Bring CRM, inventory, orders, finance, and people into one scoped workspace. Roles, permissions, and the audit trail come with it.",
    },
    {
        title: "Ask across the business",
        body: "SkyAgent answers from live records, flags low stock and unusual movement, and turns a question into a next step.",
    },
    {
        title: "Review before you act",
        body: "Recommendations stop at the approval step. You can inspect the records and sources behind an answer before anything changes.",
    },
];

function HowItWorks() {
    return (
        <section
            id="how-it-works"
            aria-labelledby="how-it-works-heading"
            className="scroll-mt-24 border-t border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1120px] px-6 py-20 sm:py-24 lg:py-28">
                <RevealSection>
                    <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
                        <h2
                            id="how-it-works-heading"
                            className="max-w-md font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl lg:text-[2.9rem]"
                        >
                            One system.
                            <br />
                            Three moves.
                        </h2>
                        <div className="lg:pt-2">
                            <p className="max-w-xl text-base leading-relaxed text-marketing-muted">
                                Skyrict is a scoped ERP and an agent workspace
                                in one. It reads your live operations, answers
                                questions in plain language, and keeps the
                                records behind each answer in view.
                            </p>
                            <Link
                                href="/product"
                                className="group mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-marketing-ink underline decoration-marketing-sky/70 decoration-2 underline-offset-4 transition-colors hover:decoration-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                            >
                                See how the workspace fits together
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                />
                            </Link>
                        </div>
                    </div>
                </RevealSection>

                <RevealSection delay={60}>
                    <ol className="mt-12 grid border-y border-marketing-line/80 md:mt-16 md:grid-cols-3">
                        {steps.map((step) => (
                            <li
                                key={step.title}
                                className="border-t border-marketing-line/80 py-6 first:border-t-0 md:border-t-0 md:border-l md:px-7 md:py-7 md:first:border-l-0 md:first:pl-0 md:last:pr-0"
                            >
                                <h3 className="font-display text-xl font-semibold tracking-tight text-marketing-ink">
                                    {step.title}
                                </h3>
                                <p className="mt-2 max-w-sm text-sm leading-relaxed text-marketing-muted">
                                    {step.body}
                                </p>
                            </li>
                        ))}
                    </ol>
                </RevealSection>
            </div>
        </section>
    );
}

export { HowItWorks };
