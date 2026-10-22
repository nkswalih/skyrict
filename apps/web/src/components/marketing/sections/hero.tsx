import type { CSSProperties } from "react";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AuthAwareCta } from "@/components/marketing/auth-aware-cta";
import { GlassFrame } from "@/components/marketing/glass-frame";
import { Button } from "@/components/ui/button";

const delay = (ms: number) => ({ "--sky-delay": `${ms}ms` }) as CSSProperties;

function Hero() {
    return (
        <section className="relative isolate -mt-20 overflow-hidden">
            {/*
             * The wallpaper is CSS-built so the hero can ship before the final
             * painted artwork lands. Swap the layer stack in
             * `.marketing-hero-art` for the supplied image when it is ready.
             */}
            <div
                aria-hidden="true"
                className="marketing-hero-art pointer-events-none absolute inset-0 -z-20"
            />
            <div
                aria-hidden="true"
                className="marketing-hero-art-grain pointer-events-none absolute inset-0 -z-10"
            />
            <div
                aria-hidden="true"
                className="pointer-events-none absolute -right-40 top-8 size-[34rem] rounded-full bg-[#ffd8c6]/25 blur-[130px]"
            />
            <div
                aria-hidden="true"
                className="pointer-events-none absolute -left-40 top-52 size-[32rem] rounded-full bg-[#87ceeb]/22 blur-[140px]"
            />

            <div className="relative mx-auto w-full max-w-[1180px] px-6 pt-40 pb-16 sm:pt-48 sm:pb-20 lg:pt-52 lg:pb-24">
                <div className="mx-auto max-w-4xl text-center">
                    <p
                        className="sky-anim inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/40 px-3 py-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-marketing-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] backdrop-blur-md sm:text-[11px]"
                        style={delay(0)}
                    >
                        <span
                            aria-hidden="true"
                            className="size-1.5 rounded-full bg-marketing-sky shadow-[0_0_0_3px_rgba(135,206,235,0.18)]"
                        />
                        AI Business Operating System
                    </p>

                    <h1
                        className="sky-anim mt-7 text-balance font-display text-[2.6rem] font-semibold leading-[0.94] tracking-[-0.055em] text-marketing-ink max-[359px]:text-[2.15rem] sm:text-[4.5rem] lg:text-[5.35rem]"
                        style={delay(120)}
                    >
                        Run the business
                        <br />
                        on live evidence.
                    </h1>

                    <p
                        className="sky-anim mx-auto mt-6 max-w-2xl text-pretty text-base leading-relaxed text-marketing-muted sm:text-lg"
                        style={delay(240)}
                    >
                        CRM, inventory, orders, finance, and people in one
                        operating workspace. Skyrict reads the market alongside
                        them, so every decision starts with context.
                    </p>

                    <div
                        className="sky-anim mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
                        style={delay(360)}
                    >
                        <AuthAwareCta />
                        <Button
                            variant="outline"
                            size="pill-lg"
                            className="group border-marketing-ink/15 bg-white/35 text-marketing-ink backdrop-blur-md hover:bg-white/60 hover:text-marketing-ink"
                            asChild
                        >
                            <Link href="/product">
                                Explore the platform
                                <ArrowRight
                                    aria-hidden="true"
                                    className="size-4 transition-transform duration-200 group-hover/button:translate-x-0.5"
                                />
                            </Link>
                        </Button>
                    </div>
                </div>

                <div
                    className="sky-anim mx-auto mt-12 max-w-[1120px] sm:mt-16 lg:mt-20"
                    style={delay(540)}
                >
                    <GlassFrame
                        src="/marketing/vastraline-crm-overview.png"
                        alt="Skyrict CRM overview showing open pipeline, active leads, won business, follow-ups, and top opportunities."
                        priority
                    />
                </div>
            </div>
        </section>
    );
}

export { Hero };
