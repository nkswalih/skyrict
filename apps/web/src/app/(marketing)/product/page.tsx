import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AiGlyph } from "@/components/brand/logo";
import { RevealSection } from "@/components/marketing/reveal-section";
import { Cta } from "@/components/marketing/sections/cta";
import { Faq } from "@/components/marketing/sections/faq";
import { SignalSparkline } from "@/components/marketing/signal-sparkline";
import { BreadcrumbJsonLd } from "@/components/seo/breadcrumb-json-ld";
import { Button } from "@/components/ui/button";
import { signalSources } from "@/config";

export const metadata: Metadata = {
    title: "AI ERP Platform",
    description:
        "Skyrict connects inventory, sales, cash, orders, CRM, HR, and reporting in one live workspace. AI agents turn those records into decisions your team can act on.",
    alternates: {
        canonical: "/product",
    },
};

const inventoryRows = [
    {
        sku: "EARB-M",
        name: "Earbuds, size M",
        stock: "124",
        cover: "2d",
        status: "Low",
    },
    {
        sku: "EARB-L",
        name: "Earbuds, size L",
        stock: "512",
        cover: "8d",
        status: "OK",
    },
    {
        sku: "CBL-1M",
        name: "USB-C cable, 1m",
        stock: "318",
        cover: "11d",
        status: "OK",
    },
    {
        sku: "PWR-65W",
        name: "65W charger",
        stock: "96",
        cover: "3d",
        status: "Low",
    },
];

const insightFeed = [
    {
        source: "Google Trends",
        text: "Earbuds demand +18% w/w",
        time: "Example",
    },
    {
        source: "Reddit",
        text: "Thread on wireless earbuds is growing fast",
        time: "Example",
    },
    {
        source: "YouTube",
        text: "Search share shifts to small size format",
        time: "Example",
    },
    {
        source: "News",
        text: "Competitor restock delays reported",
        time: "Example",
    },
];

