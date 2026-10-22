import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";
import { Button } from "@/components/ui/button";

function Cta({
    eyebrow = "Start free",
    title = "Make your first call on live signals.",
    description = "Create an account, connect your business, and Skyrict surfaces the market's next signal before it reaches your stock.",
    ctaLabel = "Get started",
    ctaHref = "/signup",
    secondaryCtaLabel = "Contact sales",
    secondaryCtaHref = "/contact",
}: {
    eyebrow?: string;
    title?: React.ReactNode;
    description?: React.ReactNode;
    ctaLabel?: string;
    ctaHref?: string;
    secondaryCtaLabel?: string;
    secondaryCtaHref?: string;
}) {
    return (
        <section aria-labelledby="cta-heading">
            <div className="mx-auto w-full max-w-6xl px-6 pb-24">
                <RevealSection>
                    <div className="relative overflow-hidden rounded-[2rem] border border-marketing-line bg-card px-6 py-14 text-center shadow-[0_32px_100px_-64px_rgba(10,47,62,0.4)] sm:px-12 sm:py-20 lg:px-16">
                        <div
                            aria-hidden="true"
                            className="pointer-events-none absolute inset-0 opacity-40"
                            style={{
                                backgroundImage:
                                    "radial-gradient(circle at 1px 1px, rgba(10,47,62,0.12) 1px, transparent 0)",
                                backgroundSize: "24px 24px",
                                maskImage:
                                    "linear-gradient(to bottom, black, transparent 78%)",
                                WebkitMaskImage:
                                    "linear-gradient(to bottom, black, transparent 78%)",
                            }}
                        />
                        <div
                            aria-hidden="true"
                            className="pointer-events-none absolute inset-0"
                            style={{
                                background:
                                    "radial-gradient(60% 85% at 50% 112%, rgba(135,206,235,0.24), transparent 68%)",
                            }}
                        />
                        <div
                            aria-hidden="true"
                            className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-marketing-line to-transparent"
                        />

                        <div className="relative mx-auto max-w-3xl">
                            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-marketing-muted">
                                {eyebrow}
                            </p>
                            <h2
                                id="cta-heading"
                                className="mt-5 text-balance font-display text-4xl font-semibold leading-[1.04] tracking-[-0.04em] text-marketing-ink sm:text-5xl lg:text-[3.5rem]"
                            >
                                {title}
                            </h2>
                            <p className="mx-auto mt-5 max-w-xl text-pretty text-base leading-relaxed text-marketing-muted">
                                {description}
                            </p>

                            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
                                <Button
                                    variant="brand"
                                    size="pill-lg"
                                    className="group w-full sm:w-auto"
                                    asChild
                                >
                                    <Link href={ctaHref}>
                                        {ctaLabel}
                                        <ArrowUpRight
                                            aria-hidden="true"
                                            className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                                        />
                                    </Link>
                                </Button>
                                <Button
                                    variant="outline"
                                    size="pill-lg"
                                    className="w-full border-marketing-ink/15 bg-transparent text-marketing-ink hover:bg-marketing-ink/[0.04] hover:text-marketing-ink sm:w-auto"
                                    asChild
                                >
                                    <Link href={secondaryCtaHref}>
                                        {secondaryCtaLabel}
                                    </Link>
                                </Button>
                            </div>

                            <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.14em] text-marketing-muted">
                                {[
                                    "Free to start",
                                    "No card required",
                                    "14-day trial",
                                ].map((item) => (
                                    <li
                                        key={item}
                                        className="flex items-center gap-2"
                                    >
                                        <span
                                            aria-hidden="true"
                                            className="size-1 rounded-full bg-marketing-sky"
                                        />
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Cta };
