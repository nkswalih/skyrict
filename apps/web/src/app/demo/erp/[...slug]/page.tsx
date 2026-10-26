"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Users,
  ShoppingCart,
  Package,
  Wallet,
  Receipt,
  TrendingUp,
  Plus,
  Trash2,
  ArrowLeft,
  SearchX,
} from "lucide-react";
import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { DemoAiGate } from "@/components/demo/demo-ai-gate";
import { DemoModuleRecords } from "@/components/demo/demo-module-records";
import { DemoProfilePage } from "@/components/demo/demo-profile";
import {
  DEMO_SETTINGS_ROUTES,
  DemoSettings,
} from "@/components/demo/demo-settings";
import { useDemo } from "@/components/demo/demo-provider";
import {
  DEMO_MODULE_ROUTES,
  isDemoAiRoute,
} from "@/lib/demo/demo-routes";
import type { DemoOpportunity } from "@/lib/demo/demo-store";

function newId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function emailSlug(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ".")
      .replace(/^\.+|\.+$/g, "") || "contact"
  );
}

export default function DemoCatchAllPage() {
  const params = useParams();
  const router = useRouter();
  const { state, updateState } = useDemo();
  const slug = (params?.slug as string[]) || [];
  const routePath = slug.join("/");

  const [search, setSearch] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [newRowInput, setNewRowInput] = useState("");

  const leads = state?.leads ?? [];
  const opportunities = state?.opportunities ?? [];
  const customers = state?.customers ?? [];
  const orders = state?.orders ?? [];
  const products = state?.products ?? [];
  const employees = state?.employees ?? [];
  const journalEntries = state?.journalEntries ?? [];
  const invoices = state?.invoices ?? [];

  // ==========================================
  // 0. ACCOUNT: PROFILE, SETTINGS & PREFERENCES
  // ==========================================
  if (routePath === "profile") {
    return <DemoProfilePage />;
  }

  const settingsSection = DEMO_SETTINGS_ROUTES[routePath];
  if (settingsSection) {
    return <DemoSettings section={settingsSection} />;
  }

  // ==========================================
  // 1. CRM MODULE: OVERVIEW & KANBAN PIPELINE
  // ==========================================
  if (routePath === "crm/overview" || routePath === "crm") {
    const activePipeline = opportunities
      .filter((o) => o.stage !== "won" && o.stage !== "lost")
      .reduce((a, b) => a + b.amount, 0);

    return (
      <div className="space-y-6">
        <PageHeader title="CRM Overview" description="Pipeline velocity, follow-up calendar, and customer acquisition." icon={Users} />

        {/* KPI Strip */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Active Leads</span>
            <p className="text-2xl font-bold mt-1 text-foreground">{leads.length}</p>
            <span className="text-xs text-muted-foreground">{leads.filter(l => l.status === "new").length} new this week</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Open Pipeline</span>
            <p className="text-2xl font-bold mt-1 text-foreground">₹{activePipeline.toLocaleString()}</p>
            <span className="text-xs text-emerald-600 font-medium">{opportunities.length} total deals</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Won Revenue</span>
            <p className="text-2xl font-bold mt-1 text-emerald-600">
              ₹{opportunities.filter(o => o.stage === "won").reduce((a, b) => a + b.amount, 0).toLocaleString()}
            </p>
            <span className="text-xs text-muted-foreground">Closed contracts</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Customers</span>
            <p className="text-2xl font-bold mt-1 text-foreground">{customers.length}</p>
            <span className="text-xs text-muted-foreground">100% active standing</span>
          </div>
        </div>

        {/* Real ERP Replica: Pipeline by Stage Bar Graph */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Pipeline by Stage</h2>
            <Button variant="outline" size="sm" onClick={() => router.push("/demo/erp/crm/opportunities")}>
              View Kanban Board
            </Button>
          </div>
          <div className="space-y-3">
            {[
              { stage: "prospecting", label: "Prospecting" },
              { stage: "qualified", label: "Qualified" },
              { stage: "proposal", label: "Proposal" },
              { stage: "negotiation", label: "Negotiation" },
            ].map(({ stage, label }) => {
              const stageDeals = opportunities.filter((o) => o.stage === stage);
              const stageTotal = stageDeals.reduce((a, b) => a + b.amount, 0);
              const pct = (stageDeals.length / (opportunities.length || 1)) * 100;
              return (
                <div key={stage} className="space-y-1">
                  <div className="flex justify-between text-xs font-medium">
                    <span>{label} ({stageDeals.length} deals)</span>
                    <span className="tabular-nums">₹{stageTotal.toLocaleString()}</span>
                  </div>
                  <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-primary transition-all duration-500" style={{ width: `${Math.max(6, pct)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Real ERP Replica: Follow-ups 2x2 Grid */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-3">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Follow-up Activity</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
              <span className="text-xs text-muted-foreground font-semibold uppercase">Overdue</span>
              <p className="text-2xl font-bold text-red-600 mt-1">0</p>
            </div>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
              <span className="text-xs text-muted-foreground font-semibold uppercase">Due Today</span>
              <p className="text-2xl font-bold text-amber-600 mt-1">2</p>
            </div>
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <span className="text-xs text-muted-foreground font-semibold uppercase">Upcoming</span>
              <p className="text-2xl font-bold text-foreground mt-1">5</p>
            </div>
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
              <span className="text-xs text-muted-foreground font-semibold uppercase">Done (30d)</span>
              <p className="text-2xl font-bold text-emerald-600 mt-1">18</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (routePath === "crm/opportunities") {
    const moveOpportunity = (id: string, nextStage: DemoOpportunity["stage"]) => {
      updateState((curr) => ({
        ...curr,
        opportunities: (curr.opportunities ?? []).map((o) =>
          o.id === id ? { ...o, stage: nextStage } : o
        ),
      }));
    };

    return (
      <div className="space-y-6">
        <PageHeader title="Opportunities Kanban" description="Interactive deal stages. Move deals forward in real-time." icon={TrendingUp} />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {(["prospecting", "qualified", "proposal", "negotiation"] as const).map((colStage) => {
            const colDeals = opportunities.filter((o) => o.stage === colStage);
            const total = colDeals.reduce((a, b) => a + b.amount, 0);

            return (
              <div key={colStage} className="rounded-xl border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-border/50 pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    {colStage} ({colDeals.length})
                  </span>
                  <span className="text-xs font-semibold tabular-nums text-foreground">
                    ₹{total.toLocaleString()}
                  </span>
                </div>

                <div className="space-y-2.5">
                  {colDeals.length === 0 ? (
                    <p className="text-xs text-muted-foreground py-4 text-center italic">No deals in this stage</p>
                  ) : (
                    colDeals.map((opp) => (
                      <div key={opp.id} className="rounded-lg border border-border/70 bg-muted/30 p-3 text-sm space-y-2">
                        <p className="font-semibold text-foreground leading-snug">{opp.name}</p>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span className="font-bold text-foreground">₹{opp.amount.toLocaleString()}</span>
                          <span>{opp.probability}% win prob</span>
                        </div>
                        <div className="pt-2 border-t border-border/40 flex items-center justify-between">
                          <span className="text-[10px] text-muted-foreground">{opp.expectedCloseDate}</span>
                          {colStage === "prospecting" && (
                            <Button size="xs" variant="outline" onClick={() => moveOpportunity(opp.id, "qualified")}>
                              Qualify →
                            </Button>
                          )}
                          {colStage === "qualified" && (
                            <Button size="xs" variant="outline" onClick={() => moveOpportunity(opp.id, "proposal")}>
                              Proposal →
                            </Button>
                          )}
                          {colStage === "proposal" && (
                            <Button size="xs" variant="outline" onClick={() => moveOpportunity(opp.id, "negotiation")}>
                              Negotiate →
                            </Button>
                          )}
                          {colStage === "negotiation" && (
                            <Button size="xs" variant="brand" onClick={() => moveOpportunity(opp.id, "won")}>
                              Win deal ✓
                            </Button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (routePath === "crm/leads") {
    const filteredLeads = leads.filter(
      (l) => l.name.toLowerCase().includes(search.toLowerCase()) || l.company.toLowerCase().includes(search.toLowerCase())
    );

    const addLead = () => {
      if (!newRowInput.trim()) return;
      const name = newRowInput.trim();
      updateState((curr) => ({
        ...curr,
        leads: [
          {
            id: newId("lead"),
            name,
            company: "New Business Inquiry",
            email: `${emailSlug(name)}@example.demo`,
            phone: "+91 98000 00000",
            source: "Direct Entry (Demo)",
            status: "new",
            createdAt: new Date().toISOString().split("T")[0],
          },
          ...(curr.leads ?? []),
        ],
      }));
      setNewRowInput("");
    };

    const deleteLead = (id: string) => {
      updateState((curr) => ({
        ...curr,
        leads: (curr.leads ?? []).filter((l) => l.id !== id),
      }));
    };

    return (
      <div className="space-y-6">
        <PageHeader title="Leads" description="Inbound inquiries and qualification pipeline." icon={Users} />
        <div className="flex flex-wrap items-center gap-3">
          <Input placeholder="Filter leads by name/company..." value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-sm" />
          <div className="flex gap-2 ml-auto">
            <Input placeholder="Lead contact name" value={newRowInput} onChange={(e) => setNewRowInput(e.target.value)} className="w-56" />
            <Button onClick={addLead}><Plus className="size-4 mr-1" /> Add Lead</Button>
          </div>
        </div>
        <p role="status" className="text-xs text-muted-foreground">
          Showing {filteredLeads.length} of {leads.length} leads
        </p>

        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {filteredLeads.length === 0 ? (
            <p role="status" className="px-4 py-10 text-center text-sm text-muted-foreground">
              No leads match this filter.
            </p>
          ) : null}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Lead</th>
                  <th scope="col" className="px-4 py-3">Company</th>
                  <th scope="col" className="px-4 py-3">Contact</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filteredLeads.map((l) => (
                  <tr key={l.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-medium cursor-pointer text-primary" onClick={() => router.push(`/demo/erp/crm/leads/${l.id}`)}>
                      {l.name}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{l.company}</td>
                    <td className="px-4 py-3 text-muted-foreground">{l.email}</td>
                    <td className="px-4 py-3"><Badge variant="outline">{l.status}</Badge></td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete lead ${l.name}`}
                        onClick={() => deleteLead(l.id)}
                      >
                        <Trash2 className="size-4 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (routePath.startsWith("crm/leads/")) {
    const leadId = slug[2];
    const lead = leads.find((l) => l.id === leadId);

    if (!lead) {
      return (
        <div className="space-y-6">
          <Button variant="ghost" size="sm" onClick={() => router.push("/demo/erp/crm/leads")}>
            <ArrowLeft className="size-4 mr-1" /> Back to Leads
          </Button>
          <PageHeader title="Lead not found" description="This lead was deleted or never existed in the demo workspace." icon={SearchX} />
        </div>
      );
    }

    return (
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={() => router.push("/demo/erp/crm/leads")}>
          <ArrowLeft className="size-4 mr-1" /> Back to Leads
        </Button>
        <PageHeader title={lead.name} description={`Company: ${lead.company}`} icon={Users} />
        <div className="rounded-xl border border-border bg-card p-6 space-y-4 max-w-2xl">
          <p><strong>Email:</strong> {lead.email}</p>
          <p><strong>Phone:</strong> {lead.phone}</p>
          <p><strong>Source:</strong> {lead.source}</p>
          <p><strong>Created:</strong> {lead.createdAt}</p>
          <p><strong>Status:</strong> {lead.status}</p>
        </div>
      </div>
    );
  }

  if (routePath === "crm/customers") {
    return (
      <div className="space-y-6">
        <PageHeader title="Customers" description="Active business customer relationships." icon={Users} />
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Customer</th>
                  <th scope="col" className="px-4 py-3">Code</th>
                  <th scope="col" className="px-4 py-3">Contact</th>
                  <th scope="col" className="px-4 py-3 text-right">Credit Limit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {customers.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3 font-medium text-foreground">{c.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.customerCode}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.email}</td>
                    <td className="px-4 py-3 text-right font-medium">₹{c.creditLimit.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================
  // 2. FINANCE MODULE: OVERVIEW, LEDGER, INVOICES
  // ==========================================
  if (routePath === "finance" || routePath === "finance/overview") {
    const totalRev = invoices.filter((i) => i.status === "paid").reduce((a, b) => a + b.amount, 0);
    const overdue = invoices.filter((i) => i.status === "overdue").reduce((a, b) => a + b.amount, 0);

    return (
      <div className="space-y-6">
        <PageHeader title="Finance Overview" description="Cash flow, general ledger, and receivables." icon={Wallet} />

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Revenue Received</span>
            <p className="text-2xl font-bold mt-1 text-foreground">₹{totalRev.toLocaleString()}</p>
            <span className="text-xs text-emerald-600 font-medium">+14.2% vs last month</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Overdue Receivables</span>
            <p className="text-2xl font-bold mt-1 text-destructive">₹{overdue.toLocaleString()}</p>
            <span className="text-xs text-muted-foreground">Action required in AR</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Operating Cash</span>
            <p className="text-2xl font-bold mt-1 text-foreground">₹4,850,000</p>
            <span className="text-xs text-muted-foreground">Main Treasury (1100)</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Gross Margin</span>
            <p className="text-2xl font-bold mt-1 text-foreground">38.4%</p>
            <span className="text-xs text-muted-foreground">Target: 35.0%</span>
          </div>
        </div>

        {/* General Ledger Table */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Recent General Ledger Entries</h2>
            <Button variant="ghost" size="sm" onClick={() => router.push("/demo/erp/finance/journal-entries")}>
              View all
            </Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-2.5">Entry #</th>
                  <th scope="col" className="px-4 py-2.5">Description</th>
                  <th scope="col" className="px-4 py-2.5">Debit</th>
                  <th scope="col" className="px-4 py-2.5">Credit</th>
                  <th scope="col" className="px-4 py-2.5 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {journalEntries.map((je) => (
                  <tr key={je.id}>
                    <td className="px-4 py-2.5 font-mono text-xs">{je.entryNumber}</td>
                    <td className="px-4 py-2.5 font-medium">{je.description}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{je.debitAccount}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{je.creditAccount}</td>
                    <td className="px-4 py-2.5 text-right font-medium">₹{je.amount.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (routePath === "finance/invoices") {
    return (
      <div className="space-y-6">
        <PageHeader title="Invoices" description="Customer invoices and payment status." icon={Wallet} />
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Invoice #</th>
                  <th scope="col" className="px-4 py-3">Customer</th>
                  <th scope="col" className="px-4 py-3">Due Date</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {invoices.map((inv) => (
                  <tr key={inv.id}>
                    <td className="px-4 py-3 font-mono text-xs">{inv.invoiceNumber}</td>
                    <td className="px-4 py-3 font-medium">{inv.customerName}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inv.dueDate}</td>
                    <td className="px-4 py-3">
                      <Badge variant={inv.status === "paid" ? "secondary" : inv.status === "overdue" ? "destructive" : "outline"}>
                        {inv.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-bold">₹{inv.amount.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================
  // 3. INVENTORY MODULE: OVERVIEW, PRODUCTS & STOCK
  // ==========================================
  if (routePath === "inventory" || routePath === "inventory/overview") {
    const totalStock = products.reduce((a, b) => a + b.qtyOnHand, 0);
    const lowStock = products.filter((p) => p.qtyOnHand <= p.reorderPoint);

    return (
      <div className="space-y-6">
        <PageHeader title="Inventory Overview" description="Stock levels, warehouse allocation, and SKU tracking." icon={Package} />

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Total SKUs</span>
            <p className="text-2xl font-bold mt-1 text-foreground">{products.length}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Units On Hand</span>
            <p className="text-2xl font-bold mt-1 text-foreground">{totalStock}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <span className="text-xs text-muted-foreground uppercase font-semibold">Reorder Alerts</span>
            <p className="text-2xl font-bold mt-1 text-amber-600">{lowStock.length}</p>
          </div>
        </div>

        {/* Low Stock Replenishment Priority */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Replenishment Priority (Low Stock)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-2.5">SKU</th>
                  <th scope="col" className="px-4 py-2.5">Product</th>
                  <th scope="col" className="px-4 py-2.5">Warehouse</th>
                  <th scope="col" className="px-4 py-2.5 text-right">On Hand</th>
                  <th scope="col" className="px-4 py-2.5 text-right">Reorder Threshold</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {lowStock.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-2.5 font-mono text-xs">{p.sku}</td>
                    <td className="px-4 py-2.5 font-medium">{p.name}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{p.warehouse}</td>
                    <td className="px-4 py-2.5 text-right font-bold text-destructive">{p.qtyOnHand}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{p.reorderPoint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (routePath === "inventory/products" || routePath === "inventory/stock") {
    const addProduct = () => {
      if (!newRowInput.trim()) return;
      updateState((curr) => ({
        ...curr,
        products: [
          {
            id: newId("prod"),
            sku: `IND-SKU-${Math.floor(1000 + Math.random() * 9000)}`,
            name: newRowInput.trim(),
            category: "Industrial Components",
            costPrice: 5000,
            sellPrice: 7500,
            reorderPoint: 10,
            qtyOnHand: 25,
            warehouse: "Central DC",
            isActive: true,
          },
          ...(curr.products ?? []),
        ],
      }));
      setNewRowInput("");
    };

    const filteredProducts = products.filter((product) => {
      const query = productSearch.trim().toLowerCase();
      if (!query) return true;
      return (
        product.name.toLowerCase().includes(query) ||
        product.sku.toLowerCase().includes(query) ||
        product.category.toLowerCase().includes(query)
      );
    });

    return (
      <div className="space-y-6">
        <PageHeader title="Products & Stock" description="Warehouse item master, valuations, and replenishment triggers." icon={Package} />
        <div className="flex flex-wrap items-center gap-3">
          <Input placeholder="Filter products by name/SKU..." aria-label="Filter products by name or SKU" value={productSearch} onChange={(e) => setProductSearch(e.target.value)} className="max-w-sm" />
          <div className="ml-auto flex gap-2">
            <Input placeholder="Product name to add..." value={newRowInput} onChange={(e) => setNewRowInput(e.target.value)} className="w-56" />
            <Button onClick={addProduct}><Plus className="size-4 mr-1" /> Add Product</Button>
          </div>
        </div>
        <p role="status" className="text-xs text-muted-foreground">
          Showing {filteredProducts.length} of {products.length} products
        </p>

        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {filteredProducts.length === 0 ? (
            <p role="status" className="px-4 py-10 text-center text-sm text-muted-foreground">
              No products match this filter.
            </p>
          ) : null}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">SKU</th>
                  <th scope="col" className="px-4 py-3">Name</th>
                  <th scope="col" className="px-4 py-3">Category</th>
                  <th scope="col" className="px-4 py-3 text-right">Cost</th>
                  <th scope="col" className="px-4 py-3 text-right">Selling</th>
                  <th scope="col" className="px-4 py-3 text-right">On Hand</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filteredProducts.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3 font-mono text-xs">{p.sku}</td>
                    <td className="px-4 py-3 font-medium">{p.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.category}</td>
                    <td className="px-4 py-3 text-right">₹{p.costPrice.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">₹{p.sellPrice.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-bold text-foreground">{p.qtyOnHand}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================
  // 4. ORDERS & SALES MODULE
  // ==========================================
  if (routePath === "orders" || routePath === "sales") {
    return (
      <div className="space-y-6">
        <PageHeader title="Sales Orders" description="Customer order confirmations and delivery fulfilment." icon={ShoppingCart} />
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Order Number</th>
                  <th scope="col" className="px-4 py-3">Customer</th>
                  <th scope="col" className="px-4 py-3">Credit Check</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="px-4 py-3 font-mono text-xs">{o.orderNumber}</td>
                    <td className="px-4 py-3 font-medium">{o.customerName}</td>
                    <td className="px-4 py-3"><Badge variant="outline">{o.creditCheck}</Badge></td>
                    <td className="px-4 py-3"><Badge variant="secondary">{o.status}</Badge></td>
                    <td className="px-4 py-3 text-right font-medium">₹{o.total.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================
  // 5. HR & PAYROLL MODULES
  // ==========================================
  if (routePath === "hr" || routePath === "hr/overview" || routePath === "hr/employees") {
    return (
      <div className="space-y-6">
        <PageHeader title="People & Employees" description="Workforce management, compensation, and active roster." icon={Users} />
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Emp ID</th>
                  <th scope="col" className="px-4 py-3">Name</th>
                  <th scope="col" className="px-4 py-3">Department</th>
                  <th scope="col" className="px-4 py-3">Role</th>
                  <th scope="col" className="px-4 py-3 text-right">Monthly Compensation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {employees.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-3 font-mono text-xs">{e.employeeNumber}</td>
                    <td className="px-4 py-3 font-medium">{e.firstName} {e.lastName}</td>
                    <td className="px-4 py-3 text-muted-foreground">{e.department}</td>
                    <td className="px-4 py-3 text-muted-foreground">{e.jobTitle}</td>
                    <td className="px-4 py-3 text-right font-medium">₹{e.monthlySalary.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (routePath === "payroll" || routePath === "payroll/runs") {
    const payrollTotal = employees
      .filter((employee) => employee.employmentStatus === "active")
      .reduce((total, employee) => total + employee.monthlySalary, 0);

    return (
      <div className="space-y-6">
        <PageHeader title="Payroll Runs" description="Monthly salary calculations, approvals, and disbursement status." icon={Receipt} />
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground uppercase font-semibold">
                <tr>
                  <th scope="col" className="px-4 py-3">Run Code</th>
                  <th scope="col" className="px-4 py-3">Period</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Total Net</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                <tr>
                  <td className="px-4 py-3 font-mono text-xs">PR-2026-10</td>
                  <td className="px-4 py-3 font-medium">01 Oct 2026 – 31 Oct 2026</td>
                  <td className="px-4 py-3"><Badge variant="outline">computed</Badge></td>
                  <td className="px-4 py-3 text-right font-bold">₹{payrollTotal.toLocaleString()}</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-xs">PR-2026-09</td>
                  <td className="px-4 py-3 font-medium">01 Sep 2026 – 30 Sep 2026</td>
                  <td className="px-4 py-3"><Badge variant="secondary">paid</Badge></td>
                  <td className="px-4 py-3 text-right font-bold">₹{payrollTotal.toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================
  // 6. AI & AUTOMATION ROUTES (Gated Previews)
  // ==========================================
  if (isDemoAiRoute(routePath)) {
    return (
      <div className="space-y-6">
        <PageHeader title="Autonomous Engine & Machine Intelligence" description="Real-time multi-agent business orchestration." icon={Package} />
        <DemoAiGate
          title="SkyAgent Production Orchestration"
          description="In live production workspaces, SkyAgent executes autonomous background routines directly on your ledger, inventory sensors, and payroll registers."
          features={[
            "Lead-time adjusted safety stock thresholds & predictive purchasing",
            "Automatic general ledger reconciliation (accounts 5010 / 2010)",
            "Duplicate-payout, ghost-employee & tax variance scans",
            "Multi-channel customer relationship health monitoring",
          ]}
        />
      </div>
    );
  }

  // ==========================================
  // 7. SEEDED MODULE RECORDS
  // ==========================================
  if (DEMO_MODULE_ROUTES.has(routePath)) {
    return <DemoModuleRecords routePath={routePath} state={state} />;
  }

  // ==========================================
  // 8. UNKNOWN ROUTE (client-side navigation fallback)
  // ==========================================
  return (
    <div className="space-y-6">
      <PageHeader title="Page not found" description="This demo module does not exist." icon={SearchX} />
      <Button variant="outline" onClick={() => router.push("/demo/erp")}>
        <ArrowLeft className="size-4 mr-1" /> Back to dashboard
      </Button>
    </div>
  );
}