function PanelHeader({
    label,
    right,
}: {
    label: string;
    right?: React.ReactNode;
}) {
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
                        Scoped ERP · live
                    </span>
                }
            />
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead>
                        <tr className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <th className="px-4 py-2.5 font-medium">SKU</th>
                            <th className="px-4 py-2.5 font-medium">Product</th>
                            <th className="px-4 py-2.5 text-right font-medium">
                                Stock
                            </th>
                            <th className="px-4 py-2.5 text-right font-medium">
                                Cover
                            </th>
                            <th className="px-4 py-2.5 text-right font-medium">
                                Status
                            </th>
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
                label="Market · in development"
                right={
                    <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        Not live
                    </span>
                }
            />
            <div className="space-y-3 p-4">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Planned sources
                </p>
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
                <SignalSparkline label="Illustrative: earbuds search demand over eight weeks" />
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
                label="Agents · sources attached"
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
                        "Cover is two days, below the reorder point of five.",
                        "Sales are running above the 30-day average.",
                        "The reorder fits the current cash position.",
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
                        Vendor lead time 5 days. Send to Approvals.
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
            <BreadcrumbJsonLd
                items={[
                    { name: "Home", path: "/" },
                    { name: "AI ERP Platform", path: "/product" },
                ]}
            />
            <section className="mx-auto w-full max-w-6xl px-6 pb-20 pt-16 sm:pt-24">
                <RevealSection>
                    <div className="mx-auto max-w-3xl space-y-6 text-center">
                        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                            The platform
                        </p>
                        <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl">
                            One operating system for your operations, with
                            agents on top.
                        </h1>
                        <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
                            Skyrict brings CRM, inventory, orders, finance, HR,
                            and reporting into one scoped ERP. SkyAgent answers
                            questions from those live records and shows the
                            sources behind its answers.
                        </p>
                        <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
                            <Button variant="brand" size="pill-lg" asChild>
                                <Link href="/signup">Try it free</Link>
                            </Button>
                            <Button
                                variant="outline"
                                size="pill-lg"
                                className="border-marketing-ink/15 bg-transparent text-marketing-ink hover:bg-marketing-ink/[0.04] hover:text-marketing-ink"
                                asChild
                            >
                                <Link href="/docs">
                                    Read the docs
                                    <ArrowRight
                                        aria-hidden="true"
                                        className="size-4"
                                    />
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
                            description="Skyrict is the system of record for the slice of your business that drives the rest: inventory, orders, sales, cash, payroll, HR, CRM, and reporting. The records live in one place, so the numbers you decide on are the numbers your operations run on."
                        />
                        <ul className="mt-8 space-y-3">
                            {[
                                "Run inventory, orders, sales, finance, CRM, HR, and reporting in one workspace.",
                                "See live stock and movement.",
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
                            replacement. It is a live operating core built
                            around the modules that drive the rest.
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
                                    eyebrow="Layer 02 · Global market intelligence (in development)"
                                    title="The context layer. The market, being built into the workspace."
                                    description="Demand trends, market movement, news, community signals, competitors, and category changes are the next layer. Skyrict is building a signal collection engine to read public sources and map them to the categories you sell. This layer is not live yet."
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
                                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                                    Preview data. The signal collection engine
                                    is in development and external signals are
                                    not live yet.
                                </p>
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
                            title="The decision layer. Agents that show their work."
                            description="SkyAgent answers direct questions from your live records and can show the sources behind an answer. Restock suggestions and anomaly detection are live. Guardian and Coaching consoles are in progress."
                        />
                        <ul className="mt-8 space-y-3">
                            {[
                                "SkyAgent: ask across your live records.",
                                "Restock and anomaly agents: suggestions and flags, live.",
                                "Guardian and Coaching: consoles in progress.",
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
                            eyebrow="How the records connect"
                            title="One decision, built from your live records."
                            description="A single recommendation pulls the records behind it from stock, sales, and cash. Nothing arrives as a bare suggestion."
                        />
                    </RevealSection>
                    <RevealSection delay={120}>
                        <div className="mt-12 overflow-hidden rounded-2xl border border-border bg-card p-6 sm:p-8">
                            <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-stretch">
                                <div className="rounded-xl border border-border bg-muted/20 p-5">
                                    <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                        Stock and movement
                                    </p>
                                    <ul className="mt-4 space-y-2 text-sm text-foreground">
                                        <li>Cover on size M is 2 days</li>
                                        <li>3 low-stock alerts active</li>
                                        <li>
                                            Last restock arrived 12 days ago
                                        </li>
                                    </ul>
                                </div>
                                <div className="hidden items-center justify-center lg:flex">
                                    <span className="flex size-12 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-primary">
                                        <AiGlyph
                                            aria-hidden="true"
                                            className="size-5"
                                        />
                                    </span>
                                </div>
                                <div className="rounded-xl border border-border bg-muted/20 p-5">
                                    <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                                        Sales and cash
                                    </p>
                                    <ul className="mt-4 space-y-2 text-sm text-foreground">
                                        <li>Sales above the 30-day average</li>
                                        <li>Cash available for the reorder</li>
                                        <li>Supplier lead time is 5 days</li>
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
                                    Cover is two days, sales are above the
                                    30-day average, and the reorder fits the
                                    current cash position. Vendor lead time is
                                    five days.
                                </p>
                            </div>
                        </div>
                    </RevealSection>
                </div>
            </section>

            <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-24">
                <RevealSection>
                    <SectionHeader
                        eyebrow="Tenants and trust"
                        title="Built for real, tenant-based operations."
                        description="The platform is designed around workspaces, roles, and verifiable security."
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
                                Platform
                            </h3>
                            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
                                <li>Scoped ERP modules</li>
                                <li>Role-based access</li>
                            </ul>
                            <Button
                                variant="link"
                                className="mt-4 px-0"
                                asChild
                            >
                                <Link href="/docs/getting-started/connect-operations">
                                    How to set up your operations
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

            <Faq />

            <Cta
                eyebrow="Start free"
                title="Run your operations from one live system."
                description="Create an account, set up the modules you need, and ask SkyAgent what needs attention. The answer comes with the records behind it."
            />
        </>
    );
}
