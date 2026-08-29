/**
 * Employee self-service portal API client (own leave balances & requests).
 *
 * Mirrors hr-api.ts conventions: calls go through the same-origin /api/v1/*
 * BFF proxy, payloads are mapped from snake_case to camelCase here, and every
 * failure surfaces an `ApiError`. Deliberately separate from hr-api — the
 * portal reads its own /portal/* endpoints, never HR's admin surface.
 */

import { apiFetch, apiList, apiPost, type Paginated } from "@/lib/api/http";

export type PortalLeaveRequestStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface PortalEmployee {
  id: string;
  employeeNumber: string;
  firstName: string;
  lastName: string;
  jobTitle: string;
  email: string | null;
}

export interface PortalLeaveType {
  code: string;
  name: string;
  isAccrual: boolean;
}

export interface PortalLeaveBalance {
  leaveType: string;
  balance: number;
}

export interface PortalMe {
  employee: PortalEmployee;
  leaveTypes: PortalLeaveType[];
  balances: PortalLeaveBalance[];
}

export interface PortalLeaveRequest {
  id: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  days: number;
  status: PortalLeaveRequestStatus;
  reason: string | null;
  approvedAt: string | null;
  createdAt: string;
}

export interface PortalLeaveSuggestion {
  suggestionId: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  days: number;
  reasons: string[];
  status: string;
}

interface PortalEmployeePayload {
  id?: unknown;
  employee_number?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  job_title?: unknown;
  email?: unknown;
}

interface PortalLeaveTypePayload {
  code?: unknown;
  name?: unknown;
  is_accrual?: unknown;
}

interface PortalBalancePayload {
  leave_type?: unknown;
  balance?: unknown;
}

interface PortalMePayload {
  employee?: unknown;
  leave_types?: unknown;
  balances?: unknown;
}

interface PortalLeaveRequestPayload {
  id?: unknown;
  leave_type?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  days?: unknown;
  status?: unknown;
  reason?: unknown;
  approved_at?: unknown;
  created_at?: unknown;
}

interface PortalSuggestionPayload {
  suggestion_id?: unknown;
  employee_id?: unknown;
  employee_number?: unknown;
  name?: unknown;
  department_name?: unknown;
  leave_type?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  days?: unknown;
  reasons?: unknown;
  status?: unknown;
  used_at?: unknown;
  created_at?: unknown;
}

function mapPortalEmployee(payload: PortalEmployeePayload): PortalEmployee {
  return {
    id: String(payload.id ?? ""),
    employeeNumber: String(payload.employee_number ?? ""),
    firstName: String(payload.first_name ?? ""),
    lastName: String(payload.last_name ?? ""),
    jobTitle: String(payload.job_title ?? ""),
    email: payload.email == null ? null : String(payload.email),
  };
}

function mapLeaveRequest(payload: PortalLeaveRequestPayload): PortalLeaveRequest {
  return {
    id: String(payload.id ?? ""),
    leaveType: String(payload.leave_type ?? ""),
    startDate: String(payload.start_date ?? ""),
    endDate: String(payload.end_date ?? ""),
    days: Number(payload.days ?? 0),
    status: (String(payload.status ?? "pending") as PortalLeaveRequestStatus),
    reason: payload.reason == null ? null : String(payload.reason),
    approvedAt: payload.approved_at == null ? null : String(payload.approved_at),
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapSuggestion(payload: PortalSuggestionPayload): PortalLeaveSuggestion {
  return {
    suggestionId: String(payload.suggestion_id ?? ""),
    leaveType: String(payload.leave_type ?? ""),
    startDate: String(payload.start_date ?? ""),
    endDate: String(payload.end_date ?? ""),
    days: Number(payload.days ?? 0),
    reasons: Array.isArray(payload.reasons)
      ? (payload.reasons as unknown[]).filter(
          (reason): reason is string => typeof reason === "string",
        )
      : [],
    status: String(payload.status ?? "pending"),
  };
}

/** Who am I + my tenant's leave-type catalogue + my materialized balances. */
export async function getPortalMe(): Promise<PortalMe> {
  const raw = await apiFetch<PortalMePayload | null>("/api/v1/portal/me");
  const employeeRaw = (raw?.employee ?? {}) as PortalEmployeePayload;
  const typesRaw = Array.isArray(raw?.leave_types)
    ? (raw.leave_types as PortalLeaveTypePayload[])
    : [];
  const balancesRaw = Array.isArray(raw?.balances)
    ? (raw.balances as PortalBalancePayload[])
    : [];
  return {
    employee: mapPortalEmployee(employeeRaw),
    leaveTypes: typesRaw.map((type) => ({
      code: String(type.code ?? ""),
      name: String(type.name ?? type.code ?? ""),
      isAccrual: Boolean(type.is_accrual),
    })),
    balances: balancesRaw.map((balance) => ({
      leaveType: String(balance.leave_type ?? ""),
      balance: Number(balance.balance ?? 0),
    })),
  };
}

/** Own leave-request history, newest first, self-scoped server-side. */
export function listMyLeaveRequests(
  input: { page?: number; pageSize?: number; status?: string } = {},
): Promise<Paginated<PortalLeaveRequest>> {
  return apiList<PortalLeaveRequest>("/api/v1/portal/leave/requests", {
    page: input.page,
    pageSize: input.pageSize,
    query: { status: input.status },
  });
}

export interface SubmitLeaveInput {
  leaveType: string;
  startDate: string;
  endDate: string;
  reason?: string;
}

/** Submit an own leave request — employee_id is forced server-side. */
export async function submitLeaveRequest(input: SubmitLeaveInput): Promise<PortalLeaveRequest> {
  const raw = await apiPost<PortalLeaveRequestPayload | null>(
    "/api/v1/portal/leave/requests",
    {
      leave_type: input.leaveType,
      start_date: input.startDate,
      end_date: input.endDate,
      reason: input.reason || null,
    },
  );
  return mapLeaveRequest(raw ?? {});
}

/** Own calendar-aware leave suggestions (prefill chips), self-scoped. */
export async function getLeaveSuggestions(): Promise<PortalLeaveSuggestion[]> {
  const raw = await apiFetch<PortalSuggestionPayload[] | null>(
    "/api/v1/portal/leave/suggestions",
  );
  return Array.isArray(raw) ? raw.map(mapSuggestion) : [];
}

/**
 * Mark one suggestion as used — records the prefill so the chip stops being
 * suggested. Never submits a leave request by itself.
 */
export async function markSuggestionUsed(
  suggestionId: string,
): Promise<PortalLeaveSuggestion> {
  const raw = await apiPost<PortalSuggestionPayload | null>(
    `/api/v1/portal/leave/suggestions/${suggestionId}/use`,
    {},
  );
  return mapSuggestion(raw ?? {});
}

/** Opt out of one suggestion (status `dismissed`). */
export async function dismissLeaveSuggestion(
  suggestionId: string,
): Promise<PortalLeaveSuggestion> {
  const raw = await apiPost<PortalSuggestionPayload | null>(
    `/api/v1/portal/leave/suggestions/${suggestionId}/dismiss`,
    {},
  );
  return mapSuggestion(raw ?? {});
}
