"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  BadgeCheck,
  Building2,
  CalendarDays,
  Clock3,
  Fingerprint,
  Globe2,
  Mail,
  MapPin,
  Phone,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDemo } from "@/components/demo/demo-provider";
import { formatDemoDate } from "@/lib/demo/demo-format";

function initialsFor(name: string, email: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length > 1)
    return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
  if (parts[0]) return parts[0].slice(0, 2).toUpperCase();
  return email.slice(0, 2).toUpperCase() || "SK";
}

/**
 * Read-only public profile preview for the demo persona. Everything derives
 * from the seeded demo snapshot, so editing the profile in Settings is visible
 * here immediately and nothing is fetched.
 */
export function DemoProfilePage() {
  const { state } = useDemo();
  const profile = state.profile;
  const workspace = state.preferences.workspace;

  const openDeals = state.opportunities.filter(
    (opportunity) =>
      opportunity.stage !== "won" && opportunity.stage !== "lost",
  );
  const pipeline = openDeals.reduce(
    (total, opportunity) => total + opportunity.amount,
    0,
  );
  const overdue = state.invoices.filter(
    (invoice) => invoice.status === "overdue",
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Profile"
        description="How this teammate appears to the rest of the demo workspace."
      />

      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="relative h-32 bg-secondary">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_20%,rgba(135,206,235,0.6),transparent_45%),radial-gradient(circle_at_82%_0%,rgba(14,165,233,0.28),transparent_42%)]" />
          <div className="absolute inset-0 opacity-[0.18] [background-image:radial-gradient(circle_at_1px_1px,var(--foreground)_1px,transparent_0)] [background-size:18px_18px]" />
        </div>
        <div className="px-5 pb-6">
          <div className="relative -mt-12 flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex size-24 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-sky-400 font-display text-3xl font-semibold text-primary-foreground ring-4 ring-card">
                {initialsFor(profile.fullName, profile.email)}
              </div>
              <div className="pb-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-display text-2xl font-semibold tracking-tight text-foreground">
                    {profile.fullName}
                  </h2>
                  <BadgeCheck
                    aria-label="Verified workspace owner"
                    className="size-4 text-primary"
                  />
                </div>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {profile.jobTitle} · {profile.department}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 pb-1">
              <Badge variant="secondary">Owner</Badge>
              <Badge variant="outline">{profile.pronouns}</Badge>
              <Button asChild size="sm" variant="outline">
                <Link href="/demo/erp/settings" prefetch={false}>
                  Edit profile
                  <ArrowUpRight aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <MapPin aria-hidden="true" className="size-3.5" />
              {profile.location}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock3 aria-hidden="true" className="size-3.5" />
              {profile.timezone}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays aria-hidden="true" className="size-3.5" />
              Joined {formatDemoDate(profile.memberSince)}
            </span>
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground">About</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {profile.bio}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {["Operations", "Supply chain", "ERP rollout", "Approvals"].map(
                (tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-secondary-foreground"
                  >
                    {tag}
                  </span>
                ),
              )}
            </div>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground">Contact</h2>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="flex items-start gap-2.5">
                <Mail
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                />
                <div className="min-w-0">
                  <dt className="text-[11px] text-muted-foreground">
                    Work email
                  </dt>
                  <dd className="truncate text-sm text-foreground">
                    {profile.email}
                  </dd>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <Phone
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                />
                <div>
                  <dt className="text-[11px] text-muted-foreground">Phone</dt>
                  <dd className="text-sm text-foreground">{profile.phone}</dd>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <Globe2
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                />
                <div>
                  <dt className="text-[11px] text-muted-foreground">
                    Timezone
                  </dt>
                  <dd className="text-sm text-foreground">{profile.timezone}</dd>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <Building2
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                />
                <div className="min-w-0">
                  <dt className="text-[11px] text-muted-foreground">
                    Workspace
                  </dt>
                  <dd className="truncate text-sm text-foreground">
                    {workspace.name}
                  </dd>
                </div>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-foreground">
                Recent activity
              </h2>
              <span className="text-[11px] text-muted-foreground">
                Sample audit trail
              </span>
            </div>
            <ol className="mt-4 space-y-4">
              {[
                {
                  icon: Wallet,
                  title: "Approved payroll run PR-2026-10",
                  meta: "Today · 09:18 · ₹6,70,000 across 4 employees",
                },
                {
                  icon: TrendingUp,
                  title: "Moved Regional ERP Enterprise License to negotiation",
                  meta: "24 Oct 2026 · 16:05 · ₹38,00,000 · 80% probability",
                },
                {
                  icon: ShieldCheck,
                  title: "Enabled two-factor for all administrators",
                  meta: "1 Oct 2026 · 11:05 · Security policy",
                },
                {
                  icon: Users,
                  title: "Onboarded Sneha Reddy as Warehouse Supervisor",
                  meta: "10 Jan 2026 · 10:02 · Inventory",
                },
              ].map((event) => {
                const Icon = event.icon;
                return (
                  <li key={event.title} className="flex items-start gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
                      <Icon aria-hidden="true" className="size-4" />
                    </span>
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {event.title}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {event.meta}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground">
              Operating impact
            </h2>
            <dl className="mt-3 space-y-3">
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-muted-foreground">
                  Open pipeline
                </dt>
                <dd className="text-sm font-semibold tabular-nums text-foreground">
                  ₹{pipeline.toLocaleString()}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-muted-foreground">Active deals</dt>
                <dd className="text-sm font-semibold tabular-nums text-foreground">
                  {openDeals.length}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-muted-foreground">
                  Team on roster
                </dt>
                <dd className="text-sm font-semibold tabular-nums text-foreground">
                  {state.employees.length}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-muted-foreground">
                  Overdue invoices
                </dt>
                <dd className="text-sm font-semibold tabular-nums text-foreground">
                  {overdue}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground">
              Access &amp; security
            </h2>
            <ul className="mt-3 space-y-3 text-xs">
              <li className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-muted-foreground">
                  <ShieldCheck aria-hidden="true" className="size-3.5" />
                  Two-factor
                </span>
                <Badge variant="secondary">
                  {state.security.twoFactorEnabled ? "On" : "Off"}
                </Badge>
              </li>
              <li className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-muted-foreground">
                  <Fingerprint aria-hidden="true" className="size-3.5" />
                  Passkeys
                </span>
                <span className="font-medium text-foreground">
                  {state.security.passkeys.length}
                </span>
              </li>
              <li className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-muted-foreground">
                  <Sparkles aria-hidden="true" className="size-3.5" />
                  Role
                </span>
                <span className="font-medium text-foreground">
                  Workspace owner
                </span>
              </li>
            </ul>
            <Button
              asChild
              variant="outline"
              size="sm"
              className="mt-4 w-full"
            >
              <Link href="/demo/erp/settings/security" prefetch={false}>
                Review security
              </Link>
            </Button>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground">
              Demo persona
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              This profile is seeded for the walkthrough. Edits stay in this
              browser and are never written to Skyrict.
            </p>
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="mt-3 w-full"
            >
              <Link href="/demo/erp/settings" prefetch={false}>
                Edit profile settings
              </Link>
            </Button>
          </section>
        </div>
      </div>
    </div>
  );
}
