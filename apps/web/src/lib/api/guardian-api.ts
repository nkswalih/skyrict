/**
 * Audit Guardian AI API client (SKY-90 wave 2).
 *
 * Weekly integrity reports behind /api/v1/ai/guardian/* - proxied through the
 * BFF to core's AI router and on to the ai-agent microservice. The report
 * LIST carries no evidence; the detail view is the only place evidence
 * payloads are exposed, so the operator can follow investigation links from
 * the report page.
 */

import { apiFetchBody, apiPostBody } from "@/lib/api/http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type GuardianReportStatus = "generated" | "reviewed" | "archived";

export type GuardianEventSeverity =
    | "info"
    | "low"
    | "medium"
    | "high"
    | "critical";

export interface GuardianReportItem {
    id: string;
    report_week_start: string;
    report_week_end: string;
    summary: string;
    total_events_scanned: number;
    flagged_count: number;
    status: GuardianReportStatus;
    generated_at: string;
}

export interface GuardianEventItem {
    id: string;
    source_table: string;
    source_id: string;
    event_action: string;
    severity: GuardianEventSeverity;
    reason: string;
    evidence: Record<string, unknown>;
    flagged_at: string;
}

export interface GuardianReportListResponse {
    data: GuardianReportItem[];
    meta: Record<string, unknown>;
}

export interface GuardianReportDetailResponse extends GuardianReportItem {
    events: GuardianEventItem[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

const GUARDIAN_BASE = "/api/v1/ai/guardian/reports";

/**
 * List weekly integrity reports, newest week first.
 */
export async function listGuardianReports(): Promise<GuardianReportListResponse> {
    return apiFetchBody<GuardianReportListResponse>(GUARDIAN_BASE);
}

/**
 * Fetch one weekly report with its flagged events + evidence payloads.
 */
export async function getGuardianReport(
    reportId: string,
): Promise<GuardianReportDetailResponse> {
    return apiFetchBody<GuardianReportDetailResponse>(
        `${GUARDIAN_BASE}/${reportId}`,
    );
}

/**
 * Mark one weekly report as reviewed by an operator.
 */
export async function reviewGuardianReport(
    reportId: string,
): Promise<GuardianReportItem> {
    return apiPostBody<GuardianReportItem>(
        `${GUARDIAN_BASE}/${reportId}/review`,
        {},
    );
}