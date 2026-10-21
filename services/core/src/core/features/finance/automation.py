"""Finance automation routes - SKY-56/SKY-64 wave 1 + SKY-66 wave 2.

A thin service + router over :class:`FinanceRepositoryPort` for the finance
automation widgets: close checklist, duplicates, account-code suggestions,
working-capital alert, health score, cash-flow projection, anomalies,
comparative P&L, journal-entry reversal, and tenant automation settings. Wave
2 adds revenue concentration, working-capital trend, payment-method analytics,
audit readiness, and audit-log search. Wave 3 adds customer payment analytics
and vendor-ref extraction.

Reads use ``erp.finance.read``; the reversal (a money moment) uses
``erp.finance.approve``; settings writes use ``erp.finance.write``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import (
    get_core_audit_service,
    get_finance_automation_service,
    get_finance_automation_service_with_ai,
    require_permission,
)
from core.core.audit_events import (
    FINANCE_AI_ANOMALY_NARRATED,
    FINANCE_AI_DRAFT_GENERATED,
    FINANCE_AI_REMINDER_GENERATED,
    FINANCE_ANOMALY_DETECTED,
    FINANCE_DUPLICATE_SUGGESTION_CREATED,
    FINANCE_JOURNAL_ENTRY_REVERSED,
)
from core.core.constants import INVOICE_PREFIX
from core.core.exceptions import AiServiceUnavailableError
from core.core.logging import get_logger
from core.core.permissions import ERP_FINANCE_READ
from core.db.session import commit_writes, get_db
from core.domain.entities import (
    AccountCodeSuggestion,
    AiFinanceAnomaly,
    AiFinanceQualityScore,
    AiFinanceSuggestion,
    AnomalyNarration,
    ChartOfAccount,
    CustomerPaymentAnalytics,
    CustomerPaymentAnalyticsEntry,
    DraftEntry,
    DraftEntryLine,
    InvoiceLineSuggestion,
    ReminderDraft,
    RevenueConcentration,
    RevenueConcentrationEntry,
    WorkingCapitalAlert,
)
from core.features.finance.ports import AuditSink, CustomerPort, FinanceRepositoryPort
from core.features.finance.reminder_email import send_reminder_email
from core.features.finance.report_cache import (
    REPORT_CACHE_TTL_SECONDS,
    ReportCacheRepository,
    hash_report_key,
    serialize_entity,
)
from core.features.finance.schemas import (
    AccountCodeSuggestionResponse,
    AnomalyNarrationResponse,
    AnomalyResponse,
    ArAgingResponse,
    AuditLogEntryResponse,
    AuditLogSearchResponse,
    AuditReadinessResponse,
    CashflowProjectionResponse,
    CloseChecklistResponse,
    ComparativePnlResponse,
    CustomerPaymentAnalyticsResponse,
    DraftEntryLineResponse,
    DraftEntryResponse,
    DuplicateGroupResponse,
    HealthScoreResponse,
    InvoiceLineSuggestionResponse,
    InvoiceNumberingSchemeResponse,
    JournalEntryResponse,
    PaymentMethodAnalyticsResponse,
    ReminderDraftLineResponse,
    ReminderDraftResponse,
    ReminderGenerateRequest,
    RevenueConcentrationResponse,
    SuggestAccountCodeRequest,
    SuggestInvoiceLinesRequest,
    SuggestionQualityResponse,
    TenantSettingsResponse,
    VendorRefExtractionRequest,
    VendorRefExtractionResponse,
    WorkingCapitalAlertResponse,
    WorkingCapitalSeriesResponse,
    WorkingCapitalSettingsRequest,
)
from skyrict_common.exceptions import NotFoundError
from skyrict_common.schemas import ResponseEnvelope

logger = get_logger("core.finance.automation")

router = APIRouter(prefix="/finance/automation", tags=["finance-automation"])


async def emit_working_capital_notification(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    alert: WorkingCapitalAlert,
    as_of: date,
) -> None:
    """Emit a B34 working-capital breach notification (best-effort).

    FIN-AUT B34 wire-up (SKY-93): when the working-capital ratio is below
    the configured threshold, the automation GET is the first producer
    consumer of the notification SDK. The emission is treated as a side
    effect - a producer failure must never turn a read-only GET into a 500 -
    hence try/except + logged exception and a stable dedupe key
    (``finance.b34.working-capital:{tenant}:{as_of}``) so repeated reads and
    retries deliver exactly once per day.
    """
    if not alert.alert:
        return

    from core.features.notifications.domain import (
        NotificationDraft,
        NotificationSeverity,
        RecipientSpec,
    )
    from core.features.notifications.producer import NotificationProducer

    draft = NotificationDraft(
        dedupe_key=f"finance.b34.working-capital:{tenant_id}:{as_of.isoformat()}",
        event_type="finance.working_capital_alert",
        category="finance",
        module="finance",
        severity=NotificationSeverity.HIGH,
        title="Working capital below threshold",
        body=(
            f"Working capital ratio {alert.ratio.normalize()} is below the "
            f"{alert.threshold.normalize()} threshold "
            f"(assets {alert.current_assets.normalize()} / "
            f"liabilities {alert.current_liabilities.normalize()})."
        ),
        recipients=RecipientSpec.from_permissions(ERP_FINANCE_READ),
        relevance_key=ERP_FINANCE_READ,
        payload={
            "as_of": as_of.isoformat(),
            "ratio": str(alert.ratio),
            "threshold": str(alert.threshold),
        },
    )
    try:
        await NotificationProducer(db).emit(draft)
    except Exception:
        logger.exception(
            "finance.notifications.b34_failed",
            tenant_id=str(tenant_id),
            as_of=as_of.isoformat(),
            message="B34 notification emission failed; the alert response is unaffected",
        )


require_finance_read = require_permission("erp.finance.read")
require_finance_write = require_permission("erp.finance.write")
require_finance_approve = require_permission("erp.finance.approve")
require_finance_ai_read = require_permission("erp.finance.ai.read")
require_finance_ai_write = require_permission("erp.finance.ai.write")


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


def _user_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["user_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


AiSuggester = Callable[[str, Sequence[ChartOfAccount]], Awaitable[AccountCodeSuggestion | None]]
AiDrafter = Callable[[str, Sequence[ChartOfAccount]], Awaitable[DraftEntry | None]]
AiNarrater = Callable[[str, str, str], Awaitable[AnomalyNarration | None]]
AiReminder = Callable[[str | None, str, Decimal, int, str], Awaitable[ReminderDraft | None]]
AiLineSuggester = Callable[[str], Awaitable[list[InvoiceLineSuggestion] | None]]


def _narration_cites_figure(narration: str) -> bool:
    """AI narration must quote at least one triggering figure (spec A7)."""
    return any(ch.isdigit() for ch in narration)


@dataclass
class FinanceAutomationService:
    """Business rules for finance automation widgets (thin over the repo)."""

    repo: FinanceRepositoryPort
    audit: AuditSink
    customers: CustomerPort | None = field(default=None)
    ai_suggest: AiSuggester | None = field(default=None)
    ai_draft: AiDrafter | None = field(default=None)
    ai_narrate: AiNarrater | None = field(default=None)
    ai_remind: AiReminder | None = field(default=None)
    ai_lines: AiLineSuggester | None = field(default=None)
    cache: ReportCacheRepository | None = field(default=None)

    async def _cached(
        self,
        tenant_id: uuid.UUID,
        key_parts: tuple[str, ...],
        compute: Callable[..., Awaitable[Any]],
    ) -> Any:
        """Look up cache; on miss, call *compute*, store, and return.

        If ``self.cache`` is ``None`` (default in tests), always hits compute.
        On a hit the stored dict is returned directly — the router layer calls
        ``model_validate()`` which accepts dicts natively.
        """
        if self.cache is None:
            return await compute()
        cache_key = hash_report_key(*key_parts)
        hit = await self.cache.get(tenant_id=tenant_id, cache_key=cache_key)
        if hit is not None:
            return hit
        entity = await compute()
        await self.cache.put(
            tenant_id=tenant_id,
            cache_key=cache_key,
            payload=serialize_entity(entity),
            ttl_seconds=REPORT_CACHE_TTL_SECONDS,
        )
        return entity

    async def close_checklist(self, tenant_id: uuid.UUID, period_id: uuid.UUID) -> Any:
        return await self.repo.close_checklist(tenant_id, period_id)

    async def duplicates(self, tenant_id: uuid.UUID) -> Any:
        return await self.repo.duplicates(tenant_id)

    async def suggest_account_code(self, tenant_id: uuid.UUID, description: str) -> Any:
        accounts = await self.repo.list_accounts(tenant_id)
        suggestion: AccountCodeSuggestion
        if self.ai_suggest is not None and accounts:
            try:
                ai = await self.ai_suggest(description, accounts)
            except AiServiceUnavailableError:
                ai = None
            suggestion = ai or await self.repo.suggest_account_code(tenant_id, description)
        else:
            suggestion = await self.repo.suggest_account_code(tenant_id, description)
        persisted: AiFinanceSuggestion | None = None
        if suggestion.suggested_code:
            persisted = await self.repo.upsert_ai_suggestion(
                tenant_id,
                AiFinanceSuggestion(
                    tenant_id=tenant_id,
                    description=description,
                    suggested_code=suggestion.suggested_code,
                    suggested_name=suggestion.suggested_name,
                    confidence=suggestion.confidence,
                ),
            )
            await self.audit.log(
                tenant_id=tenant_id,
                user_id=None,
                action=FINANCE_DUPLICATE_SUGGESTION_CREATED,
                target="finance:suggestion",
                details={"code": suggestion.suggested_code},
            )
        if persisted is None:
            return suggestion
        return AccountCodeSuggestion(
            description=suggestion.description,
            suggested_code=suggestion.suggested_code,
            suggested_name=suggestion.suggested_name,
            confidence=suggestion.confidence,
            reasoning=suggestion.reasoning,
            amount=suggestion.amount,
            side=suggestion.side,
            contra_code=suggestion.contra_code,
            contra_name=suggestion.contra_name,
            id=persisted.id,
            status=persisted.status,
            feature=persisted.feature,
        )

    async def suggest_invoice_lines(
        self, tenant_id: uuid.UUID, description: str
    ) -> list[InvoiceLineSuggestion]:
        """Best-effort line-item suggestions from the tenant's line history (C1).

        The ai-agent vector store is a read-only enhancement over the plain
        invoice form (never an auto-insert); any failure returns an empty list
        so the dialog degrades to manual entry without an error.
        """
        if self.ai_lines is not None:
            try:
                suggestions = await self.ai_lines(description)
            except AiServiceUnavailableError:
                return []
            return suggestions or []
        return []

    async def accept_suggestion(
        self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> AiFinanceSuggestion:
        result = await self.repo.review_ai_suggestion(tenant_id, suggestion_id, accepted=True)
        if result is None:
            raise NotFoundError("Suggestion not found")
        return result

    async def dismiss_suggestion(
        self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> AiFinanceSuggestion:
        result = await self.repo.review_ai_suggestion(tenant_id, suggestion_id, accepted=False)
        if result is None:
            raise NotFoundError("Suggestion not found")
        return result

    async def suggestion_quality(self, tenant_id: uuid.UUID, window_days: int = 30) -> Any:
        counts = await self.repo.suggestion_acceptance_counts(tenant_id, window_days)
        from decimal import Decimal

        feature_scores = []
        total_accepted = 0
        total_decisions = 0
        for feature, accepted, dismissed in counts:
            total_accepted += accepted
            total_decisions += accepted + dismissed
            rate = (
                Decimal(accepted) / Decimal(accepted + dismissed)
                if accepted + dismissed > 0
                else None
            )
            below = rate is not None and rate < Decimal("0.30")
            score = AiFinanceQualityScore(
                tenant_id=tenant_id,
                feature=feature,
                window_days=window_days,
                sample_count=accepted + dismissed,
                acceptance_rate=rate,
                below_threshold=below,
            )
            persisted_score = await self.repo.upsert_ai_quality_score(tenant_id, score)
            feature_scores.append(persisted_score)
        overall_rate = (
            Decimal(total_accepted) / Decimal(total_decisions) if total_decisions > 0 else None
        )
        from core.features.finance.schemas import (
            SuggestionQualityResponse,
            SuggestionQualityScoreResponse,
        )

        return SuggestionQualityResponse(
            window_days=window_days,
            overall_acceptance_rate=overall_rate,
            low_quality=any(s.below_threshold for s in feature_scores),
            features=[
                SuggestionQualityScoreResponse(
                    feature=s.feature,
                    window_days=s.window_days,
                    sample_count=s.sample_count,
                    acceptance_rate=s.acceptance_rate,
                    below_threshold=s.below_threshold,
                    computed_at=s.computed_at,
                )
                for s in feature_scores
            ],
        )

    async def working_capital_alert(self, tenant_id: uuid.UUID, as_of: date) -> Any:
        return await self.repo.working_capital_alert(tenant_id, as_of)

    async def health_score(self, tenant_id: uuid.UUID, as_of: date) -> Any:
        return await self._cached(
            tenant_id,
            ("health_score", as_of.isoformat()),
            lambda: self.repo.health_score(tenant_id, as_of),
        )

    async def cashflow_projection(self, tenant_id: uuid.UUID, as_of: date) -> Any:
        return await self._cached(
            tenant_id,
            ("cashflow_projection", as_of.isoformat()),
            lambda: self.repo.cashflow_projection(tenant_id, as_of),
        )

    async def run_anomaly_scan(self, tenant_id: uuid.UUID) -> Any:
        detected: list[AiFinanceAnomaly] = []
        dupes = await self.repo.duplicates(tenant_id)
        active_entity_ids: set[uuid.UUID] = set()
        for group in dupes:
            first = group.entries[0]
            anomaly = await self.repo.upsert_ai_anomaly(
                tenant_id,
                AiFinanceAnomaly(
                    tenant_id=tenant_id,
                    entity_type="journal_entry",
                    entity_id=first.entry_id,
                    anomaly_type="duplicate_entry",
                    severity="medium",
                    description=group.reason,
                ),
            )
            detected.append(anomaly)
            active_entity_ids.add(anomaly.entity_id)
        await self.repo.close_stale_anomalies(
            tenant_id,
            anomaly_type="duplicate_entry",
            keep_entity_ids=active_entity_ids,
        )
        for anomaly in detected:
            await self.audit.log(
                tenant_id=tenant_id,
                user_id=None,
                action=FINANCE_ANOMALY_DETECTED,
                target=f"journal_entry:{anomaly.entity_id}",
                details={"anomaly_type": anomaly.anomaly_type},
            )
        return detected

    async def anomalies(self, tenant_id: uuid.UUID) -> Any:
        return await self.repo.list_open_ai_anomalies(tenant_id)

    async def comparative_pnl(
        self,
        tenant_id: uuid.UUID,
        current_from: date,
        current_to: date,
        prior_from: date,
        prior_to: date,
    ) -> Any:
        return await self._cached(
            tenant_id,
            (
                "comparative_pnl",
                current_from.isoformat(),
                current_to.isoformat(),
                prior_from.isoformat(),
                prior_to.isoformat(),
            ),
            lambda: self.repo.comparative_pnl(
                tenant_id, current_from, current_to, prior_from, prior_to
            ),
        )

    async def revenue_concentration(
        self, tenant_id: uuid.UUID, from_date: date, to_date: date
    ) -> Any:
        async def _compute() -> RevenueConcentration:
            report = await self.repo.revenue_concentration(tenant_id, from_date, to_date)
            if self.customers is not None and report.entries:
                names = await self.customers.get_customer_names(
                    [e.customer_id for e in report.entries], tenant_id=tenant_id
                )
                report = RevenueConcentration(
                    from_date=report.from_date,
                    to_date=report.to_date,
                    threshold=report.threshold,
                    total_revenue=report.total_revenue,
                    entries=tuple(
                        RevenueConcentrationEntry(
                            customer_id=e.customer_id,
                            customer_name=names.get(e.customer_id),
                            amount=e.amount,
                            share=e.share,
                            above_threshold=e.above_threshold,
                        )
                        for e in report.entries
                    ),
                )
            return report

        return await self._cached(
            tenant_id,
            ("revenue_concentration", from_date.isoformat(), to_date.isoformat()),
            _compute,
        )

    async def working_capital_series(
        self, tenant_id: uuid.UUID, as_of: date, months: int = 6
    ) -> Any:
        return await self._cached(
            tenant_id,
            ("working_capital_series", as_of.isoformat(), str(months)),
            lambda: self.repo.working_capital_series(tenant_id, as_of, months),
        )

    async def payment_method_analytics(
        self, tenant_id: uuid.UUID, from_date: date, to_date: date
    ) -> Any:
        return await self.repo.payment_method_analytics(tenant_id, from_date, to_date)

    async def customer_payment_analytics(
        self, tenant_id: uuid.UUID, from_date: date, to_date: date
    ) -> Any:
        report = await self.repo.customer_payment_analytics(tenant_id, from_date, to_date)
        if self.customers is not None and report.entries:
            names = await self.customers.get_customer_names(
                [e.customer_id for e in report.entries], tenant_id=tenant_id
            )
            report = CustomerPaymentAnalytics(
                from_date=report.from_date,
                to_date=report.to_date,
                entries=tuple(
                    CustomerPaymentAnalyticsEntry(
                        customer_id=e.customer_id,
                        customer_name=names.get(e.customer_id),
                        payment_count=e.payment_count,
                        total_paid=e.total_paid,
                        avg_days_to_pay=e.avg_days_to_pay,
                        consistency_score=e.consistency_score,
                    )
                    for e in report.entries
                ),
            )
        return report

    async def audit_readiness(self, tenant_id: uuid.UUID) -> Any:
        return await self._cached(
            tenant_id,
            ("audit_readiness",),
            lambda: self.repo.audit_readiness(tenant_id),
        )

    async def reverse_journal_entry(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, entry_id: uuid.UUID
    ) -> Any:
        entry = await self.repo.get_journal_entry(entry_id, tenant_id)
        if entry is None:
            raise NotFoundError(f"Journal entry {entry_id} not found")
        if entry.status.value != "posted":
            raise NotFoundError("Only posted journal entries can be reversed")
        reversed_entry = await self.repo.reverse_journal_entry(
            entry_id,
            tenant_id,
            reversed_by_user_id=user_id,
            reversed_at=datetime.now(UTC),
        )
        if reversed_entry is None:
            raise NotFoundError("Journal entry could not be reversed")
        await self.audit.log(
            tenant_id=tenant_id,
            user_id=user_id,
            action=FINANCE_JOURNAL_ENTRY_REVERSED,
            target=f"journal_entry:{entry_id}",
        )
        return reversed_entry

    async def get_settings(self, tenant_id: uuid.UUID) -> TenantSettingsResponse:
        setting = await self.repo.get_tenant_setting(tenant_id, "working_capital_threshold")
        value = setting.value if setting else "1.5"
        scheme = await self.repo.get_tenant_setting(tenant_id, "invoice_numbering_scheme")
        return TenantSettingsResponse(
            working_capital_threshold=Decimal(value),
            invoice_numbering_scheme=scheme.value if scheme else None,
        )

    async def put_settings(
        self,
        tenant_id: uuid.UUID,
        threshold: Decimal,
        invoice_numbering_scheme: str | None = None,
    ) -> TenantSettingsResponse:
        await self.repo.upsert_tenant_setting(
            tenant_id, "working_capital_threshold", str(threshold)
        )
        if invoice_numbering_scheme is not None:
            await self.repo.upsert_tenant_setting(
                tenant_id, "invoice_numbering_scheme", invoice_numbering_scheme
            )
        return await self.get_settings(tenant_id)

    async def recommend_numbering_scheme(
        self, tenant_id: uuid.UUID, today: date | None = None
    ) -> InvoiceNumberingSchemeResponse:
        """Suggest a sequence width this year's volume won't overflow in ~10 years.

        Deterministic rule keyed off this year's invoice volume (spec C6).
        ``next_invoice_number`` keeps emitting INV-YYYY-##### today -- applying
        the suggested scheme is a separate future step, so this never renumbers
        active invoices.
        """
        if today is None:
            today = date.today()
        since = datetime(today.year, 1, 1, tzinfo=UTC)
        volume = await self.repo.count_invoices_since(tenant_id, since)
        if volume >= 100_000:
            seq_width = 7
        elif volume >= 10_000:
            seq_width = 6
        else:
            seq_width = 5
        scheme = f"{INVOICE_PREFIX}-{today.year}-{'#' * seq_width}"
        rationale = (
            f"{volume:,} invoices this year. A {seq_width}-digit sequence "
            f"leaves room for the next ~10 years at the current volume."
        )
        return InvoiceNumberingSchemeResponse(
            prefix=INVOICE_PREFIX,
            scheme=scheme,
            seq_width=seq_width,
            rationale=rationale,
        )

    async def draft_journal_entry(self, tenant_id: uuid.UUID, description: str) -> DraftEntry:
        accounts = await self.repo.list_accounts(tenant_id)
        if self.ai_draft is not None and accounts:
            try:
                ai = await self.ai_draft(description, accounts)
            except AiServiceUnavailableError:
                ai = None
            if ai is not None:
                await self.audit.log(
                    tenant_id=tenant_id,
                    user_id=None,
                    action=FINANCE_AI_DRAFT_GENERATED,
                    target="finance:draft",
                    details={"description": description, "model_used": ai.model_used},
                )
                return ai
        # Deterministic fallback: suggest debit + contra credit
        suggestion = await self.repo.suggest_account_code(tenant_id, description)
        from decimal import Decimal

        draft = DraftEntry(
            lines=(
                DraftEntryLine(
                    account_code=suggestion.suggested_code,
                    account_name=suggestion.suggested_name,
                    amount=Decimal("0"),
                    side="debit",
                    description=description,
                ),
                DraftEntryLine(
                    account_code=suggestion.contra_code or suggestion.suggested_code,
                    account_name=suggestion.contra_name or "",
                    amount=Decimal("0"),
                    side="credit",
                    description=description,
                ),
            ),
            explanation="",
            confidence=suggestion.confidence,
            reasoning="Deterministic fallback — AI service unavailable",
            fallback=True,
        )
        await self.audit.log(
            tenant_id=tenant_id,
            user_id=None,
            action=FINANCE_AI_DRAFT_GENERATED,
            target="finance:draft",
            details={"description": description},
        )
        return draft

    async def narrate_anomaly(self, tenant_id: uuid.UUID, anomaly_id: uuid.UUID) -> dict[str, str]:
        anomaly = await self.repo.get_ai_anomaly(tenant_id, anomaly_id)
        if anomaly is None:
            raise NotFoundError(f"Anomaly {anomaly_id} not found")
        # Fallback: return a basic narration from the description
        narration = {
            "narration": f"Anomaly detected: {anomaly.anomaly_type} — {anomaly.description}",
            "model_used": "",
        }
        if self.ai_narrate is not None:
            try:
                ai = await self.ai_narrate(
                    anomaly.anomaly_type, anomaly.description, anomaly.severity
                )
            except AiServiceUnavailableError:
                ai = None
            if ai is not None and _narration_cites_figure(ai.narration):
                narration = {"narration": ai.narration, "model_used": ai.model_used}
        await self.audit.log(
            tenant_id=tenant_id,
            user_id=None,
            action=FINANCE_AI_ANOMALY_NARRATED,
            target=f"finance:anomaly:{anomaly_id}",
            details={"anomaly_type": anomaly.anomaly_type, "model_used": narration["model_used"]},
        )
        return narration

    async def generate_reminder(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> ReminderDraft:
        invoice = await self.repo.get_invoice_by_id(tenant_id, invoice_id)
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        from datetime import date as _date

        days_overdue = (_date.today() - invoice.due_date).days if invoice.due_date else 0
        tone = "polite" if days_overdue < 30 else "firm" if days_overdue < 60 else "final"
        reminder = ReminderDraft(
            invoice_number=invoice.invoice_number,
            customer_name=None,
            amount=invoice.total,
            days_overdue=days_overdue,
            tone=tone,
            subject=f"Payment Reminder — Invoice {invoice.invoice_number}",
            body=f"Please remit payment for invoice {invoice.invoice_number} totaling {invoice.total}.",
            model_used="",
        )
        model_used = ""
        if self.ai_remind is not None:
            try:
                ai = await self.ai_remind(
                    None, invoice.invoice_number, invoice.total, days_overdue, tone
                )
            except AiServiceUnavailableError:
                ai = None
            if ai is not None and ai.subject and ai.body:
                reminder = ai
                model_used = ai.model_used
        await send_reminder_email(reminder=reminder)
        await self.audit.log(
            tenant_id=tenant_id,
            user_id=None,
            action=FINANCE_AI_REMINDER_GENERATED,
            target=f"finance:invoice:{invoice_id}",
            details={"invoice": invoice.invoice_number, "tone": tone, "model_used": model_used},
        )
        return reminder

    async def batch_reminders(self, tenant_id: uuid.UUID) -> list[ReminderDraft]:
        invoices = await self.repo.list_invoices_overdue(tenant_id)
        reminders = []
        for inv in invoices:
            from datetime import date as _date

            days_overdue = (_date.today() - inv.due_date).days if inv.due_date else 0
            tone = "polite" if days_overdue < 30 else "firm" if days_overdue < 60 else "final"
            reminder = ReminderDraft(
                invoice_number=inv.invoice_number,
                customer_name=None,
                amount=inv.total,
                days_overdue=days_overdue,
                tone=tone,
                subject=f"Payment Reminder — Invoice {inv.invoice_number}",
                body=f"Please remit payment for invoice {inv.invoice_number} totaling {inv.total}.",
                model_used="",
            )
            model_used = ""
            if self.ai_remind is not None:
                try:
                    ai = await self.ai_remind(
                        None, inv.invoice_number, inv.total, days_overdue, tone
                    )
                except AiServiceUnavailableError:
                    ai = None
                if ai is not None and ai.subject and ai.body:
                    reminder = ai
                    model_used = ai.model_used
            if model_used:
                await self.audit.log(
                    tenant_id=tenant_id,
                    user_id=None,
                    action=FINANCE_AI_REMINDER_GENERATED,
                    target=f"finance:invoice:{inv.id}",
                    details={"invoice": inv.invoice_number, "tone": tone, "model_used": model_used},
                )
            reminders.append(reminder)
        for reminder in reminders:
            await send_reminder_email(reminder=reminder)
        return reminders


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/aging", response_model=ResponseEnvelope[ArAgingResponse])
async def get_aging(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[ArAgingResponse]:
    aging = await svc.repo.ar_aging(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=ArAgingResponse.model_validate(aging))


@router.get("/close-checklist", response_model=ResponseEnvelope[CloseChecklistResponse])
async def get_close_checklist(
    period_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[CloseChecklistResponse]:
    checklist = await svc.close_checklist(_tenant_id(current_user), period_id)
    return ResponseEnvelope(data=CloseChecklistResponse.model_validate(checklist))


@router.get(
    "/duplicates",
    response_model=ResponseEnvelope[list[DuplicateGroupResponse]],
)
async def get_duplicates(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[list[DuplicateGroupResponse]]:
    groups = await svc.duplicates(_tenant_id(current_user))
    return ResponseEnvelope(data=[DuplicateGroupResponse.model_validate(g) for g in groups])


@router.post(
    "/suggest-account-code",
    response_model=ResponseEnvelope[AccountCodeSuggestionResponse],
)
async def suggest_account_code(
    body: SuggestAccountCodeRequest,
    current_user: dict[str, Any] = Depends(require_finance_ai_write),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[AccountCodeSuggestionResponse]:
    suggestion = await svc.suggest_account_code(_tenant_id(current_user), body.description)
    return ResponseEnvelope(data=AccountCodeSuggestionResponse.model_validate(suggestion))


@router.get(
    "/working-capital-alert",
    response_model=ResponseEnvelope[WorkingCapitalAlertResponse],
)
async def get_working_capital_alert(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[WorkingCapitalAlertResponse]:
    alert = await svc.working_capital_alert(_tenant_id(current_user), as_of)
    await emit_working_capital_notification(
        db,
        tenant_id=_tenant_id(current_user),
        alert=alert,
        as_of=as_of,
    )
    return ResponseEnvelope(data=WorkingCapitalAlertResponse.model_validate(alert))


@router.get("/health-score", response_model=ResponseEnvelope[HealthScoreResponse])
async def get_health_score(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[HealthScoreResponse]:
    score = await svc.health_score(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=HealthScoreResponse.model_validate(score))


@router.get(
    "/cashflow-projection",
    response_model=ResponseEnvelope[CashflowProjectionResponse],
)
async def get_cashflow_projection(
    as_of: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[CashflowProjectionResponse]:
    projection = await svc.cashflow_projection(_tenant_id(current_user), as_of)
    return ResponseEnvelope(data=CashflowProjectionResponse.model_validate(projection))


@router.post("/anomalies/scan", response_model=ResponseEnvelope[list[AnomalyResponse]])
async def scan_anomalies(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[list[AnomalyResponse]]:
    anomalies = await svc.run_anomaly_scan(_tenant_id(current_user))
    return ResponseEnvelope(data=[AnomalyResponse.model_validate(a) for a in anomalies])


@router.get("/anomalies", response_model=ResponseEnvelope[list[AnomalyResponse]])
async def list_anomalies(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[list[AnomalyResponse]]:
    anomalies = await svc.anomalies(_tenant_id(current_user))
    return ResponseEnvelope(data=[AnomalyResponse.model_validate(a) for a in anomalies])


@router.get("/reports/comparative-pnl", response_model=ResponseEnvelope[ComparativePnlResponse])
async def get_comparative_pnl(
    current_from: date,
    current_to: date,
    prior_from: date,
    prior_to: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[ComparativePnlResponse]:
    pnl = await svc.comparative_pnl(
        _tenant_id(current_user), current_from, current_to, prior_from, prior_to
    )
    return ResponseEnvelope(data=ComparativePnlResponse.model_validate(pnl))


@router.get(
    "/revenue-concentration",
    response_model=ResponseEnvelope[RevenueConcentrationResponse],
)
async def get_revenue_concentration(
    from_date: date,
    to_date: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[RevenueConcentrationResponse]:
    report = await svc.revenue_concentration(_tenant_id(current_user), from_date, to_date)
    return ResponseEnvelope(data=RevenueConcentrationResponse.model_validate(report))


@router.get(
    "/working-capital-series",
    response_model=ResponseEnvelope[WorkingCapitalSeriesResponse],
)
async def get_working_capital_series(
    as_of: date,
    months: int = Query(default=6, ge=1, le=24),
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[WorkingCapitalSeriesResponse]:
    series = await svc.working_capital_series(_tenant_id(current_user), as_of, months)
    return ResponseEnvelope(data=WorkingCapitalSeriesResponse.model_validate(series))


@router.get(
    "/payment-methods",
    response_model=ResponseEnvelope[PaymentMethodAnalyticsResponse],
)
async def get_payment_method_analytics(
    from_date: date,
    to_date: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[PaymentMethodAnalyticsResponse]:
    analytics = await svc.payment_method_analytics(_tenant_id(current_user), from_date, to_date)
    return ResponseEnvelope(data=PaymentMethodAnalyticsResponse.model_validate(analytics))


@router.get(
    "/customer-analytics",
    response_model=ResponseEnvelope[CustomerPaymentAnalyticsResponse],
)
async def get_customer_payment_analytics(
    from_date: date,
    to_date: date,
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[CustomerPaymentAnalyticsResponse]:
    analytics = await svc.customer_payment_analytics(_tenant_id(current_user), from_date, to_date)
    return ResponseEnvelope(data=CustomerPaymentAnalyticsResponse.model_validate(analytics))


@router.get("/audit-readiness", response_model=ResponseEnvelope[AuditReadinessResponse])
async def get_audit_readiness(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[AuditReadinessResponse]:
    readiness = await svc.audit_readiness(_tenant_id(current_user))
    return ResponseEnvelope(data=AuditReadinessResponse.model_validate(readiness))


@router.get("/audit/search", response_model=ResponseEnvelope[AuditLogSearchResponse])
async def search_audit_log(
    q: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(require_finance_read),
    audit_svc: Any = Depends(get_core_audit_service),
) -> ResponseEnvelope[AuditLogSearchResponse]:
    entries, total = await audit_svc.search(
        _tenant_id(current_user),
        action=action,
        actor_user_id=actor_user_id,
        q=q,
        from_date=from_date,
        to_date=to_date,
        offset=offset,
        limit=limit,
    )
    return ResponseEnvelope(
        data=AuditLogSearchResponse(
            entries=[AuditLogEntryResponse.model_validate(e) for e in entries],
            total=total,
            offset=offset,
            limit=limit,
        )
    )


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=ResponseEnvelope[JournalEntryResponse],
)
async def reverse_journal_entry(
    entry_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_approve),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[JournalEntryResponse]:
    entry = await svc.reverse_journal_entry(
        _tenant_id(current_user), _user_id(current_user), entry_id
    )
    await commit_writes(db)
    return ResponseEnvelope(data=JournalEntryResponse.model_validate(entry))


@router.get("/settings", response_model=ResponseEnvelope[TenantSettingsResponse])
async def get_settings(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[TenantSettingsResponse]:
    return ResponseEnvelope(data=await svc.get_settings(_tenant_id(current_user)))


@router.put("/settings", response_model=ResponseEnvelope[TenantSettingsResponse])
async def put_settings(
    body: WorkingCapitalSettingsRequest,
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[TenantSettingsResponse]:
    settings = await svc.put_settings(
        _tenant_id(current_user),
        body.threshold,
        invoice_numbering_scheme=body.invoice_numbering_scheme,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=settings)


@router.get(
    "/invoice-numbering-scheme",
    response_model=ResponseEnvelope[InvoiceNumberingSchemeResponse],
)
async def invoice_numbering_scheme(
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[InvoiceNumberingSchemeResponse]:
    suggestion = await svc.recommend_numbering_scheme(_tenant_id(current_user))
    return ResponseEnvelope(data=suggestion)


@router.post(
    "/suggest-invoice-lines",
    response_model=ResponseEnvelope[list[InvoiceLineSuggestionResponse]],
)
async def suggest_invoice_lines(
    body: SuggestInvoiceLinesRequest,
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[list[InvoiceLineSuggestionResponse]]:
    suggestions = await svc.suggest_invoice_lines(_tenant_id(current_user), body.description)
    return ResponseEnvelope(
        data=[InvoiceLineSuggestionResponse.model_validate(item) for item in suggestions]
    )


# ---------------------------------------------------------------------------
# AI Draft / Narrate / Remind endpoints (FIN-AI-001)
# ---------------------------------------------------------------------------


@router.post("/draft-entry", response_model=ResponseEnvelope[DraftEntryResponse])
async def draft_journal_entry(
    body: SuggestAccountCodeRequest,
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[DraftEntryResponse]:
    draft = await svc.draft_journal_entry(_tenant_id(current_user), body.description)
    return ResponseEnvelope(
        data=DraftEntryResponse(
            lines=[
                DraftEntryLineResponse(
                    account_code=line.account_code,
                    account_name=line.account_name,
                    amount=line.amount,
                    side=line.side,
                    description=line.description,
                )
                for line in draft.lines
            ],
            explanation=draft.explanation,
            confidence=draft.confidence,
            reasoning=draft.reasoning,
            model_used=draft.model_used,
            fallback=draft.fallback,
        )
    )


@router.post(
    "/anomalies/{anomaly_id}/narrate",
    response_model=ResponseEnvelope[AnomalyNarrationResponse],
)
async def narrate_anomaly(
    anomaly_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[AnomalyNarrationResponse]:
    narration = await svc.narrate_anomaly(_tenant_id(current_user), anomaly_id)
    return ResponseEnvelope(
        data=AnomalyNarrationResponse(
            narration=narration["narration"],
            model_used=narration.get("model_used", ""),
        )
    )


@router.post(
    "/reminders/generate",
    response_model=ResponseEnvelope[ReminderDraftLineResponse],
)
async def generate_reminder(
    body: ReminderGenerateRequest,
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[ReminderDraftLineResponse]:
    reminder = await svc.generate_reminder(_tenant_id(current_user), body.invoice_id)
    return ResponseEnvelope(data=ReminderDraftLineResponse.model_validate(reminder))


@router.post(
    "/reminders/batch",
    response_model=ResponseEnvelope[ReminderDraftResponse],
)
async def batch_reminders(
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service_with_ai),
) -> ResponseEnvelope[ReminderDraftResponse]:
    reminders = await svc.batch_reminders(_tenant_id(current_user))
    return ResponseEnvelope(
        data=ReminderDraftResponse(
            reminders=[
                ReminderDraftLineResponse(
                    invoice_number=r.invoice_number,
                    customer_name=r.customer_name,
                    amount=r.amount,
                    days_overdue=r.days_overdue,
                    tone=r.tone,
                    subject=r.subject,
                    body=r.body,
                )
                for r in reminders
            ]
        )
    )


@router.post(
    "/suggestions/{suggestion_id}/accept",
    response_model=ResponseEnvelope[AccountCodeSuggestionResponse],
)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_ai_write),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AccountCodeSuggestionResponse]:
    suggestion = await svc.accept_suggestion(_tenant_id(current_user), suggestion_id)
    await commit_writes(db)
    return ResponseEnvelope(
        data=AccountCodeSuggestionResponse(
            description=suggestion.description,
            suggested_code=suggestion.suggested_code,
            suggested_name=suggestion.suggested_name,
            confidence=suggestion.confidence,
            id=suggestion.id,
            status=suggestion.status,
            feature=suggestion.feature,
        )
    )


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=ResponseEnvelope[AccountCodeSuggestionResponse],
)
async def dismiss_suggestion(
    suggestion_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(require_finance_ai_write),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AccountCodeSuggestionResponse]:
    suggestion = await svc.dismiss_suggestion(_tenant_id(current_user), suggestion_id)
    await commit_writes(db)
    return ResponseEnvelope(
        data=AccountCodeSuggestionResponse(
            description=suggestion.description,
            suggested_code=suggestion.suggested_code,
            suggested_name=suggestion.suggested_name,
            confidence=suggestion.confidence,
            id=suggestion.id,
            status=suggestion.status,
            feature=suggestion.feature,
        )
    )


@router.get(
    "/suggestions/quality",
    response_model=ResponseEnvelope[SuggestionQualityResponse],
)
async def suggestion_quality(
    window_days: int = Query(default=30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(require_finance_ai_read),
    svc: FinanceAutomationService = Depends(get_finance_automation_service),
) -> ResponseEnvelope[SuggestionQualityResponse]:
    result = await svc.suggestion_quality(_tenant_id(current_user), window_days)
    return ResponseEnvelope(data=result)


# ---------------------------------------------------------------------------
# B23: Vendor-invoice-number extraction (SKY-84)
# ---------------------------------------------------------------------------

_VENDOR_INV_RE = re.compile(
    r"(?:"
    r"(?:invoice|inv)[\s#:\-]*([A-Z0-9][A-Z0-9\-]{2,30})"
    r"|"
    r"(?:reference|ref|po)[\s#:\-]*([A-Z0-9][A-Z0-9\-]{2,30})"
    r")",
    re.IGNORECASE,
)


def extract_vendor_ref(reference: str) -> str | None:
    """Best-effort extraction of a vendor invoice number from free text."""
    match = _VENDOR_INV_RE.search(reference)
    if match is None:
        return None
    token = (match.group(1) or match.group(2)).strip()
    token = re.sub(r"^(?:invoice|inv)\b[\-_:]?\s*", "", token, flags=re.IGNORECASE)
    return token or None


@router.post(
    "/extract-vendor-ref",
    response_model=ResponseEnvelope[VendorRefExtractionResponse],
)
async def extract_vendor_invoice_ref(
    body: VendorRefExtractionRequest,
    current_user: dict[str, Any] = Depends(require_finance_read),
) -> ResponseEnvelope[VendorRefExtractionResponse]:
    _ = current_user  # pure function, no tenant context needed
    return ResponseEnvelope(
        data=VendorRefExtractionResponse(extracted=extract_vendor_ref(body.reference))
    )
