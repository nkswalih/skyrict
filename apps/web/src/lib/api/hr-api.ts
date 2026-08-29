/**
 * HR API client (departments, employees, leave).
 *
 * Mirrors identity-api.ts: calls go through the same-origin /api/v1/* BFF
 * proxy, payloads are mapped from snake_case over the wire to camelCase here,
 * and every failure surfaces an `ApiError` the UI can render inline.
 */

import {
  apiFetch,
  apiList,
  apiPost,
  buildQueryString,
  type Paginated,
} from "@/lib/api/http";

export type EmployeeStatus = "active" | "on_leave" | "terminated";

export type LeaveRequestStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface Money {
  amount: string;
  currency: string;
}

export interface Employee {
  id: string;
  employeeNumber: string;
  firstName: string;
  lastName: string;
  jobTitle: string;
  hireDate: string;
  employmentStatus: EmployeeStatus;
  email: string | null;
  phone: string | null;
  userId: string | null;
  departmentId: string | null;
  terminationDate: string | null;
  activeCompensation: Money | null;
  createdAt: string;
}

/** "First Last" — the one canonical way to render an employee's name. */
export function employeeName(employee: Pick<Employee, "firstName" | "lastName">): string {
  return `${employee.firstName} ${employee.lastName}`;
}

/** Alphabetical by name — dropdown options read naturally regardless of list order. */
export function byEmployeeName(
  a: Pick<Employee, "firstName" | "lastName">,
  b: Pick<Employee, "firstName" | "lastName">,
): number {
  return employeeName(a).localeCompare(employeeName(b));
}

