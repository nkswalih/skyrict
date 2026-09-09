/**
 * HR API client (departments, employees, leave).
 *
 * Mirrors identity-api.ts: calls go through the same-origin /api/v1/* BFF
 * proxy, payloads are mapped from snake_case over the wire to camelCase here,
 * and every failure surfaces an `ApiError` the UI can render inline.
 */

import {
    ApiError,
    apiFetch,
    apiList,
    apiPost,
    buildQueryString,
    fetchWithSession,
    type Paginated,
} from "@/lib/api/http";

export type EmployeeStatus = "active" | "on_leave" | "terminated";

export type LeaveRequestStatus =
    "pending" | "approved" | "rejected" | "cancelled";

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

/** "First Last" - the one canonical way to render an employee's name. */
export function employeeName(
    employee: Pick<Employee, "firstName" | "lastName">,
): string {
    return `${employee.firstName} ${employee.lastName}`;
}

/** Alphabetical by name - dropdown options read naturally regardless of list order. */
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
    /** Joined display fields - null on single-employee reads. */
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
        employmentStatus: String(
            payload.employment_status ?? "active",
        ) as EmployeeStatus,
        email: typeof payload.email === "string" ? payload.email : null,
        phone: typeof payload.phone === "string" ? payload.phone : null,
        userId: typeof payload.user_id === "string" ? payload.user_id : null,
        departmentId:
            typeof payload.department_id === "string"
                ? payload.department_id
                : null,
        terminationDate:
            typeof payload.termination_date === "string"
                ? payload.termination_date
                : null,
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
        approvedBy:
            typeof payload.approved_by === "string"
                ? payload.approved_by
                : null,
        approvedAt:
            typeof payload.approved_at === "string"
                ? payload.approved_at
                : null,
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
            typeof payload.occurred_at === "string"
                ? payload.occurred_at
                : null,
    };
}

function mapAttendanceRecord(
    payload: AttendanceRecordPayload,
): AttendanceRecord {
    return {
        id: String(payload.id ?? ""),
        employeeId: String(payload.employee_id ?? ""),
        workDate: String(payload.work_date ?? ""),
        status: String(payload.status ?? "on_time") as AttendanceStatus,
        payImpact: String(payload.pay_impact ?? "full") as PayImpact,
        note: typeof payload.note === "string" ? payload.note : null,
        createdAt: String(payload.created_at ?? ""),
        firstName:
            typeof payload.first_name === "string" ? payload.first_name : null,
        lastName:
            typeof payload.last_name === "string" ? payload.last_name : null,
        employeeNumber:
            typeof payload.employee_number === "string"
                ? payload.employee_number
                : null,
    };
}

export interface EmployeeListFilters {
    q?: string;
    /** A single status or a set (sent comma-separated, e.g. "active,on_leave"). */
    status?: EmployeeStatus | EmployeeStatus[];
    departmentId?: string;
}

export async function listEmployees(
    input: {
        page?: number;
        pageSize?: number;
        filters?: EmployeeListFilters;
    } = {},
): Promise<Paginated<Employee>> {
    const rawStatus = input.filters?.status;
    const status = Array.isArray(rawStatus) ? rawStatus.join(",") : rawStatus;
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
    const raw = await apiFetch<EmployeePayload>(
        `/api/v1/hr/employees/${employeeId}`,
    );
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
    const raw = await apiFetch<EmployeePayload>(
        `/api/v1/hr/employees/${employeeId}`,
        {
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
        },
    );
    return mapEmployee(raw ?? {});
}

export async function changeEmployeeStatus(
    employeeId: string,
    status: "active" | "on_leave",
): Promise<Employee> {
    const raw = await apiPost<EmployeePayload>(
        `/api/v1/hr/employees/${employeeId}/status`,
        {
            employment_status: status,
        },
    );
    return mapEmployee(raw ?? {});
}

export async function terminateEmployee(
    employeeId: string,
    input: { terminationDate?: string; reason?: string },
): Promise<Employee> {
    const raw = await apiPost<EmployeePayload>(
        `/api/v1/hr/employees/${employeeId}/terminate`,
        {
            termination_date: input.terminationDate,
            reason: input.reason,
        },
    );
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
    const raw = await apiFetch<DepartmentPayload>(
        `/api/v1/hr/departments/${departmentId}`,
        {
            method: "PATCH",
            body: JSON.stringify({
                name: input.name,
                manager_employee_id: input.managerEmployeeId,
                is_active: input.isActive,
            }),
        },
    );
    return mapDepartment(raw ?? {});
}

export interface LeaveRequestListFilters {
    status?: LeaveRequestStatus;
    employeeId?: string;
    fromDate?: string;
    toDate?: string;
}

export async function listLeaveRequests(
    input: {
        page?: number;
        pageSize?: number;
        filters?: LeaveRequestListFilters;
    } = {},
): Promise<Paginated<LeaveRequest>> {
    const result = await apiList<LeaveRequestPayload>(
        "/api/v1/hr/leave/requests",
        {
            page: input.page,
            pageSize: input.pageSize,
            query: {
                status: input.filters?.status,
                employee_id: input.filters?.employeeId,
                from_date: input.filters?.fromDate,
                to_date: input.filters?.toDate,
            },
        },
    );
    return { items: result.items.map(mapLeaveRequest), meta: result.meta };
}

