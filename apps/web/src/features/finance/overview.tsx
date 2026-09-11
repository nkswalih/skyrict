"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, MessageSquare, Wallet } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/ui/page-skeletons";
import { StatCardSkeleton } from "@/components/ui/page-skeletons";
import { createConversation } from "@/lib/api/agents-api";
import {
    getProfitAndLoss,
    getWorkingCapitalAlert,
    getHealthScore,
    getAnomalies,
    scanAnomalies,
    getRevenueConcentration,
    getWorkingCapitalSeries,
    getPaymentMethodAnalytics,
    getAuditReadiness,
    listAccounts,
    listFiscalPeriods,
    listInvoices,
    listJournalEntries,
    type Account,
    type AuditReadiness,
    type FiscalPeriod,
    type Invoice,
    type JournalEntry,
    type PaymentMethodAnalytics,
    type ProfitAndLoss,
    type RevenueConcentration,
    type WorkingCapitalAlert,
    type WorkingCapitalSeries,
    type HealthScore,
    type FinanceAnomaly,
} from "@/lib/api/finance-api";
import { ApiError } from "@/lib/api/http";
import { formatDate, formatMoney, sumMoney } from "@/lib/finance/format";
import { hasPermission, useModuleAccess } from "@/lib/access/modules";
import { CreateAccountDialog } from "@/features/finance/accounts";
import { CreateInvoiceDialog } from "@/features/finance/invoices";
import { CreateJournalEntryDialog } from "@/features/finance/journal-entries";
import {
    FinanceTable,
    type FinanceColumn,
} from "@/features/finance/components/finance-table";
import {
    PeriodSelector,
    defaultPeriodValue,
    resolvePeriodRange,
    today,
    type PeriodValue,
} from "@/features/finance/components/period-selector";
import {
    EntryStatusBadge,
    InvoiceStatusBadge,
} from "@/features/finance/components/status-badge";
import { KpiCard } from "@/features/finance/components/kpi-card";
import { RevenueForecastCard } from "@/features/finance/components/forecast-card";
import { FinanceErrorState } from "@/features/finance/components/state-cards";
import {
    WorkingCapitalCard,
    HealthScoreCard,
    AnomalyFeed,
    RevenueConcentrationCard,
    WorkingCapitalTrendCard,
    PaymentMethodsCard,
    AuditReadinessCard,
} from "@/features/finance/components/automation-widgets";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | {
          state: "ready";
          accounts: Account[];
          entries: JournalEntry[];
          invoices: Invoice[];
          periods: FiscalPeriod[];
          pnl: ProfitAndLoss;
          workingCapital: WorkingCapitalAlert;
          health: HealthScore;
          anomalies: FinanceAnomaly[];
          revenueConcentration: RevenueConcentration | null;
          workingCapitalSeries: WorkingCapitalSeries | null;
          paymentMethods: PaymentMethodAnalytics | null;
          readiness: AuditReadiness | null;
          scanning: boolean;
      };

const entryColumns: FinanceColumn<JournalEntry>[] = [
    { label: "Date", render: (entry) => formatDate(entry.entry_date) },
    { label: "Memo", render: (entry) => entry.memo ?? "-" },
    {
        label: "Status",
        render: (entry) => <EntryStatusBadge status={entry.status} />,
    },
    {
        label: "Debit",
        align: "right",
        render: (entry) => (
            <span className="tabular-nums">
                {formatMoney(sumMoney(entry.lines.map((line) => line.debit)))}
            </span>
        ),
    },
    {
        label: "Credit",
        align: "right",
        render: (entry) => (
            <span className="tabular-nums">
                {formatMoney(sumMoney(entry.lines.map((line) => line.credit)))}
            </span>
        ),
    },
    {
        label: "Lines",
        align: "right",
        render: (entry) => (
            <span className="tabular-nums">{entry.lines.length}</span>
        ),
    },
    {
        label: "",
        align: "right",
        render: (entry) => (
            <Link
                href={`/dashboard/erp/finance/journal-entries/${entry.id}`}
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
                View <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
        ),
    },
];

const invoiceColumns: FinanceColumn<Invoice>[] = [
    { label: "Number", render: (invoice) => invoice.invoice_number },
    { label: "Date", render: (invoice) => formatDate(invoice.invoice_date) },
    {
        label: "Status",
        render: (invoice) => <InvoiceStatusBadge status={invoice.status} />,
    },
    {
        label: "Total",
        align: "right",
        render: (invoice) => formatMoney(invoice.total),
    },
    {
        label: "",
        align: "right",
        render: (invoice) => (
            <Link
                href={`/dashboard/erp/finance/invoices/${invoice.id}`}
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
                View <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
        ),
    },
];

