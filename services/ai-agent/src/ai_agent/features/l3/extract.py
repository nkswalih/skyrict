"""Signal extraction - collapse L3 core reads into a compact payload with token figures.

Figures are referenced by tokens like ``{{OVERTIME_DELTA}}`` in the prompt and
LLM output, then substituted at render time from the verified source data.
"""

from __future__ import annotations

import json

_DELTA_KEYS = (
    "headcount_delta",
    "gross_delta",
    "net_delta",
    "overtime_delta",
    "current_gross",
    "current_net",
    "current_overtime",
    "current_headcount",
    "previous_headcount",
)

_MATERIAL_DELTA_KEYS = _DELTA_KEYS[:4]


def build_payroll_cost_signals(raw: dict) -> dict:
    """Transform the core payroll-cost response into a gold-signal dict.

    ``raw`` is the core ``PayrollCostMovementOut`` data (flat fields, money as
    strings). Figure tokens are built only from fields that exist on the wire;
    values are the verified source strings, substituted at render time.
    """
    figures = {
        f"{{{{{key}}}}}": str(raw.get(key, "0"))
        for key in _DELTA_KEYS
        if key in raw
    }
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


def build_prompt(kind: str, signals: dict) -> str:
    """Build a user prompt that tells the LLM to narrate using token references."""
    return (
        f"You are writing an executive narrative for L3 HR/Payroll metric: {kind}.\n"
        "Use the provided data to write a concise, specific narrative. "
        "Reference ALL figures via their {{TOKEN}} placeholders exactly as provided. "
        "NEVER type actual numbers or currency values - use ONLY the token placeholders.\n\n"
        f"Data:\n{json.dumps(signals, indent=2)}"
    )


def has_material_activity(kind: str, signals: dict) -> bool:
    """For payroll_cost: true when any movement delta is non-zero."""
    if kind == "payroll_cost":
        return bool(signals.get("has_material_activity"))
    return True
