import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";
import { Button } from "@/components/ui/button";

function Cta({
    eyebrow = "Get started",
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
        <section>
            <div className="mx-auto w-full max-w-6xl px-6 pb-24">
                <RevealSection>
                    <div className="relative overflow-hidden rounded-3xl border border-marketing-ink/40 bg-marketing-ink px-8 py-16 text-center text-marketing-paper sm:py-20">
                        <div
                            aria-hidden="true"
                            className="pointer-events-none absolute inset-0"
                            style={{
                                background:
                                    "radial-gradient(55% 60% at 50% 0%, rgba(135,206,235,0.25), transparent 70%)",
                            }}
                        />
                        <div className="relative mx-auto max-w-2xl space-y-6">
                            <p className="font-mono text-xs uppercase tracking-[0.2em] text-marketing-sky">
                                {eyebrow}
                            </p>
                            <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                                {title}
                            </h2>
                            <p className="text-base leading-relaxed text-marketing-sky/90">
                                {description}
                            </p>
                            <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
                                <Button
                                    variant="brand-inverse"
                                    size="pill-lg"
                                    asChild
                                >
                                    <Link href={ctaHref}>{ctaLabel}</Link>
                                </Button>
                                <Button
                                    variant="outline"
                                    size="pill-lg"
                                    className="border-marketing-sky/40 bg-transparent text-marketing-paper hover:border-marketing-sky/70 hover:bg-marketing-sky/10 hover:text-marketing-paper"
                                    asChild
                                >
                                    <Link href={secondaryCtaHref}>
                                        {secondaryCtaLabel}
                                    </Link>
                                </Button>
                            </div>
                        </div>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Cta };
