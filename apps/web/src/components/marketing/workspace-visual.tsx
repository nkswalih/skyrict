import {
    Activity,
    BarChart3,
    Boxes,
    Bot,
    ChevronDown,
    CircleCheck,
    Search,
    Settings,
    TrendingUp,
    type LucideIcon,
} from "lucide-react";

import { AiGlyph } from "@/components/brand/logo";
import { SignalSparkline } from "@/components/marketing/signal-sparkline";
import { cn } from "@/lib/utils";

const delay = (ms: number) => ({ "--sky-delay": `${ms}ms` }) as React.CSSProperties;

const stats = [
    { label: "Inventory cover", value: "2 days", note: "size M, below reorder" },
    { label: "Cash on hand", value: "$84.2K", note: "covers restock PO" },
    { label: "Open orders", value: "14", note: "3 marked urgent" },
    { label: "Sales velocity", value: "+9%", note: "w/w, earbuds +18%" },
];

const inventoryRows = [
    { sku: "EARB-M", name: "Earbuds, size M", stock: "124", cover: "2d", status: "Low" },
    { sku: "EARB-L", name: "Earbuds, size L", stock: "512", cover: "8d", status: "OK" },
    { sku: "CBL-1M", name: "USB-C cable, 1 m", stock: "318", cover: "11d", status: "OK" },
    { sku: "PWR-65W", name: "65 W charger", stock: "96", cover: "3d", status: "Low" },
    { sku: "CBL-2M", name: "USB-C cable, 2 m", stock: "42", cover: "5d", status: "Reorder" },
];

const activityItems = [
    { time: "09:42", text: "Signal update: Trends +18% w/w" },
    { time: "09:40", text: "Agent finished analysis for size M" },
    { time: "09:35", text: "Order ORD-2081 flagged: cover low" },
    { time: "09:28", text: "Payroll run approved by Admin" },
];

const evidence = [
    "Demand +18% w/w across Trends and Reddit",
    "Cover 2 days, below reorder point of 5",
    "Cash $84.2K on hand, PO of $9.4K close",
    "14 open orders, none inbound for size M",
];

function RailItem({
    icon: Icon,
    label,
    active,
}: {
    icon: LucideIcon;
    label: string;
    active?: boolean;
}) {
    return (
        <span
            title={label}
            aria-label={label}
            className={cn(
                "flex size-8 items-center justify-center rounded-lg",
                active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground/70 hover:text-foreground",
            )}
        >
            <Icon aria-hidden="true" className="size-4" />
        </span>
    );
}

function StatusChip({ status }: { status: string }) {
    const tone =
        status === "Low"
            ? "border-primary/40 bg-primary/10 text-primary"
            : status === "Reorder"
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-border bg-muted/40 text-muted-foreground";
    return (
        <span
            className={cn(
                "inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium",
                tone,
            )}
        >
            {status}
        </span>
    );
}

