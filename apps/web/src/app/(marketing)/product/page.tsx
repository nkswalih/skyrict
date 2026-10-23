import type { CSSProperties, ReactNode } from "react";
import {
    ArrowRight,
    ArrowUpRight,
    Code2,
    Database,
    Fingerprint,
    Lock,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ProductFigure } from "@/components/marketing/product/product-figure";
import { SkyAgentReplay } from "@/components/marketing/product/skyagent-replay";
import { RevealSection } from "@/components/marketing/reveal-section";
import { Cta } from "@/components/marketing/sections/cta";
import { Faq } from "@/components/marketing/sections/faq";
import { BreadcrumbJsonLd } from "@/components/seo/breadcrumb-json-ld";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
    title: "Product: Skyrict ERP and SkyAgent",
    description:
        "See the Skyrict ERP and SkyAgent workspace: HR, payroll, finance, reports, inventory, orders, and CRM. Explore how the records connect and how the agent drafts from them.",
    alternates: {
        canonical: "/product",
    },
};

const delay = (ms: number) => ({ "--sky-delay": `${ms}ms` }) as CSSProperties;

const heroMetrics = [
    { label: "Active employees", value: "21" },
    { label: "Latest run", value: "$2,456,500" },
    { label: "Revenue booked", value: "$25,320" },
    { label: "Low-stock SKUs", value: "8" },
];

const moduleBlocks = [
    {
        index: "01.1",
        eyebrow: "People",
        title: "HR, without the spreadsheet.",
        description:
            "Active employees, departments, leave balances, and the requests waiting on a decision. The workspace has 21 active employees across 7 departments. The request queue shows who is waiting, for how long, and in which department.",
        metrics: [
            { label: "Active", value: "21" },
            { label: "Open leave", value: "5" },
            { label: "Departments", value: "7" },
        ],
        figure: {
            src: "/marketing/product/live-hr-activity-desktop.png",
            mobileSrc: "/marketing/product/live-hr-overview-mobile.png",
            width: 550,
            height: 400,
            mobileWidth: 370,
            mobileHeight: 600,
            alt: "Skyrict HR workspace showing recent leave requests with employee names, departments, dates, and statuses.",
            sizes: "(min-width: 1024px) 58vw, 100vw",
        },
        docsHref: "/docs/operations/payroll-hr",
        docsLabel: "Read the Payroll & HR docs",
    },
    {
        index: "01.2",
        eyebrow: "Payroll",
        title: "Runs you can audit.",
        description:
            "Eighteen runs, thirteen paid, one draft. The latest run is PR-2026-09 for $2,456,500.00. Each run keeps its period and status, so the number has a trail instead of a single total.",
        metrics: [
            { label: "Runs", value: "18" },
            { label: "Paid", value: "13" },
            { label: "Latest run", value: "$2,456,500" },
        ],
        figure: {
            src: "/marketing/product/live-payroll-runs-desktop.png",
            mobileSrc: "/marketing/product/live-payroll-kpis-mobile.png",
            width: 555,
            height: 390,
            mobileWidth: 370,
            mobileHeight: 590,
            alt: "Skyrict payroll workspace showing recent payroll runs and their statuses.",
            sizes: "(min-width: 1024px) 58vw, 100vw",
        },
        docsHref: "/docs/operations/payroll-hr",
        docsLabel: "Read the Payroll & HR docs",
        reversed: true,
    },
    {
        index: "01.3",
        eyebrow: "Finance",
        title: "Revenue history, with the limits stated.",
        description:
            "Revenue, expenses, net income, and outstanding invoices on one surface. When there is not enough history to forecast, the product states the limit instead of drawing a line.",
        metrics: [
            { label: "Revenue", value: "$25,320" },
            { label: "Expenses", value: "$784,800" },
            { label: "Outstanding", value: "$377,550" },
        ],
        figure: {
            src: "/marketing/product/live-finance-history-desktop.png",
            mobileSrc: "/marketing/product/live-finance-kpis-mobile.png",
            width: 1110,
            height: 300,
            mobileWidth: 370,
            mobileHeight: 590,
            alt: "Skyrict finance workspace showing revenue history and a note that there is not enough history to forecast yet.",
            sizes: "(min-width: 1240px) 1188px, 100vw",
        },
        docsHref: "/docs/getting-started/read-your-first-pulse",
        docsLabel: "Read the pulse docs",
        fullWidth: true,
    },
    {
        index: "01.4",
        eyebrow: "Reports",
        title: "Cross-department answers, built from the same records.",
        description:
            "Cash received, open receivables, pipeline value, stock alerts, and headcount on one page. The report studio turns a plain-language request into a reviewed template, so the output has a definition behind it.",
        metrics: [
            { label: "Cash received", value: "$25,000" },
            { label: "Open receivables", value: "$292,950" },
            { label: "Headcount", value: "28" },
        ],
        figure: {
            src: "/marketing/product/live-reports-overview-desktop.png",
            mobileSrc: "/marketing/product/live-reports-kpis-mobile.png",
            width: 1110,
            height: 640,
            mobileWidth: 370,
            mobileHeight: 360,
            alt: "Skyrict reports workspace showing cash received, open receivables, pipeline value, stock alerts, headcount, and the report studio.",
            sizes: "(min-width: 1024px) 58vw, 100vw",
        },
        docsHref: "/docs/operations/reports",
        docsLabel: "Read the Reports docs",
        reversed: true,
    },
];

