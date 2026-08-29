"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { ErpDataTable, ErpDataTableSkeleton, type ErpColumn } from "@/components/dashboard/shared/erp-data-table";
import { Button } from "@/components/ui/button";
import { TruncatedTooltip } from "@/components/ui/truncated-tooltip";
import {
  getQualityOrgKpi,
  listQualityScores,
  type EmployeeQualityScore,
  type QualityGrade,
  type QualityOrgKpi,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

const GRADE_STYLES: Record<QualityGrade, string> = {
  A: "bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-400",
  B: "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-400",
  C: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400",
  D: "bg-orange-500/15 text-orange-700 ring-1 ring-orange-500/30 dark:text-orange-400",
  F: "bg-destructive/10 text-destructive ring-1 ring-destructive/30",
};

function GradeBadge({ grade }: { grade: QualityGrade }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        GRADE_STYLES[grade] ?? GRADE_STYLES.F,
      )}
    >
      {grade}
    </span>
  );
}

/** "missing_email" → "missing email" — the raw codes shown in the tooltip. */
function humanizeIssue(issue: string): string {
  const [, qualifier] = issue.split(":", 2);
  const code = qualifier ?? issue;
  return code.replaceAll("_", " ");
}

function issuesSummary(issues: EmployeeQualityScore["issues"]): string {
  return [...issues.mandatory, ...issues.contact, ...issues.document]
    .map(humanizeIssue)
    .join(", ");
}

function percent(score: number, max: number): string {
  return `${Math.round((score / max) * 100)}%`;
}

type PageStatus =
  | { state: "loading" }
  | { state: "error"; message: string }
  | {
      state: "ready";
      kpi: QualityOrgKpi | null;
      scores: EmployeeQualityScore[];
      totalPages: number;
      /** Set when the L2 list is off-limits (`erp.hr.ai.individual` absent). */
      individualBlocked: string | null;
      listError: string | null;
    };

export function DataQualityClient() {
  const [status, setStatus] = useState<PageStatus>({ state: "loading" });
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setStatus({ state: "loading" });
    const [kpiResult, listResult] = await Promise.allSettled([
      getQualityOrgKpi(),
      listQualityScores({ page, pageSize: PAGE_SIZE }),
    ]);

    if (kpiResult.status === "rejected") {
      const error = kpiResult.reason;
      setStatus({
        state: "error",
        message: error instanceof ApiError ? error.message : "Could not load data quality.",
      });
      return;
    }

    let scores: EmployeeQualityScore[] = [];
    let totalPages = 1;
    let individualBlocked: string | null = null;
    let listError: string | null = null;
    if (listResult.status === "rejected") {
      const error = listResult.reason;
      if (error instanceof ApiError && error.status === 403) {
        individualBlocked =
          "Per-employee scores need the erp.hr.ai.individual permission — the aggregate view below is still available.";
      } else {
        listError =
          error instanceof ApiError ? error.message : "Could not load the employee table.";
      }
    } else {
      scores = listResult.value.items;
      totalPages = listResult.value.meta.total_pages;
    }

    setStatus({
      state: "ready",
      kpi: kpiResult.value,
      scores,
      totalPages,
      individualBlocked,
      listError,
    });
  }, [page]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ErpColumn<EmployeeQualityScore>[] = [
    {
      key: "name",
      label: "Employee",
      render: (row) => (
        <span className="font-medium text-foreground">
          {row.name ?? row.employeeId}
          {row.employeeNumber ? (
            <span className="ml-2 font-normal tabular-nums text-muted-foreground">
              {row.employeeNumber}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "departmentName",
      label: "Department",
      render: (row) => (
        <span className="text-muted-foreground">{row.departmentName ?? "Unassigned"}</span>
      ),
    },
    {
      key: "grade",
      label: "Grade",
      render: (row) => <GradeBadge grade={row.grade} />,
    },
    {
      key: "mandatoryScore",
      label: "Identity",
      align: "right",
      render: (row) => (
        <span className="tabular-nums">{percent(row.mandatoryScore, 0.5)}</span>
      ),
    },
    {
      key: "contactScore",
      label: "Contact",
      align: "right",
      render: (row) => (
        <span className="tabular-nums">{percent(row.contactScore, 0.25)}</span>
      ),
    },
    {
      key: "documentScore",
      label: "Documents",
      align: "right",
      render: (row) => (
        <span className="tabular-nums">{percent(row.documentScore, 0.25)}</span>
      ),
    },
    {
      key: "score",
      label: "Overall",
      align: "right",
      render: (row) => (
        <span className="font-medium tabular-nums">{percent(row.score, 1)}</span>
      ),
    },
    {
      key: "issues",
      label: "Issues",
      render: (row) => (
        <TruncatedTooltip text={issuesSummary(row.issues)} className="text-muted-foreground" />
      ),
    },
  ];

  if (status.state === "loading") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Data quality"
          description="How complete every employee's record is — identity, contact, and documents."
          icon={ClipboardCheck}
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
          <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
          <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
          <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
        </div>
        <ErpDataTableSkeleton columns={8} />
      </div>
    );
  }

  if (status.state === "error") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Data quality"
          description="How complete every employee's record is — identity, contact, and documents."
          icon={ClipboardCheck}
        />
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-destructive">{status.message}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  const { kpi, scores, totalPages } = status;
  const gradeOrder: QualityGrade[] = ["A", "B", "C", "D", "F"];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data quality"
        description="How complete every employee's record is — identity, contact, and documents."
        icon={ClipboardCheck}
      />

      {kpi ? (
        <section aria-label="Data-quality summary" className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Scored employees</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{kpi.totalScored}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Average score</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">
                {kpi.totalScored > 0 ? percent(kpi.averageScore, 1) : "—"}
              </p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Lowest grade present</p>
              <p className="mt-2 text-2xl font-semibold">
                {[...gradeOrder].reverse().find((grade) => (kpi.gradeDistribution[grade] ?? 0) > 0) ??
                  "—"}
              </p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Needs attention</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">
                {(kpi.gradeDistribution["D"] ?? 0) + (kpi.gradeDistribution["F"] ?? 0)}{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  D or F grades
                </span>
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">{kpi.narrative}</p>
            {kpi.departmentAverages.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {kpi.departmentAverages.map((dept) => (
                  <span
                    key={dept.departmentName}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-3 py-1 text-xs"
                  >
                    <span className="font-medium text-foreground">{dept.departmentName}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {percent(dept.averageScore, 1)}
                    </span>
                    {dept.lowQualityCount > 0 ? (
                      <span className="text-destructive">{dept.lowQualityCount} low</span>
                    ) : null}
                  </span>
                ))}
              </div>
            ) : null}
            <p className="mt-3 text-xs text-muted-foreground">
              As of {formatDateTime(kpi.generatedAt)}
            </p>
          </div>
        </section>
      ) : null}

      <section aria-label="Per-employee scores" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
            Employees by score
          </h2>
          <p className="text-xs text-muted-foreground">
            Identity 50% · Contact 25% · Documents 25%
          </p>
        </div>

        {status.individualBlocked ? (
          <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {status.individualBlocked}
          </p>
        ) : null}
        {status.listError ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium text-destructive">
            {status.listError}
          </p>
        ) : null}

        {status.individualBlocked || status.listError ? null : (
          <ErpDataTable
            columns={columns}
            rows={scores}
            meta={{
              total: scores.length,
              page,
              page_size: PAGE_SIZE,
              total_pages: totalPages,
            }}
            onPageChange={setPage}
          />
        )}
      </section>
    </div>
  );
}