export interface Department {
  id: string;
  name: string;
  managerEmployeeId: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface LeaveRequest {
  id: string;
  employeeId: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  days: number;
  status: LeaveRequestStatus;
  reason: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  createdAt: string;
}

export interface LeaveBalance {
  employeeId: string;
  leaveType: string;
  balance: number;
}

export interface LeaveMovement {
  id: string;
  employeeId: string;
  leaveType: string;
  qty: number;
  refType: string;
  refId: string | null;
  reason: string | null;
  occurredAt: string | null;
}

export type AttendanceStatus = "on_time" | "late" | "absent";

export type PayImpact = "full" | "half" | "none";

export interface AttendanceRecord {
  id: string;
  employeeId: string;
  workDate: string;
  status: AttendanceStatus;
  payImpact: PayImpact;
  note: string | null;
  createdAt: string;
  /** Joined display fields — null on single-employee reads. */
  firstName: string | null;
  lastName: string | null;
  employeeNumber: string | null;
}

interface MoneyPayload {
  amount?: unknown;
  currency?: unknown;
}

interface EmployeePayload {
  id?: unknown;
  employee_number?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  job_title?: unknown;
  hire_date?: unknown;
  employment_status?: unknown;
  email?: unknown;
  phone?: unknown;
  user_id?: unknown;
  department_id?: unknown;
  termination_date?: unknown;
  active_compensation?: MoneyPayload | null;
  created_at?: unknown;
}

interface DepartmentPayload {
  id?: unknown;
  name?: unknown;
  manager_employee_id?: unknown;
  is_active?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
}

interface LeaveRequestPayload {
  id?: unknown;
  employee_id?: unknown;
  leave_type?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  days?: unknown;
  status?: unknown;
  reason?: unknown;
  approved_by?: unknown;
  approved_at?: unknown;
  created_at?: unknown;
}

interface LeaveBalancePayload {
  employee_id?: unknown;
  leave_type?: unknown;
  balance?: unknown;
}

interface LeaveMovementPayload {
  id?: unknown;
  employee_id?: unknown;
  leave_type?: unknown;
  qty?: unknown;
  ref_type?: unknown;
  ref_id?: unknown;
  reason?: unknown;
  occurred_at?: unknown;
}

interface AttendanceRecordPayload {
  id?: unknown;
  employee_id?: unknown;
  work_date?: unknown;
  status?: unknown;
  pay_impact?: unknown;
  note?: unknown;
  created_at?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  employee_number?: unknown;
}

function mapMoney(payload: MoneyPayload | null | undefined): Money | null {
  if (!payload) return null;
  return {
    amount: String(payload.amount ?? ""),
    currency: String(payload.currency ?? "USD"),
  };
}

function mapEmployee(payload: EmployeePayload): Employee {
  return {
    id: String(payload.id ?? ""),
    employeeNumber: String(payload.employee_number ?? ""),
    firstName: String(payload.first_name ?? ""),
    lastName: String(payload.last_name ?? ""),
    jobTitle: String(payload.job_title ?? ""),
    hireDate: String(payload.hire_date ?? ""),
    employmentStatus: String(payload.employment_status ?? "active") as EmployeeStatus,
    email: typeof payload.email === "string" ? payload.email : null,
    phone: typeof payload.phone === "string" ? payload.phone : null,
    userId: typeof payload.user_id === "string" ? payload.user_id : null,
    departmentId:
      typeof payload.department_id === "string" ? payload.department_id : null,
    terminationDate:
      typeof payload.termination_date === "string" ? payload.termination_date : null,
    activeCompensation: mapMoney(payload.active_compensation),
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapDepartment(payload: DepartmentPayload): Department {
  return {
    id: String(payload.id ?? ""),
    name: String(payload.name ?? ""),
    managerEmployeeId:
      typeof payload.manager_employee_id === "string"
        ? payload.manager_employee_id
        : null,
    isActive: payload.is_active !== false,
    createdAt: String(payload.created_at ?? ""),
    updatedAt: String(payload.updated_at ?? ""),
  };
}

function mapLeaveRequest(payload: LeaveRequestPayload): LeaveRequest {
  return {
    id: String(payload.id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    leaveType: String(payload.leave_type ?? ""),
    startDate: String(payload.start_date ?? ""),
    endDate: String(payload.end_date ?? ""),
    days: typeof payload.days === "number" ? payload.days : 0,
    status: String(payload.status ?? "pending") as LeaveRequestStatus,
    reason: typeof payload.reason === "string" ? payload.reason : null,
    approvedBy: typeof payload.approved_by === "string" ? payload.approved_by : null,
    approvedAt: typeof payload.approved_at === "string" ? payload.approved_at : null,
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapLeaveBalance(payload: LeaveBalancePayload): LeaveBalance {
  return {
    employeeId: String(payload.employee_id ?? ""),
    leaveType: String(payload.leave_type ?? ""),
    balance: typeof payload.balance === "number" ? payload.balance : 0,
  };
}

function mapLeaveMovement(payload: LeaveMovementPayload): LeaveMovement {
  return {
    id: String(payload.id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    leaveType: String(payload.leave_type ?? ""),
    qty: typeof payload.qty === "number" ? payload.qty : 0,
    refType: String(payload.ref_type ?? ""),
    refId: typeof payload.ref_id === "string" ? payload.ref_id : null,
    reason: typeof payload.reason === "string" ? payload.reason : null,
    occurredAt:
      typeof payload.occurred_at === "string" ? payload.occurred_at : null,
  };
}

function mapAttendanceRecord(payload: AttendanceRecordPayload): AttendanceRecord {
  return {
    id: String(payload.id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    workDate: String(payload.work_date ?? ""),
    status: String(payload.status ?? "on_time") as AttendanceStatus,
    payImpact: String(payload.pay_impact ?? "full") as PayImpact,
    note: typeof payload.note === "string" ? payload.note : null,
    createdAt: String(payload.created_at ?? ""),
    firstName: typeof payload.first_name === "string" ? payload.first_name : null,
    lastName: typeof payload.last_name === "string" ? payload.last_name : null,
    employeeNumber:
      typeof payload.employee_number === "string" ? payload.employee_number : null,
  };
}

export interface EmployeeListFilters {
  q?: string;
  /** A single status or a set (sent comma-separated, e.g. "active,on_leave"). */
  status?: EmployeeStatus | EmployeeStatus[];
  departmentId?: string;
}

export async function listEmployees(input: {
  page?: number;
  pageSize?: number;
  filters?: EmployeeListFilters;
} = {}): Promise<Paginated<Employee>> {
  const rawStatus = input.filters?.status;
  const status = Array.isArray(rawStatus)
    ? rawStatus.join(",")
    : rawStatus;
  const result = await apiList<EmployeePayload>("/api/v1/hr/employees", {
    page: input.page,
    pageSize: input.pageSize,
    query: {
      q: input.filters?.q,
      status,
      department_id: input.filters?.departmentId,
    },
  });
  return { items: result.items.map(mapEmployee), meta: result.meta };
}

export async function getEmployee(employeeId: string): Promise<Employee> {
  const raw = await apiFetch<EmployeePayload>(`/api/v1/hr/employees/${employeeId}`);
  return mapEmployee(raw ?? {});
}

export async function createEmployee(input: {
  firstName: string;
  lastName: string;
  jobTitle: string;
  hireDate: string;
  email?: string;
  phone?: string;
  departmentId?: string;
  monthlySalary?: string;
  currency?: string;
}): Promise<Employee> {
  const raw = await apiPost<EmployeePayload>("/api/v1/hr/employees", {
    first_name: input.firstName,
    last_name: input.lastName,
    job_title: input.jobTitle,
    hire_date: input.hireDate,
    email: input.email,
    phone: input.phone,
    department_id: input.departmentId,
    monthly_salary: input.monthlySalary,
    currency: input.currency,
  });
  return mapEmployee(raw ?? {});
}

export async function updateEmployee(
  employeeId: string,
  input: Partial<{
    firstName: string;
    lastName: string;
    jobTitle: string;
    hireDate: string;
    email: string;
    phone: string;
    departmentId: string;
  }>,
): Promise<Employee> {
  const raw = await apiFetch<EmployeePayload>(`/api/v1/hr/employees/${employeeId}`, {
    method: "PATCH",
    body: JSON.stringify({
      first_name: input.firstName,
      last_name: input.lastName,
      job_title: input.jobTitle,
      hire_date: input.hireDate,
      email: input.email,
      phone: input.phone,
      department_id: input.departmentId,
    }),
  });
  return mapEmployee(raw ?? {});
}

export async function changeEmployeeStatus(
  employeeId: string,
  status: "active" | "on_leave",
): Promise<Employee> {
  const raw = await apiPost<EmployeePayload>(`/api/v1/hr/employees/${employeeId}/status`, {
    employment_status: status,
  });
  return mapEmployee(raw ?? {});
}

export async function terminateEmployee(
  employeeId: string,
  input: { terminationDate?: string; reason?: string },
): Promise<Employee> {
  const raw = await apiPost<EmployeePayload>(`/api/v1/hr/employees/${employeeId}/terminate`, {
    termination_date: input.terminationDate,
    reason: input.reason,
  });
  return mapEmployee(raw ?? {});
}

export async function listDepartments(): Promise<Department[]> {
  const items = await apiFetch<DepartmentPayload[]>("/api/v1/hr/departments");
  return (items ?? []).map(mapDepartment);
}

export async function createDepartment(input: {
  name: string;
  managerEmployeeId?: string;
}): Promise<Department> {
  const raw = await apiPost<DepartmentPayload>("/api/v1/hr/departments", {
    name: input.name,
    manager_employee_id: input.managerEmployeeId,
  });
  return mapDepartment(raw ?? {});
}

export async function updateDepartment(
  departmentId: string,
  input: { name?: string; managerEmployeeId?: string; isActive?: boolean },
): Promise<Department> {
  const raw = await apiFetch<DepartmentPayload>(`/api/v1/hr/departments/${departmentId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: input.name,
      manager_employee_id: input.managerEmployeeId,
      is_active: input.isActive,
    }),
  });
  return mapDepartment(raw ?? {});
}

export interface LeaveRequestListFilters {
  status?: LeaveRequestStatus;
  employeeId?: string;
  fromDate?: string;
  toDate?: string;
}

export async function listLeaveRequests(input: {
  page?: number;
  pageSize?: number;
  filters?: LeaveRequestListFilters;
} = {}): Promise<Paginated<LeaveRequest>> {
  const result = await apiList<LeaveRequestPayload>("/api/v1/hr/leave/requests", {
    page: input.page,
    pageSize: input.pageSize,
    query: {
      status: input.filters?.status,
      employee_id: input.filters?.employeeId,
      from_date: input.filters?.fromDate,
      to_date: input.filters?.toDate,
    },
  });
  return { items: result.items.map(mapLeaveRequest), meta: result.meta };
}

export async function createLeaveRequest(input: {
  employeeId: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  reason?: string;
}): Promise<LeaveRequest> {
  const raw = await apiPost<LeaveRequestPayload>("/api/v1/hr/leave/requests", {
    employee_id: input.employeeId,
    leave_type: input.leaveType,
    start_date: input.startDate,
    end_date: input.endDate,
    reason: input.reason,
  });
  return mapLeaveRequest(raw ?? {});
}

export async function approveLeaveRequest(requestId: string): Promise<LeaveRequest> {
  const raw = await apiPost<LeaveRequestPayload>(
    `/api/v1/hr/leave/requests/${requestId}/approve`,
    {},
  );
  return mapLeaveRequest(raw ?? {});
}

export async function rejectLeaveRequest(
  requestId: string,
  reason?: string,
): Promise<LeaveRequest> {
  const raw = await apiPost<LeaveRequestPayload>(
    `/api/v1/hr/leave/requests/${requestId}/reject`,
    { reason },
  );
  return mapLeaveRequest(raw ?? {});
}

export async function cancelLeaveRequest(requestId: string): Promise<LeaveRequest> {
  const raw = await apiPost<LeaveRequestPayload>(
    `/api/v1/hr/leave/requests/${requestId}/cancel`,
    {},
  );
  return mapLeaveRequest(raw ?? {});
}

export async function getLeaveBalances(employeeId: string): Promise<LeaveBalance[]> {
  const items = await apiFetch<LeaveBalancePayload[]>(
    `/api/v1/hr/leave/balances?employee_id=${encodeURIComponent(employeeId)}`,
  );
  return (items ?? []).map(mapLeaveBalance);
}

export async function adjustLeaveBalance(input: {
  employeeId: string;
  leaveType: string;
  qty: number;
  reason: string;
}): Promise<LeaveBalance> {
  const raw = await apiPost<LeaveBalancePayload>("/api/v1/hr/leave/balances/adjust", {
    employee_id: input.employeeId,
    leave_type: input.leaveType,
    qty: input.qty,
    reason: input.reason,
  });
  return mapLeaveBalance(raw ?? {});
}

export async function accrueLeave(input: {
  employeeId: string;
  leaveType?: string;
  leaveYear?: number;
}): Promise<LeaveMovement | null> {
  const raw = await apiPost<LeaveMovementPayload | null>("/api/v1/hr/leave/accrue", {
    employee_id: input.employeeId,
    leave_type: input.leaveType,
    leave_year: input.leaveYear,
  });
  return raw ? mapLeaveMovement(raw) : null;
}

export async function listLeaveMovements(
  employeeId: string,
  leaveType?: string,
): Promise<LeaveMovement[]> {
  const items = await apiFetch<LeaveMovementPayload[]>(
    `/api/v1/hr/leave/movements${buildQueryString({
      employee_id: employeeId,
      leave_type: leaveType,
    })}`,
  );
  return (items ?? []).map(mapLeaveMovement);
}

// ---------------------------------------------------------------------------
// Leave Policy
// ---------------------------------------------------------------------------

export interface LeavePolicy {
  id: string;
  casualDaysPerYear: number;
  sickDaysPerYear: number;
  effectiveFrom: string;
  lastAccrualYear: number | null;
  createdAt: string;
  updatedAt: string;
}

interface LeavePolicyPayload {
  id?: unknown;
  casual_days_per_year?: unknown;
  sick_days_per_year?: unknown;
  effective_from?: unknown;
  last_accrual_year?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
}

function mapLeavePolicy(payload: LeavePolicyPayload): LeavePolicy {
  return {
    id: String(payload.id ?? ""),
    casualDaysPerYear: typeof payload.casual_days_per_year === "number" ? payload.casual_days_per_year : 0,
    sickDaysPerYear: typeof payload.sick_days_per_year === "number" ? payload.sick_days_per_year : 0,
    effectiveFrom: String(payload.effective_from ?? ""),
    lastAccrualYear: typeof payload.last_accrual_year === "number" ? payload.last_accrual_year : null,
    createdAt: String(payload.created_at ?? ""),
    updatedAt: String(payload.updated_at ?? ""),
  };
}

export async function getLeavePolicy(): Promise<LeavePolicy | null> {
  const raw = await apiFetch<LeavePolicyPayload | null>("/api/v1/hr/leave/policy");
  return raw ? mapLeavePolicy(raw) : null;
}

export async function updateLeavePolicy(input: {
  casualDaysPerYear: number;
  sickDaysPerYear: number;
  effectiveFrom: string;
}): Promise<LeavePolicy> {
  const raw = await apiFetch<LeavePolicyPayload>("/api/v1/hr/leave/policy", {
    method: "PUT",
    body: JSON.stringify({
      casual_days_per_year: input.casualDaysPerYear,
      sick_days_per_year: input.sickDaysPerYear,
      effective_from: input.effectiveFrom,
    }),
  });
  return mapLeavePolicy(raw ?? {});
}

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------

export interface AttendanceListFilters {
  employeeId?: string;
  status?: AttendanceStatus;
  dateFrom?: string;
  dateTo?: string;
}

export async function listAttendance(input: {
  page?: number;
  pageSize?: number;
  filters?: AttendanceListFilters;
} = {}): Promise<Paginated<AttendanceRecord>> {
  const result = await apiList<AttendanceRecordPayload>("/api/v1/hr/attendance", {
    page: input.page,
    pageSize: input.pageSize,
    query: {
      employee_id: input.filters?.employeeId,
      status: input.filters?.status,
      date_from: input.filters?.dateFrom,
      date_to: input.filters?.dateTo,
    },
  });
  return { items: result.items.map(mapAttendanceRecord), meta: result.meta };
}

export async function upsertAttendance(input: {
  employeeId: string;
  workDate: string;
  status: AttendanceStatus;
  note?: string | null;
}): Promise<AttendanceRecord> {
  const raw = await apiFetch<AttendanceRecordPayload>("/api/v1/hr/attendance", {
    method: "PUT",
    body: JSON.stringify({
      employee_id: input.employeeId,
      work_date: input.workDate,
      status: input.status,
      note: input.note ?? null,
    }),
  });
  return mapAttendanceRecord(raw ?? {});
}

// ---------------------------------------------------------------------------
// HR AI — leave suggestions (per-employee, `erp.hr.ai.individual` gate)
// ---------------------------------------------------------------------------

export interface HrLeaveSuggestion {
  suggestionId: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  days: number;
  reasons: string[];
}

interface HrSuggestionPayload {
  suggestion_id?: unknown;
  leave_type?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  days?: unknown;
  reasons?: unknown;
  status?: unknown;
}

export async function listEmployeeSuggestions(
  employeeId: string,
): Promise<HrLeaveSuggestion[]> {
  const raw = await apiFetch<HrSuggestionPayload[] | null>(
    `/api/v1/ai/hr/suggestions/${employeeId}`,
  );
  const rows = Array.isArray(raw) ? raw : [];
  return rows
    .filter((suggestion) => suggestion.status === "pending")
    .map((suggestion) => ({
      suggestionId: String(suggestion.suggestion_id ?? ""),
      leaveType: String(suggestion.leave_type ?? ""),
      startDate: String(suggestion.start_date ?? ""),
      endDate: String(suggestion.end_date ?? ""),
      days: Number(suggestion.days ?? 0),
      reasons: Array.isArray(suggestion.reasons)
        ? (suggestion.reasons as unknown[]).filter(
            (reason): reason is string => typeof reason === "string",
          )
        : [],
    }));
}

// ---------------------------------------------------------------------------
// HR AI — data quality (8.1.3): L1 org KPI + L2 per-employee drill-down
// ---------------------------------------------------------------------------

export type QualityGrade = "A" | "B" | "C" | "D" | "F";

export interface QualityIssues {
  mandatory: string[];
  contact: string[];
  document: string[];
}

export interface EmployeeQualityScore {
  id: string;
  employeeId: string;
  employeeNumber: string | null;
  name: string | null;
  departmentName: string | null;
  score: number;
  grade: QualityGrade;
  mandatoryScore: number;
  contactScore: number;
  documentScore: number;
  issues: QualityIssues;
  generatedAt: string;
}

export interface QualityOrgKpi {
  totalScored: number;
  averageScore: number;
  gradeDistribution: Record<string, number>;
  departmentAverages: {
    departmentName: string;
    averageScore: number;
    lowQualityCount: number;
    scored: number;
  }[];
  generatedAt: string;
  narrative: string;
}

interface QualityScorePayload {
  employee_id?: unknown;
  employee_number?: unknown;
  name?: unknown;
  department_name?: unknown;
  score?: unknown;
  grade?: unknown;
  mandatory_score?: unknown;
  contact_score?: unknown;
  document_score?: unknown;
  issues?: unknown;
  generated_at?: unknown;
}

function mapQualityScore(payload: QualityScorePayload): EmployeeQualityScore {
  const issues = (payload.issues ?? {}) as Record<string, unknown>;
  return {
    id: String(payload.employee_id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    employeeNumber: payload.employee_number == null ? null : String(payload.employee_number),
    name: payload.name == null ? null : String(payload.name),
    departmentName:
      payload.department_name == null ? null : String(payload.department_name),
    score: Number(payload.score ?? 0),
    grade: (String(payload.grade ?? "F") as QualityGrade),
    mandatoryScore: Number(payload.mandatory_score ?? 0),
    contactScore: Number(payload.contact_score ?? 0),
    documentScore: Number(payload.document_score ?? 0),
    issues: {
      mandatory: Array.isArray(issues.mandatory)
        ? (issues.mandatory as unknown[]).filter(
            (issue): issue is string => typeof issue === "string",
          )
        : [],
      contact: Array.isArray(issues.contact)
        ? (issues.contact as unknown[]).filter(
            (issue): issue is string => typeof issue === "string",
          )
        : [],
      document: Array.isArray(issues.document)
        ? (issues.document as unknown[]).filter(
            (issue): issue is string => typeof issue === "string",
          )
        : [],
    },
    generatedAt: String(payload.generated_at ?? ""),
  };
}

interface QualityOrgPayload {
  total_scored?: unknown;
  average_score?: unknown;
  grade_distribution?: unknown;
  department_averages?: unknown;
  generated_at?: unknown;
  narrative?: unknown;
}

/** L1 org data-quality KPI (never carries per-employee values). */
export async function getQualityOrgKpi(): Promise<QualityOrgKpi | null> {
  const raw = await apiFetch<QualityOrgPayload | null>("/api/v1/ai/hr/quality");
  if (!raw) return null;
  return {
    totalScored: Number(raw.total_scored ?? 0),
    averageScore: Number(raw.average_score ?? 0),
    gradeDistribution: Object.fromEntries(
      Object.entries((raw.grade_distribution ?? {}) as Record<string, unknown>).map(
        ([grade, count]) => [grade, Number(count ?? 0)],
      ),
    ),
    departmentAverages: Array.isArray(raw.department_averages)
      ? (raw.department_averages as Record<string, unknown>[]).map((entry) => ({
          departmentName: String(entry.department_name ?? ""),
          averageScore: Number(entry.average_score ?? 0),
          lowQualityCount: Number(entry.low_quality_count ?? 0),
          scored: Number(entry.scored ?? 0),
        }))
      : [],
    generatedAt: String(raw.generated_at ?? ""),
    narrative: String(raw.narrative ?? ""),
  };
}

/** L2 pageable per-employee quality rows, worst first. Requires `erp.hr.ai.individual`. */
export async function listQualityScores(input: {
  page?: number;
  pageSize?: number;
} = {}): Promise<Paginated<EmployeeQualityScore>> {
  const result = await apiList<QualityScorePayload>("/api/v1/ai/hr/quality/list", {
    page: input.page,
    pageSize: input.pageSize,
  });
  return { items: result.items.map(mapQualityScore), meta: result.meta };
}
