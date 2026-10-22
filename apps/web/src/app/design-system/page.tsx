import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Logo, LogoMark } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/ui/error-panel";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/**
 * Living reference for the Skyrict design system.
 *
 * Development-only by default so an internal style guide never becomes a
 * public route. Set NEXT_PUBLIC_DESIGN_SYSTEM=true to expose it in a deployed
 * environment (for example an internal staging review).
 *
 * The canonical written spec lives in docs/design-system/README.md. If a token
 * changes in src/styles/globals.css, update both the spec and this page.
 */

const enabled =
    process.env.NODE_ENV !== "production" ||
    process.env.NEXT_PUBLIC_DESIGN_SYSTEM === "true";

export const metadata: Metadata = {
    title: "Design System",
    robots: { index: false, follow: false },
};

const CORE_TOKENS = [
    {
        name: "Background",
        token: "--background",
        value: "#f4fafd / #0b1119",
        className: "bg-background",
    },
    {
        name: "Foreground",
        token: "--foreground",
        value: "#0a2f3e / #e6edf5",
        className: "bg-foreground",
    },
    {
        name: "Card",
        token: "--card",
        value: "#ffffff / #111a24",
        className: "bg-card",
    },
    {
        name: "Muted",
        token: "--muted",
        value: "#edf7fc / #151f2b",
        className: "bg-muted",
    },
    {
        name: "Primary",
        token: "--primary",
        value: "#87ceeb / #6ec2e8",
        className: "bg-primary",
    },
    {
        name: "Secondary",
        token: "--secondary",
        value: "#e6f5fa / #1a2836",
        className: "bg-secondary",
    },
    {
        name: "Accent",
        token: "--accent",
        value: "#e6f5fa / #182636",
        className: "bg-accent",
    },
    {
        name: "Border",
        token: "--border",
        value: "#cae9f6 / #1f2c3d",
        className: "bg-border",
    },
] as const;

const STATUS_TOKENS = [
    {
        name: "Success",
        token: "--success",
        value: "#047857 / #34d399",
        solidClassName: "bg-success",
        softClassName: "bg-success/10 text-success",
    },
    {
        name: "Warning",
        token: "--warning",
        value: "#b45309 / #fbbf24",
        solidClassName: "bg-warning",
        softClassName: "bg-warning/10 text-warning",
    },
    {
        name: "Info",
        token: "--info",
        value: "#0369a1 / #38bdf8",
        solidClassName: "bg-info",
        softClassName: "bg-info/10 text-info",
    },
    {
        name: "Destructive",
        token: "--destructive",
        value: "#dc2626 / #f87171",
        solidClassName: "bg-destructive",
        softClassName: "bg-destructive/10 text-destructive",
    },
] as const;

const CHART_TOKENS = [
    "#87ceeb",
    "#4cb6e1",
    "#2199ca",
    "#114f68",
    "#aedef1",
] as const;

const WORLDS = [
    {
        name: "Sky",
        className: "",
        primary: "#87ceeb",
        darkPrimary: "#6ec2e8",
        use: "Marketing, docs, workspace, auth",
    },
    {
        name: "Agents",
        className: "theme-agents",
        primary: "#a5b4fc",
        darkPrimary: "#8b93f8",
        use: "Agent conversations and runs",
    },
    {
        name: "ERP",
        className: "theme-erp",
        primary: "#86efac",
        darkPrimary: "#55cf96",
        use: "Finance, inventory, CRM, HR",
    },
    {
        name: "Intelligence",
        className: "theme-intelligence",
        primary: "#38bdf8",
        darkPrimary: "#55c2ee",
        use: "Market signals and reporting",
    },
] as const;

const TYPE_SCALE = [
    ["Display XL", "36 → 48px", "600", "Marketing hero"],
    ["Display L", "30 → 36px", "600", "Section heading"],
    ["Display M", "24px", "600", "Page / dialog title"],
    ["Heading", "18px", "600", "Card title"],
    ["Body L", "16 → 18px", "400", "Lead paragraph"],
    ["Body", "15px", "400", "Docs, long form"],
    ["UI", "14px", "400–500", "Controls, tables"],
    ["Small", "12px", "400–500", "Helper, metadata"],
    ["Overline", "11–12px mono", "500", "Eyebrow, table header"],
] as const;