function MarketPanel() {
    return (
        <div
            className="sky-anim overflow-hidden rounded-lg border border-border/70"
            style={delay(760)}
        >
            <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-3.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Market movement
                </p>
                <span
                    className="sky-anim sky-pop-in flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
                    style={delay(1350)}
                >
                    <span
                        className="sky-anim sky-blink size-1.5 rounded-full bg-primary"
                        style={delay(1200)}
                        aria-hidden="true"
                    />
                    Signal update
                </span>
            </div>
            <div className="space-y-2.5 p-3.5">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-foreground">
                            Earbuds demand, size M
                        </p>
                        <p className="mt-0.5 text-[10px] text-muted-foreground">
                            Google Trends, last 8 weeks
                        </p>
                    </div>
                    <span
                        className="sky-anim sky-pop-in shrink-0 rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-primary"
                        style={delay(1250)}
                    >
                        +18% w/w
                    </span>
                </div>
                <div className="[&_svg]:h-10 [&_svg]:w-full">
                    <SignalSparkline label="Earbuds search demand rising over eight weeks" />
                </div>
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {["Google Trends", "Reddit", "YouTube"].map((source) => (
                        <span
                            key={source}
                            className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground"
                        >
                            {source}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
}

function AgentPanel() {
    return (
        <div
            className="sky-anim relative overflow-hidden rounded-lg border border-border/70"
            style={delay(800)}
        >
            <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-3.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Agent recommendation
                </p>
                <span className="flex size-6 items-center justify-center rounded-md border border-primary/25 bg-primary/10 text-primary">
                    <AiGlyph aria-hidden="true" className="size-3.5" />
                </span>
            </div>
            <div className="relative">
                <div
                    className="sky-anim sky-analyzing absolute inset-0 z-10 flex flex-col items-start justify-center gap-1.5 bg-card px-4 motion-reduce:hidden"
                    style={delay(1750)}
                >
                    <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                        <span
                            className="sky-blink sky-anim size-1.5 rounded-full bg-primary"
                            style={delay(0)}
                            aria-hidden="true"
                        />
                        Agent is checking stock, cash, and orders
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                        Reading live ERP state against the signal
                    </span>
                </div>

                <div
                    className="sky-anim sky-recommendation space-y-2.5 p-3.5"
                    style={delay(2050)}
                >
                    <div
                        className="sky-highlight rounded-md border border-primary/40 bg-primary/5 px-3.5 py-3"
                        style={delay(2750)}
                    >
                        <p className="text-xs font-semibold text-foreground">
                            Restock size M, 600 units
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                            Vendor lead 5 days, delivery next Friday
                        </p>
                    </div>
                    <ul className="space-y-1.5">
                        {evidence.map((line) => (
                            <li
                                key={line}
                                className="flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground"
                            >
                                <CircleCheck
                                    aria-hidden="true"
                                    className="mt-0.5 size-3 shrink-0 text-primary/70"
                                />
                                {line}
                            </li>
                        ))}
                    </ul>
                    <div className="flex items-center gap-3 pt-1">
                        <span className="rounded-md bg-primary px-2.5 py-1 text-[11px] font-semibold text-primary-foreground">
                            Approve
                        </span>
                        <span className="text-[11px] font-medium text-primary">Adjust</span>
                        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                            Analyzed 09:40 UTC
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}

function InventoryPanel() {
    return (
        <div
            className="sky-anim overflow-hidden rounded-lg border border-border/70"
            style={delay(880)}
        >
            <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-3.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Inventory
                </p>
                <span className="font-mono text-[10px] text-muted-foreground">
                    128 SKUs, 3 low
                </span>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead>
                        <tr className="border-b border-border/60 text-[10px] uppercase tracking-wider text-muted-foreground">
                            <th className="px-3.5 py-2 font-medium">Product</th>
                            <th className="px-3.5 py-2 text-right font-medium">Stock</th>
                            <th className="px-3.5 py-2 text-right font-medium">Cover</th>
                            <th className="px-3.5 py-2 text-right font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inventoryRows.map((row, index) => (
                            <tr
                                key={row.sku}
                                className="sky-row border-b border-border/40 last:border-0"
                                style={delay(1000 + index * 70)}
                            >
                                <td className="px-3.5 py-2">
                                    <div className="flex items-center gap-2">
                                        <span
                                            aria-hidden="true"
                                            className="size-1.5 shrink-0 rounded-full bg-muted-foreground/40"
                                        />
                                        <span className="text-xs font-medium text-foreground">
                                            {row.name}
                                        </span>
                                        <span className="font-mono text-[10px] text-muted-foreground">
                                            {row.sku}
                                        </span>
                                    </div>
                                </td>
                                <td className="px-3.5 py-2 text-right font-mono text-[11px] tabular-nums text-foreground">
                                    {row.stock}
                                </td>
                                <td className="px-3.5 py-2 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                                    {row.cover}
                                </td>
                                <td className="px-3.5 py-2 text-right">
                                    <StatusChip status={row.status} />
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function ActivityPanel() {
    return (
        <div
            className="sky-anim overflow-hidden rounded-lg border border-border/70"
            style={delay(920)}
        >
            <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-3.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Recent activity
                </p>
                <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />
            </div>
            <ul className="divide-y divide-border/40">
                {activityItems.map((item, index) => (
                    <li
                        key={item.time}
                        className="sky-row flex items-center gap-3 px-3.5 py-2.5"
                        style={delay(1040 + index * 70)}
                    >
                        <span
                            aria-hidden="true"
                            className={cn(
                                "size-1.5 shrink-0 rounded-full",
                                index === 0 ? "bg-primary" : "bg-muted-foreground/30",
                            )}
                        />
                        <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">
                            {item.text}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                            {item.time}
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function WorkspaceVisual() {
    return (
        <div
            className="sky-anim overflow-hidden rounded-xl border border-border bg-card shadow-[0_24px_60px_-24px_rgba(10,47,62,0.35)]"
            style={delay(480)}
        >
            <div className="flex">
                <aside className="hidden w-12 shrink-0 flex-col items-center gap-1 border-r border-border/60 bg-muted/20 py-3 sm:flex">
                    <span className="mb-1.5 flex size-7 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                        <AiGlyph aria-hidden="true" className="size-4" />
                    </span>
                    <RailItem icon={Activity} label="Pulse" active />
                    <RailItem icon={Boxes} label="Operations" />
                    <RailItem icon={TrendingUp} label="Intelligence" />
                    <RailItem icon={Bot} label="Agents" />
                    <RailItem icon={BarChart3} label="Reports" />
                    <div className="mt-auto flex flex-col items-center gap-1 pt-3">
                        <span className="flex size-8 items-center justify-center rounded-lg text-muted-foreground/70">
                            <Settings aria-hidden="true" className="size-4" />
                        </span>
                        <span aria-hidden="true" className="mt-1 size-6 rounded-full bg-primary/20" />
                    </div>
                </aside>

                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3 border-b border-border/60 px-4 py-2.5">
                        <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                            Meridian Supply Co.
                            <ChevronDown
                                aria-hidden="true"
                                className="size-3.5 text-muted-foreground"
                            />
                        </div>
                        <span className="hidden items-center rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground md:inline-flex">
                            beta
                        </span>
                        <span
                            aria-hidden="true"
                            className="mx-1 hidden h-4 w-px bg-border/70 sm:block"
                        />
                        <span className="hidden text-xs text-muted-foreground sm:inline">
                            Business Pulse
                        </span>
                        <div className="ml-auto flex items-center gap-3">
                            <span className="hidden items-center gap-1.5 rounded-md border border-border/70 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground lg:flex">
                                <Search aria-hidden="true" className="size-3" />
                                Search SKUs, orders, signals
                            </span>
                            <span className="flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                                <span
                                    className="sky-anim sky-blink size-1.5 rounded-full bg-primary"
                                    style={delay(1100)}
                                    aria-hidden="true"
                                />
                                Live
                            </span>
                            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                                09:42 UTC
                            </span>
                        </div>
                    </div>

                    <div className="space-y-4 p-4 sm:p-5">
                        <div
                            className="sky-anim sky-enter-fade flex items-start justify-between gap-3"
                            style={delay(640)}
                        >
                            <div>
                                <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                                    Business Pulse
                                </h2>
                                <p className="mt-0.5 text-[11px] text-muted-foreground">
                                    Daily operating picture, across ERP and market sources
                                </p>
                            </div>
                            <span className="rounded-md border border-border bg-muted/40 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                Refreshed 2 min ago
                            </span>
                        </div>

                        <dl
                            className="sky-anim grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border/70 bg-border/70 sm:grid-cols-4"
                            style={delay(700)}
                        >
                            {stats.map((stat) => (
                                <div key={stat.label} className="bg-card px-3.5 py-3">
                                    <dt className="text-[11px] font-medium text-muted-foreground">
                                        {stat.label}
                                    </dt>
                                    <dd className="mt-1 font-display text-lg font-semibold tabular-nums tracking-tight text-foreground">
                                        {stat.value}
                                    </dd>
                                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                                        {stat.note}
                                    </p>
                                </div>
                            ))}
                        </dl>

                        <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
                            <MarketPanel />
                            <AgentPanel />
                        </div>

                        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
                            <InventoryPanel />
                            <ActivityPanel />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export { WorkspaceVisual };