export async function createLeaveRequest(input: {
    employeeId: string;
    leaveType: string;
    startDate: string;
    endDate: string;
    reason?: string;
}): Promise<LeaveRequest> {
    const raw = await apiPost<LeaveRequestPayload>(
        "/api/v1/hr/leave/requests",
        {
            employee_id: input.employeeId,
            leave_type: input.leaveType,
            start_date: input.startDate,
            end_date: input.endDate,
            reason: input.reason,
        },
    );
    return mapLeaveRequest(raw ?? {});
}

export async function approveLeaveRequest(
    requestId: string,
): Promise<LeaveRequest> {
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

export async function cancelLeaveRequest(
    requestId: string,
): Promise<LeaveRequest> {
    const raw = await apiPost<LeaveRequestPayload>(
        `/api/v1/hr/leave/requests/${requestId}/cancel`,
        {},
    );
    return mapLeaveRequest(raw ?? {});
}

export async function getLeaveBalances(
    employeeId: string,
): Promise<LeaveBalance[]> {
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
    const raw = await apiPost<LeaveBalancePayload>(
        "/api/v1/hr/leave/balances/adjust",
        {
            employee_id: input.employeeId,
            leave_type: input.leaveType,
            qty: input.qty,
            reason: input.reason,
        },
    );
    return mapLeaveBalance(raw ?? {});
}

export async function accrueLeave(input: {
    employeeId: string;
    leaveType?: string;
    leaveYear?: number;
}): Promise<LeaveMovement | null> {
    const raw = await apiPost<LeaveMovementPayload | null>(
        "/api/v1/hr/leave/accrue",
        {
            employee_id: input.employeeId,
            leave_type: input.leaveType,
            leave_year: input.leaveYear,
        },
    );
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
        casualDaysPerYear:
            typeof payload.casual_days_per_year === "number"
                ? payload.casual_days_per_year
                : 0,
        sickDaysPerYear:
            typeof payload.sick_days_per_year === "number"
                ? payload.sick_days_per_year
                : 0,
        effectiveFrom: String(payload.effective_from ?? ""),
        lastAccrualYear:
            typeof payload.last_accrual_year === "number"
                ? payload.last_accrual_year
                : null,
        createdAt: String(payload.created_at ?? ""),
        updatedAt: String(payload.updated_at ?? ""),
    };
}

