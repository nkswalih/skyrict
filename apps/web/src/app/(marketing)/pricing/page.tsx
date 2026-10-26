import type { Metadata } from "next";

import { PricingTiers } from "@/components/marketing/pricing/pricing-tiers";
import { RevealSection } from "@/components/marketing/reveal-section";
import { Cta } from "@/components/marketing/sections/cta";
import { BreadcrumbJsonLd } from "@/components/seo/breadcrumb-json-ld";
import { pricingFaq } from "@/config";
import { resolvePricingContext } from "@/lib/server/geo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
    title: "Pricing and Plans",
    description:
        "Skyrict pricing and plans. Starter is free forever. Paid plans start with a 14-day free trial, no credit card required, and prices resolve to your currency.",
    alternates: {
        canonical: "/pricing",
    },
};

export default async function PricingPage() {
    const pricing = await resolvePricingContext();

    return (
        <>
            <BreadcrumbJsonLd
                items={[
                    { name: "Home", path: "/" },
                    { name: "Pricing and Plans", path: "/pricing" },
                ]}
            />
            <section className="mx-auto w-full max-w-6xl px-6 pt-16 sm:pt-20">
                <RevealSection>
                    <div className="mx-auto max-w-2xl space-y-4 text-center">
                        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                            Transparent pricing
                        </p>
                        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                            Pricing for a business that runs on live records.
                        </h1>
                        <p className="text-base leading-relaxed text-muted-foreground">
                            Start free today. Upgrade when the work grows. Paid
                            plans begin with a 14-day trial, no card required.
                        </p>
                    </div>
                </RevealSection>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 pb-10 pt-12">
                <RevealSection>
                    <PricingTiers
                        currency={pricing.currency}
                        available={pricing.available}
                    />
                    <p className="mx-auto mt-6 max-w-2xl text-center text-xs leading-relaxed text-muted-foreground">
                        Market intelligence is in development. Plan details will
                        be updated when the signal engine ships.
                    </p>
                </RevealSection>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 py-20 sm:py-24">
                <div className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                    <RevealSection>
                        <div className="space-y-3">
                            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                                FAQ
                            </p>
                            <h2 className="font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                                Straight answers.
                            </h2>
                            <p className="text-sm leading-relaxed text-muted-foreground">
                                Nothing buried in fine print. If your question
                                is missing, write to us and we will answer it in
                                the open.
                            </p>
                        </div>
                    </RevealSection>
                    <RevealSection>
                        <dl className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
                            {pricingFaq.map((item) => (
                                <div key={item.question} className="space-y-2">
                                    <dt className="font-display text-sm font-semibold text-foreground">
                                        {item.question}
                                    </dt>
                                    <dd className="text-sm leading-relaxed text-muted-foreground">
                                        {item.answer}
                                    </dd>
                                </div>
                            ))}
                        </dl>
                    </RevealSection>
                </div>
            </section>

            <Cta
                eyebrow="Start free"
                title="Start with one workspace."
                description="Create an account, set up the modules you need, and ask SkyAgent what needs attention."
            />
        </>
    );
}
