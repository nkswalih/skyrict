"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Contact,
  FileText,
  Package,
  Receipt,
  ShoppingCart,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

const quickLinks: {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
}[] = [
  { href: "/dashboard/erp/crm/overview", title: "CRM", description: "Leads, pipelines, and customers.", icon: Contact },
  { href: "/dashboard/erp/orders", title: "Orders", description: "Sales orders and the fulfilment flow.", icon: ShoppingCart },
  { href: "/dashboard/erp/inventory", title: "Inventory", description: "Stock and warehouses.", icon: Package },
  { href: "/dashboard/erp/finance", title: "Finance", description: "Cash flow and ledgers.", icon: Wallet },
  { href: "/dashboard/erp/hr", title: "HR", description: "People and the team.", icon: Users },
  { href: "/dashboard/erp/documents", title: "Documents", description: "Central document store with AI extraction.", icon: FileText },
  { href: "/dashboard/erp/payroll", title: "Payroll", description: "Runs, compensation, and pay rules.", icon: Receipt },
  { href: "/dashboard/erp/reports", title: "Reports", description: "Dashboards and exports.", icon: BarChart3 },
];

/** Module quick-link cards rendered on the ERP overview page. */
export function ModuleQuickLinks() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {quickLinks.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="group relative flex flex-col rounded-xl border border-border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-muted/40 active:translate-y-0"
        >
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
            <link.icon aria-hidden="true" className="size-5" />
          </div>
          <h3 className="mt-4 font-display text-base font-semibold text-foreground">
            {link.title}
          </h3>
          <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">
            {link.description}
          </p>
          <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary">
            Open
            <ArrowRight
              aria-hidden="true"
              className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
            />
          </span>
        </Link>
      ))}
    </div>
  );
}