export async function getLeavePolicy(): Promise<LeavePolicy | null> {
    const raw = await apiFetch<LeavePolicyPayload | null>(
        "/api/v1/hr/leave/policy",
    );
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

export async function listAttendance(
    input: {
        page?: number;
        pageSize?: number;
        filters?: AttendanceListFilters;
    } = {},
): Promise<Paginated<AttendanceRecord>> {
    const result = await apiList<AttendanceRecordPayload>(
        "/api/v1/hr/attendance",
        {
            page: input.page,
            pageSize: input.pageSize,
            query: {
                employee_id: input.filters?.employeeId,
                status: input.filters?.status,
                date_from: input.filters?.dateFrom,
                date_to: input.filters?.dateTo,
            },
        },
    );
    return { items: result.items.map(mapAttendanceRecord), meta: result.meta };
}

export async function upsertAttendance(input: {
    employeeId: string;
    workDate: string;
    status: AttendanceStatus;
    note?: string | null;
}): Promise<AttendanceRecord> {
    const raw = await apiFetch<AttendanceRecordPayload>(
        "/api/v1/hr/attendance",
        {
            method: "PUT",
            body: JSON.stringify({
                employee_id: input.employeeId,
                work_date: input.workDate,
                status: input.status,
                note: input.note ?? null,
            }),
        },
    );
    return mapAttendanceRecord(raw ?? {});
}

// ---------------------------------------------------------------------------
// HR AI - leave suggestions (per-employee, `erp.hr.ai.individual` gate)
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
// HR AI — utilization alerts (8.1.4) + leave-pattern anomalies (8.2.1)
// ---------------------------------------------------------------------------

export interface HrUtilizationOrg {
    totalAlerts: number;
    byType: Record<string, number>;
    bySeverity: Record<string, number>;
    generatedAt: string;
    narrative: string;
}

export interface HrUtilizationAlert {
    employeeId: string;
    employeeNumber: string | null;
    name: string | null;
    departmentName: string | null;
    alertType: string;
    severity: string;
    balanceDays: number;
    projectedForfeitureDays: number | null;
    daysRemainingInYear: number | null;
    leaveType: string | null;
    status: string | null;
    evidence: Record<string, unknown>;
    createdAt: string;
}

interface HrUtilizationOrgPayload {
    total_alerts?: unknown;
    by_type?: unknown;
    by_severity?: unknown;
    generated_at?: unknown;
    narrative?: unknown;
}

interface HrUtilizationAlertPayload {
    employee_id?: unknown;
    employee_number?: unknown;
    name?: unknown;
    department_name?: unknown;
    alert_type?: unknown;
    severity?: unknown;
    balance_days?: unknown;
    projected_forfeiture_days?: unknown;
    days_remaining_in_year?: unknown;
    leave_type?: unknown;
    status?: unknown;
    evidence?: unknown;
    created_at?: unknown;
}

function mapUtilizationAlert(
    payload: HrUtilizationAlertPayload,
): HrUtilizationAlert {
    return {
        employeeId: String(payload.employee_id ?? ""),
        employeeNumber:
            payload.employee_number != null
                ? String(payload.employee_number)
                : null,
        name: payload.name != null ? String(payload.name) : null,
        departmentName:
            payload.department_name != null
                ? String(payload.department_name)
                : null,
        alertType: String(payload.alert_type ?? ""),
        severity: String(payload.severity ?? ""),
        balanceDays: Number(payload.balance_days ?? 0),
        projectedForfeitureDays:
            payload.projected_forfeiture_days != null
                ? Number(payload.projected_forfeiture_days)
                : null,
        daysRemainingInYear:
            payload.days_remaining_in_year != null
                ? Number(payload.days_remaining_in_year)
                : null,
        leaveType:
            payload.leave_type != null ? String(payload.leave_type) : null,
        status: payload.status != null ? String(payload.status) : null,
        evidence:
            payload.evidence != null && typeof payload.evidence === "object"
                ? (payload.evidence as Record<string, unknown>)
                : {},
        createdAt: String(payload.created_at ?? ""),
    };
}

/** L1 usage-balance alert aggregate (never carries per-person values). */
export async function getUtilizationSummary(): Promise<HrUtilizationOrg | null> {
    const raw = await apiFetch<HrUtilizationOrgPayload | null>(
        "/api/v1/ai/hr/alerts/utilization",
    );
    if (!raw) return null;
    return {
        totalAlerts: Number(raw.total_alerts ?? 0),
        byType: Object.fromEntries(
            Object.entries((raw.by_type ?? {}) as Record<string, unknown>).map(
                ([key, value]) => [key, Number(value ?? 0)],
            ),
        ),
        bySeverity: Object.fromEntries(
            Object.entries(
                (raw.by_severity ?? {}) as Record<string, unknown>,
            ).map(([key, value]) => [key, Number(value ?? 0)]),
        ),
        generatedAt: String(raw.generated_at ?? ""),
        narrative: String(raw.narrative ?? ""),
    };
}

/** L2 per-employee utilization alerts. Requires `erp.hr.ai.individual`. */
export async function getEmployeeUtilization(
    employeeId: string,
): Promise<HrUtilizationAlert[]> {
    const raw = await apiFetch<HrUtilizationAlertPayload[] | null>(
        `/api/v1/ai/hr/alerts/utilization/${employeeId}`,
    );
    return Array.isArray(raw) ? raw.map(mapUtilizationAlert) : [];
}

export interface HrAnomalyOrg {
    totalAnomalies: number;
    byType: Record<string, number>;
    bySeverity: Record<string, number>;
    generatedAt: string;
    narrative: string;
}

export interface HrLeaveAnomaly {
    employeeId: string;
    employeeNumber: string | null;
    name: string | null;
    departmentName: string | null;
    anomalyType: string;
    severity: string;
    title: string;
    description: string;
    teamSize: number;
    evidence: Record<string, unknown>;
    status: string | null;
    createdAt: string;
}

interface HrAnomalyOrgPayload {
    total_anomalies?: unknown;
    by_type?: unknown;
    by_severity?: unknown;
    generated_at?: unknown;
    narrative?: unknown;
}

interface HrLeaveAnomalyPayload {
    employee_id?: unknown;
    employee_number?: unknown;
    name?: unknown;
    department_name?: unknown;
    anomaly_type?: unknown;
    severity?: unknown;
    title?: unknown;
    description?: unknown;
    team_size?: unknown;
    evidence?: unknown;
    status?: unknown;
    created_at?: unknown;
}

function mapLeaveAnomaly(payload: HrLeaveAnomalyPayload): HrLeaveAnomaly {
    return {
        employeeId: String(payload.employee_id ?? ""),
        employeeNumber:
            payload.employee_number != null
                ? String(payload.employee_number)
                : null,
        name: payload.name != null ? String(payload.name) : null,
        departmentName:
            payload.department_name != null
                ? String(payload.department_name)
                : null,
        anomalyType: String(payload.anomaly_type ?? ""),
        severity: String(payload.severity ?? ""),
        title: String(payload.title ?? ""),
        description: String(payload.description ?? ""),
        teamSize: Number(payload.team_size ?? 0),
        evidence:
            payload.evidence != null && typeof payload.evidence === "object"
                ? (payload.evidence as Record<string, unknown>)
                : {},
        status: payload.status != null ? String(payload.status) : null,
        createdAt: String(payload.created_at ?? ""),
    };
}

/** L1 leave-pattern anomaly aggregate (never carries per-person values). */
export async function getAnomalySummary(): Promise<HrAnomalyOrg | null> {
    const raw = await apiFetch<HrAnomalyOrgPayload | null>(
        "/api/v1/ai/hr/alerts/anomalies",
    );
    if (!raw) return null;
    return {
        totalAnomalies: Number(raw.total_anomalies ?? 0),
        byType: Object.fromEntries(
            Object.entries((raw.by_type ?? {}) as Record<string, unknown>).map(
                ([key, value]) => [key, Number(value ?? 0)],
            ),
        ),
        bySeverity: Object.fromEntries(
            Object.entries(
                (raw.by_severity ?? {}) as Record<string, unknown>,
            ).map(([key, value]) => [key, Number(value ?? 0)]),
        ),
        generatedAt: String(raw.generated_at ?? ""),
        narrative: String(raw.narrative ?? ""),
    };
}

/** L2 per-employee leave-pattern anomalies. Requires `erp.hr.ai.individual`. */
export async function getEmployeeAnomalies(
    employeeId: string,
): Promise<HrLeaveAnomaly[]> {
    const raw = await apiFetch<HrLeaveAnomalyPayload[] | null>(
        `/api/v1/ai/hr/alerts/anomalies/${employeeId}`,
    );
    return Array.isArray(raw) ? raw.map(mapLeaveAnomaly) : [];
}

// ---------------------------------------------------------------------------
// HR AI — data quality (8.1.3): L1 org KPI + L2 per-employee drill-down
// HR AI - data quality (8.1.3): L1 org KPI + L2 per-employee drill-down
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
        employeeNumber:
            payload.employee_number == null
                ? null
                : String(payload.employee_number),
        name: payload.name == null ? null : String(payload.name),
        departmentName:
            payload.department_name == null
                ? null
                : String(payload.department_name),
        score: Number(payload.score ?? 0),
        grade: String(payload.grade ?? "F") as QualityGrade,
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
    const raw = await apiFetch<QualityOrgPayload | null>(
        "/api/v1/ai/hr/quality",
    );
    if (!raw) return null;
    return {
        totalScored: Number(raw.total_scored ?? 0),
        averageScore: Number(raw.average_score ?? 0),
        gradeDistribution: Object.fromEntries(
            Object.entries(
                (raw.grade_distribution ?? {}) as Record<string, unknown>,
            ).map(([grade, count]) => [grade, Number(count ?? 0)]),
        ),
        departmentAverages: Array.isArray(raw.department_averages)
            ? (raw.department_averages as Record<string, unknown>[]).map(
                  (entry) => ({
                      departmentName: String(entry.department_name ?? ""),
                      averageScore: Number(entry.average_score ?? 0),
                      lowQualityCount: Number(entry.low_quality_count ?? 0),
                      scored: Number(entry.scored ?? 0),
                  }),
              )
            : [],
        generatedAt: String(raw.generated_at ?? ""),
        narrative: String(raw.narrative ?? ""),
    };
}