export function FinanceOverview() {
    const { permissions } = useModuleAccess();
    const router = useRouter();
    const canWrite = hasPermission(permissions, "erp.finance.write");
    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [periodValue, setPeriodValue] =
        useState<PeriodValue>(defaultPeriodValue());
    const [startingChat, setStartingChat] = useState(false);
    const [chatError, setChatError] = useState<string | null>(null);

    const startAdvisorChat = useCallback(async () => {
        if (startingChat) return;
        setStartingChat(true);
        setChatError(null);
        try {
            const conversation = await createConversation({});
            router.push(`/dashboard/agents/c/${conversation.id}`);
        } catch (error) {
            setChatError(
                error instanceof ApiError
                    ? error.message
                    : "Could not start the Finance Advisor chat.",
            );
        } finally {
            setStartingChat(false);
        }
    }, [router, startingChat]);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const range = resolvePeriodRange(periodValue);
            const asOf = range.asOf ?? today();
            const [
                accounts,
                entries,
                invoices,
                periods,
                workingCapital,
                health,
                anomalies,
            ] = await Promise.all([
                listAccounts(false),
                listJournalEntries({
                    limit: 5,
                    from_date: range.from ?? undefined,
                    to_date: range.to ?? undefined,
                }),
                listInvoices({ limit: 200 }),
                listFiscalPeriods(),
                getWorkingCapitalAlert(asOf),
                getHealthScore(asOf),
                getAnomalies().catch(() => []),
            ]);
            const pnlFrom =
                range.from ??
                (periods.length > 0
                    ? [...periods].map((period) => period.start_date).sort()[0]
                    : today());
            const pnlTo = range.to ?? today();
            const [
                pnl,
                revenueConcentration,
                workingCapitalSeries,
                paymentMethods,
                readiness,
            ] = await Promise.all([
                getProfitAndLoss(pnlFrom, pnlTo),
                getRevenueConcentration(pnlFrom, pnlTo).catch(() => null),
                getWorkingCapitalSeries(asOf).catch(() => null),
                getPaymentMethodAnalytics(pnlFrom, pnlTo).catch(() => null),
                getAuditReadiness().catch(() => null),
            ]);
            setStatus({
                state: "ready",
                accounts,
                entries: entries.data,
                invoices: invoices.data,
                periods,
                pnl,
                workingCapital,
                health,
                anomalies,
                revenueConcentration,
                workingCapitalSeries,
                paymentMethods,
                readiness,
                scanning: false,
            });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not load finance data.",
            });
        }
    }, [periodValue]);

    const runScan = useCallback(async () => {
        if (status.state !== "ready" || status.scanning) return;
        setStatus({ ...status, scanning: true });
        try {
            await scanAnomalies();
            // Re-fetch the persisted open anomalies so the panel mirrors the
            // DB after the scan, matching the initial load (scanning returns
            // only newly-detected rows and would otherwise blank the feed).
            const anomalies = await getAnomalies().catch(
                () => [] as FinanceAnomaly[],
            );
            setStatus({ ...status, scanning: false, anomalies });
        } catch (error) {
            setStatus({
                ...status,
                scanning: false,
            });
            void error;
        }
    }, [status]);

    useEffect(() => {
        void load();
    }, [load]);

    if (status.state === "loading") {
        return (
            <div className="space-y-6">
                <PageHeader
                    title="Finance"
                    description="Cash, ledgers, invoices, and accounting."
                    icon={Wallet}
                />
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                    <StatCardSkeleton />
                </div>
                <TableSkeleton rows={5} />
            </div>
        );
    }

    if (status.state === "error") {
        return (
            <div className="space-y-6">
                <PageHeader
                    title="Finance"
                    description="Cash, ledgers, invoices, and accounting."
                    icon={Wallet}
                />
                <FinanceErrorState
                    message={status.message}
                    onRetry={() => void load()}
                />
            </div>
        );
    }

    const activeAccounts = status.accounts.filter(
        (account) => account.is_active,
    ).length;
    const openPeriods = status.periods.filter(
        (period) => !period.is_closed,
    ).length;
    const range = resolvePeriodRange(periodValue);
    const visibleInvoices = status.invoices.filter((invoice) => {
        if (range.from && invoice.invoice_date < range.from) return false;
        if (range.to && invoice.invoice_date > range.to) return false;
        return true;
    });
    const unpaidInvoices = visibleInvoices.filter(
        (invoice) => invoice.status !== "paid" && invoice.status !== "voided",
    );
    const outstanding = sumMoney(
        unpaidInvoices.map((invoice) => invoice.total),
    );
    const maxAmount = Math.max(
        status.pnl.total_revenue,
        status.pnl.total_expenses,
        1,
    );

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <PageHeader
                    title="Finance"
                    description="Cash, ledgers, invoices, and accounting."
                    icon={Wallet}
                />
                <div className="flex flex-wrap items-center gap-2">
                    <Button
                        variant="outline"
                        onClick={() => void startAdvisorChat()}
                        disabled={startingChat}
                    >
                        {startingChat ? (
                            <Loader2
                                aria-hidden="true"
                                className="mr-1.5 size-4 animate-spin"
                            />
                        ) : (
                            <MessageSquare
                                aria-hidden="true"
                                className="mr-1.5 size-4"
                            />
                        )}
                        Ask Finance Advisor
                    </Button>
                    <PeriodSelector
                        value={periodValue}
                        onChange={setPeriodValue}
                        periods={status.periods}
                        label="Overview period"
                    />
                </div>
            </div>
            {chatError ? (
                <p className="text-sm text-destructive">{chatError}</p>
            ) : null}

            {canWrite ? (
                <div className="flex flex-wrap gap-2">
                    <CreateInvoiceDialog />
                    <CreateJournalEntryDialog />
                    <CreateAccountDialog onCreated={() => void load()} />
                </div>
            ) : null}

            <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                    label="Net income"
                    value={formatMoney(status.pnl.net_income)}
                    hint="Selected period"
                />
                <KpiCard
                    label="Revenue"
                    value={formatMoney(status.pnl.total_revenue)}
                    hint={`${status.entries.length} journal entries`}
                />
                <KpiCard
                    label="Expenses"
                    value={formatMoney(status.pnl.total_expenses)}
                    hint={`${visibleInvoices.length} invoices`}
                />
                <KpiCard
                    label="Outstanding invoices"
                    value={formatMoney(outstanding)}
                    hint={`${unpaidInvoices.length} unpaid`}
                />
            </section>

            <section>
                <RevenueForecastCard canRefresh={canWrite} />
            </section>

            <section className="grid gap-4 lg:grid-cols-3">
                <WorkingCapitalCard alert={status.workingCapital} />
                <HealthScoreCard score={status.health} />
                <div className="rounded-xl border border-border bg-card p-4">
                    <AnomalyFeed
                        anomalies={status.anomalies}
                        onScan={() => void runScan()}
                        scanning={status.scanning}
                    />
                </div>
            </section>

            <section className="grid gap-4 sm:grid-cols-2">
                <RevenueConcentrationCard
                    concentration={status.revenueConcentration}
                    loading={false}
                />
                <PaymentMethodsCard
                    analytics={status.paymentMethods}
                    loading={false}
                />
            </section>

            <section className="grid gap-4 sm:grid-cols-2">
                <WorkingCapitalTrendCard
                    series={status.workingCapitalSeries}
                    loading={false}
                />
                <AuditReadinessCard
                    readiness={status.readiness}
                    loading={false}
                />
            </section>

            <section className="space-y-4 rounded-xl border border-border bg-card p-5">
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    Revenue vs expenses
                </h2>
                <div className="space-y-4">
                    <div>
                        <div className="mb-1 flex justify-between text-sm">
                            <span className="text-muted-foreground">
                                Revenue
                            </span>
                            <span className="font-medium tabular-nums text-foreground">
                                {formatMoney(status.pnl.total_revenue)}
                            </span>
                        </div>
                        <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                            <div
                                className="h-full rounded-full bg-primary"
                                style={{
                                    width: `${Math.max((status.pnl.total_revenue / maxAmount) * 100, 2)}%`,
                                }}
                            />
                        </div>
                    </div>
                    <div>
                        <div className="mb-1 flex justify-between text-sm">
                            <span className="text-muted-foreground">
                                Expenses
                            </span>
                            <span className="font-medium tabular-nums text-foreground">
                                {formatMoney(status.pnl.total_expenses)}
                            </span>
                        </div>
                        <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                            <div
                                className="h-full rounded-full bg-destructive"
                                style={{
                                    width: `${Math.max((status.pnl.total_expenses / maxAmount) * 100, 2)}%`,
                                }}
                            />
                        </div>
                    </div>
                </div>
            </section>

            <section className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                        Recent journal entries
                    </h2>
                    <Link
                        href="/dashboard/erp/finance/journal-entries"
                        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                        All entries{" "}
                        <ArrowRight aria-hidden="true" className="size-3.5" />
                    </Link>
                </div>
                <FinanceTable
                    columns={entryColumns}
                    rows={status.entries}
                    getKey={(entry) => entry.id}
                    emptyMessage="No journal entries yet."
                />
            </section>

            <section className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                        Recent invoices
                    </h2>
                    <Link
                        href="/dashboard/erp/finance/invoices"
                        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                        All invoices{" "}
                        <ArrowRight aria-hidden="true" className="size-3.5" />
                    </Link>
                </div>
                <FinanceTable
                    columns={invoiceColumns}
                    rows={visibleInvoices}
                    getKey={(invoice) => invoice.id}
                    emptyMessage="No invoices yet."
                />
            </section>

            <p className="text-sm text-muted-foreground">
                {activeAccounts} active accounts · {status.accounts.length}{" "}
                total · {openPeriods} open fiscal periods
            </p>
        </div>
    );
}
