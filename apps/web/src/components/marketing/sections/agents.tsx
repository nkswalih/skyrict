import { ArrowUpRight, Check } from "lucide-react";
import Link from "next/link";

import { ProductShot } from "@/components/marketing/product-shot";
import { RevealSection } from "@/components/marketing/reveal-section";

const guarantees = [
    "Reads the live workspace, not a stale export",
    "Shows the records behind an answer",
    "Stops at the approval step",
];

function Agents() {
    return (
        <section
            id="agents"
            aria-labelledby="agents-heading"
            className="scroll-mt-24 border-t border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1120px] px-6 py-20 sm:py-24 lg:py-28">
                <RevealSection>
                    <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-16">
                        <div>
                            <h2
                                id="agents-heading"
                                className="max-w-lg font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl lg:text-[2.9rem]"
                            >
                                An answer with
                                <br />
                                the evidence attached.
                            </h2>
                            <p className="mt-5 max-w-md text-base leading-relaxed text-marketing-muted">
                                Ask across your CRM, operations, and market
                                context. SkyAgent returns a plan, a follow-up,
                                or a decision memo—and shows the records behind
                                it before anything leaves the workspace.
                            </p>

                            <ul className="mt-7 border-t border-marketing-line/80">
                                {guarantees.map((item) => (
                                    <li
                                        key={item}
                                        className="flex items-center gap-3 border-b border-marketing-line/80 py-3.5 text-sm text-marketing-ink"
                                    >
                                        <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-marketing-sky/60 bg-marketing-sky/15 text-marketing-ink">
                                            <Check
                                                aria-hidden="true"
                                                className="size-3"
                                            />
                                        </span>
                                        {item}
                                    </li>
                                ))}
                            </ul>

                            <Link
                                href="/docs/agents/guardian"
                                className="group mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-marketing-ink underline decoration-marketing-sky/70 decoration-2 underline-offset-4 transition-colors hover:decoration-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                            >
                                How SkyAgent works
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                />
                            </Link>
                        </div>

                        <ProductShot
                            src="/marketing/vastraline-agent.png"
                            alt="SkyAgent chat with a follow-up prompt for a Zephyr Airlines proposal, grounded in the workspace."
                            sizes="(min-width: 1024px) 620px, 100vw"
                        />
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Agents };
