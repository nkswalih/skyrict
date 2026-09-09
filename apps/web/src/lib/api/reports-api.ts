import {
  ApiError,
  apiFetch,
  apiFetchRaw,
  apiPost,
  apiPostBody,
  buildQueryString,
} from "@/lib/api/http";

/*
 * Typed client for the Core reporting feature through the BFF proxy at
 * /api/v1/reports. The shapes mirror the service's ReportDefinition,
 * ReportRunResult and ReportSnapshot schemas; every call goes through the
 * shared session-hydration/refresh chain in lib/api/http.
 */

const REPORTS_BASE = "/api/v1/reports";

/* ---------------------------------------------------------------------------
 * Types
 * ------------------------------------------------------------------------- */

export interface ReportDefinition {
  id: string;
  slug: string;
  title: string;
  module: string;
  description: string | null;
  params: string[];
  /** NL-builder selectable vocabulary (SKY-80): the dataset the template
   *  reads from and the grouping dimensions / numeric measures an LLM may
   *  pick. Populated from the canonical seed, so saved reports inherit
   *  their template's semantics. */
  dataset: string | null;
  dimensions: string[];
  measures: string[];
  permission_key: string;
  version: number;
  updated_at: string;
}

export interface ReportRunResult {
  columns: string[];
  rows: Record<string, string>[];
  truncated: boolean;
  period: string;
  snapshot_id: string;
  generated_at: string;
}

export interface ReportSnapshot {
  id: string;
  definition_id: string;
  period: string;
  generated_at: string;
}

/** The ERP workspace modules a report can belong to (seeded by Core). */
export type ReportModule = "finance" | "sales" | "inventory" | "hr" | "other";

export const REPORT_MODULES: ReportModule[] = ["finance", "sales", "inventory", "hr"];

export const REPORT_MODULE_LABELS: Record<ReportModule, string> = {
  finance: "Finance",
  sales: "Sales & CRM",
  inventory: "Inventory",
  hr: "People & HR",
  other: "Other",
};

export function normalizeModule(module?: string | null): ReportModule {
  if (!module) return "other";
  const normalized = module.toLowerCase();
  return (REPORT_MODULES as string[]).includes(normalized)
    ? (normalized as ReportModule)
    : "other";
}

/* ---------------------------------------------------------------------------
 * Fetch helpers
 * ------------------------------------------------------------------------- */

/** List report definitions, optionally filtered to one module. */
export async function listReports(module?: string): Promise<ReportDefinition[]> {
  return apiFetch<ReportDefinition[]>(`${REPORTS_BASE}${buildQueryString({ module })}`);
}

/** Fetch a single report definition by slug. */
export async function getReport(slug: string): Promise<ReportDefinition> {
  return apiFetch<ReportDefinition>(`${REPORTS_BASE}/${encodeURIComponent(slug)}`);
}

/** Run (or re-use the latest snapshot for) a report with the given parameters. */
export async function runReport(
  slug: string,
  params: Record<string, string>,
): Promise<ReportRunResult> {
  return apiPost<ReportRunResult>(`${REPORTS_BASE}/${encodeURIComponent(slug)}/run`, { params });
}

/** Export the report's current result for the given parameters as a CSV download. */
export async function exportReport(
  slug: string,
  params: Record<string, string>,
): Promise<Response> {
  return apiFetchRaw(`${REPORTS_BASE}/${encodeURIComponent(slug)}/export`, {
    method: "POST",
    body: JSON.stringify({ params }),
  });
}

/** List the most recent snapshots for a report definition, newest first. */
export async function listSnapshots(slug: string, limit = 20): Promise<ReportSnapshot[]> {
  return apiFetch<ReportSnapshot[]>(
    `${REPORTS_BASE}/${encodeURIComponent(slug)}/snapshots${buildQueryString({ limit })}`,
  );
}

export interface ReportListProvenance {
  reports: ReportDefinition[];
  /** True when the BFF served the sample fallback because Core was unreachable. */
  mockFallback: boolean;
}