/** L2 pageable per-employee quality rows, worst first. Requires `erp.hr.ai.individual`. */
export async function listQualityScores(
    input: {
        page?: number;
        pageSize?: number;
    } = {},
): Promise<Paginated<EmployeeQualityScore>> {
    const result = await apiList<QualityScorePayload>(
        "/api/v1/ai/hr/quality/list",
        {
            page: input.page,
            pageSize: input.pageSize,
        },
    );
    return { items: result.items.map(mapQualityScore), meta: result.meta };
}

// ---------------------------------------------------------------------------
// HR AI — attrition risk (8.1.x): L1 aggregates / L2 per-employee slices
// ---------------------------------------------------------------------------

export interface HrDepartmentRisk {
    departmentName: string;
    highRiskCount: number;
    totalScores: number;
    averageRisk: number;
}

export interface HrAttritionSummary {
    generatedAt: string;
    modelVersion: string;
    highRiskCount: number;
    mediumRiskCount: number;
    lowRiskCount: number;
    topRiskDepartments: HrDepartmentRisk[];
    narrative: string;
}

export interface HrAttritionFactor {
    feature: string;
    contribution: number;
    direction: string;
}

export interface HrEmployeeRisk {
    employeeId: string;
    employeeNumber: string | null;
    name: string | null;
    departmentName: string | null;
    riskBand: "high" | "medium" | "low";
    score: number;
    confidence: number;
    factors: HrAttritionFactor[];
    acknowledged: boolean;
    acknowledgedAt: string | null;
}

/** The `/attrition` endpoint varies on the caller's `erp.hr.ai.individual`. */
export type HrAttritionView =
    | { mode: "summary"; summary: HrAttritionSummary }
    | {
          mode: "detail";
          modelVersion: string;
          generatedAt: string;
          employees: HrEmployeeRisk[];
      };

interface HrDepartmentRiskPayload {
    department_name?: unknown;
    high_risk_count?: unknown;
    total_scores?: unknown;
    average_risk?: unknown;
}

interface HrAttritionSummaryPayload {
    generated_at?: unknown;
    model_version?: unknown;
    high_risk_count?: unknown;
    medium_risk_count?: unknown;
    low_risk_count?: unknown;
    top_risk_departments?: unknown;
    narrative?: unknown;
}