const signalSteps = [
    {
        index: "01",
        label: "Signal",
        title: "What needs attention",
        description:
            "The dashboard attention row counts the work that needs a decision. Six SKUs are out of stock, one invoice is overdue, and ten opportunities are open. Each count links to the records behind it.",
        figure: {
            src: "/marketing/product/live-dashboard-attention-desktop.png",
            mobileSrc: "/marketing/product/live-dashboard-attention-mobile.png",
            width: 1110,
            height: 180,
            mobileWidth: 370,
            mobileHeight: 500,
            alt: "Skyrict dashboard attention row showing out-of-stock SKUs, an overdue invoice, and open opportunities.",
            sizes: "(min-width: 1024px) 46vw, 100vw",
        },
        docsHref: "/docs/getting-started/read-your-first-pulse",
        docsLabel: "Read the pulse docs",
    },
    {
        index: "02",
        label: "Detail",
        title: "The SKUs behind the count",
        description:
            "Inventory shows what is on hand, the reorder point, and the shortfall. The list starts with API Gateway Setup, CRM Module Add-on, Analytics Dashboard, and HR Module Add-on. The inventory assistant sits on the same screen, so a question can start from the record instead of a separate tool.",
        figure: {
            src: "/marketing/product/live-inventory-attention-desktop.png",
            mobileSrc: "/marketing/product/live-inventory-mobile.png",
            width: 1110,
            height: 300,
            mobileWidth: 370,
            mobileHeight: 590,
            alt: "Skyrict inventory workspace showing products that need attention, their on-hand quantity, and reorder point.",
            sizes: "(min-width: 1024px) 46vw, 100vw",
        },
        docsHref: "/docs/operations/inventory",
        docsLabel: "Read the Inventory docs",
    },
    {
        index: "03",
        label: "Commitment",
        title: "The order and the credit check",
        description:
            "Orders keep the status, the customer's credit check, and the value in the same row. SO-0011 is a $30,800 draft with a pending credit check. Confirmation runs the check before the order moves, while fulfilled, confirmed, and cancelled orders stay visible.",
        figure: {
            src: "/marketing/product/live-orders-table-desktop.png",
            mobileSrc: "/marketing/product/live-orders-table-mobile.png",
            width: 1110,
            height: 560,
            mobileWidth: 370,
            mobileHeight: 480,
            alt: "Skyrict orders table showing order numbers, statuses, credit checks, dates, and totals.",
            sizes: "(min-width: 1024px) 46vw, 100vw",
        },
        docsHref: "/docs/operations/orders",
        docsLabel: "Read the Orders docs",
    },
    {
        index: "04",
        label: "Follow-up",
        title: "The opportunity and the next step",
        description:
            "CRM holds the deal, stage, value, and close date. Zephyr Airlines is a $310,000 opportunity at Negotiation, 70%, closing 17 November 2026. SkyAgent drafts the follow-up from that record, then stops at the approval step.",
        figure: {
            src: "/marketing/product/live-crm-top-desktop.png",
            mobileSrc: "/marketing/product/live-crm-kpis-mobile.png",
            width: 720,
            height: 290,
            mobileWidth: 370,
            mobileHeight: 600,
            alt: "Skyrict CRM top opportunities list showing Zephyr Airlines, Quicksilver Bank, and Forma Group with values and stages.",
            sizes: "(min-width: 1024px) 46vw, 100vw",
        },
        docsHref: "/docs/agents/your-agents",
        docsLabel: "Read the SkyAgent docs",
    },
];

