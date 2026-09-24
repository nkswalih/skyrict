import { ArrowRight, TrendingUp } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AiGlyph } from "@/components/brand/logo";
import { RevealSection } from "@/components/marketing/reveal-section";
import { Cta } from "@/components/marketing/sections/cta";
import { SignalSparkline } from "@/components/marketing/signal-sparkline";
import { Button } from "@/components/ui/button";
import { signalSources } from "@/config";

export const metadata: Metadata = {
    title: "Product",
    description:
        "Skyrict connects ERP operations, global market intelligence, and AI agents into one decision system. See the data layer, context layer, and decision layer.",
    alternates: {
        canonical: "/product",
    },
};

const inventoryRows = [
    { sku: "EARB-M", name: "Earbuds, size M", stock: "124", cover: "2d", status: "Low" },
    { sku: "EARB-L", name: "Earbuds, size L", stock: "512", cover: "8d", status: "OK" },
    { sku: "CBL-1M", name: "USB-C cable, 1m", stock: "318", cover: "11d", status: "OK" },
    { sku: "PWR-65W", name: "65W charger", stock: "96", cover: "3d", status: "Low" },
];

const insightFeed = [
    { source: "Google Trends", text: "Earbuds demand +18% w/w", time: "09:12 UTC" },
    { source: "Reddit", text: "Thread on wireless earbuds is growing fast", time: "08:47 UTC" },
    { source: "YouTube", text: "Search share shifts to small size format", time: "08:20 UTC" },
    { source: "News", text: "Competitor restock delays reported", time: "07:58 UTC" },
];

function PanelHeader({ label, right }: { label: string; right?: React.ReactNode }) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
            <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                {label}
            </p>
            {right}
        </div>
    );
}

