import {
    apiFetch,
    apiFetchWithMeta,
    apiPost,
    type PaginationMeta,
} from "@/lib/api/http";

const FINANCE = "/api/v1/finance";

function queryString(
    params: Record<string, string | number | boolean | undefined>,
): string {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (
            value === undefined ||
            value === null ||
            value === "" ||
            value === false
        )
            continue;
        search.set(key, String(value));
    }
    const encoded = search.toString();
    return encoded ? `?${encoded}` : "";
}

export type AccountType =
    "asset" | "liability" | "equity" | "revenue" | "expense";

export interface Account {
    id: string;
    tenant_id: string;
    code: string;
    name: string;
    account_type: AccountType;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface AccountCreateInput {
    code: string;
    name: string;
    account_type: AccountType;
}

export type EntryStatus = "draft" | "posted" | "voided" | "reversed";

export interface JournalLine {
    id: string;
    account_id: string;
    debit: number | null;
    credit: number | null;
    currency: string;
}

export interface JournalLineInput {
    account_code: string;
    debit?: number | null;
    credit?: number | null;
}

export interface JournalEntry {
    id: string;
    tenant_id: string;
    entry_date: string;
    memo: string | null;
    status: EntryStatus;
    source: string;
    source_ref: string | null;
    lines: JournalLine[];
    posted_at: string | null;
    posted_by_user_id: string | null;
    voided_at: string | null;
    reversal_entry_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface JournalEntryCreateInput {
    entry_date: string;
    memo?: string | null;
    lines: JournalLineInput[];
}

export type JournalEntryListParams = {
    status?: EntryStatus;
    from_date?: string;
    to_date?: string;
    offset?: number;
    limit?: number;
};

export interface FiscalPeriod {
    id: string;
    tenant_id: string;
    name: string;
    start_date: string;
    end_date: string;
    is_closed: boolean;
    created_at: string;
    updated_at: string;
}

export interface FiscalPeriodCreateInput {
    name: string;
    start_date: string;
    end_date: string;
}

export type InvoiceStatus = "draft" | "issued" | "approved" | "paid" | "voided";

export interface InvoiceLine {
    id: string;
    line_no: number;
    description: string;
    account_id: string;
    quantity: number;
    unit_price: number;
    amount: number;
}

export interface InvoiceLineInput {
    description: string;
    account_code: string;
    quantity: number;
    unit_price: number;
}

export interface Invoice {
    id: string;
    tenant_id: string;
    invoice_number: string;
    customer_id: string;
    customer_name?: string | null;
    invoice_date: string;
    due_date: string;
    status: InvoiceStatus;
    total: number;
    currency: string;
    exchange_rate: number;
    source: string;
    source_ref: string | null;
    source_order_number?: string | null;
    lines: InvoiceLine[];
    issued_at: string | null;
    approved_at: string | null;
    voided_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface InvoiceCreateInput {
    customer_id: string;
    invoice_date: string;
    due_date: string;
    lines: InvoiceLineInput[];
    currency?: string;
}

export interface ExchangeRateEntry {
    base_currency: string;
    quote_currency: string;
    effective_date: string;
    rate: number;
}

export interface FxContext {
    default_currency: string;
    currencies: string[];
}

export type InvoiceListParams = {
    status?: InvoiceStatus;
    offset?: number;
    limit?: number;
};

export interface Payment {
    id: string;
    tenant_id: string;
    payment_number: string;
    invoice_id: string;
    amount: number;
    method: string;
    paid_at: string;
    status: string;
    source: string;
    source_ref: string | null;
    created_at: string;
    updated_at: string;
}

export interface PaymentApplyInput {
    amount: number;
    method: string;
    paid_at: string;
}

export interface TrialBalanceRow {
    account_id: string;
    code: string;
    name: string;
    account_type: AccountType;
    debit: number;
    credit: number;
}

export interface TrialBalance {
    as_of: string;
    rows: TrialBalanceRow[];
    total_debit: number;
    total_credit: number;
}

export interface PnlLine {
    account_id: string;
    code: string;
    name: string;
    amount: number;
}

export interface ProfitAndLoss {
    from_date: string;
    to_date: string;
    revenue: PnlLine[];
    expenses: PnlLine[];
    total_revenue: number;
    total_expenses: number;
    net_income: number;
}

export interface BalanceSheetLine {
    account_id: string;
    code: string;
    name: string;
    balance: number;
}

export interface BalanceSheet {
    as_of: string;
    assets: BalanceSheetLine[];
    liabilities: BalanceSheetLine[];
    equity: BalanceSheetLine[];
    total_assets: number;
    total_liabilities: number;
    total_equity: number;
}

// --- Chart of accounts ---

export function listAccounts(activeOnly = true): Promise<Account[]> {
    const search = activeOnly ? "" : "?include_inactive=true";
    return apiFetch<Account[]>(`${FINANCE}/accounts${search}`);
}

export function createAccount(input: AccountCreateInput): Promise<Account> {
    return apiPost<Account>(`${FINANCE}/accounts`, input);
}

export function deactivateAccount(accountId: string): Promise<Account> {
    return apiFetch<Account>(`${FINANCE}/accounts/${accountId}`, {
        method: "DELETE",
    });
}

// --- Journal entries ---

export function listJournalEntries(
    params: JournalEntryListParams = {},
): Promise<{ data: JournalEntry[]; meta: PaginationMeta | null }> {
    return apiFetchWithMeta<JournalEntry[]>(
        `${FINANCE}/journal-entries${queryString(params)}`,
    );
}

export function getJournalEntry(entryId: string): Promise<JournalEntry> {
    return apiFetch<JournalEntry>(`${FINANCE}/journal-entries/${entryId}`);
}

export function createJournalEntry(
    input: JournalEntryCreateInput,
): Promise<JournalEntry> {
    return apiPost<JournalEntry>(`${FINANCE}/journal-entries`, input);
}

export function postJournalEntry(entryId: string): Promise<JournalEntry> {
    return apiPost<JournalEntry>(
        `${FINANCE}/journal-entries/${entryId}/post`,
        {},
    );
}

export function voidJournalEntry(entryId: string): Promise<JournalEntry> {
    return apiPost<JournalEntry>(
        `${FINANCE}/journal-entries/${entryId}/void`,
        {},
    );
}

// --- Fiscal periods ---

export function listFiscalPeriods(): Promise<FiscalPeriod[]> {
    return apiFetch<FiscalPeriod[]>(`${FINANCE}/fiscal-periods`);
}

export function createFiscalPeriod(
    input: FiscalPeriodCreateInput,
): Promise<FiscalPeriod> {
    return apiPost<FiscalPeriod>(`${FINANCE}/fiscal-periods`, input);
}

export function closeFiscalPeriod(periodId: string): Promise<FiscalPeriod> {
    return apiPost<FiscalPeriod>(
        `${FINANCE}/fiscal-periods/${periodId}/close`,
        {},
    );
}

// --- Invoices & payments ---

export function listInvoices(
    params: InvoiceListParams = {},
): Promise<{ data: Invoice[]; meta: PaginationMeta | null }> {
    return apiFetchWithMeta<Invoice[]>(
        `${FINANCE}/invoices${queryString(params)}`,
    );
}

export function getInvoice(invoiceId: string): Promise<Invoice> {
    return apiFetch<Invoice>(`${FINANCE}/invoices/${invoiceId}`);
}

export function createInvoice(input: InvoiceCreateInput): Promise<Invoice> {
    return apiPost<Invoice>(`${FINANCE}/invoices`, input);
}

// --- FX rates (invoice currency) ---

export function getFxContext(): Promise<FxContext> {
    return apiFetch<FxContext>(`${FINANCE}/fx/context`);
}

export function getFxRate(
    quoteCurrency: string,
    on: string,
): Promise<ExchangeRateEntry> {
    return apiFetch<ExchangeRateEntry>(
        `${FINANCE}/fx/rates/${encodeURIComponent(quoteCurrency)}${queryString({ on })}`,
    );
}

export function upsertFxRate(input: {
    base_currency: string;
    quote_currency: string;
    effective_date: string;
    rate: number;
}): Promise<ExchangeRateEntry> {
    return apiFetch<ExchangeRateEntry>(`${FINANCE}/fx/rates`, {
        method: "PUT",
        body: JSON.stringify(input),
    });
}

export function issueInvoice(invoiceId: string): Promise<Invoice> {
    return apiPost<Invoice>(`${FINANCE}/invoices/${invoiceId}/issue`, {});
}

export function approveInvoice(invoiceId: string): Promise<Invoice> {
    return apiPost<Invoice>(`${FINANCE}/invoices/${invoiceId}/approve`, {});
}

export function voidInvoice(invoiceId: string): Promise<Invoice> {
    return apiPost<Invoice>(`${FINANCE}/invoices/${invoiceId}/void`, {});
}

export function applyPayment(
    invoiceId: string,
    input: PaymentApplyInput,
): Promise<Payment> {
    return apiPost<Payment>(`${FINANCE}/invoices/${invoiceId}/payments`, input);
}

export function getPayment(paymentId: string): Promise<Payment> {
    return apiFetch<Payment>(`${FINANCE}/payments/${paymentId}`);
}

// --- Reports ---

export function getTrialBalance(asOf: string): Promise<TrialBalance> {
    return apiFetch<TrialBalance>(
        `${FINANCE}/reports/trial-balance${queryString({ as_of: asOf })}`,
    );
}

export function getProfitAndLoss(
    fromDate: string,
    toDate: string,
): Promise<ProfitAndLoss> {
    return apiFetch<ProfitAndLoss>(
        `${FINANCE}/reports/profit-and-loss${queryString({ from_date: fromDate, to_date: toDate })}`,
    );
}

export function getBalanceSheet(asOf: string): Promise<BalanceSheet> {
    return apiFetch<BalanceSheet>(
        `${FINANCE}/reports/balance-sheet${queryString({ as_of: asOf })}`,
    );
}

// --- Customers (CRM) ---

export interface Customer {
    id: string;
    tenant_id: string;
    customer_code: string;
    name: string;
    email: string | null;
    phone: string | null;
    credit_limit: number | null;
    currency: string | null;
    is_active: boolean;
}

export function listCustomers(): Promise<Customer[]> {
    return apiFetch<Customer[]>("/api/v1/crm/customers");
}

// --- Finance automation (SKY-56/SKY-64) ---

const AUTOMATION = "/api/v1/finance/automation";

export interface ArAgingBucket {
    bucket: string;
    count: number;
    amount: number;
    share: number;
}

export interface ArAging {
    as_of: string;
    total_ar: number;
    buckets: ArAgingBucket[];
}

export interface CloseChecklistItem {
    label: string;
    status: string;
    detail: string | null;
}

export interface CloseChecklist {
    period_id: string;
    period_name: string;
    items: CloseChecklistItem[];
    ready: boolean;
}

export interface DuplicateCandidate {
    entry_id: string;
    entry_date: string;
    memo: string | null;
    source_ref: string | null;
}

export interface DuplicateGroup {
    key: string;
    reason: string;
    entries: DuplicateCandidate[];
}

export interface AccountCodeSuggestion {
    description: string;
    suggested_code: string;
    suggested_name: string;
    confidence: number;
    reasoning: string;
    amount: number | null;
    side: "debit" | "credit";
    contra_code: string;
    contra_name: string;
    id?: string | null;
    status?: string;
    feature?: string;
}

export interface SuggestionQualityScore {
    feature: string;
    window_days: number;
    sample_count: number;
    acceptance_rate: number | null;
    below_threshold: boolean;
    computed_at: string | null;
}

export interface SuggestionQuality {
    window_days: number;
    overall_acceptance_rate: number | null;
    low_quality: boolean;
    features: SuggestionQualityScore[];
}

export interface WorkingCapitalAlert {
    ratio: number;
    threshold: number;
    current_assets: number;
    current_liabilities: number;
    alert: boolean;
}

export interface HealthComponent {
    name: string;
    score: number;
    weight: number;
    detail: string | null;
}

export interface HealthScore {
    overall: number;
    components: HealthComponent[];
}

export interface CashflowPosition {
    month: string;
    opening: number;
    inflows: number;
    outflows: number;
    closing: number;
}

export interface CashflowProjection {
    positions: CashflowPosition[];
}

export interface ComparativePnlRow {
    account_code: string;
    account_name: string;
    current_amount: number;
    prior_amount: number;
    variance: number;
    variance_pct: number;
}

export interface ComparativePnl {
    current_from: string;
    current_to: string;
    prior_from: string;
    prior_to: string;
    rows: ComparativePnlRow[];
}

export interface FinanceAnomaly {
    id: string;
    entity_type: string;
    entity_id: string;
    anomaly_type: string;
    severity: string;
    description: string;
    status: string;
    detected_at: string;
}

export interface TenantSettings {
    working_capital_threshold: number;
    invoice_numbering_scheme?: string | null;
}

export interface InvoiceNumberingScheme {
    prefix: string;
    scheme: string;
    seq_width: number;
    rationale: string;
}

export function getAging(asOf: string): Promise<ArAging> {
    return apiFetch<ArAging>(
        `${AUTOMATION}/aging${queryString({ as_of: asOf })}`,
    );
}

export function getCloseChecklist(periodId: string): Promise<CloseChecklist> {
    return apiFetch<CloseChecklist>(
        `${AUTOMATION}/close-checklist${queryString({ period_id: periodId })}`,
    );
}

export function getDuplicates(): Promise<DuplicateGroup[]> {
    return apiFetch<DuplicateGroup[]>(`${AUTOMATION}/duplicates`);
}

export function suggestAccountCode(
    description: string,
): Promise<AccountCodeSuggestion> {
    return apiPost<AccountCodeSuggestion>(
        `${AUTOMATION}/suggest-account-code`,
        { description },
    );
}

export interface InvoiceLineSuggestion {
    description: string;
    account_code: string;
    account_name: string;
    times_used: number;
    score: number;
}

export function suggestInvoiceLines(
    description: string,
): Promise<InvoiceLineSuggestion[]> {
    return apiPost<InvoiceLineSuggestion[]>(
        `${AUTOMATION}/suggest-invoice-lines`,
        { description },
    );
}

export function acceptSuggestion(
    suggestionId: string,
): Promise<AccountCodeSuggestion> {
    return apiPost<AccountCodeSuggestion>(
        `${AUTOMATION}/suggestions/${suggestionId}/accept`,
        {},
    );
}

export function dismissSuggestion(
    suggestionId: string,
): Promise<AccountCodeSuggestion> {
    return apiPost<AccountCodeSuggestion>(
        `${AUTOMATION}/suggestions/${suggestionId}/dismiss`,
        {},
    );
}

export function getSuggestionQuality(
    windowDays = 30,
): Promise<SuggestionQuality> {
    return apiFetch<SuggestionQuality>(
        `${AUTOMATION}/suggestions/quality${queryString({
            window_days: windowDays,
        })}`,
    );
}

export function getWorkingCapitalAlert(
    asOf: string,
): Promise<WorkingCapitalAlert> {
    return apiFetch<WorkingCapitalAlert>(
        `${AUTOMATION}/working-capital-alert${queryString({ as_of: asOf })}`,
    );
}

export function getHealthScore(asOf: string): Promise<HealthScore> {
    return apiFetch<HealthScore>(
        `${AUTOMATION}/health-score${queryString({ as_of: asOf })}`,
    );
}

export function getCashflowProjection(
    asOf: string,
): Promise<CashflowProjection> {
    return apiFetch<CashflowProjection>(
        `${AUTOMATION}/cashflow-projection${queryString({ as_of: asOf })}`,
    );
}

export function getAnomalies(): Promise<FinanceAnomaly[]> {
    return apiFetch<FinanceAnomaly[]>(`${AUTOMATION}/anomalies`);
}

export function scanAnomalies(): Promise<FinanceAnomaly[]> {
    return apiPost<FinanceAnomaly[]>(`${AUTOMATION}/anomalies/scan`, {});
}

export function getComparativePnl(
    currentFrom: string,
    currentTo: string,
    priorFrom: string,
    priorTo: string,
): Promise<ComparativePnl> {
    return apiFetch<ComparativePnl>(
        `${AUTOMATION}/reports/comparative-pnl${queryString({
            current_from: currentFrom,
            current_to: currentTo,
            prior_from: priorFrom,
            prior_to: priorTo,
        })}`,
    );
}

export function getAutomationSettings(): Promise<TenantSettings> {
    return apiFetch<TenantSettings>(`${AUTOMATION}/settings`);
}

export function updateAutomationSettings(
    threshold: number,
    invoiceNumberingScheme?: string,
): Promise<TenantSettings> {
    return apiFetch<TenantSettings>(`${AUTOMATION}/settings`, {
        method: "PUT",
        body: JSON.stringify({
            threshold,
            ...(invoiceNumberingScheme !== undefined
                ? { invoice_numbering_scheme: invoiceNumberingScheme }
                : {}),
        }),
    });
}

export function recommendInvoiceNumberingScheme(): Promise<InvoiceNumberingScheme> {
    return apiFetch<InvoiceNumberingScheme>(
        `${AUTOMATION}/invoice-numbering-scheme`,
    );
}

export function reverseJournalEntry(entryId: string): Promise<JournalEntry> {
    return apiPost<JournalEntry>(
        `${AUTOMATION}/journal-entries/${entryId}/reverse`,
        {},
    );
}

// ---------------------------------------------------------------------------
// FIN-AI-001: AI draft / narrate / remind
// ---------------------------------------------------------------------------

export interface DraftEntryLine {
    account_code: string;
    account_name: string;
    amount: number;
    side: "debit" | "credit";
    description: string;
}

export interface DraftEntry {
    lines: DraftEntryLine[];
    explanation: string;
    confidence: number;
    reasoning: string;
    model_used: string;
}

export interface AnomalyNarration {
    narration: string;
    model_used: string;
}

export interface ReminderDraft {
    invoice_number: string;
    customer_name: string | null;
    amount: number;
    days_overdue: number;
    tone: "polite" | "firm" | "final";
    subject: string;
    body: string;
}

export function draftJournalEntry(description: string): Promise<DraftEntry> {
    return apiPost<DraftEntry>(`${AUTOMATION}/draft-entry`, { description });
}

export function narrateAnomaly(anomalyId: string): Promise<AnomalyNarration> {
    return apiPost<AnomalyNarration>(
        `${AUTOMATION}/anomalies/${anomalyId}/narrate`,
        {},
    );
}

export function generateReminder(invoiceId: string): Promise<ReminderDraft> {
    return apiPost<ReminderDraft>(`${AUTOMATION}/reminders/generate`, {
        invoice_id: invoiceId,
    });
}

export function batchReminders(): Promise<{ reminders: ReminderDraft[] }> {
    return apiPost<{ reminders: ReminderDraft[] }>(
        `${AUTOMATION}/reminders/batch`,
        {},
    );
}

// ---------------------------------------------------------------------------
// SKY-66 (FIN-AUT-002): finance automation wave 2
// ---------------------------------------------------------------------------

export interface RevenueConcentrationEntry {
    customer_id: string;
    customer_name: string | null;
    amount: number;
    share: number;
    above_threshold: boolean;
}

export interface RevenueConcentration {
    from_date: string;
    to_date: string;
    threshold: number;
    total_revenue: number;
    entries: RevenueConcentrationEntry[];
}

export interface WorkingCapitalPosition {
    month: string;
    assets: number;
    liabilities: number;
    working_capital: number;
}

export interface WorkingCapitalSeries {
    positions: WorkingCapitalPosition[];
}

export interface PaymentMethodAnalyticsEntry {
    method: string;
    count: number;
    amount: number;
    share: number;
}

export interface PaymentMethodAnalytics {
    from_date: string;
    to_date: string;
    total_amount: number;
    entries: PaymentMethodAnalyticsEntry[];
}

export interface AuditReadinessCheck {
    key: string;
    label: string;
    status: "ok" | "warning" | "missing";
    detail: string | null;
}

export interface AuditReadiness {
    ready: boolean;
    checks: AuditReadinessCheck[];
}

export interface AuditLogEntry {
    id: string | null;
    action: string;
    target: string;
    actor_user_id: string | null;
    details: Record<string, unknown> | null;
    ip_address: string | null;
    user_agent: string | null;
    hash: string | null;
    prev_hash: string | null;
    created_at: string | null;
}

export interface AuditLogSearchResult {
    entries: AuditLogEntry[];
    total: number;
    offset: number;
    limit: number;
}

export interface AuditSearchParams {
    q?: string;
    action?: string;
    actorUserId?: string;
    fromDate?: string;
    toDate?: string;
    offset?: number;
    limit?: number;
}

export function getRevenueConcentration(
    fromDate: string,
    toDate: string,
): Promise<RevenueConcentration> {
    return apiFetch<RevenueConcentration>(
        `${AUTOMATION}/revenue-concentration${queryString({
            from_date: fromDate,
            to_date: toDate,
        })}`,
    );
}

export function getWorkingCapitalSeries(
    asOf: string,
    months?: number,
): Promise<WorkingCapitalSeries> {
    return apiFetch<WorkingCapitalSeries>(
        `${AUTOMATION}/working-capital-series${queryString({
            as_of: asOf,
            months,
        })}`,
    );
}

export function getPaymentMethodAnalytics(
    fromDate: string,
    toDate: string,
): Promise<PaymentMethodAnalytics> {
    return apiFetch<PaymentMethodAnalytics>(
        `${AUTOMATION}/payment-methods${queryString({
            from_date: fromDate,
            to_date: toDate,
        })}`,
    );
}

export function getAuditReadiness(): Promise<AuditReadiness> {
    return apiFetch<AuditReadiness>(`${AUTOMATION}/audit-readiness`);
}

export function searchAuditLog(
    params: AuditSearchParams = {},
): Promise<AuditLogSearchResult> {
    return apiFetch<AuditLogSearchResult>(
        `${AUTOMATION}/audit/search${queryString({
            q: params.q,
            action: params.action,
            actor_user_id: params.actorUserId,
            from_date: params.fromDate,
            to_date: params.toDate,
            offset: params.offset,
            limit: params.limit,
        })}`,
    );
}

// ---------------------------------------------------------------------------
// SKY-82 A4: revenue forecasting
// ---------------------------------------------------------------------------

export interface RevenueForecastDeal {
    id: string;
    name: string;
    amount: number | null;
    probability: number;
    expected_close_date: string;
    // Raw conversion value (probability/100 x amount) vs the health-adjusted
    // value actually blended into the month's pipeline.
    weighted: number;
    health: string | null;
    confidence: number | null;
    factor: number;
    adjusted: number;
}

export interface RevenueForecastPoint {
    month: string;
    predicted: number;
    // Per-point decomposition: baseline = trend + seasonal projection alone,
    // pipeline = weighted open-deal uplift blended in (predicted == baseline + pipeline).
    baseline: number | null;
    pipeline: number | null;
    lower_bound: number | null;
    upper_bound: number | null;
    // The deals behind this month's pipeline, health-adjusted value each.
    deals: RevenueForecastDeal[];
}

export interface RevenueForecastActual {
    month: string;
    actual: number;
}

export interface RevenueForecast {
    model_version: string;
    backtest_mape: number | null;
    sigma: number | null;
    points: RevenueForecastPoint[];
    history: RevenueForecastActual[];
    pipeline_value: number | null;
}

function asNumber(value: string | number | null | undefined): number | null {
    if (value === null || value === undefined || value === "") return null;
    const n = typeof value === "number" ? value : Number(value);
    return Number.isFinite(n) ? n : null;
}

// Core serializes Decimal keys as strings; coerce every numeric field once so
// downstream consumers get real numbers (string compares were sorting money
// lexicographically, e.g. "71927" > "573221").
export function mapRevenueForecast(payload: RevenueForecast): RevenueForecast {
    return {
        ...payload,
        backtest_mape: asNumber(payload.backtest_mape),
        sigma: asNumber(payload.sigma),
        pipeline_value: asNumber(payload.pipeline_value),
        points: (payload.points ?? []).map((point) => ({
            ...point,
            predicted: asNumber(point.predicted) ?? 0,
            baseline: asNumber(point.baseline),
            pipeline: asNumber(point.pipeline),
            lower_bound: asNumber(point.lower_bound),
            upper_bound: asNumber(point.upper_bound),
            deals: (point.deals ?? []).map((deal) => ({
                ...deal,
                amount: asNumber(deal.amount),
                weighted: asNumber(deal.weighted) ?? 0,
                factor: asNumber(deal.factor) ?? 1,
                adjusted: asNumber(deal.adjusted) ?? 0,
                confidence: asNumber(deal.confidence),
            })),
        })),
        history: (payload.history ?? []).map((actual) => ({
            ...actual,
            actual: asNumber(actual.actual) ?? 0,
        })),
    };
}

export function getRevenueForecast(): Promise<RevenueForecast> {
    return apiFetch<RevenueForecast>(`${FINANCE}/forecast/revenue`).then(
        mapRevenueForecast,
    );
}

export function refreshRevenueForecast(): Promise<RevenueForecast> {
    return apiPost<RevenueForecast>(
        `${FINANCE}/forecast/revenue/refresh`,
        {},
    ).then(mapRevenueForecast);
}
