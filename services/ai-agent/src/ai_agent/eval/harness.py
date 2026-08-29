"""Deterministic eval harness for the deployed HR models (HR-AI-002, SKY-72).

Runs each labeled seed set from ``tests/eval/hr_models.yaml`` through the SAME
scorers the runtime uses and computes per-metric precision. Two model kinds are
registered:

- ``attrition`` (metrics ``attrition_precision``): the bundled GBC model via
  :func:`ai_agent.features.attrition.scorer.score_employee`, abstention rule
  included.
- ``anomaly`` (metric ``anomaly_precision``): the **literal shared leave-rule
  engine** :func:`skyrict_common.ai_hr_rules.detect_leave_pattern_anomalies`
  that core's ``ai_hr_leave_anomalies`` inbox runs, so the eval grades the
  deployed detection code (pattern-fires = true positives, near-miss guards =
  false-positive checks).

The result rows are what the ``eval-hr-models`` CLI posts to core's
``/api/v1/ai/hr/eval-runs`` endpoint.

Design notes:

- Non-LLM and deterministic (bundled fixed-seed model + stable seed sets), so
  a run is reproducible and the recorded numbers are comparable across weeks.
- Precision below the documented 0.70 threshold WARNS (exit code 0) instead of
  failing: an eval regression is an operator alert, not a hard deploy gate.
- Anomaly seed rows carry dates + magnitudes only — never employee PII.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import yaml

from ai_agent.features.attrition.features import EmployeeFeatures
from ai_agent.features.attrition.model import LoadedModel, load_model
from ai_agent.features.attrition.scorer import ScoredEmployee, score_employee
from skyrict_common.ai_hr_rules import (
    Holiday,
    RequestSignal,
    detect_leave_pattern_anomalies,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

DEFAULT_THRESHOLD = 0.70

# A score is "flagged attrition-prone" when its band is medium or high; LOW
# means the model does not call the employee at-risk. Precision counts a
# flagged (medium/high) result against its labeled seed.
_POSITIVE_BANDS = ("medium", "high")

# The anomaly model is the shared rules engine itself.
ANOMALY_MODEL_NAME = "anomaly"
ANOMALY_METRIC = "anomaly_precision"
ANOMALY_VERSION = "rules-v2-2026-08"
ANOMALY_SOURCE = "skyrict_common.ai_hr_rules"
_ANOMALY_NS = uuid.NAMESPACE_URL


@dataclass(frozen=True, slots=True)
class EvalMetric:
    """One measured precision value for one metric of one model."""

    model_name: str
    model_version: str
    model_source: str
    metric: str
    precision: float
    considered: int
    abstained: int
    threshold: float
    met_threshold: bool
    details: dict[str, Any]


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load the YAML model registry (top-level ``models`` list required)."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError(f"invalid eval registry {path}: expected a top-level 'models' list")
    return data


def run_registry(
    path: str | Path,
    *,
    model_path: str | None = None,
    threshold_override: float | None = None,
) -> list[EvalMetric]:
    """Evaluate every registered model/metric and return the metric rows."""
    registry = load_registry(path)
    default = (
        threshold_override
        if threshold_override is not None
        else float(registry.get("threshold", DEFAULT_THRESHOLD))
    )
    results: list[EvalMetric] = []
    for spec in registry["models"]:
        name = str(spec["name"])
        for metric in spec.get("metrics", []):
            threshold = (
                float(metric.get("threshold", default) or default)
                if threshold_override is None
                else threshold_override
            )
            results.append(
                evaluate_metric(
                    model_name=name,
                    metric=str(metric["metric"]),
                    cases=metric["cases"],
                    threshold=threshold,
                    model_path=model_path,
                    model_version=spec.get("version"),
                )
            )
    return results


def evaluate_metric(
    *,
    model_name: str,
    metric: str,
    cases: Sequence[dict[str, Any]],
    threshold: float,
    model_path: str | None,
    model_version: str | None = None,
) -> EvalMetric:
    """Run the seed cases against the registered evaluator and compute precision."""
    if model_name == "attrition":
        return _evaluate_attrition_metric(
            metric=metric, cases=cases, threshold=threshold, model_path=model_path
        )
    if model_name == ANOMALY_MODEL_NAME:
        return _evaluate_anomaly_metric(cases=cases, threshold=threshold, version=model_version)
    raise ValueError(f"no evaluator registered for model {model_name!r}")


def _evaluate_attrition_metric(
    *,
    metric: str,
    cases: Sequence[dict[str, Any]],
    threshold: float,
    model_path: str | None,
) -> EvalMetric:
    """Grade the labeled seed set against the bundled attrition model."""
    model = load_model(model_path)
    predicted_positive = 0
    confirmed = 0
    abstained = 0
    band_counts: dict[str, int] = {}
    for index, case in enumerate(cases):
        scored = _score_case(metric, case, index, model)
        if scored is None:
            abstained += 1
            continue
        band_counts[scored.risk_band] = band_counts.get(scored.risk_band, 0) + 1
        if scored.risk_band in _POSITIVE_BANDS:
            predicted_positive += 1
            if _as_int(case.get("label")) == 1:
                confirmed += 1
    considered = len(cases)
    precision = round(confirmed / predicted_positive, 4) if predicted_positive else 0.0
    return EvalMetric(
        model_name="attrition",
        model_version=model.version,
        model_source=model.source,
        metric=metric,
        precision=precision,
        considered=considered,
        abstained=abstained,
        threshold=threshold,
        met_threshold=precision >= threshold,
        details={
            "confirmed": confirmed,
            "predicted_positive": predicted_positive,
            "band_counts": band_counts,
            "no_positive_predictions": predicted_positive == 0,
        },
    )


def _evaluate_anomaly_metric(
    *,
    cases: Sequence[dict[str, Any]],
    threshold: float,
    version: str | None,
) -> EvalMetric:
    """Run engineered teams through the SHARED rules engine and grade them.

    A prediction is one ``(employee, anomaly_type)`` finding; a label is one
    expected finding from the case. Each case is a recall PRESENCE probe (the
    two new patterns must fire) or a near-miss guard (the pattern must NOT fire
    just outside its window/threshold). Precision is TP/(TP+FP) across all
    cases; recall TP/(TP+FN) is recorded in ``details``.
    """
    true_positive = 0
    false_positive = 0
    false_negative = 0
    case_details: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        predicted, labeled = _run_anomaly_case(case, index)
        true_positive += len(predicted & labeled)
        false_positive += len(predicted - labeled)
        false_negative += len(labeled - predicted)
        case_details.append(
            {
                "case_index": index,
                "predicted": sorted(f"{e}:{t}" for e, t in predicted),
                "labeled": sorted(f"{e}:{t}" for e, t in labeled),
            }
        )
    denom = true_positive + false_positive
    precision = round(true_positive / denom, 4) if denom else 0.0
    recall_denom = true_positive + false_negative
    recall = round(true_positive / recall_denom, 4) if recall_denom else 0.0
    return EvalMetric(
        model_name=ANOMALY_MODEL_NAME,
        model_version=version or ANOMALY_VERSION,
        model_source=ANOMALY_SOURCE,
        metric=ANOMALY_METRIC,
        precision=precision,
        considered=len(cases),
        abstained=0,
        threshold=threshold,
        met_threshold=precision >= threshold,
        details={
            "recall": recall,
            "true_positives": true_positive,
            "false_positives": false_positive,
            "false_negatives": false_negative,
            "cases": case_details,
        },
    )


def _anomaly_uid(label: str) -> uuid.UUID:
    """Deterministic identity for fixture employees/requests (`m1`, `c0-r1`, ...)."""
    return uuid.uuid5(_ANOMALY_NS, f"skyrict-eval-anomaly::{label}")


def _run_anomaly_case(
    case: dict[str, Any], index: int
) -> tuple[set[tuple[uuid.UUID, str]], set[tuple[uuid.UUID, str]]]:
    """Run one labeled case through ``detect_leave_pattern_anomalies``."""
    today = date.fromisoformat(str(case["today"]))
    team_size = int(case.get("team_size", 5))
    members: dict[uuid.UUID | None, list[uuid.UUID]] = {
        None: [_anomaly_uid(f"m{i}") for i in range(1, team_size + 1)]
    }
    requests: dict[uuid.UUID, list[RequestSignal]] = {}
    for i, raw in enumerate(case.get("requests", ())):
        employee = _anomaly_uid(str(raw["employee"]))
        requests.setdefault(employee, []).append(
            RequestSignal(
                request_id=_anomaly_uid(f"c{index}-r{i}"),
                employee_id=employee,
                start_date=date.fromisoformat(str(raw["start"])),
                end_date=date.fromisoformat(str(raw["end"])),
                days=int(raw["days"]),
                leave_type=str(raw.get("type", "annual")),
                filed_on=date.fromisoformat(str(raw["filed"])),
            )
        )
    holidays = [
        Holiday(date.fromisoformat(str(h["date"])), str(h["name"]), None)
        for h in case.get("holidays", ())
    ]
    findings = detect_leave_pattern_anomalies(
        members=members,
        requests_by_employee=requests,
        holidays=holidays,
        today=today,
    )
    predicted = {(f.employee_id, f.anomaly_type) for f in findings}
    labeled = {
        (_anomaly_uid(str(expect["employee"])), str(expect["type"]))
        for expect in case.get("expected", ())
    }
    return predicted, labeled


def to_payload(metric: EvalMetric) -> dict[str, Any]:
    """Shape a metric row for core's ``POST /ai/hr/eval-runs`` payload."""
    return {
        "model_name": metric.model_name,
        "metric": metric.metric,
        "precision": metric.precision,
        "considered": metric.considered,
        "threshold": metric.threshold,
        "met_threshold": metric.met_threshold,
        "details": metric.details,
    }