interface HrAttritionFactorPayload {
    feature?: unknown;
    contribution?: unknown;
    direction?: unknown;
}

interface HrEmployeeRiskPayload {
    employee_id?: unknown;
    employee_number?: unknown;
    name?: unknown;
    department_name?: unknown;
    risk_band?: unknown;
    score?: unknown;
    confidence?: unknown;
    factors?: unknown;
    acknowledged?: unknown;
    acknowledged_at?: unknown;
}

interface HrAttritionDetailPayload {
    generated_at?: unknown;
    model_version?: unknown;
    employees?: unknown;
}

function mapDepartmentRisk(payload: HrDepartmentRiskPayload): HrDepartmentRisk {
    return {
        departmentName: String(payload.department_name ?? ""),
        highRiskCount: Number(payload.high_risk_count ?? 0),
        totalScores: Number(payload.total_scores ?? 0),
        averageRisk: Number(payload.average_risk ?? 0),
    };
}

function mapAttritionSummary(
    payload: HrAttritionSummaryPayload,
): HrAttritionSummary {
    return {
        generatedAt: String(payload.generated_at ?? ""),
        modelVersion: String(payload.model_version ?? ""),
        highRiskCount: Number(payload.high_risk_count ?? 0),
        mediumRiskCount: Number(payload.medium_risk_count ?? 0),
        lowRiskCount: Number(payload.low_risk_count ?? 0),
        topRiskDepartments: Array.isArray(payload.top_risk_departments)
            ? (payload.top_risk_departments as HrDepartmentRiskPayload[]).map(
                  mapDepartmentRisk,
              )
            : [],
        narrative: String(payload.narrative ?? ""),
    };
}

function mapEmployeeRisk(payload: HrEmployeeRiskPayload): HrEmployeeRisk {
    const band = String(payload.risk_band ?? "low");
    return {
        employeeId: String(payload.employee_id ?? ""),
        employeeNumber:
            payload.employee_number != null
                ? String(payload.employee_number)
                : null,
        name: payload.name != null ? String(payload.name) : null,
        departmentName:
            payload.department_name != null
                ? String(payload.department_name)
                : null,
        riskBand: band === "high" || band === "medium" ? band : "low",
        score: Number(payload.score ?? 0),
        confidence: Number(payload.confidence ?? 0),
        factors: Array.isArray(payload.factors)
            ? (payload.factors as HrAttritionFactorPayload[]).map((factor) => ({
                  feature: String(factor.feature ?? ""),
                  contribution: Number(factor.contribution ?? 0),
                  direction: String(factor.direction ?? ""),
              }))
            : [],
        acknowledged: Boolean(payload.acknowledged ?? false),
        acknowledgedAt:
            payload.acknowledged_at != null
                ? String(payload.acknowledged_at)
                : null,
    };
}

/**
 * Attrition risk: L2 per-employee detail for `erp.hr.ai.individual` holders,
 * otherwise the backend answers 403 with the L1 aggregates in the body — which
 * is a usable summary, not a lock. This client keeps both modes so the page can
 * render the aggregate always and the drill-down only when permitted.
 */
export async function getAttrition(): Promise<HrAttritionView> {
    const response = await fetchWithSession("/api/v1/ai/hr/attrition", {});
    const payload = (await response.json().catch(() => ({}))) as {
        data?: HrAttritionDetailPayload | HrAttritionSummaryPayload | null;
    };
    const data = payload.data;
    if (data && typeof data === "object") {
        if (
            "employees" in data &&
            Array.isArray((data as HrAttritionDetailPayload).employees)
        ) {
            const detail = data as HrAttritionDetailPayload;
            return {
                mode: "detail",
                modelVersion: String(detail.model_version ?? ""),
                generatedAt: String(detail.generated_at ?? ""),
                employees: Array.isArray(detail.employees)
                    ? (detail.employees as HrEmployeeRiskPayload[]).map(
                          mapEmployeeRisk,
                      )
                    : [],
            };
        }
        if ("high_risk_count" in data) {
            return {
                mode: "summary",
                summary: mapAttritionSummary(data as HrAttritionSummaryPayload),
            };
        }
    }
    throw new ApiError(
        response.status,
        response.status === 403
            ? "erp.hr.ai.individual required for the individual view."
            : "Attrition risk could not be loaded.",
    );
}

/** Record a manager's acknowledgement of one employee's attrition risk. */
export async function acknowledgeAttrition(employeeId: string): Promise<void> {
    await apiPost<void>(
        `/api/v1/ai/hr/attrition/${employeeId}/acknowledge`,
        {},
    );
}

// ---------------------------------------------------------------------------
// HR AI — payroll anomalies (HR-AI-001, Unit B): L1 feed / L2 drill-down /
// dispositions
// ---------------------------------------------------------------------------

export type HrPayrollAnomalyType =
    "net_pay_delta" | "duplicate_account" | "ghost_employee";