const availableModules = [
    {
        title: "Dashboard",
        body: "Attention needed, finance and revenue, operations and sales, and report KPIs on one surface.",
    },
    {
        title: "CRM",
        body: "Leads, opportunities, customers, contacts, activities, and notes, with pipeline stage and value.",
    },
    {
        title: "Orders",
        body: "Draft, confirm, fulfil, and cancel sales orders. Confirmation runs the customer's credit check.",
    },
    {
        title: "Inventory",
        body: "Stock levels, warehouses, reorder points, movement, and an inventory assistant.",
    },
    {
        title: "HR",
        body: "Employees, departments, leave balances, and leave requests with their status.",
    },
    {
        title: "Finance",
        body: "Cash, invoices, journal entries, and accounting, with the limits of the history stated.",
    },
    {
        title: "Payroll",
        body: "Runs, compensation, and payroll rules, with each run's period and status.",
    },
    {
        title: "Documents",
        body: "A central document store. The surface is ready; this workspace has no uploaded documents yet.",
    },
    {
        title: "Reports",
        body: "Cross-department KPIs, reviewed templates, and exports from the same records.",
    },
    {
        title: "SkyAgent",
        body: "Ask across the workspace. Answers show the records used, and drafts stop before sending.",
    },
];

const inDevelopment = [
    {
        title: "Market intelligence",
        body: "Competitor and trend tracking. The signal collection engine is still being built.",
    },
    {
        title: "Sales Coach",
        body: "The console loads, but the coaching queue is empty. It is in development and not counted as an available capability.",
    },
    {
        title: "Audit Guardian",
        body: "The console loads, but the audit queue is empty. The review workflow is still in development.",
    },
    {
        title: "Revenue forecasting",
        body: "Requires at least three months of approved invoice history. Finance states this in the product instead of drawing a speculative line.",
    },
];

const trustFacts = [
    {
        icon: Database,
        title: "Workspace isolation",
        body: "Each account runs in its own tenant. Records never cross workspaces.",
    },
    {
        icon: Lock,
        title: "Roles and permissions",
        body: "Owner, admin, and member roles, with custom roles built from a fixed permission menu.",
    },
    {
        icon: Fingerprint,
        title: "Multi-factor authentication",
        body: "TOTP support with one-time backup codes.",
    },
    {
        icon: Code2,
        title: "Open source",
        body: "The codebase is public, so the security model can be checked.",
    },
];

function SectionHeading({
    eyebrow,
    title,
    description,
    id,
}: {
    eyebrow: string;
    title: string;
    description: ReactNode;
    id?: string;
}) {
    return (
        <RevealSection>
            <div className="grid gap-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:items-end lg:gap-16">
                <div>
                    <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                        {eyebrow}
                    </p>
                    <h2
                        id={id}
                        className="mt-4 text-balance font-display text-3xl font-semibold leading-[1.04] tracking-[-0.045em] text-marketing-ink sm:text-4xl lg:text-[3.15rem]"
                    >
                        {title}
                    </h2>
                </div>
                <div className="lg:pb-1">
                    <p className="max-w-xl text-pretty text-sm leading-relaxed text-marketing-muted sm:text-base">
                        {description}
                    </p>
                </div>
            </div>
        </RevealSection>
    );
}