const SPACING = [1, 2, 3, 4, 6, 8, 12, 16] as const;

const RADII = [
    { label: "sm", className: "rounded-sm" },
    { label: "md", className: "rounded-md" },
    { label: "lg", className: "rounded-lg" },
    { label: "xl", className: "rounded-xl" },
    { label: "2xl", className: "rounded-2xl" },
    { label: "4xl", className: "rounded-4xl" },
] as const;

function Section({
    id,
    title,
    intro,
    children,
}: {
    id: string;
    title: string;
    intro: string;
    children: React.ReactNode;
}) {
    return (
        <section
            id={id}
            aria-labelledby={`${id}-title`}
            className="scroll-mt-20"
        >
            <div className="max-w-2xl">
                <h2
                    id={`${id}-title`}
                    className="font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl"
                >
                    {title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {intro}
                </p>
            </div>
            <div className="mt-6">{children}</div>
        </section>
    );
}

function Panel({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div
            className={cn(
                "rounded-2xl border border-border bg-card p-5 text-card-foreground",
                className,
            )}
        >
            {children}
        </div>
    );
}

function PanelTitle({ children }: { children: React.ReactNode }) {
    return (
        <h3 className="font-display text-sm font-semibold tracking-tight text-foreground">
            {children}
        </h3>
    );
}

function Swatch({
    name,
    token,
    value,
    className,
}: {
    name: string;
    token: string;
    value: string;
    className: string;
}) {
    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className={cn("h-14 border-b border-border", className)} />
            <div className="space-y-0.5 px-3 py-2">
                <p className="text-xs font-medium text-foreground">{name}</p>
                <code className="block font-mono text-[10px] text-muted-foreground">
                    {token}
                </code>
                <p className="font-mono text-[10px] text-muted-foreground">
                    {value}
                </p>
            </div>
        </div>
    );
}