async def post_eval_runs(
    base_url: str,
    token: str,
    tenant_slug: str,
    rows: list[dict[str, Any]],
) -> None:
    """POST the collected metric rows to core's eval-runs endpoint."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/v1/ai/hr/eval-runs",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Slug": tenant_slug,
            },
            json=rows,
        )
    if response.status_code != 200:
        raise RuntimeError(f"core returned {response.status_code}: {response.text[:200]}")


def _score_case(
    model_name: str,
    case: dict[str, Any],
    index: int,
    model: LoadedModel,
) -> ScoredEmployee | None:
    """Build one employee feature vector from a registry case and score it."""
    raw = case["features"]
    features = EmployeeFeatures(
        employee_ref=f"seed-{model_name}-{index}",
        tenure_years=float(raw[0]),
        compa_ratio=float(raw[1]),
        promotion_gap_months=float(raw[2]),
        activity_count=float(raw[3]),
    )
    return score_employee(features, model)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "ANOMALY_METRIC",
    "ANOMALY_MODEL_NAME",
    "ANOMALY_SOURCE",
    "ANOMALY_VERSION",
    "DEFAULT_THRESHOLD",
    "EvalMetric",
    "evaluate_metric",
    "load_registry",
    "post_eval_runs",
    "run_registry",
    "to_payload",
]
