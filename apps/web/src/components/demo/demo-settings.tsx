"use client";

import {
  useEffect,
  useMemo,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowUpRight,
  BellRing,
  Building2,
  Check,
  Clock3,
  CreditCard,
  Fingerprint,
  Globe2,
  Layers,
  LockKeyhole,
  Monitor,
  MonitorSmartphone,
  Moon,
  Palette,
  Plug,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Sun,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDemo } from "@/components/demo/demo-provider";
import { DEMO_MONTHS, formatDemoDate } from "@/lib/demo/demo-format";
import type {
  DemoAppearance,
  DemoIntegration,
  DemoProfile,
  DemoSecurity,
  DemoWorkspacePreferences,
} from "@/lib/demo/demo-store";
import { cn } from "@/lib/utils";

export type DemoSettingsSection =
  | "profile"
  | "appearance"
  | "workspace"
  | "notifications"
  | "billing"
  | "security"
  | "integrations";

/** Route path (relative to `/demo/erp/`) → settings section. */
export const DEMO_SETTINGS_ROUTES: Record<string, DemoSettingsSection> = {
  settings: "profile",
  "settings/appearance": "appearance",
  "settings/workspace": "workspace",
  "settings/notifications": "notifications",
  "settings/billing": "billing",
  "settings/security": "security",
  "settings/integrations": "integrations",
};

const SECTIONS: Array<{
  id: DemoSettingsSection;
  label: string;
  href: string;
  icon: LucideIcon;
  heading: string;
  description: string;
}> = [
  {
    id: "profile",
    label: "Profile",
    href: "/demo/erp/settings",
    icon: UserRound,
    heading: "Profile & settings",
    description:
      "Your identity across the demo workspace the same profile the sidebar and approvals use.",
  },
  {
    id: "appearance",
    label: "Appearance",
    href: "/demo/erp/settings/appearance",
    icon: Palette,
    heading: "Appearance",
    description:
      "Theme, density, and motion for the demo workspace applied instantly and saved in this browser.",
  },
  {
    id: "workspace",
    label: "Workspace",
    href: "/demo/erp/settings/workspace",
    icon: Building2,
    heading: "Workspace preferences",
    description:
      "Company identity, fiscal defaults, and the operating conventions every module inherits.",
  },
  {
    id: "notifications",
    label: "Notifications",
    href: "/demo/erp/settings/notifications",
    icon: BellRing,
    heading: "Notification preferences",
    description:
      "Choose which operational signals interrupt you and which wait for the digest.",
  },
  {
    id: "billing",
    label: "Billing",
    href: "/demo/erp/settings/billing",
    icon: CreditCard,
    heading: "Plans & billing",
    description:
      "Plan, seats, usage, and invoices for the sample workspace.",
  },
  {
    id: "security",
    label: "Security",
    href: "/demo/erp/settings/security",
    icon: ShieldCheck,
    heading: "Security & access",
    description:
      "Two-factor, passkeys, and every device currently trusted by this workspace.",
  },
  {
    id: "integrations",
    label: "Integrations",
    href: "/demo/erp/settings/integrations",
    icon: Plug,
    heading: "Integrations",
    description:
      "Connect the finance, communication, and data tools the operation already runs on.",
  },
];

const MONTHS = DEMO_MONTHS;

function initialsFor(name: string, email: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length > 1)
    return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
  if (parts[0]) return parts[0].slice(0, 2).toUpperCase();
  return email.slice(0, 2).toUpperCase() || "SK";
}