export default function DesignSystemPage() {
    if (!enabled) {
        notFound();
    }

    return (
        <div className="min-h-dvh bg-background text-foreground">
            <div className="mx-auto w-full max-w-6xl px-6 py-12 sm:py-16">
                <header className="border-b border-border pb-8">
                    <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary">Living reference</Badge>
                        <Badge variant="outline">v1.0</Badge>
                        <Badge variant="outline">Sky theme</Badge>
                    </div>
                    <h1 className="mt-5 font-display text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
                        Skyrict Design System
                    </h1>
                    <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted-foreground">
                        Calm density, one clear action, and a sky-blue
                        signature. This page renders the live tokens and
                        primitives used across marketing, the workspace, ERP,
                        agents, and intelligence. The written spec lives in{" "}
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                            docs/design-system/README.md
                        </code>
                        .
                    </p>
                    <div className="mt-6 flex flex-wrap items-end gap-6">
                        <Logo />
                        <LogoMark tone="erp" />
                        <LogoMark tone="ai" />
                    </div>
                </header>

                <div className="mt-12 space-y-16">
                    <Section
                        id="principles"
                        title="Principles"
                        intro="Six rules that decide what ships. When a design is ambiguous, resolve it in this order."
                    >
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {[
                                [
                                    "Signals over noise",
                                    "One primary action per surface. Decoration must clarify state or hierarchy.",
                                ],
                                [
                                    "Calm density",
                                    "Neutrals, line height, and a single accent carry dense operational data.",
                                ],
                                [
                                    "Sky is the signature",
                                    "The sky accent marks interaction and new importance — never body areas.",
                                ],
                                [
                                    "One product, many worlds",
                                    "Modules change hue, never structure, spacing, or typography.",
                                ],
                                [
                                    "Accessible by default",
                                    "Focus, contrast, labels, and reduced motion are part of the component.",
                                ],
                                [
                                    "Tokens, not hex",
                                    "Product code consumes semantic tokens; raw values live in globals.css.",
                                ],
                            ].map(([title, body]) => (
                                <Panel key={title}>
                                    <PanelTitle>{title}</PanelTitle>
                                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                                        {body}
                                    </p>
                                </Panel>
                            ))}
                        </div>
                    </Section>

                    <Section
                        id="colour"
                        title="Colour"
                        intro="Semantic tokens resolve to a light and dark value. The swatches below render the active theme; hex pairs list light / dark."
                    >
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            {CORE_TOKENS.map((token) => (
                                <Swatch key={token.token} {...token} />
                            ))}
                        </div>

                        <div className="mt-8 grid gap-6 lg:grid-cols-2">
                            <Panel>
                                <PanelTitle>Status</PanelTitle>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    Use the soft pattern by default; solid fills
                                    only for decisive confirmation.
                                </p>
                                <div className="mt-4 space-y-3">
                                    {STATUS_TOKENS.map((status) => (
                                        <div
                                            key={status.token}
                                            className="flex items-center gap-3"
                                        >
                                            <span
                                                className={cn(
                                                    "size-8 shrink-0 rounded-lg",
                                                    status.solidClassName,
                                                )}
                                            />
                                            <div className="min-w-0 flex-1">
                                                <p className="text-xs font-medium">
                                                    {status.name}
                                                </p>
                                                <p className="font-mono text-[10px] text-muted-foreground">
                                                    {status.token} ·{" "}
                                                    {status.value}
                                                </p>
                                            </div>
                                            <span
                                                className={cn(
                                                    "rounded-full px-2 py-0.5 text-xs font-medium",
                                                    status.softClassName,
                                                )}
                                            >
                                                {status.name}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </Panel>

                            <Panel>
                                <PanelTitle>Charts</PanelTitle>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    Order series 1 → 5. Always pair colour with
                                    labels or direct annotations.
                                </p>
                                <div className="mt-4 flex overflow-hidden rounded-lg">
                                    {CHART_TOKENS.map((hex, index) => (
                                        <div
                                            key={hex}
                                            className="flex h-20 flex-1 items-end justify-center pb-2"
                                            style={{
                                                backgroundColor: hex,
                                            }}
                                        >
                                            <span className="font-mono text-[10px] text-[#0a2f3e]">
                                                {index + 1}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                                <p className="mt-3 font-mono text-[10px] text-muted-foreground">
                                    chart-1 → chart-5
                                </p>
                            </Panel>
                        </div>

                        <div className="mt-8">
                            <h3 className="font-display text-sm font-semibold">
                                Module worlds
                            </h3>
                            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                {WORLDS.map((world) => (
                                    <div
                                        key={world.name}
                                        className={cn(
                                            "rounded-2xl border border-border bg-card p-4 text-card-foreground",
                                            world.className,
                                        )}
                                    >
                                        <div className="flex items-center justify-between">
                                            <span className="font-display text-sm font-semibold">
                                                {world.name}
                                            </span>
                                            <span className="size-6 rounded-lg bg-primary" />
                                        </div>
                                        <p className="mt-3 font-mono text-[10px] text-muted-foreground">
                                            {world.primary} /{" "}
                                            {world.darkPrimary}
                                        </p>
                                        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                                            {world.use}
                                        </p>
                                        <div className="mt-3 flex gap-1.5">
                                            <span className="h-1.5 flex-1 rounded-full bg-primary" />
                                            <span className="h-1.5 flex-1 rounded-full bg-primary/50" />
                                            <span className="h-1.5 flex-1 rounded-full bg-muted" />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </Section>

                    <Section
                        id="typography"
                        title="Typography"
                        intro="Inter for the interface, Bricolage Grotesque for headings and the wordmark, JetBrains Mono for code and overlines."
                    >
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Panel>
                                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">
                                    Display
                                </p>
                                <p className="mt-2 font-display text-4xl font-semibold leading-tight tracking-tight">
                                    Make tomorrow&apos;s calls on today&apos;s
                                    signals.
                                </p>
                                <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                                    Bricolage Grotesque · 600 · tracking-tight
                                </p>
                            </Panel>
                            <Panel>
                                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">
                                    Interface
                                </p>
                                <p className="mt-2 text-base leading-relaxed">
                                    Skyrict pairs live operations with
                                    continuous market signals. Agents read both
                                    and return the next move.
                                </p>
                                <p className="mt-3 text-sm text-muted-foreground">
                                    Muted supporting copy uses the
                                    muted-foreground token and stays secondary.
                                </p>
                                <p className="mt-4 font-mono text-xs">
                                    const runway = 18; // months
                                </p>
                                <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                                    Inter · 400–500 · 14–16px
                                </p>
                            </Panel>
                        </div>

                        <div className="mt-6 overflow-x-auto rounded-2xl border border-border bg-card">
                            <table className="w-full min-w-[36rem] text-left text-sm">
                                <thead className="bg-muted/50 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                    <tr>
                                        <th className="px-4 py-2 font-medium">
                                            Level
                                        </th>
                                        <th className="px-4 py-2 font-medium">
                                            Size
                                        </th>
                                        <th className="px-4 py-2 font-medium">
                                            Weight
                                        </th>
                                        <th className="px-4 py-2 font-medium">
                                            Usage
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {TYPE_SCALE.map(
                                        ([level, size, weight, use]) => (
                                            <tr
                                                key={level}
                                                className="border-t border-border/60"
                                            >
                                                <td className="px-4 py-2 font-medium">
                                                    {level}
                                                </td>
                                                <td className="px-4 py-2 font-mono text-xs text-muted-foreground">
                                                    {size}
                                                </td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {weight}
                                                </td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {use}
                                                </td>
                                            </tr>
                                        ),
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Section>

                    <Section
                        id="space"
                        title="Space, layout, radius"
                        intro="A 4px base scale, a 1152px content width, and a 10px base radius keep every surface on the same rhythm."
                    >
                        <div className="grid gap-6 lg:grid-cols-3">
                            <Panel>
                                <PanelTitle>Spacing</PanelTitle>
                                <div className="mt-4 flex items-end gap-2">
                                    {SPACING.map((step) => (
                                        <div key={step} className="text-center">
                                            <div
                                                className="rounded-sm bg-primary/30 ring-1 ring-primary/40"
                                                style={{
                                                    width: step * 4,
                                                    height: step * 4,
                                                }}
                                            />
                                            <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
                                                {step}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                                    4 · 8 · 12 · 16 · 24 · 32 · 48 · 64px
                                </p>
                            </Panel>

                            <Panel>
                                <PanelTitle>Radius</PanelTitle>
                                <div className="mt-4 flex flex-wrap gap-2">
                                    {RADII.map((radius) => (
                                        <div
                                            key={radius.label}
                                            className={cn(
                                                "flex size-12 items-center justify-center border border-border bg-secondary font-mono text-[10px] text-secondary-foreground",
                                                radius.className,
                                            )}
                                        >
                                            {radius.label}
                                        </div>
                                    ))}
                                </div>
                                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                                    Base 10px; cards use xl, controls use lg,
                                    badges are pills.
                                </p>
                            </Panel>

                            <Panel>
                                <PanelTitle>Elevation</PanelTitle>
                                <div className="mt-4 space-y-2">
                                    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs">
                                        Surface · border only
                                    </div>
                                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-lg">
                                        Floating · border + shadow
                                    </div>
                                    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-[0_24px_60px_-24px_rgba(10,47,62,0.35)]">
                                        Hero · one long soft shadow
                                    </div>
                                </div>
                            </Panel>
                        </div>
                    </Section>

                    <Section
                        id="components"
                        title="Components"
                        intro="Primitives from components/ui. Compose them instead of restyling raw HTML."
                    >
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Panel>
                                <PanelTitle>Buttons</PanelTitle>
                                <div className="mt-4 flex flex-wrap items-center gap-2">
                                    <Button>Create invoice</Button>
                                    <Button variant="secondary">
                                        Secondary
                                    </Button>
                                    <Button variant="outline">Outline</Button>
                                    <Button variant="ghost">Ghost</Button>
                                    <Button variant="destructive">
                                        Delete
                                    </Button>
                                    <Button variant="link">Link</Button>
                                    <Button disabled>Disabled</Button>
                                </div>
                                <div className="mt-4 flex flex-wrap items-end gap-2">
                                    <Button size="xs">xs</Button>
                                    <Button size="sm">sm</Button>
                                    <Button>default</Button>
                                    <Button size="lg">lg</Button>
                                </div>
                                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                                    One primary action per view. Focus ring is
                                    3px at ring/50; press moves 1px.
                                </p>
                            </Panel>

                            <Panel>
                                <PanelTitle>Badges</PanelTitle>
                                <div className="mt-4 flex flex-wrap items-center gap-2">
                                    <Badge>New</Badge>
                                    <Badge variant="secondary">Beta</Badge>
                                    <Badge variant="outline">Draft</Badge>
                                    <Badge variant="ghost">Quiet</Badge>
                                    <Badge variant="destructive">Overdue</Badge>
                                </div>
                                <div className="mt-4 flex flex-wrap items-center gap-2">
                                    <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
                                        Paid
                                    </span>
                                    <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
                                        Pending
                                    </span>
                                    <span className="rounded-full bg-info/10 px-2 py-0.5 text-xs font-medium text-info">
                                        Info
                                    </span>
                                    <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
                                        Failed
                                    </span>
                                </div>
                                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                                    Status always includes a word, never colour
                                    alone.
                                </p>
                            </Panel>

                            <Panel>
                                <PanelTitle>Form controls</PanelTitle>
                                <div className="mt-4 space-y-3">
                                    <div className="space-y-1.5">
                                        <Label htmlFor="ds-email">
                                            Work email
                                        </Label>
                                        <Input
                                            id="ds-email"
                                            type="email"
                                            placeholder="name@company.com"
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            Use a visible label, not a
                                            placeholder.
                                        </p>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label htmlFor="ds-note">Note</Label>
                                        <Textarea
                                            id="ds-note"
                                            placeholder="Add context for the approver"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label htmlFor="ds-error">
                                            Billing email
                                        </Label>
                                        <Input
                                            id="ds-error"
                                            aria-invalid="true"
                                            defaultValue="not-an-email"
                                        />
                                        <p className="text-xs text-destructive">
                                            Enter a valid email address.
                                        </p>
                                    </div>
                                </div>
                            </Panel>

                            <Panel>
                                <PanelTitle>Feedback & loading</PanelTitle>
                                <div className="mt-4 flex items-center gap-4">
                                    <Spinner className="size-6" />
                                    <Spinner className="size-4 text-primary" />
                                    <span className="text-sm text-muted-foreground">
                                        Shared spinner · 0.7s
                                    </span>
                                </div>
                                <div className="mt-5 space-y-2">
                                    <Skeleton className="h-8 w-full" />
                                    <SkeletonText className="w-3/4" />
                                    <SkeletonText className="w-1/2" />
                                </div>
                                <div className="mt-5">
                                    <ErrorPanel
                                        title="Plans are temporarily unavailable"
                                        message="We could not load pricing. Your workspace data is unchanged. Try again in a moment."
                                    />
                                </div>
                            </Panel>
                        </div>
                    </Section>

                    <Section
                        id="motion"
                        title="Motion"
                        intro="Motion explains a change. It never delays interaction and always yields to reduced-motion preferences."
                    >
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            {[
                                ["Fast", "150ms", "Hover, press, toggles"],
                                ["Base", "200ms", "Colour transitions"],
                                ["Enter", "380ms", "Popovers, reveals"],
                                [
                                    "Ambient",
                                    "1.6–2.8s",
                                    "Shimmer, pulse, thinking",
                                ],
                            ].map(([name, duration, use]) => (
                                <Panel key={name}>
                                    <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                        {name}
                                    </p>
                                    <p className="mt-1 font-display text-lg font-semibold">
                                        {duration}
                                    </p>
                                    <p className="mt-1 text-xs text-muted-foreground">
                                        {use}
                                    </p>
                                </Panel>
                            ))}
                        </div>
                        <Panel className="mt-3">
                            <p className="text-xs leading-relaxed text-muted-foreground">
                                Entrance easing:{" "}
                                <code className="font-mono">
                                    cubic-bezier(0.22, 1, 0.36, 1)
                                </code>
                                . Named utilities:{" "}
                                <code className="font-mono">.sky-anim</code>,{" "}
                                <code className="font-mono">.sky-pop-in</code>,{" "}
                                <code className="font-mono">
                                    .sky-recommendation
                                </code>
                                , <code className="font-mono">.skeleton</code>,{" "}
                                <code className="font-mono">
                                    .chat-thinking
                                </code>
                                . Disable or reduce every loop under{" "}
                                <code className="font-mono">
                                    prefers-reduced-motion
                                </code>
                                .
                            </p>
                        </Panel>
                    </Section>

                    <Section
                        id="accessibility"
                        title="Accessibility"
                        intro="Target WCAG 2.2 AA. The component defaults carry most of the work; authors own labels, order, and state."
                    >
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {[
                                [
                                    "Focus is never hidden",
                                    "Every control keeps a visible focus-visible ring. Never remove outline without a replacement.",
                                ],
                                [
                                    "Colour is never alone",
                                    "Status pairs colour with a word or icon. Charts carry direct labels.",
                                ],
                                [
                                    "Labels are permanent",
                                    "Inputs use visible labels; placeholders are examples only.",
                                ],
                                [
                                    "Targets stay reachable",
                                    "Aim for 44×44px on touch. Compact 24–32px controls are desktop-only.",
                                ],
                                [
                                    "Motion yields",
                                    "All animation collapses under prefers-reduced-motion; no autoplay video.",
                                ],
                                [
                                    "Zoom survives",
                                    "Layouts hold at 200% zoom and 320px width without page-level horizontal scroll.",
                                ],
                            ].map(([title, body]) => (
                                <Panel key={title}>
                                    <PanelTitle>{title}</PanelTitle>
                                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                                        {body}
                                    </p>
                                </Panel>
                            ))}
                        </div>
                    </Section>

                    <Section
                        id="usage"
                        title="Usage rules"
                        intro="The quickest way to keep the system coherent is to make the right thing the easy thing."
                    >
                        <div className="grid gap-3 lg:grid-cols-2">
                            <Panel>
                                <PanelTitle>Do</PanelTitle>
                                <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                                    <li>
                                        Use{" "}
                                        <code className="font-mono">
                                            bg-primary
                                        </code>
                                        ,{" "}
                                        <code className="font-mono">
                                            text-muted-foreground
                                        </code>
                                        , and{" "}
                                        <code className="font-mono">
                                            border-border
                                        </code>
                                        .
                                    </li>
                                    <li>
                                        Put one primary button on the surface
                                        and make secondary actions outline or
                                        ghost.
                                    </li>
                                    <li>
                                        Check light, dark, and the active module
                                        world before shipping.
                                    </li>
                                    <li>
                                        Use{" "}
                                        <code className="font-mono">
                                            tabular-nums
                                        </code>{" "}
                                        for money and metrics.
                                    </li>
                                    <li>
                                        Mount portalled surfaces with{" "}
                                        <code className="font-mono">
                                            getThemeContainer()
                                        </code>
                                        .
                                    </li>
                                </ul>
                            </Panel>
                            <Panel>
                                <PanelTitle>Don&apos;t</PanelTitle>
                                <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                                    <li>
                                        Don&apos;t use raw hex or{" "}
                                        <code className="font-mono">
                                            hsl(var(--token))
                                        </code>{" "}
                                        in product code.
                                    </li>
                                    <li>
                                        Don&apos;t hand-roll spinners or
                                        skeletons; use the shared primitives.
                                    </li>
                                    <li>
                                        Don&apos;t use destructive colour for
                                        decoration or emphasis.
                                    </li>
                                    <li>
                                        Don&apos;t offer retry on a failed POST.
                                    </li>
                                    <li>
                                        Don&apos;t introduce a second page-level
                                        scroll container.
                                    </li>
                                </ul>
                            </Panel>
                        </div>
                    </Section>
                </div>

                <footer className="mt-16 border-t border-border pt-6 text-xs text-muted-foreground">
                    Source of truth:{" "}
                    <code className="font-mono">
                        apps/web/src/styles/globals.css
                    </code>
                    . Written spec:{" "}
                    <code className="font-mono">
                        docs/design-system/README.md
                    </code>
                    . This route is development-only unless{" "}
                    <code className="font-mono">NEXT_PUBLIC_DESIGN_SYSTEM</code>{" "}
                    is set to <code className="font-mono">true</code>.
                </footer>
            </div>
        </div>
    );
}