function DataLayerVisual() {
    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <PanelHeader
                label="Inventory · live"
                right={
                    <span className="font-mono text-[10px] text-muted-foreground">
                        Connected · 2 sources
                    </span>
                }
            />
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead>
                        <tr className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <th className="px-4 py-2.5 font-medium">SKU</th>
                            <th className="px-4 py-2.5 font-medium">Product</th>
                            <th className="px-4 py-2.5 text-right font-medium">Stock</th>
                            <th className="px-4 py-2.5 text-right font-medium">Cover</th>
                            <th className="px-4 py-2.5 text-right font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inventoryRows.map((row) => (
                            <tr
                                key={row.sku}
                                className="border-b border-border/40 last:border-0"
                            >
                                <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                                    {row.sku}
                                </td>
                                <td className="px-4 py-2.5 font-medium text-foreground">
                                    {row.name}
                                </td>
                                <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-foreground">
                                    {row.stock}
                                </td>
                                <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                                    {row.cover}
                                </td>
                                <td className="px-4 py-2.5 text-right">
                                    <span
                                        className={
                                            row.status === "Low"
                                                ? "rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
                                                : "rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground"
                                        }
                                    >
                                        {row.status}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function ContextLayerVisual() {
    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <PanelHeader
                label="Market · continuous"
                right={
                    <span className="flex items-center gap-1.5 text-[11px] font-medium text-primary">
                        <TrendingUp aria-hidden="true" className="size-3" />
                        +18% w/w
                    </span>
                }
            />
            <div className="space-y-3 p-4">
                <div className="flex flex-wrap gap-1.5">
                    {signalSources.map((source) => (
                        <span
                            key={source}
                            className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground"
                        >
                            {source}
                        </span>
                    ))}
                </div>
                <SignalSparkline label="Earbuds search demand rising over eight weeks" />
                <ul className="space-y-2">
                    {insightFeed.map((item) => (
                        <li
                            key={item.text}
                            className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2 text-xs"
                        >
                            <span className="flex items-center gap-2 text-muted-foreground">
                                <span className="font-mono text-[10px] uppercase tracking-wider text-primary">
                                    {item.source}
                                </span>
                                {item.text}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground/70">
                                {item.time}
                            </span>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}

function DecisionLayerVisual() {
    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <PanelHeader
                label="Agents · explanation attached"
                right={
                    <span className="flex size-6 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-primary">
                        <AiGlyph aria-hidden="true" className="size-3.5" />
                    </span>
                }
            />
            <div className="space-y-3 p-4">
                <div className="rounded-lg border border-border bg-muted/20 px-3.5 py-2.5 text-sm text-muted-foreground">
                    Question: what should we do about size M?
                </div>
                <ul className="space-y-2">
                    {[
                        "Demand is up three straight weeks across Trends and Reddit.",
                        "Cover is two days, below the reorder point of five.",
                        "Margin stays intact at the current price.",
                    ].map((evidence) => (
                        <li
                            key={evidence}
                            className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground"
                        >
                            <span
                                aria-hidden="true"
                                className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary"
                            />
                            {evidence}
                        </li>
                    ))}
                </ul>
                <div className="rounded-lg border border-primary/30 bg-primary/5 px-3.5 py-3">
                    <p className="font-display text-sm font-semibold text-foreground">
                        Restock 600 units of size M
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        Vendor lead time 5 days. Approve in one step.
                    </p>
                </div>
            </div>
        </div>
    );
}

function SectionHeader({
    eyebrow,
    title,
    description,
}: {
    eyebrow: string;
    title: string;
    description: string;
}) {
    return (
        <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                {eyebrow}
            </p>
            <h2 className="mt-4 font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                {title}
            </h2>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                {description}
            </p>
        </div>
    );
}

export default function ProductPage() {
    return (
        <>
            <section className="mx-auto w-full max-w-6xl px-6 pb-20 pt-16 sm:pt-24">
                <RevealSection>
                    <div className="mx-auto max-w-3xl space-y-6 text-center">
                        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                            The platform
                        </p>
                        <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl">
                            One decision system for your operations and the
                            market.
                        </h1>
                        <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
                            Skyrict connects the ERP data you already run on
                            with continuous market intelligence, then uses
                            agents to turn the combination into recommended
                            actions, with the reasoning attached.
                        </p>
                        <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
                            <Button size="lg" asChild>
                                <Link href="/signup">Create your account</Link>
                            </Button>
                            <Button variant="outline" size="lg" asChild>
                                <Link href="/docs">
                                    Read the docs
                                    <ArrowRight aria-hidden="true" className="size-4" />
                                </Link>
                            </Button>
                        </div>
                    </div>
                </RevealSection>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16">
                    <RevealSection className="min-w-0">
                        <SectionHeader
                            eyebrow="Layer 01 · ERP and operations"
                            title="The data layer. Your operations, live."
                            description="Skyrict reads the slice of your business that drives the rest: inventory, orders, sales, cash, payroll, HR, CRM, and reporting. It connects to the source of truth instead of asking for exports, so the numbers you decide on are the numbers your operations run on."
                        />
                        <ul className="mt-8 space-y-3">
                            {[
                                "Connect the systems you already run.",
                                "Skyrict reads live stock and movement.",
                                "Every surface shows the same numbers.",
                            ].map((item) => (
                                <li
                                    key={item}
                                    className="flex items-center gap-3 text-sm text-foreground"
                                >
                                    <ArrowRight
                                        aria-hidden="true"
                                        className="size-4 shrink-0 text-primary"
                                    />
                                    {item}
                                </li>
                            ))}
                        </ul>
                        <p className="mt-8 rounded-xl border border-border bg-card p-4 text-sm leading-relaxed text-muted-foreground">
                            Deliberately scoped. Skyrict is not a 400-module ERP
                            swap. It is a live read of the operations that
                            matter, connected without a migration project.
                        </p>
                    </RevealSection>
                    <RevealSection delay={120} className="min-w-0">
                        <DataLayerVisual />
                    </RevealSection>
                </div>
            </section>

            <section className="border-y border-border/60 bg-card/60">
                <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                    <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-16">
                        <RevealSection className="min-w-0">
                            <div className="lg:order-2">
                                <SectionHeader
                                    eyebrow="Layer 02 · Global market intelligence"
                                    title="The context layer. The market, read continuously."
                                    description="Demand trends, market movement, news, community signals, competitors, and category changes. Five public sources are watched around the clock, so a shift surfaces the week it happens, not a quarter later in a report."
                                />
                                <div className="mt-8 grid gap-3 sm:grid-cols-2">
                                    {[
                                        "Demand trends",
                                        "Market movement",
                                        "News and community",
                                        "Competitor moves",
                                        "Category changes",
                                    ].map((item, index) => (
                                        <div
                                            key={item}
                                            className="rounded-xl border border-border bg-card p-3.5 text-sm text-foreground"
                                        >
                                            <span className="font-mono text-[10px] text-muted-foreground">
                                                0{index + 1}
                                            </span>
                                            <p className="mt-1">{item}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </RevealSection>
                        <RevealSection delay={120} className="min-w-0">
                            <div className="lg:order-1">
                                <ContextLayerVisual />
                            </div>
                        </RevealSection>
                    </div>
                </div>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16">
                    <RevealSection className="min-w-0">
                        <SectionHeader
                            eyebrow="Layer 03 · AI agents"
                            title="The decision layer. Agents that explain themselves."
                            description="Guardian reports on what changed and why. Coaching turns history into playbooks. Your agents answer direct questions with both layers in context. Every recommended action carries the reasoning, so you can verify it before you approve it."
                        />
                        <ul className="mt-8 space-y-3">
                            {[
                                "Guardian: daily risk and change reports.",
                                "Coaching: playbooks built from your history.",
                                "Your agents: ask with both layers in context.",
                            ].map((item) => (
                                <li
                                    key={item}
                                    className="flex items-center gap-3 text-sm text-foreground"
                                >
                                    <ArrowRight
                                        aria-hidden="true"
                                        className="size-4 shrink-0 text-primary"
                                    />
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </RevealSection>
                    <RevealSection delay={120} className="min-w-0">
                        <DecisionLayerVisual />
                    </RevealSection>
                </div>
            </section>

            <section className="border-y border-border/60 bg-card/60">
                <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                    <RevealSection>
                        <SectionHeader
                            eyebrow="How the layers connect"
                            title="One decision, built from both truths."
                            description="A single recommended action pulls the evidence from operations on one side and the market on the other. Nothing arrives as a bare suggestion."
                        />
                    </RevealSection>
                    <RevealSection delay={120}>
                        <div className="mt-12 overflow-hidden rounded-2xl border border-border bg-card p-6 sm:p-8">
                            <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-stretch">
                                <div className="rounded-xl border border-border bg-muted/20 p-5">
                                    <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                        Inside your operations
                                    </p>
                                    <ul className="mt-4 space-y-2 text-sm text-foreground">
                                        <li>Cover on size M is 2 days</li>
                                        <li>3 low-stock alerts active</li>
                                        <li>Cash on hand $84.2K</li>
                                    </ul>
                                </div>
                                <div className="hidden items-center justify-center lg:flex">
                                    <span className="flex size-12 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-primary">
                                        <AiGlyph aria-hidden="true" className="size-5" />
                                    </span>
                                </div>
                                <div className="rounded-xl border border-border bg-muted/20 p-5">
                                    <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                        Outside, in the market
                                    </p>
                                    <ul className="mt-4 space-y-2 text-sm text-foreground">
                                        <li>Trends +18% w/w, up 3 weeks</li>
                                        <li>Reddit mentions accelerating</li>
                                        <li>Competitor supply tightening</li>
                                    </ul>
                                </div>
                            </div>
                            <div className="mt-6 rounded-xl border border-primary/30 bg-primary/5 px-5 py-4">
                                <p className="font-mono text-[11px] uppercase tracking-wider text-primary">
                                    Recommended decision
                                </p>
                                <p className="mt-1.5 font-display text-lg font-semibold text-foreground">
                                    Restock size M, 600 units
                                </p>
                                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                                    Demand is up three weeks, cover is two days,
                                    and margin holds at the current price.
                                    Vendor lead time is five days.
                                </p>
                            </div>
                        </div>
                    </RevealSection>
                </div>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                <RevealSection>
                    <SectionHeader
                        eyebrow="Tenants, integrations, and trust"
                        title="Built for real, tenant-based operations."
                        description="The platform is designed around workspaces, roles, and verifiable security, with integrations that read your real systems."
                    />
                </RevealSection>
                <div className="mt-12 grid gap-6 md:grid-cols-3">
                    <RevealSection>
                        <div className="h-full rounded-2xl border border-border bg-card p-6">
                            <h3 className="font-display text-lg font-semibold text-foreground">
                                Tenant model
                            </h3>
                            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
                                <li>Workspace isolation</li>
                                <li>Roles and permissions</li>
                                <li>Multi-factor authentication</li>
                            </ul>
                        </div>
                    </RevealSection>
                    <RevealSection delay={100}>
                        <div className="h-full rounded-2xl border border-border bg-card p-6">
                            <h3 className="font-display text-lg font-semibold text-foreground">
                                Integrations
                            </h3>
                            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
                                <li>Connected source systems</li>
                                <li>Progressive ERP sync</li>
                            </ul>
                            <Button variant="link" className="mt-4 px-0" asChild>
                                <Link href="/docs/getting-started/connect-operations">
                                    How to connect your operations
                                </Link>
                            </Button>
                        </div>
                    </RevealSection>
                    <RevealSection delay={200}>
                        <div className="h-full rounded-2xl border border-border bg-card p-6">
                            <h3 className="font-display text-lg font-semibold text-foreground">
                                Trust
                            </h3>
                            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
                                <li>Open source, publicly readable</li>
                                <li>Security defaults in the code</li>
                            </ul>
                            <div className="mt-4 flex flex-col gap-2">
                                <Button variant="link" className="px-0" asChild>
                                    <Link href="/docs/security/multi-factor-authentication">
                                        Read the security guide
                                    </Link>
                                </Button>
                                <Button variant="link" className="px-0" asChild>
                                    <Link
                                        href="https://github.com/nkswalih/skyrict"
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        Read the source on GitHub
                                    </Link>
                                </Button>
                            </div>
                        </div>
                    </RevealSection>
                </div>
            </section>

            <Cta
                eyebrow="Start free"
                title="Connect your operations to the market."
                description="Create an account, connect your business, and get a recommended next move built on both truths."
            />
        </>
    );
}