export function DemoSettings({ section }: { section: DemoSettingsSection }) {
  const active = SECTIONS.find((entry) => entry.id === section) ?? SECTIONS[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title={active.heading}
        description={active.description}
        icon={active.icon}
      />

      <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <div className="min-w-0 space-y-3 lg:sticky lg:top-4 lg:self-start">
          <nav
            aria-label="Settings sections"
            className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1 scrollbar-hide lg:flex-col"
          >
            {SECTIONS.map((entry) => {
              const Icon = entry.icon;
              const isActive = entry.id === section;
              return (
                <Link
                  key={entry.id}
                  href={entry.href}
                  prefetch={false}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors lg:w-full",
                    isActive
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <Icon
                    aria-hidden="true"
                    className={cn(
                      "size-4 shrink-0",
                      isActive && "text-foreground",
                    )}
                  />
                  {entry.label}
                </Link>
              );
            })}
          </nav>
          <PlanSummaryCard />
        </div>

        <div className="min-w-0">
          {section === "profile" ? <ProfileSection /> : null}
          {section === "appearance" ? <AppearanceSection /> : null}
          {section === "workspace" ? <WorkspaceSection /> : null}
          {section === "notifications" ? <NotificationsSection /> : null}
          {section === "billing" ? <BillingSection /> : null}
          {section === "security" ? <SecuritySection /> : null}
          {section === "integrations" ? <IntegrationsSection /> : null}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Shared primitives
   ------------------------------------------------------------------------- */

function PlanSummaryCard() {
  const { state } = useDemo();
  const seats = state.employees.length;

  return (
    <div className="hidden rounded-xl border border-border bg-card p-4 lg:block">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
          Workspace
        </span>
        <Badge variant="secondary">Scale</Badge>
      </div>
      <p className="mt-1.5 truncate text-sm font-semibold text-foreground">
        {state.preferences.workspace.name}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {seats} of 25 seats used
      </p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${Math.round((seats / 25) * 100)}%` }}
        />
      </div>
      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
        <Link href="/demo/erp/settings/billing" prefetch={false}>
          View plan &amp; usage
        </Link>
      </Button>
    </div>
  );
}

function SettingsCard({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Field({
  id,
  label,
  hint,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? (
        <p className="text-[11px] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

function NativeSelect({
  className,
  ...props
}: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

/** Accessible switch built in-component (the codebase has no Switch primitive). */
function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        checked
          ? "bg-primary ring-1 ring-primary/50 ring-inset"
          : "bg-muted-foreground/25",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-4 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[1.125rem]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
  label,
  disabled,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
      <Toggle
        checked={checked}
        onChange={onChange}
        label={label}
        disabled={disabled}
      />
    </div>
  );
}

function SaveBar({
  dirty,
  saved,
  onSave,
  disabled = false,
  label = "Save changes",
}: {
  dirty: boolean;
  saved: boolean;
  onSave: () => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
      <p
        role="status"
        className={cn(
          "text-xs",
          saved ? "font-medium text-success" : "text-muted-foreground",
        )}
      >
        {saved
          ? "Saved to this browser"
          : dirty
            ? "Unsaved changes the demo keeps edits in localStorage"
            : "Everything is up to date"}
      </p>
      <Button
        type="button"
        size="sm"
        onClick={onSave}
        disabled={disabled || !dirty}
      >
        <Save aria-hidden="true" />
        {label}
      </Button>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Profile
   ------------------------------------------------------------------------- */

function ProfileSection() {
  const { state, updateState, reset } = useDemo();
  const [form, setForm] = useState<DemoProfile>(state.profile);
  const [saved, setSaved] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  useEffect(() => {
    setForm(state.profile);
  }, [state.profile]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 4000);
    return () => clearTimeout(timer);
  }, [saved]);

  const dirty = JSON.stringify(form) !== JSON.stringify(state.profile);
  const valid = form.fullName.trim().length > 0 && form.email.trim().length > 0;

  const save = () => {
    updateState((current) => ({
      ...current,
      profile: {
        ...form,
        fullName: form.fullName.trim(),
        email: form.email.trim(),
      },
    }));
    setSaved(true);
  };

  const update = (key: keyof DemoProfile, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="relative h-24 bg-secondary">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(135,206,235,0.55),transparent_45%),radial-gradient(circle_at_85%_0%,rgba(14,165,233,0.22),transparent_42%)]" />
        </div>
        <div className="px-5 pb-5">
          <div className="relative -mt-10 flex flex-wrap items-end justify-between gap-4">
            <div className="flex items-end gap-4">
              <div className="flex size-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-sky-400 font-display text-2xl font-semibold text-primary-foreground ring-4 ring-card">
                {initialsFor(state.profile.fullName, state.profile.email)}
              </div>
              <div className="pb-1">
                <h2 className="font-display text-xl font-semibold tracking-tight text-foreground">
                  {state.profile.fullName}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {state.profile.jobTitle} · {state.profile.department}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 pb-1">
              <Badge variant="secondary">Owner</Badge>
              <Badge variant="outline">Demo persona</Badge>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Globe2 aria-hidden="true" className="size-3.5" />
              {state.profile.location}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock3 aria-hidden="true" className="size-3.5" />
              {state.profile.timezone}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Users aria-hidden="true" className="size-3.5" />
              Member since {formatDemoDate(state.profile.memberSince)}
            </span>
          </div>
          <div className="mt-4">
            <Button asChild size="sm" variant="outline">
              <Link href="/demo/erp/profile" prefetch={false}>
                Preview public profile
                <ArrowUpRight aria-hidden="true" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <SettingsCard
        title="Personal details"
        description="Used across approvals, audit entries, and the sidebar persona."
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) save();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="demo-profile-name" label="Full name">
              <Input
                id="demo-profile-name"
                value={form.fullName}
                onChange={(event) => update("fullName", event.target.value)}
                autoComplete="name"
              />
            </Field>
            <Field id="demo-profile-email" label="Work email">
              <Input
                id="demo-profile-email"
                type="email"
                value={form.email}
                onChange={(event) => update("email", event.target.value)}
                autoComplete="email"
              />
            </Field>
            <Field id="demo-profile-title" label="Job title">
              <Input
                id="demo-profile-title"
                value={form.jobTitle}
                onChange={(event) => update("jobTitle", event.target.value)}
              />
            </Field>
            <Field id="demo-profile-department" label="Department">
              <NativeSelect
                id="demo-profile-department"
                value={form.department}
                onChange={(event) => update("department", event.target.value)}
              >
                {[
                  "Executive",
                  "Finance",
                  "Sales",
                  "Inventory",
                  "People",
                  "Technology",
                ].map((department) => (
                  <option key={department} value={department}>
                    {department}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-profile-phone" label="Phone">
              <Input
                id="demo-profile-phone"
                type="tel"
                value={form.phone}
                onChange={(event) => update("phone", event.target.value)}
                autoComplete="tel"
              />
            </Field>
            <Field id="demo-profile-timezone" label="Timezone">
              <NativeSelect
                id="demo-profile-timezone"
                value={form.timezone}
                onChange={(event) => update("timezone", event.target.value)}
              >
                {[
                  "Asia/Kolkata",
                  "Asia/Dubai",
                  "Europe/London",
                  "America/New_York",
                  "Asia/Singapore",
                ].map((timezone) => (
                  <option key={timezone} value={timezone}>
                    {timezone}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-profile-location" label="Location">
              <Input
                id="demo-profile-location"
                value={form.location}
                onChange={(event) => update("location", event.target.value)}
              />
            </Field>
            <Field id="demo-profile-pronouns" label="Pronouns">
              <Input
                id="demo-profile-pronouns"
                value={form.pronouns}
                onChange={(event) => update("pronouns", event.target.value)}
              />
            </Field>
            <Field
              id="demo-profile-bio"
              label="About"
              className="sm:col-span-2"
              hint="Shown on the public profile preview inside the demo."
            >
              <Textarea
                id="demo-profile-bio"
                rows={3}
                value={form.bio}
                onChange={(event) => update("bio", event.target.value)}
              />
            </Field>
          </div>
          <SaveBar
            dirty={dirty}
            saved={saved}
            onSave={save}
            disabled={!valid}
            label="Save profile"
          />
        </form>
      </SettingsCard>

      <SettingsCard
        title="Demo data"
        description="The whole workspace lives in this browser. Reset it whenever you want a clean walkthrough."
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-start gap-2.5 text-xs text-muted-foreground">
            <RotateCcw
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0 text-primary"
            />
            <p className="max-w-md">
              Restores seeded leads, orders, inventory, payroll, profile,
              preferences, and notifications. Nothing is sent to a server.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setResetOpen(true)}
          >
            Reset sample data
          </Button>
        </div>
      </SettingsCard>

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Reset the demo workspace?</DialogTitle>
            <DialogDescription>
              Every sample edit in this browser is replaced with the seeded
              snapshot. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                reset();
                setResetOpen(false);
              }}
            >
              Reset demo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Appearance
   ------------------------------------------------------------------------- */

const THEME_OPTIONS = [
  {
    value: "light",
    label: "Light",
    description: "Paper canvas with the sky accent.",
    icon: Sun,
  },
  {
    value: "dark",
    label: "Dark",
    description: "Deep teal control room.",
    icon: Moon,
  },
  {
    value: "system",
    label: "System",
    description: "Follow this computer's setting.",
    icon: Monitor,
  },
] as const;

function ThemeSwatch({ mode }: { mode: DemoAppearance["theme"] }) {
  if (mode === "system") {
    return (
      <span className="flex h-16 overflow-hidden rounded-lg border border-black/10">
        <span className="flex w-1/2 flex-col gap-1.5 bg-[#f4fafd] p-2">
          <span className="h-1.5 w-8 rounded-full bg-[#0a2f3e]/40" />
          <span className="h-2 w-full rounded bg-[#e6f5fa]" />
          <span className="h-2 w-2/3 rounded bg-[#e6f5fa]" />
        </span>
        <span className="flex w-1/2 flex-col gap-1.5 bg-[#071b24] p-2">
          <span className="h-1.5 w-8 rounded-full bg-[#87ceeb]" />
          <span className="h-2 w-full rounded bg-[#103543]" />
          <span className="h-2 w-2/3 rounded bg-[#103543]" />
        </span>
      </span>
    );
  }
  const dark = mode === "dark";
  return (
    <span
      className={cn(
        "flex h-16 flex-col gap-1.5 rounded-lg border p-2",
        dark
          ? "border-white/10 bg-[#071b24]"
          : "border-black/10 bg-[#f4fafd]",
      )}
    >
      <span
        className={cn(
          "h-1.5 w-10 rounded-full",
          dark ? "bg-[#87ceeb]" : "bg-[#0a2f3e]/50",
        )}
      />
      <span
        className={cn(
          "h-2 w-full rounded",
          dark ? "bg-[#103543]" : "bg-[#e6f5fa]",
        )}
      />
      <span
        className={cn(
          "h-2 w-2/3 rounded",
          dark ? "bg-[#103543]" : "bg-[#e6f5fa]",
        )}
      />
    </span>
  );
}

function AppearanceSection() {
  const { state, updateState } = useDemo();
  const appearance = state.preferences.appearance;
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 2500);
    return () => clearTimeout(timer);
  }, [saved]);

  const update = (patch: Partial<DemoAppearance>) => {
    updateState((current) => ({
      ...current,
      preferences: {
        ...current.preferences,
        appearance: { ...current.preferences.appearance, ...patch },
      },
    }));
    setSaved(true);
  };

  return (
    <div className="space-y-6">
      <SettingsCard
        title="Theme"
        description="Applies to every demo screen, including the sidebar, topbar, and dialogs."
        action={
          <span
            role="status"
            className={cn(
              "text-[11px] font-medium",
              saved ? "text-success" : "text-muted-foreground",
            )}
          >
            {saved ? "Saved to this browser" : "Saved automatically"}
          </span>
        }
      >
        <div
          role="radiogroup"
          aria-label="Theme"
          className="grid gap-3 sm:grid-cols-3"
        >
          {THEME_OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = appearance.theme === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => update({ theme: option.value })}
                className={cn(
                  "rounded-xl border p-3 text-left transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  active
                    ? "border-primary bg-primary/[0.06] ring-2 ring-primary/30"
                    : "border-border bg-card hover:border-primary/40",
                )}
              >
                <ThemeSwatch mode={option.value} />
                <span className="mt-3 flex items-center gap-2 text-sm font-medium text-foreground">
                  <Icon aria-hidden="true" className="size-4" />
                  {option.label}
                  {active ? (
                    <Check
                      aria-hidden="true"
                      className="ml-auto size-4 text-success"
                    />
                  ) : null}
                </span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {option.description}
                </span>
              </button>
            );
          })}
        </div>
      </SettingsCard>

      <SettingsCard
        title="Layout & motion"
        description="Tune how dense the workspace feels without changing any data."
      >
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                Table density
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Compact trims row padding across ledgers and registers.
              </p>
            </div>
            <div
              role="group"
              aria-label="Table density"
              className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5"
            >
              {(
                [
                  { value: "comfortable", label: "Comfortable" },
                  { value: "compact", label: "Compact" },
                ] as const
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={appearance.density === option.value}
                  onClick={() => update({ density: option.value })}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    appearance.density === option.value
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-border/60 pt-4">
            <ToggleRow
              title="Reduce motion"
              description="Shorten transitions and disable decorative animation across the demo."
              checked={appearance.reduceMotion}
              onChange={(next) => update({ reduceMotion: next })}
              label="Reduce motion"
            />
          </div>
        </div>
      </SettingsCard>

      <div className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
        Theme and density are stored with the rest of the demo snapshot. Use
        <span className="mx-1 font-medium text-foreground">
          Reset sample data
        </span>
        in the banner to restore the light defaults.
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Workspace
   ------------------------------------------------------------------------- */

const INDUSTRIES = [
  "Industrial Manufacturing",
  "Distribution & Logistics",
  "Retail",
  "Professional Services",
  "Technology",
];

const CURRENCIES = ["INR (₹)", "USD ($)", "EUR (€)", "GBP (£)", "AED (د.إ)"];
const DATE_FORMATS = ["DD MMM YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "DD/MM/YYYY"];
const TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Europe/London",
  "America/New_York",
  "Asia/Singapore",
];

function WorkspaceSection() {
  const { state, updateState } = useDemo();
  const [form, setForm] = useState<DemoWorkspacePreferences>(
    state.preferences.workspace,
  );
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setForm(state.preferences.workspace);
  }, [state.preferences.workspace]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 4000);
    return () => clearTimeout(timer);
  }, [saved]);

  const dirty =
    JSON.stringify(form) !== JSON.stringify(state.preferences.workspace);
  const valid = form.name.trim().length > 0 && form.slug.trim().length > 0;

  const save = () => {
    updateState((current) => ({
      ...current,
      preferences: {
        ...current.preferences,
        workspace: { ...form, name: form.name.trim(), slug: form.slug.trim() },
      },
    }));
    setSaved(true);
  };

  const update = <K extends keyof DemoWorkspacePreferences>(
    key: K,
    value: DemoWorkspacePreferences[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="space-y-6">
      <SettingsCard
        title="Company identity"
        description="Printed on documents, exports, and every module header."
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) save();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="demo-workspace-name" label="Workspace name">
              <Input
                id="demo-workspace-name"
                value={form.name}
                onChange={(event) => update("name", event.target.value)}
              />
            </Field>
            <Field
              id="demo-workspace-slug"
              label="Workspace URL"
              hint="Demo only this slug is not provisioned anywhere."
            >
              <div className="flex items-center rounded-lg border border-input focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
                <span className="shrink-0 border-r border-input px-2.5 text-xs text-muted-foreground">
                  skyrict.demo/
                </span>
                <input
                  id="demo-workspace-slug"
                  value={form.slug}
                  onChange={(event) => update("slug", event.target.value)}
                  className="h-8 w-full min-w-0 rounded-r-lg bg-transparent px-2.5 text-sm outline-none"
                />
              </div>
            </Field>
            <Field id="demo-workspace-industry" label="Industry">
              <NativeSelect
                id="demo-workspace-industry"
                value={form.industry}
                onChange={(event) => update("industry", event.target.value)}
              >
                {INDUSTRIES.map((industry) => (
                  <option key={industry} value={industry}>
                    {industry}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-workspace-fiscal" label="Fiscal year starts">
              <NativeSelect
                id="demo-workspace-fiscal"
                value={form.fiscalYearStart}
                onChange={(event) =>
                  update("fiscalYearStart", event.target.value)
                }
              >
                {MONTHS.map((month) => (
                  <option key={month} value={month}>
                    {month}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-workspace-currency" label="Base currency">
              <NativeSelect
                id="demo-workspace-currency"
                value={form.currency}
                onChange={(event) => update("currency", event.target.value)}
              >
                {CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-workspace-timezone" label="Operating timezone">
              <NativeSelect
                id="demo-workspace-timezone"
                value={form.timezone}
                onChange={(event) => update("timezone", event.target.value)}
              >
                {TIMEZONES.map((timezone) => (
                  <option key={timezone} value={timezone}>
                    {timezone}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-workspace-date-format" label="Date format">
              <NativeSelect
                id="demo-workspace-date-format"
                value={form.dateFormat}
                onChange={(event) => update("dateFormat", event.target.value)}
              >
                {DATE_FORMATS.map((format) => (
                  <option key={format} value={format}>
                    {format}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="demo-workspace-week-start" label="Week starts on">
              <NativeSelect
                id="demo-workspace-week-start"
                value={form.weekStart}
                onChange={(event) =>
                  update(
                    "weekStart",
                    event.target.value as DemoWorkspacePreferences["weekStart"],
                  )
                }
              >
                <option value="monday">Monday</option>
                <option value="sunday">Sunday</option>
              </NativeSelect>
            </Field>
          </div>
          <SaveBar
            dirty={dirty}
            saved={saved}
            onSave={save}
            disabled={!valid}
            label="Save workspace"
          />
        </form>
      </SettingsCard>

      <SettingsCard
        title="Operating preferences"
        description="Applied to the demo workspace after you save."
      >
        <div className="divide-y divide-border/60">
          <ToggleRow
            title="SkyAgent suggestions"
            description="Surface AI recommendations on inventory, finance, and people screens."
            checked={form.aiAssist}
            onChange={(next) => update("aiAssist", next)}
            label="SkyAgent suggestions"
          />
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          These switches are part of the saved workspace snapshot. Save above to
          persist them. Table density lives under{" "}
          <Link
            href="/demo/erp/settings/appearance"
            prefetch={false}
            className="font-medium text-foreground underline underline-offset-2"
          >
            Appearance
          </Link>
          .
        </p>
      </SettingsCard>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Notifications
   ------------------------------------------------------------------------- */

const DIGEST_OPTIONS = [
  { value: "realtime", label: "Real time" },
  { value: "hourly", label: "Hourly" },
  { value: "daily", label: "Daily" },
] as const;

function NotificationsSection() {
  const { state, updateState } = useDemo();
  const prefs = state.preferences.notifications;

  const updateChannel = (
    id: string,
    channel: "inApp" | "email" | "push",
    value: boolean,
  ) => {
    updateState((current) => ({
      ...current,
      preferences: {
        ...current.preferences,
        notifications: {
          ...current.preferences.notifications,
          categories: current.preferences.notifications.categories.map(
            (category) =>
              category.id === id
                ? { ...category, [channel]: value }
                : category,
          ),
        },
      },
    }));
  };

  const updatePrefs = (
    patch: Partial<typeof prefs>,
  ) =>
    updateState((current) => ({
      ...current,
      preferences: {
        ...current.preferences,
        notifications: {
          ...current.preferences.notifications,
          ...patch,
        },
      },
    }));

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-2.5 rounded-xl border border-primary/25 bg-primary/[0.06] px-4 py-3 text-xs text-foreground">
        <Sparkles
          aria-hidden="true"
          className="mt-0.5 size-4 shrink-0 text-primary"
        />
        <p>
          Changes save instantly in the demo. The bell in the topbar reads the
          same preferences, so muting a category here is reflected in the
          workspace snapshot.
        </p>
      </div>

      <SettingsCard
        title="Delivery by category"
        description="Each channel is independent. Security alerts stay on in-app by policy."
      >
        <div className="hidden grid-cols-[minmax(0,1fr)_repeat(3,4.5rem)] gap-3 border-b border-border/60 pb-2 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase sm:grid">
          <span>Signal</span>
          <span className="text-center">In-app</span>
          <span className="text-center">Email</span>
          <span className="text-center">Push</span>
        </div>
        <ul className="divide-y divide-border/60">
          {prefs.categories.map((category) => (
            <li
              key={category.id}
              className="grid gap-3 py-3 sm:grid-cols-[minmax(0,1fr)_repeat(3,4.5rem)] sm:items-center"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {category.label}
                  {category.locked ? (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                      <LockKeyhole aria-hidden="true" className="size-2.5" />
                      Required
                    </span>
                  ) : null}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {category.description}
                </p>
              </div>
              {(["inApp", "email", "push"] as const).map((channel) => (
                <div
                  key={channel}
                  className="flex items-center justify-between gap-2 sm:justify-center"
                >
                  <span className="text-[11px] font-medium text-muted-foreground sm:hidden">
                    {channel === "inApp"
                      ? "In-app"
                      : channel === "email"
                        ? "Email"
                        : "Push"}
                  </span>
                  <Toggle
                    checked={category[channel]}
                    onChange={(next) =>
                      updateChannel(category.id, channel, next)
                    }
                    label={`${category.label} ${
                      channel === "inApp"
                        ? "in-app"
                        : channel === "email"
                          ? "email"
                          : "push"
                    }`}
                    disabled={category.locked && channel === "inApp"}
                  />
                </div>
              ))}
            </li>
          ))}
        </ul>
      </SettingsCard>

      <SettingsCard
        title="Rhythm"
        description="Batch low-priority signals so the urgent ones keep their weight."
      >
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                Digest frequency
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Applies to everything except security and payroll compliance.
              </p>
            </div>
            <div
              role="group"
              aria-label="Digest frequency"
              className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5"
            >
              {DIGEST_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={prefs.digestFrequency === option.value}
                  onClick={() =>
                    updatePrefs({ digestFrequency: option.value })
                  }
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    prefs.digestFrequency === option.value
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-border/60 pt-4">
            <ToggleRow
              title="Quiet hours"
              description="Hold non-critical pushes overnight in your workspace timezone."
              checked={prefs.quietHoursEnabled}
              onChange={(next) =>
                updatePrefs({ quietHoursEnabled: next })
              }
              label="Quiet hours"
            />
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <Field id="demo-quiet-start" label="From">
                <Input
                  id="demo-quiet-start"
                  type="time"
                  value={prefs.quietHoursStart}
                  onChange={(event) =>
                    updatePrefs({ quietHoursStart: event.target.value })
                  }
                  disabled={!prefs.quietHoursEnabled}
                  className="w-32"
                />
              </Field>
              <Field id="demo-quiet-end" label="Until">
                <Input
                  id="demo-quiet-end"
                  type="time"
                  value={prefs.quietHoursEnd}
                  onChange={(event) =>
                    updatePrefs({ quietHoursEnd: event.target.value })
                  }
                  disabled={!prefs.quietHoursEnabled}
                  className="w-32"
                />
              </Field>
              <p className="pb-1.5 text-[11px] text-muted-foreground">
                {prefs.quietHoursEnabled
                  ? `Pushes pause ${prefs.quietHoursStart}–${prefs.quietHoursEnd} · ${prefs.quietHoursStart > prefs.quietHoursEnd ? "overnight" : "same day"}`
                  : "Quiet hours are off"}
              </p>
            </div>
          </div>
        </div>
      </SettingsCard>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Billing
   ------------------------------------------------------------------------- */

const DEMO_INVOICES = [
  {
    id: "INV-2026-10",
    date: "1 Oct 2026",
    amount: "₹74,000",
    status: "Paid",
  },
  {
    id: "INV-2026-09",
    date: "1 Sep 2026",
    amount: "₹74,000",
    status: "Paid",
  },
  {
    id: "INV-2026-08",
    date: "1 Aug 2026",
    amount: "₹68,500",
    status: "Paid",
  },
  {
    id: "INV-2026-07",
    date: "1 Jul 2026",
    amount: "₹68,500",
    status: "Paid",
  },
];

function Meter({
  label,
  value,
  max,
  suffix,
}: {
  label: string;
  value: number;
  max: number;
  suffix: string;
}) {
  const percent = Math.min(100, Math.round((value / max) * 100));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {suffix}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full",
            percent >= 90 ? "bg-amber-500" : "bg-primary",
          )}
          style={{ width: `${Math.max(4, percent)}%` }}
        />
      </div>
    </div>
  );
}

function BillingSection() {
  const { state } = useDemo();
  const [billingOpen, setBillingOpen] = useState(false);
  const seats = state.employees.length;

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-primary/30 bg-gradient-to-br from-secondary via-card to-card">
        <div className="flex flex-wrap items-start justify-between gap-4 p-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge>Current plan</Badge>
              <span className="text-xs text-muted-foreground">
                Renews 1 Nov 2026
              </span>
            </div>
            <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-foreground">
              Scale
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              ₹74,000 / month · billed annually · {seats} of 25 seats
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setBillingOpen(true)}
            >
              <CreditCard aria-hidden="true" />
              Manage billing
            </Button>
            <Button asChild variant="brand" size="sm">
              <Link href="/signup">
                Talk to sales
                <ArrowUpRight aria-hidden="true" />
              </Link>
            </Button>
          </div>
        </div>
        <div className="grid gap-4 border-t border-border/60 bg-card/70 p-5 sm:grid-cols-3">
          <div>
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              Next invoice
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
              ₹74,000
            </p>
            <p className="text-xs text-muted-foreground">1 Nov 2026</p>
          </div>
          <div>
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              Annual contract
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
              ₹8,88,000
            </p>
            <p className="text-xs text-muted-foreground">
              Locked until 1 Nov 2027
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              Payment method
            </p>
            <p className="mt-1 flex items-center gap-2 text-sm font-medium text-foreground">
              <span className="rounded bg-[#1a1f71] px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-white">
                VISA
              </span>
              •••• 4242
            </p>
            <p className="text-xs text-muted-foreground">Expires 08 / 29</p>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <SettingsCard
          title="Usage this cycle"
          description="Refreshed every five minutes in a live workspace."
        >
          <div className="space-y-4">
            <Meter
              label="Team seats"
              value={seats}
              max={25}
              suffix={`${seats} of 25`}
            />
            <Meter
              label="Automation runs"
              value={8420}
              max={10000}
              suffix="8,420 of 10,000"
            />
            <Meter
              label="Document storage"
              value={62}
              max={100}
              suffix="62 of 100 GB"
            />
            <Meter
              label="SkyAgent credits"
              value={18300}
              max={25000}
              suffix="18,300 of 25,000"
            />
          </div>
        </SettingsCard>

        <SettingsCard
          title="Plan headroom"
          description="What the next tier unlocks."
        >
          <ul className="space-y-2.5 text-xs text-muted-foreground">
            {[
              "Unlimited warehouses",
              "SSO + SCIM provisioning",
              "Custom approval chains",
              "Dedicated success manager",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <Check
                  aria-hidden="true"
                  className="mt-0.5 size-3.5 shrink-0 text-success"
                />
                {item}
              </li>
            ))}
          </ul>
          <Button asChild variant="outline" size="sm" className="mt-4 w-full">
            <Link href="/signup" prefetch={false}>
              Compare Enterprise
            </Link>
          </Button>
        </SettingsCard>
      </div>

      <SettingsCard
        title="Invoice history"
        description="Every invoice for this sample workspace, marked paid."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border/60 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="py-2 pr-3">
                  Invoice
                </th>
                <th scope="col" className="py-2 pr-3">
                  Date
                </th>
                <th scope="col" className="py-2 pr-3 text-right">
                  Amount
                </th>
                <th scope="col" className="py-2 text-right">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {DEMO_INVOICES.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="py-2.5 pr-3 font-mono text-xs text-foreground">
                    {invoice.id}
                  </td>
                  <td className="py-2.5 pr-3 text-muted-foreground">
                    {invoice.date}
                  </td>
                  <td className="py-2.5 pr-3 text-right font-medium tabular-nums text-foreground">
                    {invoice.amount}
                  </td>
                  <td className="py-2.5 text-right">
                    <Badge variant="secondary">{invoice.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SettingsCard>

      <Dialog open={billingOpen} onOpenChange={setBillingOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Billing is read-only in the demo</DialogTitle>
            <DialogDescription>
              Payment methods, plan changes, and invoices are disabled on the
              public walkthrough. Create a real workspace to connect a billing
              account.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBillingOpen(false)}>
              Keep exploring
            </Button>
            <Button asChild onClick={() => setBillingOpen(false)}>
              <Link href="/signup">Create real workspace</Link>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Security
   ------------------------------------------------------------------------- */

function SecuritySection() {
  const { state, updateState } = useDemo();
  const security = state.security;
  const [status, setStatus] = useState<string | null>(null);

  const score =
    60 +
    (security.twoFactorEnabled ? 20 : 0) +
    (security.loginAlerts ? 10 : 0) +
    (security.passkeys.length > 0 ? 10 : 0);

  const updateSecurity = (patch: Partial<DemoSecurity>) =>
    updateState((current) => ({
      ...current,
      security: { ...current.security, ...patch },
    }));

  const revoke = (id: string) => {
    updateSecurity({
      sessions: security.sessions.filter((session) => session.id !== id),
    });
    setStatus("Session revoked in this demo.");
  };

  const removePasskey = (id: string) => {
    updateSecurity({
      passkeys: security.passkeys.filter((passkey) => passkey.id !== id),
    });
    setStatus("Passkey removed from this demo.");
  };

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-4">
          <div
            className="flex size-20 shrink-0 items-center justify-center rounded-full"
            style={{
              background: `conic-gradient(var(--primary) ${
                score * 3.6
              }deg, var(--muted) 0deg)`,
            }}
          >
            <div className="flex size-16 flex-col items-center justify-center rounded-full bg-card">
              <span className="font-display text-xl font-semibold tabular-nums text-foreground">
                {score}
              </span>
              <span className="text-[9px] font-semibold tracking-wider text-muted-foreground uppercase">
                score
              </span>
            </div>
          </div>
          <div>
            <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
              {score >= 90 ? "Hardened" : "Good, with headroom"}
            </h2>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
              Two-factor, passkeys, and login alerts cover this workspace.
              Rolling recovery codes is the only remaining recommendation.
            </p>
          </div>
        </div>
        <Badge variant="secondary" className="shrink-0">
          {security.twoFactorEnabled ? "2FA enforced" : "2FA off"}
        </Badge>
      </section>

      <SettingsCard
        title="Sign-in protection"
        description="Applies to every member of the demo workspace."
      >
        <div className="divide-y divide-border/60">
          <ToggleRow
            title="Two-factor authentication"
            description="Require a second factor for password sign-ins."
            checked={security.twoFactorEnabled}
            onChange={(next) => {
              updateSecurity({ twoFactorEnabled: next });
              setStatus("Two-factor preference saved.");
            }}
            label="Two-factor authentication"
          />
          <ToggleRow
            title="Login alerts"
            description="Email me whenever a new device signs in."
            checked={security.loginAlerts}
            onChange={(next) => {
              updateSecurity({ loginAlerts: next });
              setStatus("Login alert preference saved.");
            }}
            label="Login alerts"
          />
        </div>
      </SettingsCard>

      <SettingsCard
        title="Passkeys"
        description="Phishing-resistant sign-in bound to this device."
        action={
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              setStatus("Passkey enrolment is disabled in the demo.")
            }
          >
            <Fingerprint aria-hidden="true" />
            Add passkey
          </Button>
        }
      >
        <ul className="space-y-3">
          {security.passkeys.map((passkey) => (
            <li
              key={passkey.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5"
            >
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <Fingerprint aria-hidden="true" className="size-4" />
                </span>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {passkey.name}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Added {formatDemoDate(passkey.addedAt)} · Last used{" "}
                    {passkey.lastUsed}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove passkey ${passkey.name}`}
                onClick={() => removePasskey(passkey.id)}
              >
                Remove
              </Button>
            </li>
          ))}
          {security.passkeys.length === 0 ? (
            <li className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              No passkeys on this workspace.
            </li>
          ) : null}
        </ul>
      </SettingsCard>

      <SettingsCard
        title="Active sessions"
        description="Revoke anything you do not recognise. The current session stays connected."
      >
        {status ? (
          <p
            role="status"
            className="mb-3 rounded-lg bg-secondary px-3 py-2 text-xs font-medium text-secondary-foreground"
          >
            {status}
          </p>
        ) : null}
        <ul className="divide-y divide-border/60">
          {security.sessions.map((session) => (
            <li
              key={session.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
            >
              <div className="flex items-start gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <MonitorSmartphone aria-hidden="true" className="size-4" />
                </span>
                <div>
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                    {session.device}
                    {session.current ? (
                      <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-success">
                        This device
                      </span>
                    ) : null}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {session.browser} · {session.location} · {session.lastActive}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={session.current}
                aria-label={`Revoke session on ${session.device}`}
                onClick={() => revoke(session.id)}
              >
                {session.current ? "Current" : "Revoke"}
              </Button>
            </li>
          ))}
        </ul>
      </SettingsCard>

      <SettingsCard
        title="Recent security activity"
        description="The last three events on this account."
      >
        <ol className="space-y-3">
          {[
            {
              title: "Passkey used on MacBook Pro",
              meta: "Today · 09:42 · Bengaluru, India",
            },
            {
              title: "Recovery codes regenerated",
              meta: "12 Oct 2026 · 16:20 · Mumbai, India",
            },
            {
              title: "Two-factor enforced for all admins",
              meta: "1 Oct 2026 · 11:05 · Policy change",
            },
          ].map((event) => (
            <li key={event.title} className="flex items-start gap-3">
              <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary ring-4 ring-primary/15" />
              <div>
                <p className="text-sm font-medium text-foreground">
                  {event.title}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {event.meta}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </SettingsCard>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Integrations
   ------------------------------------------------------------------------- */

const INTEGRATION_FILTERS: Array<"All" | DemoIntegration["category"]> = [
  "All",
  "Finance",
  "CRM",
  "Communication",
  "Data",
  "AI",
];

function IntegrationsSection() {
  const { state, updateState } = useDemo();
  const [filter, setFilter] = useState<(typeof INTEGRATION_FILTERS)[number]>(
    "All",
  );
  const [savedId, setSavedId] = useState<string | null>(null);

  useEffect(() => {
    if (!savedId) return;
    const timer = setTimeout(() => setSavedId(null), 2500);
    return () => clearTimeout(timer);
  }, [savedId]);

  const connected = state.integrations.filter(
    (integration) => integration.connected,
  ).length;

  const toggle = (integration: DemoIntegration) => {
    updateState((current) => ({
      ...current,
      integrations: current.integrations.map((entry) =>
        entry.id === integration.id
          ? {
              ...entry,
              connected: !entry.connected,
              lastSync: !entry.connected ? "Just now" : "Never",
            }
          : entry,
      ),
    }));
    setSavedId(integration.id);
  };

  const visible = useMemo(
    () =>
      filter === "All"
        ? state.integrations
        : state.integrations.filter(
            (integration) => integration.category === filter,
          ),
    [filter, state.integrations],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {INTEGRATION_FILTERS.map((entry) => (
            <button
              key={entry}
              type="button"
              aria-pressed={filter === entry}
              onClick={() => setFilter(entry)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                filter === entry
                  ? "border-primary bg-primary/15 text-foreground"
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {entry}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground" role="status">
          {connected} of {state.integrations.length} connected
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {visible.map((integration) => (
          <article
            key={integration.id}
            className={cn(
              "flex flex-col rounded-xl border bg-card p-4",
              integration.id === "skyagent"
                ? "border-primary/40 bg-primary/[0.04]"
                : "border-border",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <span className="flex h-9 shrink-0 items-center">
                <Image
                  src={integration.logo}
                  alt=""
                  width={integration.logoWidth}
                  height={integration.logoHeight}
                  unoptimized
                  className={cn(
                    "h-full w-auto object-contain",
                    integration.logoInvertOnDark && "demo-logo-invert",
                  )}
                />
              </span>
              <Toggle
                checked={integration.connected}
                onChange={() => toggle(integration)}
                label={
                  integration.connected
                    ? `Disconnect ${integration.name}`
                    : `Connect ${integration.name}`
                }
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">
                {integration.name}
              </h3>
              {integration.id === "skyagent" ? (
                <Badge variant="outline">Native</Badge>
              ) : null}
            </div>
            <p className="mt-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              {integration.category}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {integration.description}
            </p>
            <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-[11px]">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 font-medium",
                  integration.connected
                    ? "text-success"
                    : "text-muted-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 rounded-full",
                    integration.connected ? "bg-emerald-500" : "bg-muted-foreground/40",
                  )}
                />
                {integration.connected ? "Connected" : "Not connected"}
              </span>
              <span className="text-muted-foreground">
                {savedId === integration.id
                  ? "Saved just now"
                  : `Synced ${integration.lastSync}`}
              </span>
            </div>
          </article>
        ))}

        <article className="flex flex-col justify-between rounded-xl border border-dashed border-border bg-muted/20 p-4">
          <div>
            <span className="flex size-10 items-center justify-center rounded-xl bg-card text-primary">
              <Layers aria-hidden="true" className="size-5" />
            </span>
            <h3 className="mt-3 text-sm font-semibold text-foreground">
              Need something else?
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Webhooks, CSV bridges, and custom connectors are available on the
              Enterprise plan.
            </p>
          </div>
          <Button asChild variant="outline" size="sm" className="mt-4 w-full">
            <Link href="/signup" prefetch={false}>
              Request an integration
              <ArrowUpRight aria-hidden="true" />
            </Link>
          </Button>
        </article>
      </div>
    </div>
  );
}
