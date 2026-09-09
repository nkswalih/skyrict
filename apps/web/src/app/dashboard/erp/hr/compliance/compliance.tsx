"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Search, ShieldCheck } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { FilterChipGroup } from "@/components/dashboard/shared/filter-chip-group";
import { SearchableSelect, type SearchableSelectOption } from "@/components/dashboard/shared/searchable-select";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import { L3NarrativeCard } from "@/components/dashboard/erp/hr/l3-narrative-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getComplianceSummary,
  getEmployeeComplianceFindings,
  listEmployees,
  setComplianceStatus,
  type Employee,
  type HrComplianceFinding,
  type HrComplianceSummary,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-destructive/10 text-destructive ring-1 ring-destructive/30",
  high: "bg-orange-500/15 text-orange-700 ring-1 ring-orange-500/30 dark:text-orange-400",
  medium: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400",
  low: "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-400",
};

const SEVERITY_BAR: Record<string, string> = {
  critical: "bg-destructive",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-sky-500",
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const SEVERITY_TONE: Record<string, "destructive" | "warning" | "info"> = {
  critical: "destructive",
  high: "destructive",
  medium: "warning",
  low: "info",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;

const TYPE_LABEL: Record<string, string> = {
  document_expiry: "Document expiry",
  training_overdue: "Overdue training",
  contract_missing_field: "Missing record field",
};

type SeverityFilter = "all" | (typeof SEVERITY_ORDER)[number];

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("capitalize", SEVERITY_STYLES[severity] ?? "bg-muted text-muted-foreground")}
    >
      {SEVERITY_LABEL[severity] ?? severity}
    </Badge>
  );
}

function CountBar({
  label,
  count,
  max,
  barClass,
}: {
  label: string;
  count: number;
  max: number;
  barClass: string;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-32 shrink-0 truncate text-muted-foreground">{label}</span>
      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", barClass)}
          style={{ width: `${max > 0 ? (count / max) * 100 : 0}%` }}
        />
      </span>
      <span className="w-6 shrink-0 text-right font-medium tabular-nums text-foreground">
        {count}
      </span>
    </div>
  );
}