export interface HrPayrollAnomaly {
    anomalyId: string;
    runId: string;
    runCode: string | null;
    periodStart: string | null;
    periodEnd: string | null;
    employeeId: string | null;
    employeeNumber: string | null;
    name: string | null;
    departmentName: string | null;
    anomalyType: HrPayrollAnomalyType;
    severity: "low" | "medium" | "high" | "critical";
    title: string;
    description: string;
    evidence: Record<string, unknown>;
    status: "open" | "acknowledged" | "dismissed" | "resolved";
    acknowledgedAt: string | null;
    createdAt: string;
}

export interface HrPayrollAnomalySummary {
    totalAnomalies: number;
    openAnomalies: number;
    byType: Record<string, number>;
    bySeverity: Record<string, number>;
    generatedAt: string;
    narrative: string;
}

interface HrPayrollAnomalyPayload {
    anomaly_id?: unknown;
    run_id?: unknown;
    run_code?: unknown;
    period_start?: unknown;
    period_end?: unknown;
    employee_id?: unknown;
    employee_number?: unknown;
    name?: unknown;
    department_name?: unknown;
    anomaly_type?: unknown;
    severity?: unknown;
    title?: unknown;
    description?: unknown;
    evidence?: unknown;
    status?: unknown;
    acknowledged_at?: unknown;
    created_at?: unknown;
}

interface HrPayrollAnomalySummaryPayload {
    total_anomalies?: unknown;
    open_anomalies?: unknown;
    by_type?: unknown;
    by_severity?: unknown;
    generated_at?: unknown;
    narrative?: unknown;
}

function mapPayrollAnomaly(payload: HrPayrollAnomalyPayload): HrPayrollAnomaly {
    const type = String(
        payload.anomaly_type ?? "net_pay_delta",
    ) as HrPayrollAnomalyType;
    const status = String(
        payload.status ?? "open",
    ) as HrPayrollAnomaly["status"];
    return {
        anomalyId: String(payload.anomaly_id ?? ""),
        runId: String(payload.run_id ?? ""),
        runCode: payload.run_code != null ? String(payload.run_code) : null,
        periodStart:
            payload.period_start != null ? String(payload.period_start) : null,
        periodEnd:
            payload.period_end != null ? String(payload.period_end) : null,
        employeeId:
            payload.employee_id != null ? String(payload.employee_id) : null,
        employeeNumber:
            payload.employee_number != null
                ? String(payload.employee_number)
                : null,
        name: payload.name != null ? String(payload.name) : null,
        departmentName:
            payload.department_name != null
                ? String(payload.department_name)
                : null,
        anomalyType: type,
        severity: String(
            payload.severity ?? "medium",
        ) as HrPayrollAnomaly["severity"],
        title: String(payload.title ?? "Payroll anomaly"),
        description: String(payload.description ?? ""),
        evidence:
            payload.evidence != null && typeof payload.evidence === "object"
                ? (payload.evidence as Record<string, unknown>)
                : {},
        status,
        acknowledgedAt:
            payload.acknowledged_at != null
                ? String(payload.acknowledged_at)
                : null,
        createdAt: String(payload.created_at ?? ""),
    };
}

function mapPayrollAnomalySummary(
    payload: HrPayrollAnomalySummaryPayload,
): HrPayrollAnomalySummary {
    return {
        totalAnomalies: Number(payload.total_anomalies ?? 0),
        openAnomalies: Number(payload.open_anomalies ?? 0),
        byType:
            payload.by_type != null && typeof payload.by_type === "object"
                ? (payload.by_type as Record<string, number>)
                : {},
        bySeverity:
            payload.by_severity != null &&
            typeof payload.by_severity === "object"
                ? (payload.by_severity as Record<string, number>)
                : {},
        generatedAt: String(payload.generated_at ?? ""),
        narrative: String(payload.narrative ?? ""),
    };
}

/** L1 payroll-anomaly feed — aggregate counts only, never per-person data. */
export async function getPayrollAnomalySummary(): Promise<HrPayrollAnomalySummary> {
    const response = await fetchWithSession("/api/v1/ai/hr/alerts/payroll", {});
    if (!response.ok) {
        throw new ApiError(
            response.status,
            "Payroll anomaly feed could not be loaded.",
        );
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: HrPayrollAnomalySummaryPayload | null;
    };
    if (payload.data && typeof payload.data === "object") {
        return mapPayrollAnomalySummary(
            payload.data as HrPayrollAnomalySummaryPayload,
        );
    }
    throw new ApiError(
        response.status,
        "Payroll anomaly feed could not be loaded.",
    );
}

/** L2 per-employee payroll findings (needs `erp.hr.ai.individual`). */
export async function getEmployeePayrollAnomalies(
    employeeId: string,
): Promise<HrPayrollAnomaly[]> {
    const response = await fetchWithSession(
        `/api/v1/ai/hr/alerts/payroll/${employeeId}`,
        {},
    );
    if (!response.ok) {
        throw new ApiError(
            response.status,
            response.status === 403
                ? "erp.hr.ai.individual required for the individual view."
                : "Payroll anomalies could not be loaded.",
        );
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: HrPayrollAnomalyPayload[] | null;
    };
    return Array.isArray(payload.data)
        ? (payload.data as HrPayrollAnomalyPayload[]).map(mapPayrollAnomaly)
        : [];
}

