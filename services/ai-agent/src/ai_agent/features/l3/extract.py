"""Signal extraction - collapse L3 core reads into a compact payload with token figures.

Figures are referenced by tokens like ``{{OVERTIME_DELTA}}`` in the prompt and
LLM output, then substituted at render time from the verified source data.
"""

from __future__ import annotations

import json
from decimal import Decimal
from statistics import StatisticsError
from statistics import correlation as pearson
from typing import Any

_DELTA_KEYS = (
    "headcount_delta",
    "gross_delta",
    "net_delta",
    "overtime_delta",
    "benefit_delta",
    "current_gross",
    "current_net",
    "current_overtime",
    "current_benefit_adjustments",
    "previous_benefit_adjustments",
    "current_headcount",
    "previous_headcount",
)

_MATERIAL_DELTA_KEYS = _DELTA_KEYS[:4]

# A leave-pay correlation is only meaningful over a full year of payroll history.
_CORRELATION_MIN_MONTHS = 12


def build_payroll_cost_signals(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform the core payroll-cost response into a gold-signal dict.

    ``raw`` is the core ``PayrollCostMovementOut`` data (flat fields, money as
    strings). Figure tokens are built only from fields that exist on the wire;
    values are the verified source strings, substituted at render time.
    """
    figures = {f"{{{{{key}}}}}": str(raw.get(key, "0")) for key in _DELTA_KEYS if key in raw}
    return {
        "period": {
            "current_period_start": str(raw.get("current_period_start", "")),
            "current_period_end": str(raw.get("current_period_end", "")),
            "current_run_code": str(raw.get("current_run_code", "")),
        },
        "figures": figures,
        "departments": raw.get("department_breakdown", []),
        "has_material_activity": any(
            str(figures.get(f"{{{{{key}}}}}", 0)) not in ("0", "0.00", "")
            for key in _MATERIAL_DELTA_KEYS
            if f"{{{{{key}}}}}" in figures
        ),
    }


def build_prompt(kind: str, signals: dict[str, Any]) -> str:
    """Build a user prompt that tells the LLM to narrate using token references."""
    return (
        f"You are writing an executive narrative for L3 HR/Payroll metric: {kind}.\n"
        "Use the provided data to write a concise, specific narrative. "
        "Reference ALL figures via their {{TOKEN}} placeholders exactly as provided. "
        "NEVER type actual numbers or currency values - use ONLY the token placeholders.\n\n"
        f"Data:\n{json.dumps(signals, indent=2)}"
    )


def build_leave_pay_signals(raw: dict[str, Any]) -> dict[str, Any]:
    """Collapse the core leave-pay series into a gold-signal dict.

    ``raw`` is the core ``LeavePayCorrelationOut`` shape: ``{"pairs": [...]}``
    newest-first with ``leave_days`` (int) and ``overtime`` (money string) per
    completed run. Pearson's r is computed on the verified pairs via the stdlib;
    the figure tokens are the verified r, sample size, and peak/highest months.
    """
    rows = [p for p in (raw.get("pairs") or []) if isinstance(p, dict)]
    if len(rows) < _CORRELATION_MIN_MONTHS:
        return {"pairs": rows, "figures": {}, "has_material_activity": False}

    leave = [int(p.get("leave_days", 0) or 0) for p in rows]
    overtime = [Decimal(str(p.get("overtime", "0"))) for p in rows]
    try:
        r = pearson(leave, [float(v) for v in overtime])
    except StatisticsError:
        # Zero variance in either series leaves r undefined - not a usable signal.
        return {"pairs": rows, "figures": {}, "has_material_activity": False}

    highest = max(rows, key=lambda p: int(p.get("leave_days", 0) or 0))
    peak = max(rows, key=lambda p: Decimal(str(p.get("overtime", "0"))))
    figures = {
        "{{correlation}}": f"{r:.2f}",
        "{{sample_size}}": str(len(rows)),
        "{{highest_leave_month}}": str(highest.get("run_code", "")),
        "{{highest_leave_days}}": str(highest.get("leave_days", "")),
        "{{peak_overtime_month}}": str(peak.get("run_code", "")),
        "{{peak_overtime}}": str(peak.get("overtime", "0")),
    }
    return {
        "pairs": rows,
        "correlation": f"{r:.2f}",
        "figures": figures,
        "has_material_activity": True,
    }


def build_compliance_digest_signals(raw: dict[str, Any]) -> dict[str, Any]:
    """Collapse the core compliance-org response into a gold-signal dict.

    ``raw`` is the core ``ComplianceOrgOut`` shape: aggregate counts by
    check type / severity with an ``open_findings`` count and narrative.
    Figure tokens are the verified counts; materiality requires at least
    one open finding.
    """
    by_type = raw.get("by_type") or {}
    by_severity = raw.get("by_severity") or {}
    open_findings = int(raw.get("open_findings") or 0)
    ranked = raw.get("risk_ranked") or []
    figures = {
        "{{total_findings}}": str(raw.get("total_findings", 0)),
        "{{open_findings}}": str(open_findings),
        "{{document_expiry_count}}": str(by_type.get("document_expiry", 0)),
        "{{training_overdue_count}}": str(by_type.get("training_overdue", 0)),
        "{{contract_missing_field_count}}": str(by_type.get("contract_missing_field", 0)),
        "{{critical_count}}": str(by_severity.get("critical", 0)),
        "{{high_count}}": str(by_severity.get("high", 0)),
    }
    for rank, group in enumerate(ranked[:3], start=1):
        figures[f"{{{{rank_{rank}_type}}}}"] = str(group.get("check_type", ""))
        figures[f"{{{{rank_{rank}_score}}}}"] = str(group.get("weighted_open_score", 0))
        figures[f"{{{{rank_{rank}_open_count}}}}"] = str(group.get("open_count", 0))
    return {
        "summary": raw.get("narrative", ""),
        "by_type": by_type,
        "by_severity": by_severity,
        "risk_ranked": ranked[:3],
        "figures": figures,
        "has_material_activity": open_findings > 0,
    }


def has_material_activity(kind: str, signals: dict[str, Any]) -> bool:
    """Kind-specific gate: payroll-cost and compliance need non-zero deltas;
    leave-pay needs 12+ completed months with a definable correlation."""
    if kind in ("payroll_cost", "leave_pay_correlation", "compliance_digest"):
        return bool(signals.get("has_material_activity"))
    return True
