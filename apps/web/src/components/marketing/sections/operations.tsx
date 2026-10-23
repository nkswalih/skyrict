import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { ProductShot } from "@/components/marketing/product-shot";
import { RevealSection } from "@/components/marketing/reveal-section";

function Operations() {
    return (
        <section
            id="operations"
            aria-labelledby="operations-heading"
            className="scroll-mt-24 border-t border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1120px] px-6 py-20 sm:py-24 lg:py-28">
                <RevealSection>
                    <div className="grid gap-8 lg:grid-cols-[1fr_0.9fr] lg:items-start lg:gap-16">
                        <h2
                            id="operations-heading"
                            className="max-w-xl font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl lg:text-[2.9rem]"
                        >
                            The operating core.
                        </h2>
                        <div className="lg:pb-1">
                            <p className="max-w-md text-base leading-relaxed text-marketing-muted">
                                CRM, inventory, orders, finance, and people in
                                one live system. The records stay in one place,
                                so teams work from the same numbers.
                            </p>
                            <Link
                                href="/product"
                                className="group mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-marketing-ink underline decoration-marketing-sky/70 decoration-2 underline-offset-4 transition-colors hover:decoration-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                            >
                                Explore the platform
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                />
                            </Link>
                        </div>
                    </div>
                </RevealSection>

                <RevealSection delay={120}>
                    <div className="mt-12 grid gap-6 lg:grid-cols-12 lg:items-start">
                        <ProductShot
                            src="/marketing/vastraline-operations.png"
                            alt="Skyrict Business Operations dashboard showing attention needed, finance and revenue, operations and sales, and report KPIs."
                            sizes="(min-width: 1024px) 720px, 100vw"
                            className="lg:col-span-8"
                        />
                        <ProductShot
                            src="/marketing/vastraline-inventory.png"
                            alt="Skyrict inventory dashboard showing product counts, low stock, and items below reorder point."
                            sizes="(min-width: 1024px) 340px, 100vw"
                            className="lg:col-span-4 lg:mt-16"
                        />
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Operations };