function SummaryCards({ summary }: { summary: HrComplianceSummary }) {
  const severityEntries = SEVERITY_ORDER.map(
    (severity) => [severity, summary.bySeverity[severity] ?? 0] as const,
  );
  const typeEntries = Object.entries(summary.byType).sort((a, b) => b[1] - a[1]);
  const typeMax = Math.max(1, ...typeEntries.map(([, count]) => count));
  return (
    <section aria-label="Compliance summary" className="space-y-4">
      <div className="flex items-center gap-2">
        <Badge
          variant="outline"
          className="border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-400"
        >
          L1 aggregate
        </Badge>
        <p className="text-xs text-muted-foreground">Counts only — no per-person data.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {severityEntries.map(([severity]) => {
          const count = summary.bySeverity[severity] ?? 0;
          return (
            <StatCard
              key={severity}
              icon={ShieldCheck}
              label={SEVERITY_LABEL[severity]}
              value={String(count)}
              hint={`${SEVERITY_LABEL[severity]} findings`}
              tone={SEVERITY_TONE[severity] ?? "default"}
            />
          );
        })}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard
          icon={CheckCircle2}
          label="Open findings"
          value={`${summary.openFindings} of ${summary.totalFindings}`}
          hint="Still to acknowledge or resolve"
          tone={summary.openFindings > 0 ? "warning" : "success"}
        />
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            By check type
          </p>
          <div className="mt-3 space-y-2">
            {typeEntries.length > 0 ? (
              typeEntries.map(([type, count]) => (
                <CountBar
                  key={type}
                  label={TYPE_LABEL[type] ?? type}
                  count={count}
                  max={typeMax}
                  barClass="bg-primary/70"
                />
              ))
            ) : (
              <p className="text-xs text-muted-foreground">No compliance findings.</p>
            )}
          </div>
        </div>
      </div>
      {summary.narrative || summary.generatedAt ? (
        <div className="rounded-xl border border-border bg-card p-5">
          {summary.narrative ? <p className="text-sm text-muted-foreground">{summary.narrative}</p> : null}
          {summary.generatedAt ? (
            <p className="mt-2 text-xs text-muted-foreground">As of {formatDateTime(summary.generatedAt)}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

type DetailState =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "blocked"; message: string }
  | { state: "error"; message: string }
  | { state: "ready"; findings: HrComplianceFinding[] };

function FindingRow({
  finding,
  onStatusChange,
  statusState,
}: {
  finding: HrComplianceFinding;
  onStatusChange: (checkId: string, status: "acknowledged" | "resolved") => void;
  statusState: Record<string, { busy?: boolean; error?: string }>;
}) {
  const state = statusState[finding.checkId];

  return (
    <div className="flex items-start justify-between gap-4 p-4">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <Badge variant="outline">{TYPE_LABEL[finding.checkType] ?? finding.checkType}</Badge>
          {finding.status !== "open" ? (
            <Badge variant="secondary" className="capitalize">
              {finding.status}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm font-medium text-foreground">{finding.title}</p>
        <p className="text-sm text-muted-foreground">{finding.description}</p>
        {finding.employeeNumber ? (
          <p className="text-xs text-muted-foreground">
            {finding.name && finding.employeeId ? (
              <Link
                href={`/dashboard/erp/hr/employees/${finding.employeeId}`}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                {finding.name}
              </Link>
            ) : (
              finding.name
            )}
            {finding.departmentName ? ` (${finding.departmentName})` : ""}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {finding.status === "resolved" ? (
          <CheckCircle2 aria-hidden="true" className="size-5 text-green-600" />
        ) : finding.status === "open" ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={state?.busy}
            onClick={() => onStatusChange(finding.checkId, "acknowledged")}
          >
            {state?.busy ? "Working…" : "Acknowledge"}
          </Button>
        ) : finding.status === "acknowledged" ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={state?.busy}
            onClick={() => onStatusChange(finding.checkId, "resolved")}
          >
            {state?.busy ? "Working…" : "Resolve"}
          </Button>
        ) : (
          <Badge variant="secondary" className="capitalize">
            {finding.status}
          </Badge>
        )}
        {state?.error ? (
          <p className="max-w-[220px] text-right text-xs font-medium text-destructive">{state.error}</p>
        ) : null}
      </div>
    </div>
  );
}

export function ComplianceClient() {
  const [view, setView] = useState<
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "summary"; summary: HrComplianceSummary }
  >({ state: "loading" });

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [employeesError, setEmployeesError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [query, setQuery] = useState("");

  const [detail, setDetail] = useState<DetailState>({ state: "idle" });
  const [statusState, setStatusState] = useState<Record<string, { busy?: boolean; error?: string }>>({});

  const load = useCallback(async () => {
    setView({ state: "loading" });
    try {
      const summary = await getComplianceSummary();
      setView({ state: "summary", summary });
    } catch (error) {
      setView({
        state: "error",
        message: error instanceof ApiError ? error.message : "Could not load compliance findings.",
      });
    }
  }, []);

  const loadEmployees = useCallback(async () => {
    try {
      const result = await listEmployees({ pageSize: 200, filters: { status: "active" } });
      setEmployees(result.items);
    } catch (error) {
      setEmployeesError(
        error instanceof ApiError ? error.message : "Could not load employee list.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
    void loadEmployees();
  }, [load, loadEmployees]);

  const loadDetail = useCallback((employeeId: string) => {
    setDetail({ state: "loading" });
    getEmployeeComplianceFindings(employeeId)
      .then((findings) => setDetail({ state: "ready", findings }))
      .catch((error) => {
        if (error instanceof ApiError && error.status === 403) {
          setDetail({
            state: "blocked",
            message:
              "Per-employee findings need the erp.hr.ai.individual permission — the aggregate overview above is still available.",
          });
        } else {
          setDetail({
            state: "error",
            message: error instanceof ApiError ? error.message : "Could not load compliance findings.",
          });
        }
      });
  }, []);

  const handleStatusChange = useCallback(
    (checkId: string, status: "acknowledged" | "resolved") => {
      setStatusState((current) => ({ ...current, [checkId]: { busy: true, error: undefined } }));

      setComplianceStatus(checkId, status)
        .then((updated) => {
          setDetail((current) =>
            current.state === "ready"
              ? {
                  ...current,
                  findings: current.findings.map((f) =>
                    f.checkId === checkId ? { ...f, status: updated.status } : f,
                  ),
                }
              : current,
          );
          setStatusState((current) => ({ ...current, [checkId]: { busy: false } }));

          getComplianceSummary()
            .then((summary) => {
              setView((current) =>
                current.state === "summary" ? { ...current, summary } : current,
              );
            })
            .catch(() => {});
        })
        .catch((error) => {
          setStatusState((current) => ({
            ...current,
            [checkId]: {
              busy: false,
              error:
                error instanceof ApiError && error.status === 403
                  ? "Status change needs the erp.hr.ai.acknowledge permission."
                  : error instanceof ApiError
                    ? error.message
                    : "Could not update status.",
            },
          }));
        });
    },
    [],
  );

  const employeeOptions = useMemo<SearchableSelectOption[]>(
    () =>
      employees.map((employee) => ({
        value: employee.id,
        label: `${employee.firstName} ${employee.lastName}`,
        keywords: employee.employeeNumber ?? undefined,
      })),
    [employees],
  );

  const severityOptions = useMemo<{ value: string; label: string }[]>(
    () => [
      { value: "all", label: "All" },
      ...SEVERITY_ORDER.map((severity) => ({ value: severity, label: SEVERITY_LABEL[severity] })),
    ],
    [],
  );

  const visibleFindings = useMemo(() => {
    if (detail.state !== "ready") return [];
    const needle = query.trim().toLowerCase();
    return detail.findings.filter((finding) => {
      if (severityFilter !== "all" && finding.severity !== severityFilter) return false;
      if (!needle) return true;
      const haystack = [
        finding.title,
        finding.description,
        finding.name ?? "",
        finding.employeeNumber ?? "",
        TYPE_LABEL[finding.checkType] ?? finding.checkType,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [detail, severityFilter, query]);

  const maxEmployees = employees.length;
  const empty = view.state === "summary" && view.summary.totalFindings === 0;

  const severityTotal =
    view.state === "summary"
      ? SEVERITY_ORDER.reduce(
          (sum, severity) => sum + (view.summary.bySeverity[severity] ?? 0),
          0,
        )
      : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Compliance"
        description="Auto-generated compliance findings — expiring identity documents, overdue required training, and missing employee record fields."
        icon={ShieldCheck}
      />

      {view.state === "error" ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-destructive">{view.message}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : null}

      {view.state === "loading" ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl border border-border bg-card" />
            ))}
          </div>
          <div className="h-40 animate-pulse rounded-xl border border-border bg-card" />
        </div>
      ) : null}

      {view.state === "summary" ? (
        <>
          <L3NarrativeCard
            kind="compliance_digest"
            label="Weekly compliance digest"
            accessibilityLabel="Weekly compliance digest"
          />
          <SummaryCards summary={view.summary} />
          {empty ? (
            <section
              aria-label="No compliance findings"
              className="rounded-xl border border-border bg-card p-4"
            >
              <div className="flex items-center gap-2">
                <SeverityBadge severity="low" />
                <p className="text-xs text-muted-foreground">
                  No compliance findings right now — identity documents are current, training is up
                  to date, and employee records are complete.
                </p>
              </div>
            </section>
          ) : (
            <>
              {severityTotal > 0 ? (
                <div className="rounded-xl border border-border bg-card p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                      Findings by severity
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      Tap a segment to filter a selected employee&apos;s findings
                    </p>
                  </div>
                  <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label="Findings by severity">
                    {SEVERITY_ORDER.map((severity) => {
                      const count = view.summary.bySeverity[severity] ?? 0;
                      if (count === 0) return null;
                      const active = severityFilter === severity;
                      return (
                        <button
                          key={severity}
                          type="button"
                          onClick={() => setSeverityFilter(active ? "all" : severity)}
                          aria-label={`Filter to ${SEVERITY_LABEL[severity]}`}
                          className={cn(
                            SEVERITY_BAR[severity],
                            "h-full transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            severityFilter !== "all" && !active && "opacity-30",
                          )}
                          style={{ width: `${(count / severityTotal) * 100}%` }}
                        />
                      );
                    })}
                  </div>
                  <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
                    {SEVERITY_ORDER.map((severity) => {
                      const count = view.summary.bySeverity[severity] ?? 0;
                      const active = severityFilter === severity;
                      return (
                        <li key={severity}>
                          <button
                            type="button"
                            onClick={() => setSeverityFilter(active ? "all" : severity)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-full px-1.5 py-0.5 text-xs transition-colors hover:bg-muted",
                              active ? "font-semibold text-foreground" : "text-muted-foreground",
                            )}
                          >
                            <span className={cn("size-2 rounded-full", SEVERITY_BAR[severity])} aria-hidden="true" />
                            {SEVERITY_LABEL[severity]} · {count}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}

              <section aria-label="Per-employee findings" className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                      Per-employee findings
                    </h2>
                    <Badge
                      variant="outline"
                      className="border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-400"
                    >
                      L2 individual
                    </Badge>
                  </div>
                  <SearchableSelect
                    className="w-full sm:w-64"
                    options={employeeOptions}
                    value={selectedId || null}
                    onValueChange={(value) => {
                      setSelectedId(value);
                      if (value) loadDetail(value);
                    }}
                    placeholder={`Select an employee (${maxEmployees} available)`}
                  />
                </div>

                {employeesError ? (
                  <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium text-destructive">
                    {employeesError}
                  </p>
                ) : null}

                {detail.state === "blocked" ? (
                  <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    {detail.message}
                  </p>
                ) : null}
                {detail.state === "error" ? (
                  <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium text-destructive">
                    {detail.message}
                  </p>
                ) : null}

                {selectedId && detail.state !== "idle" ? (
                  <>
                    {detail.state === "ready" && detail.findings.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="relative w-full sm:w-64">
                          <Search
                            aria-hidden="true"
                            className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                          />
                          <Input
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            className="pl-8"
                            placeholder="Search findings…"
                            aria-label="Search findings"
                          />
                        </div>
                        <FilterChipGroup
                          options={severityOptions}
                          value={severityFilter}
                          onChange={(value) => setSeverityFilter(value as SeverityFilter)}
                          ariaLabel="Filter by severity"
                        />
                      </div>
                    ) : null}
                    <div className="overflow-hidden rounded-xl border border-border bg-card">
                      {detail.state === "loading" ? (
                        <div className="space-y-2 p-4">
                          <div className="h-20 animate-pulse rounded-lg bg-muted" />
                          <div className="h-20 animate-pulse rounded-lg bg-muted" />
                        </div>
                      ) : null}
                      {detail.state === "ready" && visibleFindings.length === 0 ? (
                        <p className="p-4 text-sm text-muted-foreground">
                          {detail.findings.length === 0
                            ? "No compliance findings for this employee."
                            : "No findings match the current filter."}
                        </p>
                      ) : null}
                      {visibleFindings.length > 0 ? (
                        <ul className="divide-y divide-border">
                          {visibleFindings.map((finding) => (
                            <li key={finding.checkId}>
                              <FindingRow
                                finding={finding}
                                onStatusChange={handleStatusChange}
                                statusState={statusState}
                              />
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  </>
                ) : detail.state === "idle" ? (
                  <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    Pick an employee to see which compliance findings apply to them.
                  </p>
                ) : null}
              </section>
            </>
          )}
        </>
      ) : null}
    </div>
  );
}