function ModuleCopy({
    index,
    eyebrow,
    title,
    description,
    metrics,
    docsHref,
    docsLabel,
}: {
    index: string;
    eyebrow: string;
    title: string;
    description: string;
    metrics: { label: string; value: string }[];
    docsHref: string;
    docsLabel: string;
}) {
    return (
        <div className="lg:pt-2">
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                {index} · {eyebrow}
            </p>
            <h3 className="mt-4 text-balance font-display text-2xl font-semibold leading-[1.08] tracking-[-0.035em] text-marketing-ink sm:text-3xl">
                {title}
            </h3>
            <p className="mt-4 max-w-md text-pretty text-sm leading-relaxed text-marketing-muted sm:text-base">
                {description}
            </p>
            <dl className="mt-6 grid grid-cols-3 gap-3 border-t border-marketing-line/80 pt-4">
                {metrics.map((metric) => (
                    <div key={metric.label}>
                        <dt className="font-mono text-[9px] font-medium uppercase tracking-[0.14em] text-marketing-muted">
                            {metric.label}
                        </dt>
                        <dd className="mt-1 break-words font-display text-sm font-semibold tracking-tight text-marketing-ink sm:text-base">
                            {metric.value}
                        </dd>
                    </div>
                ))}
            </dl>
            <Link
                href={docsHref}
                className="mt-6 inline-flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-marketing-ink underline decoration-marketing-sky underline-offset-4 transition-colors hover:decoration-marketing-ink"
            >
                {docsLabel}
                <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </Link>
        </div>
    );
}

function StepCopy({
    index,
    label,
    title,
    description,
    docsHref,
    docsLabel,
}: {
    index: string;
    label: string;
    title: string;
    description: string;
    docsHref: string;
    docsLabel: string;
}) {
    return (
        <div className="mt-4">
            <div className="flex items-baseline gap-3 border-t border-marketing-line/80 pt-3">
                <span className="font-mono text-[10px] font-medium tracking-[0.14em] text-marketing-muted">
                    {index}
                </span>
                <span className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                    {label}
                </span>
            </div>
            <h3 className="mt-3 text-balance font-display text-xl font-semibold leading-[1.12] tracking-[-0.03em] text-marketing-ink sm:text-2xl">
                {title}
            </h3>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-marketing-muted">
                {description}
            </p>
            <Link
                href={docsHref}
                className="mt-4 inline-flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-marketing-ink underline decoration-marketing-sky underline-offset-4 transition-colors hover:decoration-marketing-ink"
            >
                {docsLabel}
                <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </Link>
        </div>
    );
}

function StatusList({
    tone,
    items,
}: {
    tone: "available" | "development";
    items: { title: string; body: string }[];
}) {
    const available = tone === "available";

    return (
        <div>
            <div className="flex items-center gap-2.5">
                <span
                    aria-hidden="true"
                    className={cn(
                        "size-2 rounded-full",
                        available ? "bg-emerald-500" : "bg-amber-500",
                    )}
                />
                <h3 className="font-display text-lg font-semibold tracking-tight text-marketing-ink">
                    {available ? "Available now" : "In development"}
                </h3>
                <span className="font-mono text-[10px] tracking-[0.14em] text-marketing-muted">
                    {items.length.toString().padStart(2, "0")}
                </span>
            </div>
            <dl className="mt-5 border-t border-marketing-line/80">
                {items.map((item) => (
                    <div
                        key={item.title}
                        className="grid gap-1 border-b border-marketing-line/80 py-4 sm:grid-cols-[minmax(0,0.55fr)_minmax(0,1fr)] sm:gap-6"
                    >
                        <dt className="font-display text-sm font-semibold text-marketing-ink">
                            {item.title}
                        </dt>
                        <dd className="text-sm leading-relaxed text-marketing-muted">
                            {item.body}
                        </dd>
                    </div>
                ))}
            </dl>
        </div>
    );
}

