"""Audit event catalog consistency tests (Appendix B of the spec).

Guards the canonical vocabulary: exact string values, no duplicates, and
ALL_AI_AUDIT_EVENTS covering exactly the documented constants. The set is
Appendix B PLUS ai.anomaly.escalated (workflow §4.4 defines escalation;
the appendix omits its event - see the constant's docstring).
"""

from __future__ import annotations

from ai_agent.core import audit_events
from ai_agent.core.audit_events import (
    AI_AGENT_INTERRUPT_APPROVED,
    AI_AGENT_INTERRUPT_DENIED,
    AI_AGENT_INTERRUPT_EXPIRED,
    AI_ANOMALY_DETECTED,
    AI_ANOMALY_DISMISSED,
    AI_ANOMALY_ESCALATED,
    AI_ANOMALY_RESOLVED,
    AI_DEAL_HEALTH_ASSESSED,
    AI_FOLLOW_UP_APPLIED,
    AI_FOLLOW_UP_DISMISSED,
    AI_FOLLOW_UP_GENERATED,
    AI_HR_COPILOT_EXCHANGE,
    AI_LEAD_SCORED,
    AI_L3_COMPLIANCE_DIGESTED,
    AI_L3_LEAVE_PAY_CORRELATED,
    AI_L3_PAYROLL_COST_GENERATED,
    AI_NARRATOR_GENERATED,
    AI_NARRATOR_REFRESHED,
    AI_QUERY_EXECUTED,
    AI_REPORT_GENERATED,
    AI_REPORT_SAVED,
    AI_SUGGESTION_APPROVED,
    AI_SUGGESTION_CREATED,
    AI_SUGGESTION_REJECTED,
    ALL_AI_AUDIT_EVENTS,
)


class TestAppendixBVocabulary:
    def test_exact_constant_values(self) -> None:
        # docs/modules/skyrict-ai/inventory-ai-features.md, Appendix B.
        assert AI_QUERY_EXECUTED == "ai.query.executed"
        assert AI_SUGGESTION_CREATED == "ai.suggestion.created"
        assert AI_SUGGESTION_APPROVED == "ai.suggestion.approved"
        assert AI_SUGGESTION_REJECTED == "ai.suggestion.rejected"
        assert AI_ANOMALY_DETECTED == "ai.anomaly.detected"
        assert AI_ANOMALY_RESOLVED == "ai.anomaly.resolved"
        assert AI_ANOMALY_DISMISSED == "ai.anomaly.dismissed"
        # Documented spec-gap addition (see module docstring).
        assert AI_ANOMALY_ESCALATED == "ai.anomaly.escalated"
        # HR-AI-001 feature 5 (spec §9).
        assert AI_HR_COPILOT_EXCHANGE == "ai.hr.copilot.exchange"
        # SKY-63 cross-module narrator events.
        assert AI_NARRATOR_GENERATED == "ai.narrator.generated"
        assert AI_NARRATOR_REFRESHED == "ai.narrator.refreshed"
        # SKY-59 agent HITL ledger events.
        assert AI_AGENT_INTERRUPT_APPROVED == "ai.agent.interrupt.approved"
        assert AI_AGENT_INTERRUPT_DENIED == "ai.agent.interrupt.denied"
        assert AI_AGENT_INTERRUPT_EXPIRED == "ai.agent.interrupt.expired"
        # SKY-61 CRM AI events.
        assert AI_LEAD_SCORED == "ai.crm.lead.scored"
        assert AI_DEAL_HEALTH_ASSESSED == "ai.crm.deal.health"
        assert AI_FOLLOW_UP_GENERATED == "ai.crm.follow_up.generated"
        assert AI_FOLLOW_UP_APPLIED == "ai.crm.follow_up.applied"
        assert AI_FOLLOW_UP_DISMISSED == "ai.crm.follow_up.dismissed"
        # SKY-80 NL report builder events.
        assert AI_REPORT_GENERATED == "ai.report.generated"
        assert AI_REPORT_SAVED == "ai.report.saved"
        # HR-AI-003 L3 HR/Payroll narrative events.
        assert AI_L3_PAYROLL_COST_GENERATED == "ai.l3.payroll_cost.generated"
        assert AI_L3_LEAVE_PAY_CORRELATED == "ai.l3.leave_pay.correlated"
        assert AI_L3_COMPLIANCE_DIGESTED == "ai.l3.compliance.digested"

    def test_all_events_covers_exactly_the_documented_constants(self) -> None:
        expected = {
            audit_events.AI_QUERY_EXECUTED,
            audit_events.AI_SUGGESTION_CREATED,
            audit_events.AI_SUGGESTION_APPROVED,
            audit_events.AI_SUGGESTION_REJECTED,
            audit_events.AI_ANOMALY_DETECTED,
            audit_events.AI_ANOMALY_RESOLVED,
            audit_events.AI_ANOMALY_DISMISSED,
            audit_events.AI_ANOMALY_ESCALATED,
            audit_events.AI_HR_COPILOT_EXCHANGE,
            audit_events.AI_NARRATOR_GENERATED,
            audit_events.AI_NARRATOR_REFRESHED,
            audit_events.AI_AGENT_INTERRUPT_APPROVED,
            audit_events.AI_AGENT_INTERRUPT_DENIED,
            audit_events.AI_AGENT_INTERRUPT_EXPIRED,
            audit_events.AI_LEAD_SCORED,
            audit_events.AI_DEAL_HEALTH_ASSESSED,
            audit_events.AI_FOLLOW_UP_GENERATED,
            audit_events.AI_FOLLOW_UP_APPLIED,
            audit_events.AI_FOLLOW_UP_DISMISSED,
            audit_events.AI_L3_PAYROLL_COST_GENERATED,
            audit_events.AI_L3_LEAVE_PAY_CORRELATED,
            audit_events.AI_L3_COMPLIANCE_DIGESTED,
            audit_events.AI_REPORT_GENERATED,
            audit_events.AI_REPORT_SAVED,
        }
        assert set(ALL_AI_AUDIT_EVENTS) == expected

    def test_vocabulary_is_ai_namespaced_and_lowercase(self) -> None:
        for event in ALL_AI_AUDIT_EVENTS:
            assert event.startswith("ai."), event
            assert event == event.lower(), event
