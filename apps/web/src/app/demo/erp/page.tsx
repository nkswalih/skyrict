"use client";

import { Users, ShoppingCart, Package, Wallet, ArrowRight } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/dashboard/shared/page-header";
import { useDemo } from "@/components/demo/demo-provider";

export default function DemoDashboardPage() {
  const { state } = useDemo();

  const openOpportunities = state.opportunities.filter(
    (opportunity) => opportunity.stage !== "won" && opportunity.stage !== "lost",
  );
  const openPipeline = openOpportunities.reduce(
    (total, opportunity) => total + opportunity.amount,
    0,
  );
  const confirmedOrders = state.orders.filter(
    (order) => order.status === "confirmed" || order.status === "fulfilled",
  );
  const confirmedVolume = confirmedOrders.reduce(
    (total, order) => total + order.total,
    0,
  );
  const activeEmployees = state.employees.filter(
    (employee) => employee.employmentStatus === "active",
  );

  return (
    <div className="space-y-8">
      <PageHeader
        title="Business Operations"
        description="Integrated management across sales, inventory, payroll, and financials."
        icon={Package}
      />

      {/* KPI Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold uppercase">
            <span>Open Pipeline</span>
            <Wallet className="size-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">
            ₹{openPipeline.toLocaleString()}
          </p>
          <span className="text-xs text-emerald-600 mt-1 inline-block font-medium">
            {openOpportunities.length} active opportunities
          </span>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold uppercase">
            <span>Confirmed Orders</span>
            <ShoppingCart className="size-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">
            {confirmedOrders.length}
          </p>
          <span className="text-xs text-muted-foreground mt-1 inline-block font-medium">
            ₹{confirmedVolume.toLocaleString()} booked volume
          </span>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold uppercase">
            <span>Catalog SKUs</span>
            <Package className="size-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">
            {state.products.length}
          </p>
          <span className="text-xs text-emerald-600 mt-1 inline-block font-medium">
            Inventory in tracking
          </span>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold uppercase">
            <span>Employees</span>
            <Users className="size-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">
            {state.employees.length}
          </p>
          <span className="text-xs text-muted-foreground mt-1 inline-block font-medium">
            {activeEmployees.length} active of {state.employees.length} on roster
          </span>
        </div>
      </div>

      {/* Quick Access Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          { title: "CRM", desc: "Manage leads, contacts, deals", href: "/demo/erp/crm/overview", icon: Users },
          { title: "Orders", desc: "Fulfil sales orders and credit checks", href: "/demo/erp/orders", icon: ShoppingCart },
          { title: "Inventory", desc: "Warehouse stock levels and products", href: "/demo/erp/inventory", icon: Package },
          { title: "Finance", desc: "General ledger and journal entries", href: "/demo/erp/finance", icon: Wallet },
          { title: "HR & Roster", desc: "Employees, departments, attendance", href: "/demo/erp/hr", icon: Users },
          { title: "Payroll Runs", desc: "Monthly salary computation & pay rules", href: "/demo/erp/payroll", icon: Package },
        ].map((m) => (
          <Link
            key={m.title}
            href={m.href}
            className="group flex flex-col justify-between rounded-xl border border-border bg-card p-5 transition-all hover:border-primary/50 hover:bg-muted/30"
          >
            <div>
              <m.icon className="size-5 text-primary mb-3" />
              <h3 className="font-semibold text-foreground text-base group-hover:text-primary transition-colors">{m.title}</h3>
              <p className="text-xs text-muted-foreground mt-1">{m.desc}</p>
            </div>
            <span className="inline-flex items-center text-xs font-medium text-primary mt-4">
              Explore Module <ArrowRight className="size-3 ml-1 transition-transform group-hover:translate-x-0.5" />
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}