/** Move one finding along `acknowledged | dismissed | resolved` (audited). */
export async function disposePayrollAnomaly(
    anomalyId: string,
    status: "acknowledged" | "dismissed" | "resolved",
): Promise<HrPayrollAnomaly> {
    const response = await apiPost<HrPayrollAnomalyPayload>(
        `/api/v1/ai/hr/alerts/payroll/${anomalyId}/disposition`,
        { status },
    );
    return mapPayrollAnomaly(response);
}

// ---------------------------------------------------------------------------
// HR AI — compliance engine v1 (HR-AI-001, Unit C): L1 feed / L2 drill-down /
// status updates
// ---------------------------------------------------------------------------

export type HrComplianceCheckType =
    "document_expiry" | "training_overdue" | "contract_missing_field";

export interface HrComplianceFinding {
    checkId: string;
    employeeId: string | null;
    employeeNumber: string | null;
    name: string | null;
    departmentName: string | null;
    checkType: HrComplianceCheckType;
    severity: "low" | "medium" | "high" | "critical";
    ownerRule: string;
    title: string;
    description: string;
    evidence: Record<string, unknown>;
    status: "open" | "acknowledged" | "resolved";
    ownerUserId: string | null;
    createdAt: string;
}

export interface HrComplianceSummary {
    totalFindings: number;
    openFindings: number;
    byType: Record<string, number>;
    bySeverity: Record<string, number>;
    generatedAt: string;
    narrative: string;
}

interface HrComplianceFindingPayload {
    check_id?: unknown;
    employee_id?: unknown;
    employee_number?: unknown;
    name?: unknown;
    department_name?: unknown;
    check_type?: unknown;
    severity?: unknown;
    owner_rule?: unknown;
    title?: unknown;
    description?: unknown;
    evidence?: unknown;
    status?: unknown;
    owner_user_id?: unknown;
    created_at?: unknown;
}

interface HrComplianceSummaryPayload {
    total_findings?: unknown;
    open_findings?: unknown;
    by_type?: unknown;
    by_severity?: unknown;
    generated_at?: unknown;
    narrative?: unknown;
}

function mapComplianceFinding(
    payload: HrComplianceFindingPayload,
): HrComplianceFinding {
    const type = String(
        payload.check_type ?? "document_expiry",
    ) as HrComplianceCheckType;
    const status = String(
        payload.status ?? "open",
    ) as HrComplianceFinding["status"];
    return {
        checkId: String(payload.check_id ?? ""),
        employeeId:
            payload.employee_id != null ? String(payload.employee_id) : null,
        employeeNumber:
            payload.employee_number != null
                ? String(payload.employee_number)
                : null,
        name: payload.name != null ? String(payload.name) : null,
        departmentName:
            payload.department_name != null
                ? String(payload.department_name)
                : null,
        checkType: type,
        severity: String(
            payload.severity ?? "medium",
        ) as HrComplianceFinding["severity"],
        ownerRule: String(payload.owner_rule ?? ""),
        title: String(payload.title ?? "Compliance finding"),
        description: String(payload.description ?? ""),
        evidence:
            payload.evidence != null && typeof payload.evidence === "object"
                ? (payload.evidence as Record<string, unknown>)
                : {},
        status,
        ownerUserId:
            payload.owner_user_id != null
                ? String(payload.owner_user_id)
                : null,
        createdAt: String(payload.created_at ?? ""),
    };
}

function mapComplianceSummary(
    payload: HrComplianceSummaryPayload,
): HrComplianceSummary {
    return {
        totalFindings: Number(payload.total_findings ?? 0),
        openFindings: Number(payload.open_findings ?? 0),
        byType:
            payload.by_type != null && typeof payload.by_type === "object"
                ? (payload.by_type as Record<string, number>)
                : {},
        bySeverity:
            payload.by_severity != null &&
            typeof payload.by_severity === "object"
                ? (payload.by_severity as Record<string, number>)
                : {},
        generatedAt: String(payload.generated_at ?? ""),
        narrative: String(payload.narrative ?? ""),
    };
}

/** L1 compliance feed — aggregate counts only, never per-person data. */
export async function getComplianceSummary(): Promise<HrComplianceSummary> {
    const response = await fetchWithSession(
        "/api/v1/ai/hr/alerts/compliance",
        {},
    );
    if (!response.ok) {
        throw new ApiError(
            response.status,
            "Compliance feed could not be loaded.",
        );
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: HrComplianceSummaryPayload | null;
    };
    if (payload.data && typeof payload.data === "object") {
        return mapComplianceSummary(payload.data as HrComplianceSummaryPayload);
    }
    throw new ApiError(response.status, "Compliance feed could not be loaded.");
}

/** L2 per-employee compliance findings (needs `erp.hr.ai.individual`). */
export async function getEmployeeComplianceFindings(
    employeeId: string,
): Promise<HrComplianceFinding[]> {
    const response = await fetchWithSession(
        `/api/v1/ai/hr/alerts/compliance/${employeeId}`,
        {},
    );
    if (!response.ok) {
        throw new ApiError(
            response.status,
            response.status === 403
                ? "erp.hr.ai.individual required for the individual view."
                : "Compliance findings could not be loaded.",
        );
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: HrComplianceFindingPayload[] | null;
    };
    return Array.isArray(payload.data)
        ? (payload.data as HrComplianceFindingPayload[]).map(
              mapComplianceFinding,
          )
        : [];
}