/**
 * List reports together with provenance so the workspace can surface the
 * mock-fallback banner instead of ever presenting sample data as live.
 * Uses the raw fetch path to inspect the X-Mock-Fallback header the BFF sets.
 */
export async function listReportsWithProvenance(
  module?: string,
): Promise<ReportListProvenance> {
  const res = await apiFetchRaw(`${REPORTS_BASE}${buildQueryString({ module })}`);
  const payload = (await res.json().catch(() => ({}))) as {
    data?: ReportDefinition[];
    detail?: { error?: { message?: string }; message?: string } | string;
  };
  if (!res.ok) {
    const detail = payload.detail;
    const message =
      (typeof detail === "object" && detail?.error?.message) ||
      (typeof detail === "object" && detail?.message) ||
      (typeof detail === "string" ? detail : null) ||
      "Could not load reports.";
    throw new ApiError(res.status, message);
  }
  return {
    reports: payload.data ?? [],
    mockFallback: res.headers.get("x-mock-fallback")?.toLowerCase() === "true",
  };
}

/* ---------------------------------------------------------------------------
 * NL report builder (SKY-80 / RPT-AI-001)
 *
 * The builder lives on the ai-agent behind the same BFF catch-all: /ai/**
 * is proxied to the Core monolith, which forwards it to the ai-agent with
 * the caller's session scope intact. The generate response echoes the
 * resolved template slug + params (server-validated), which is exactly what
 * the save flow needs - the client holds no SQL and invents nothing.
 * ------------------------------------------------------------------------- */

const AI_BASE = "/api/v1/ai";

/** The structured report a successful generate produced. */
export interface GeneratedReportData {
  /** Slug of the canonical template the builder resolved to. */
  slug: string;
  title: string;
  module: string;
  columns: string[];
  rows: Record<string, string>[];
  truncated: boolean;
  /** Backend mirror of planChart() on the user's chosen dimensions. */
  chart_hint: "line" | "bar" | null;
  /** Server-resolved bind values (ISO dates), safe for the save echo. */
  params: Record<string, string>;
}

export interface ReportBuilderGenerateResponse {
  answer: string;
  /** Absent when the builder abstained or asked for clarification. */
  data: GeneratedReportData | null;
  model_used: string | null;
  latency_ms: number;
}

export interface ReportBuilderSaveRequest {
  slug: string;
  title: string;
  description?: string | null;
  template_slug: string;
  params: Record<string, string>;
}

export interface ReportBuilderSaveResponse {
  slug: string;
  title: string;
  module: string;
  answer: string;
  default_params: Record<string, string>;
}

/** Ask the builder to turn a natural-language prompt into a report run. */
export async function generateReport(prompt: string): Promise<ReportBuilderGenerateResponse> {
  // The generate endpoint is NOT an envelope: it returns the full result
  // object {answer, data, model_used, latency_ms} at top level. apiPost
  // would unwrap the payload's `data` key, silently dropping answer and
  // collapsing a successful report into a messageless clarification. Use the
  // raw-body client so the whole response surfaces to the workspace.
  return apiPostBody<ReportBuilderGenerateResponse>(
    `${AI_BASE}/report-builder/generate`,
    { prompt },
  );
}

/** Persist a generated report as a new runnable definition (Core endorses the SQL). */
export async function saveGeneratedReport(
  body: ReportBuilderSaveRequest,
): Promise<ReportBuilderSaveResponse> {
  // Like /generate, /save answers with the bare model (no {data: ...}
  // envelope), so the raw-body client is required - apiPost would unwrap and
  // shape-misroute the response.
  return apiPostBody<ReportBuilderSaveResponse>(
    `${AI_BASE}/report-builder/save`,
    body,
  );
}

/** A display slug for the save flow, honoring Core's [a-z0-9_-] pattern. */
export function toReportSlug(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/g, "");
  return slug || "report";
}