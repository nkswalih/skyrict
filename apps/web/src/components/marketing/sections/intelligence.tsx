import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { ProductShot } from "@/components/marketing/product-shot";
import { RevealSection } from "@/components/marketing/reveal-section";

function Intelligence() {
    return (
        <section
            id="intelligence"
            aria-labelledby="intelligence-heading"
            className="marketing-dark-band relative scroll-mt-24 overflow-hidden border-y border-white/10"
        >
            <div
                aria-hidden="true"
                className="marketing-dark-grid pointer-events-none absolute inset-0"
            />
            <div
                aria-hidden="true"
                className="pointer-events-none absolute -right-32 top-0 size-[30rem] rounded-full bg-[#87ceeb]/10 blur-[120px]"
            />

            <div className="relative mx-auto w-full max-w-[1120px] px-6 py-20 sm:py-24 lg:py-28">
                <RevealSection>
                    <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-16">
                        <div>
                            <h2
                                id="intelligence-heading"
                                className="max-w-lg font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-paper sm:text-4xl lg:text-[2.9rem]"
                            >
                                The market,
                                <br />
                                before the meeting.
                            </h2>
                            <p className="mt-5 max-w-md text-base leading-relaxed text-marketing-paper/65">
                                Google Trends, YouTube, Reddit, GitHub, and news
                                read continuously, ranked by momentum, and
                                mapped to the categories you actually sell.
                            </p>
                            <Link
                                href="/docs/intelligence/market-signals"
                                className="group mt-7 inline-flex items-center gap-1.5 text-sm font-medium text-marketing-paper underline decoration-marketing-sky/60 decoration-2 underline-offset-4 transition-colors hover:decoration-marketing-sky focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                            >
                                How market signals work
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                />
                            </Link>
                        </div>

                        <ProductShot
                            src="/marketing/vastraline-trending.png"
                            alt="Skyrict market intelligence showing trending topics ranked by momentum across AI, logistics, retail, and developer tools."
                            tone="dark"
                            sizes="(min-width: 1024px) 620px, 100vw"
                        />
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Intelligence };