/** Move one finding along `acknowledged | resolved` (audited). */
export async function setComplianceStatus(
    checkId: string,
    status: "acknowledged" | "resolved",
): Promise<HrComplianceFinding> {
    const response = await apiPost<HrComplianceFindingPayload>(
        `/api/v1/ai/hr/alerts/compliance/${checkId}/status`,
        { status },
    );
    return mapComplianceFinding(response);
}

// HR AI — L3 narratives (HR-AI-003): payroll cost, leave-pay correlation,
// compliance weekly digest. Management-only (erp.hr.ai.management), aggregates
// only, every access audited. The core edge relays the ai-agent response
// verbatim (flat body, no `data` envelope).
// ---------------------------------------------------------------------------

export type L3NarrativeKind =
    | "payroll_cost"
    | "leave_pay_correlation"
    | "compliance_digest";

export interface L3Narrative {
    status: string;
    source: string;
    asOf: string;
    kind: L3NarrativeKind;
    title: string | null;
    summary: string | null;
    points: string[];
    caveat: string | null;
    generatedAt: string | null;
    modelUsed: string | null;
    figures: Record<string, string>;
}

interface L3NarrativePayload {
    status?: unknown;
    source?: unknown;
    as_of?: unknown;
    kind?: unknown;
    title?: unknown;
    summary?: unknown;
    points?: unknown;
    caveat?: unknown;
    generated_at?: unknown;
    model_used?: unknown;
    figures?: unknown;
}

export interface LeavePayPair {
    periodStart: string;
    runCode: string;
    leaveDays: number;
    overtime: string;
}

interface LeavePayCorrelationPayload {
    pairs?: unknown;
}

function mapL3Narrative(payload: L3NarrativePayload): L3Narrative {
    return {
        status: String(payload.status ?? ""),
        source: String(payload.source ?? ""),
        asOf: String(payload.as_of ?? ""),
        kind: String(payload.kind ?? "") as L3NarrativeKind,
        title: payload.title != null ? String(payload.title) : null,
        summary: payload.summary != null ? String(payload.summary) : null,
        points: Array.isArray(payload.points)
            ? (payload.points as unknown[]).map(String)
            : [],
        caveat: payload.caveat != null ? String(payload.caveat) : null,
        generatedAt:
            payload.generated_at != null ? String(payload.generated_at) : null,
        modelUsed: payload.model_used != null ? String(payload.model_used) : null,
        figures:
            payload.figures != null && typeof payload.figures === "object"
                ? Object.fromEntries(
                      Object.entries(
                          payload.figures as Record<string, unknown>,
                      ).map(([key, value]) => [key, String(value)]),
                  )
                : {},
    };
}

function mapLeavePayPairs(payload: LeavePayCorrelationPayload): LeavePayPair[] {
    if (!Array.isArray(payload.pairs)) return [];
    return (payload.pairs as unknown[]).map((raw) => {
        const pair = raw as {
            period_start?: unknown;
            run_code?: unknown;
            leave_days?: unknown;
            overtime?: unknown;
        };
        return {
            periodStart: String(pair.period_start ?? ""),
            runCode: String(pair.run_code ?? ""),
            leaveDays: Number(pair.leave_days ?? 0),
            overtime: String(pair.overtime ?? "0"),
        };
    });
}

/** L3 narrative for one kind — cached, aggregate-only, management-gated. */
export async function getL3Narrative(
    kind: L3NarrativeKind,
): Promise<L3Narrative> {
    const response = await fetchWithSession(`/api/v1/ai/l3/${kind}`, {});
    if (!response.ok) {
        throw new ApiError(
            response.status,
            response.status === 403
                ? "erp.hr.ai.management is required to view L3 narratives."
                : "L3 narrative could not be loaded.",
        );
    }
    const payload = (await response.json().catch(() => ({}))) as L3NarrativePayload;
    return mapL3Narrative(payload);
}

/** Force-recompute an L3 narrative (same management gate as the read). */
export async function refreshL3Narrative(
    kind: L3NarrativeKind,
): Promise<L3Narrative> {
    try {
        const payload = await apiPost<L3NarrativePayload>(
            `/api/v1/ai/l3/${kind}/refresh`,
            {},
        );
        return mapL3Narrative(payload);
    } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
            throw new ApiError(
                403,
                "erp.hr.ai.management is required to refresh L3 narratives.",
            );
        }
        throw error;
    }
}

/** The monthly (leave days, overtime) series the correlation narrates. */
export async function getLeavePayCorrelation(): Promise<LeavePayPair[]> {
    const payload = await apiFetch<LeavePayCorrelationPayload>(
        "/api/v1/ai/hr/l3/leave-pay-correlation",
        {},
    );
    return mapLeavePayPairs(payload);
}
