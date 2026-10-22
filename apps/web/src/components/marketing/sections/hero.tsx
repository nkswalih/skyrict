import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AuthAwareCta } from "@/components/marketing/auth-aware-cta";
import { WorkspaceVisual } from "@/components/marketing/workspace-visual";
import { Button } from "@/components/ui/button";

const delay = (ms: number) =>
    ({ "--sky-delay": `${ms}ms` }) as React.CSSProperties;

function Hero() {
    return (
        <section className="relative overflow-hidden">
            <div className="mx-auto w-full max-w-6xl px-6 pb-20 pt-16 sm:pt-24">
                <div className="mx-auto max-w-2xl text-center">
                    <p
                        className="sky-anim font-mono text-xs uppercase tracking-[0.2em] text-primary"
                        style={delay(0)}
                    >
                        AI Business Operating System
                    </p>
                    <h1
                        className="sky-anim mt-5 font-display text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl"
                        style={delay(140)}
                    >
                        Make tomorrow&apos;s calls on today&apos;s signals.
                    </h1>
                    <p
                        className="sky-anim mx-auto mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg"
                        style={delay(280)}
                    >
                        Skyrict pairs your live operations with continuous
                        market signals. Agents read both at once and return the
                        next move.
                    </p>
                    <div
                        className="sky-anim mt-9 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
                        style={delay(400)}
                    >
                        <AuthAwareCta />
                        <Button
                            variant="outline"
                            size="pill-lg"
                            className="border-marketing-ink/15 bg-transparent text-marketing-ink hover:bg-marketing-ink/[0.04] hover:text-marketing-ink"
                            asChild
                        >
                            <Link href="/product">
                                Explore the platform
                                <ArrowRight
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            </Link>
                        </Button>
                    </div>
                </div>

                <div className="mt-12 sm:mt-16">
                    <WorkspaceVisual />
                </div>
            </div>
        </section>
    );
}

export { Hero };
