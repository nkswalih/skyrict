import { ArrowUpRight, Check } from "lucide-react";
import Link from "next/link";

import { ProductShot } from "@/components/marketing/product-shot";
import { RevealSection } from "@/components/marketing/reveal-section";

const guarantees = [
    "Reads the workspace, not a stale export",
    "Shows the sources behind an answer",
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
                    <div className="grid gap-8 lg:grid-cols-[1fr_0.85fr] lg:items-end lg:gap-16">
                        <div>
                            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                                SkyAgent
                            </p>
                            <h2
                                id="agents-heading"
                                className="mt-4 max-w-xl font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl lg:text-[2.9rem]"
                            >
                                An answer with
                                <br />
                                the evidence attached.
                            </h2>
                        </div>
                        <div className="lg:pb-1">
                            <p className="max-w-md text-base leading-relaxed text-marketing-muted">
                                Ask across your CRM, inventory, orders, finance,
                                and people. SkyAgent answers from workspace
                                records, names the agent that handled the
                                question, and shows the sources behind its
                                answer.
                            </p>
                            <Link
                                href="/docs/agents/your-agents"
                                className="group mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-marketing-ink underline decoration-marketing-sky/70 decoration-2 underline-offset-4 transition-colors hover:decoration-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                            >
                                How SkyAgent works
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                />
                            </Link>
                        </div>
                    </div>
                </RevealSection>

                <RevealSection delay={120}>
                    <ul className="mt-10 grid border-y border-marketing-line/80 sm:grid-cols-3">
                        {guarantees.map((item) => (
                            <li
                                key={item}
                                className="flex items-center gap-3 border-t border-marketing-line/80 py-3.5 text-sm text-marketing-ink first:border-t-0 sm:border-t-0 sm:border-l sm:px-5 sm:first:border-l-0 sm:first:pl-0 sm:last:pr-0"
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
                </RevealSection>

                <RevealSection delay={200}>
                    <ProductShot
                        src="/marketing/skyrict-agent-history.png"
                        alt="SkyAgent conversation history about stock cover, with agent labels, a reorder recommendation, and the source records behind the answer."
                        sizes="(min-width: 1120px) 1120px, 100vw"
                        className="mt-10"
                    />
                </RevealSection>
            </div>
        </section>
    );
}

export { Agents };