function ProductHero() {
    return (
        <section
            aria-labelledby="product-hero-heading"
            className="relative isolate -mt-20 overflow-hidden border-b border-marketing-line/70"
        >
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 -z-20 bg-[radial-gradient(circle_at_18%_18%,rgba(135,206,235,0.18),transparent_34%),radial-gradient(circle_at_86%_8%,rgba(255,216,198,0.16),transparent_30%)]"
            />
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-px bg-gradient-to-r from-transparent via-marketing-line to-transparent"
            />
            <div className="mx-auto w-full max-w-[1240px] px-6 pb-16 pt-36 sm:pt-40 lg:pb-24 lg:pt-44">
                <div className="grid gap-12 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)] lg:items-center lg:gap-16">
                    <div>
                        <h1
                            id="product-hero-heading"
                            className="sky-anim text-balance font-display text-[2.7rem] font-semibold leading-[0.96] tracking-[-0.055em] text-marketing-ink max-[359px]:text-[2.25rem] sm:text-5xl lg:text-[3.5rem] xl:text-[4.35rem]"
                            style={delay(0)}
                        >
                            The work,
                            <br />
                            not the wrapper.
                        </h1>
                        <p
                            className="sky-anim mt-6 max-w-lg text-pretty text-base leading-relaxed text-marketing-muted"
                            style={delay(90)}
                        >
                            Every screen below is the Skyrict workspace. Follow
                            HR, payroll, finance, reports, inventory, orders, and
                            CRM as they connect, then watch SkyAgent answer from
                            the same records.
                        </p>
                        <div
                            className="sky-anim mt-8 flex flex-col gap-3 sm:flex-row"
                            style={delay(180)}
                        >
                            <Button variant="brand" size="pill" asChild>
                                <Link href="/signup">
                                    Create an account
                                    <ArrowRight
                                        aria-hidden="true"
                                        className="size-4 transition-transform duration-200 group-hover/button:translate-x-0.5"
                                    />
                                </Link>
                            </Button>
                            <Button
                                variant="outline"
                                size="pill"
                                className="border-marketing-ink/15 bg-white/35 text-marketing-ink hover:bg-white/60 hover:text-marketing-ink"
                                asChild
                            >
                                <Link href="/contact">Try demo first</Link>
                            </Button>
                        </div>
                    </div>

                    <div className="relative">
                        <ProductFigure
                            src="/marketing/product/live-hr-overview-desktop.png"
                            mobileSrc="/marketing/product/live-hr-overview-mobile.png"
                            width={1110}
                            height={548}
                            mobileWidth={370}
                            mobileHeight={600}
                            alt="Skyrict HR workspace showing active employees, open leave requests, departments, and recent leave activity."
                            sizes="(min-width: 1024px) 620px, 100vw"
                            mobileSizes="100vw"
                            priority
                        />
                        <div className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 border-t border-marketing-line/80 pt-4 sm:grid-cols-4">
                            {heroMetrics.map((metric) => (
                                <div key={metric.label}>
                                    <p className="font-display text-lg font-semibold tracking-tight text-marketing-ink sm:text-xl">
                                        {metric.value}
                                    </p>
                                    <p className="mt-0.5 font-mono text-[9px] font-medium uppercase tracking-[0.14em] text-marketing-muted">
                                        {metric.label}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}

function OperatingCore() {
    return (
        <section
            id="operating-core"
            aria-labelledby="operating-core-heading"
            className="scroll-mt-24 border-b border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1240px] px-6 py-20 sm:py-24 lg:py-28">
                <SectionHeading
                    eyebrow="01 · The operating core"
                    id="operating-core-heading"
                    title="Four surfaces, one set of records."
                    description={
                        <>
                            HR, payroll, finance, and reports read from the
                            same tenant, so the numbers reconcile. The status
                            table later separates what ships today from what is
                            still being built.
                        </>
                    }
                />

                <div className="mt-14 space-y-20 sm:space-y-24 lg:mt-16 lg:space-y-28">
                    {moduleBlocks.map((block) => {
                        const figure = (
                            <ProductFigure
                                src={block.figure.src}
                                mobileSrc={block.figure.mobileSrc}
                                width={block.figure.width}
                                height={block.figure.height}
                                mobileWidth={block.figure.mobileWidth}
                                mobileHeight={block.figure.mobileHeight}
                                alt={block.figure.alt}
                                sizes={block.figure.sizes}
                            />
                        );
                        const copy = (
                            <ModuleCopy
                                index={block.index}
                                eyebrow={block.eyebrow}
                                title={block.title}
                                description={block.description}
                                metrics={block.metrics}
                                docsHref={block.docsHref}
                                docsLabel={block.docsLabel}
                            />
                        );

                        if (block.fullWidth) {
                            return (
                                <div key={block.index}>
                                    <div className="grid gap-8 lg:grid-cols-[minmax(0,0.62fr)_minmax(0,1fr)] lg:items-end lg:gap-16">
                                        <RevealSection variant="text">
                                            {copy}
                                        </RevealSection>
                                        <RevealSection
                                            variant="media"
                                            delay={40}
                                        >
                                            {figure}
                                        </RevealSection>
                                    </div>
                                </div>
                            );
                        }

                        return (
                            <div
                                key={block.index}
                                className="grid gap-8 lg:grid-cols-12 lg:items-start lg:gap-12"
                            >
                                <RevealSection
                                    variant="text"
                                    className={cn(
                                        "lg:col-span-5",
                                        block.reversed &&
                                            "lg:order-2 lg:col-start-8",
                                    )}
                                >
                                    {copy}
                                </RevealSection>
                                <RevealSection
                                    variant="media"
                                    delay={40}
                                    className={cn(
                                        "lg:col-span-7",
                                        block.reversed &&
                                            "lg:order-1 lg:col-start-1",
                                    )}
                                >
                                    {figure}
                                </RevealSection>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}

function SignalToWork() {
    const signal = signalSteps[0];
    const detailSteps = signalSteps.slice(1);

    return (
        <section
            id="signal-to-work"
            aria-labelledby="signal-to-work-heading"
            className="scroll-mt-24 border-b border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1240px] px-6 py-20 sm:py-24 lg:py-28">
                <SectionHeading
                    eyebrow="02 · From signal to work"
                    id="signal-to-work-heading"
                    title="The system points. The record explains. The agent drafts."
                    description="A workspace earns its place when it connects the signal to the next action. These four surfaces come from the same workspace, in the order the work moves."
                />

                <div className="mt-12 space-y-16 sm:space-y-20 lg:mt-14">
                    {/* The attention row is a wide, short surface. Give it the
                        full measure so the four counts stay legible. */}
                    <div>
                        <RevealSection variant="media">
                            <ProductFigure
                                src={signal.figure.src}
                                mobileSrc={signal.figure.mobileSrc}
                                width={signal.figure.width}
                                height={signal.figure.height}
                                mobileWidth={signal.figure.mobileWidth}
                                mobileHeight={signal.figure.mobileHeight}
                                alt={signal.figure.alt}
                                sizes="(min-width: 1240px) 1188px, 100vw"
                            />
                        </RevealSection>
                        <RevealSection variant="text" delay={40}>
                            <div className="grid gap-6 border-t border-marketing-line/80 pt-5 lg:grid-cols-[minmax(0,0.55fr)_minmax(0,1fr)] lg:gap-16">
                                <div>
                                    <div className="flex items-baseline gap-3">
                                        <span className="font-mono text-[10px] font-medium tracking-[0.14em] text-marketing-muted">
                                            {signal.index}
                                        </span>
                                        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                                            {signal.label}
                                        </span>
                                    </div>
                                    <h3 className="mt-3 text-balance font-display text-xl font-semibold leading-[1.12] tracking-[-0.03em] text-marketing-ink sm:text-2xl">
                                        {signal.title}
                                    </h3>
                                </div>
                                <div>
                                    <p className="max-w-2xl text-sm leading-relaxed text-marketing-muted sm:text-base">
                                        {signal.description}
                                    </p>
                                    <Link
                                        href={signal.docsHref}
                                        className="mt-4 inline-flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-marketing-ink underline decoration-marketing-sky underline-offset-4 transition-colors hover:decoration-marketing-ink"
                                    >
                                        {signal.docsLabel}
                                        <ArrowUpRight
                                            aria-hidden="true"
                                            className="size-3.5"
                                        />
                                    </Link>
                                </div>
                            </div>
                        </RevealSection>
                    </div>

                    {detailSteps.map((step, index) => {
                        const reversed = index % 2 === 1;

                        return (
                            <div
                                key={step.index}
                                className="grid gap-8 lg:grid-cols-12 lg:items-start lg:gap-12"
                            >
                                <RevealSection
                                    variant="text"
                                    className={cn(
                                        "lg:col-span-5",
                                        reversed &&
                                            "lg:order-2 lg:col-start-8",
                                    )}
                                >
                                    <StepCopy
                                        index={step.index}
                                        label={step.label}
                                        title={step.title}
                                        description={step.description}
                                        docsHref={step.docsHref}
                                        docsLabel={step.docsLabel}
                                    />
                                </RevealSection>
                                <RevealSection
                                    variant="media"
                                    delay={80}
                                    className={cn(
                                        "lg:col-span-7",
                                        reversed &&
                                            "lg:order-1 lg:col-start-1",
                                    )}
                                >
                                    <ProductFigure
                                        src={step.figure.src}
                                        mobileSrc={step.figure.mobileSrc}
                                        width={step.figure.width}
                                        height={step.figure.height}
                                        mobileWidth={step.figure.mobileWidth}
                                        mobileHeight={step.figure.mobileHeight}
                                        alt={step.figure.alt}
                                        sizes="(min-width: 1024px) 58vw, 100vw"
                                    />
                                </RevealSection>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}

function SkyAgentSection() {
    return (
        <section
            id="skyagent"
            aria-labelledby="skyagent-heading"
            className="scroll-mt-24 border-b border-marketing-line/70 bg-[linear-gradient(180deg,rgba(247,246,255,0.55),rgba(250,250,249,0))]"
        >
            <div className="mx-auto w-full max-w-[1240px] px-6 py-20 sm:py-24 lg:py-28">
                <SectionHeading
                    eyebrow="03 · SkyAgent"
                    id="skyagent-heading"
                    title="Ask. Watch it work. Check the records."
                    description="Ask across the workspace. SkyAgent reads the Zephyr Airlines opportunity, streams the follow-up, and keeps the records it used attached to the answer."
                />

                <RevealSection variant="text" className="mt-10">
                    <div className="grid gap-5 border-t border-marketing-line/80 pt-6 sm:grid-cols-3 sm:gap-8">
                        {[
                            {
                                title: "Reads the workspace",
                                body: "The prompt runs against CRM records, not a pasted export.",
                            },
                            {
                                title: "Shows the sources",
                                body: "The draft is tied to the opportunity, value, stage, and close date.",
                            },
                            {
                                title: "Stops at approval",
                                body: "SkyAgent drafts. A person decides what to send.",
                            },
                        ].map((item) => (
                            <div key={item.title}>
                                <p className="font-display text-sm font-semibold text-marketing-ink">
                                    {item.title}
                                </p>
                                <p className="mt-1 text-sm leading-relaxed text-marketing-muted">
                                    {item.body}
                                </p>
                            </div>
                        ))}
                    </div>
                </RevealSection>

                <RevealSection variant="media" className="mt-10">
                    <SkyAgentReplay />
                </RevealSection>

                <RevealSection variant="text" className="mt-6">
                    <div className="flex flex-col gap-4 border-t border-marketing-line/80 pt-4 sm:flex-row sm:items-start sm:justify-between sm:gap-10">
                        <p className="max-w-2xl text-xs leading-relaxed text-marketing-muted">
                            SkyAgent drafts the follow-up and stops before
                            sending. The records it used stay attached to the
                            answer.
                        </p>
                        <div className="grid shrink-0 grid-cols-3 gap-4 sm:gap-6">
                            {[
                                { label: "CRM leads", value: "12" },
                                { label: "Open pipeline", value: "$864,500" },
                                { label: "Draft status", value: "Not sent" },
                            ].map((metric) => (
                                <div key={metric.label}>
                                    <p className="font-display text-base font-semibold tracking-tight text-marketing-ink">
                                        {metric.value}
                                    </p>
                                    <p className="mt-0.5 font-mono text-[8px] font-medium uppercase tracking-[0.14em] text-marketing-muted">
                                        {metric.label}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

function StatusSection() {
    return (
        <section
            id="status"
            aria-labelledby="status-heading"
            className="scroll-mt-24 border-b border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1240px] px-6 py-20 sm:py-24 lg:py-28">
                <SectionHeading
                    eyebrow="04 · Status"
                    id="status-heading"
                    title="What ships today. What is still being built."
                    description="We would rather show you the empty state than pretend a finished feature exists. This is the current status of the workspace."
                />

                <RevealSection className="mt-12">
                    <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
                        <StatusList tone="available" items={availableModules} />
                        <StatusList
                            tone="development"
                            items={inDevelopment}
                        />
                    </div>
                </RevealSection>

                <RevealSection variant="text" className="mt-10">
                    <p className="max-w-3xl border-t border-marketing-line/80 pt-4 text-sm leading-relaxed text-marketing-muted">
                        Empty states are part of the product, not a marketing
                        gap. The document store has no uploaded files in this
                        workspace. The coaching and guardian consoles load their
                        queues, but the workflows behind them are still in
                        development. The finance forecast tells you when it needs
                        more approved history.
                    </p>
                </RevealSection>
            </div>
        </section>
    );
}

function TrustStrip() {
    return (
        <section
            id="trust"
            aria-labelledby="trust-heading"
            className="scroll-mt-24 border-b border-marketing-line/70"
        >
            <div className="mx-auto w-full max-w-[1240px] px-6 py-20 sm:py-24">
                <RevealSection>
                    <div className="grid gap-8 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)] lg:items-start lg:gap-16">
                        <div>
                            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                                Built into the account model
                            </p>
                            <h2
                                id="trust-heading"
                                className="mt-4 text-balance font-display text-3xl font-semibold leading-[1.06] tracking-[-0.04em] text-marketing-ink sm:text-4xl"
                            >
                                Trust is a product surface, not a badge.
                            </h2>
                            <p className="mt-5 max-w-md text-sm leading-relaxed text-marketing-muted sm:text-base">
                                Tenant isolation, roles, MFA, and email
                                verification are part of the account model. The
                                source is public, so the defaults can be
                                checked instead of asserted.
                            </p>
                            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                                <Button variant="brand" size="pill" asChild>
                                    <Link href="/docs/security/multi-factor-authentication">
                                        Read the security guide
                                    </Link>
                                </Button>
                                <Button variant="ghost" asChild>
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

                        <ul className="grid border-t border-marketing-line/80 sm:grid-cols-2">
                            {trustFacts.map(({ icon: Icon, title, body }) => (
                                <li
                                    key={title}
                                    className="border-b border-marketing-line/80 py-5 sm:odd:border-r sm:odd:pr-6 sm:even:pl-6"
                                >
                                    <Icon
                                        aria-hidden="true"
                                        className="size-4 text-marketing-ink"
                                    />
                                    <h3 className="mt-3 font-display text-sm font-semibold text-marketing-ink">
                                        {title}
                                    </h3>
                                    <p className="mt-1 text-sm leading-relaxed text-marketing-muted">
                                        {body}
                                    </p>
                                </li>
                            ))}
                        </ul>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export default function ProductPage() {
    return (
        <>
            <BreadcrumbJsonLd
                items={[
                    { name: "Home", path: "/" },
                    { name: "Product", path: "/product" },
                ]}
            />
            <ProductHero />
            <OperatingCore />
            <SignalToWork />
            <SkyAgentSection />
            <StatusSection />
            <TrustStrip />
            <Faq />
            <Cta
                eyebrow="See it with your records"
                title="Bring one workflow. See the whole system."
                description="Create a workspace, add a few records, and ask SkyAgent what needs attention. The answer comes with the records behind it."
                ctaLabel="Create an account"
                ctaHref="/signup"
                secondaryCtaLabel="Try demo"
                secondaryCtaHref="/demo/erp"
            />
        </>
    );
}
