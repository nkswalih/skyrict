/**
 * Mock inbox for the public demo.
 *
 * The live bell hydrates from `/api/v1/notifications/*`. The demo must never
 * make that call (the network guard blocks it and E2E asserts zero `/api/**`),
 * so the inbox ships with a deterministic set of operational alerts that point
 * at the seeded demo records. Read/snooze state lives in the demo snapshot so
 * the badge survives navigation and reloads.
 */

export type DemoNotificationSeverity = "low" | "medium" | "high" | "critical";

export interface DemoNotification {
  id: string;
  title: string;
  body: string;
  category: string;
  module: string;
  severity: DemoNotificationSeverity;
  occurredAt: string;
  pinned: boolean;
  actionHref?: string;
  actionLabel?: string;
}

export const DEMO_NOTIFICATIONS: DemoNotification[] = [
  {
    id: "ntf-1",
    title: "Approval needed · SO-2026-089",
    body: "Vastraline Industries Ltd is 18% above its rolling credit average. Finance sign-off is required before the order can be fulfilled.",
    category: "approvals",
    module: "orders",
    severity: "high",
    occurredAt: "2026-10-25T06:42:00.000Z",
    pinned: true,
    actionHref: "/demo/erp/orders",
    actionLabel: "Open sales orders",
  },
  {
    id: "ntf-2",
    title: "Stock-out risk · Pneumatic Control Valve 2-inch",
    body: "On-hand hit zero at Central DC. The reorder point is 20 units and the supplier lead time is 9 days.",
    category: "inventory",
    module: "inventory",
    severity: "critical",
    occurredAt: "2026-10-25T05:18:00.000Z",
    pinned: true,
    actionHref: "/demo/erp/inventory",
    actionLabel: "Review replenishment",
  },
  {
    id: "ntf-3",
    title: "Deal moved to negotiation · Regional ERP Enterprise License",
    body: "₹38,00,000 · 80% win probability. Next step: a security review with Apex Distribution Hub on 28 October.",
    category: "deals",
    module: "crm",
    severity: "medium",
    occurredAt: "2026-10-24T16:05:00.000Z",
    pinned: false,
    actionHref: "/demo/erp/crm/opportunities",
    actionLabel: "Open pipeline",
  },
  {
    id: "ntf-4",
    title: "Payroll run PR-2026-10 computed",
    body: "₹6,70,000 across 4 active employees. Two reimbursements are included; the run is waiting for your approval.",
    category: "payroll",
    module: "payroll",
    severity: "low",
    occurredAt: "2026-10-24T11:30:00.000Z",
    pinned: false,
    actionHref: "/demo/erp/payroll",
    actionLabel: "Review payroll run",
  },
  {
    id: "ntf-5",
    title: "New lead · Horizon Retailers",
    body: "Vikram Malhotra arrived from LinkedIn and was auto-qualified by the demo scoring rules. Owner: Rohan Mehta.",
    category: "crm",
    module: "crm",
    severity: "low",
    occurredAt: "2026-10-23T09:12:00.000Z",
    pinned: false,
    actionHref: "/demo/erp/crm/leads",
    actionLabel: "Open leads",
  },
  {
    id: "ntf-6",
    title: "New sign-in · Chrome on macOS",
    body: "Bengaluru, India · 2 minutes ago. If this wasn't you, revoke the session from Security & access.",
    category: "security",
    module: "security",
    severity: "medium",
    occurredAt: "2026-10-22T18:47:00.000Z",
    pinned: false,
    actionHref: "/demo/erp/settings/security",
    actionLabel: "Review sessions",
  },
];

export const DEMO_NOTIFICATION_SEVERITY: Record<
  DemoNotificationSeverity,
  { dot: string; badge: string; label: string }
> = {
  low: {
    dot: "bg-sky-500",
    badge: "bg-sky-500/15 text-sky-700",
    label: "Low",
  },
  medium: {
    dot: "bg-amber-500",
    badge: "bg-amber-500/15 text-amber-700",
    label: "Medium",
  },
  high: {
    dot: "bg-orange-500",
    badge: "bg-orange-500/15 text-orange-700",
    label: "High",
  },
  critical: {
    dot: "bg-rose-500",
    badge: "bg-rose-500/15 text-rose-700",
    label: "Critical",
  },
};

export function formatDemoRelative(iso: string, now: Date): string {
  const then = new Date(iso);
  const minutes = Math.max(
    0,
    Math.floor((now.getTime() - then.getTime()) / 60000),
  );
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days}d ago`;
}

export function formatDemoAbsolute(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
