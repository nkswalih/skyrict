import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const trendCategories = [
    { label: "Earbuds", delta: "+18%", up: true },
    { label: "Chargers", delta: "+6%", up: true },
    { label: "Cases", delta: "-2%", up: false },
];

const feedRows = [
    { source: "Google Trends", text: "Earbuds search, third week up", delta: "+18%", time: "09:42" },
    { source: "Reddit", text: "r/earbuds mentioning size M more", delta: "+12%", time: "09:15" },
    { source: "YouTube", text: "Comparison videos, views up", delta: "+9%", time: "08:58" },
    { source: "News", text: "No competitive launches this week", delta: "0%", time: "08:30" },
];

function Intelligence() {
    return (
        <section id="intelligence" className="scroll-mt-20 border-t border-border/40">
            <div className="mx-auto w-full max-w-6xl px-6 py-20 sm:py-28">
                <RevealSection>
                    <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-16">
                        <div className="order-2 min-w-0 lg:order-1">
                            <div className="overflow-hidden rounded-xl border border-border bg-card">
                                <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
                                    <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                        Intelligence, market layer
                                    </p>
                                    <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                                        Live
                                    </span>
                                </div>
                                <div className="space-y-4 p-4">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                                            Trending
                                        </span>
                                        {trendCategories.map((category) => (
                                            <span
                                                key={category.label}
                                                className={cn(
                                                    "rounded-full border px-2 py-0.5 text-[11px] font-medium",
                                                    category.up
                                                        ? "border-primary/40 bg-primary/10 text-primary"
                                                        : "border-border bg-muted/40 text-muted-foreground",
                                                )}
                                            >
                                                {category.label} {category.delta}
                                            </span>
                                        ))}
                                    </div>
                                    <ul className="divide-y divide-border/60">
                                        {feedRows.map((row) => (
                                            <li
                                                key={row.source}
                                                className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0"
                                            >
                                                <span className="w-24 shrink-0 rounded-md border border-border bg-muted/40 px-1.5 py-0.5 text-center text-[10px] text-muted-foreground">
                                                    {row.source}
                                                </span>
                                                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                                                    {row.text}
                                                </span>
                                                <span
                                                    className={cn(
                                                        "font-mono text-[11px] tabular-nums",
                                                        row.delta === "0%"
                                                            ? "text-muted-foreground"
                                                            : "text-primary",
                                                    )}
                                                >
                                                    {row.delta}
                                                </span>
                                                <span className="w-10 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
                                                    {row.time}
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        </div>
                        <div className="order-1 min-w-0 lg:order-2">
                            <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                                The market, read continuously.
                            </h2>
                            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                                Demand, news, community, and competitor moves from five
                                public sources. A shift surfaces the week it happens.
                            </p>
                            <div className="mt-6">
                                <Button variant="ghost" asChild>
                                    <Link href="/docs/intelligence/market-signals">
                                        Market signal sources
                                        <ArrowRight aria-hidden="true" className="size-4" />
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

export { Intelligence };