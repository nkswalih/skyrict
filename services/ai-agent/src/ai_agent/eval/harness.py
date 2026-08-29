"""Deterministic eval harness for the deployed HR models (HR-AI-002, SKY-72).

Runs each labeled seed set from ``tests/eval/hr_models.yaml`` through the SAME
scorer the runtime uses (attrition: :func:`score_employee`, abstention rule
included) and computes per-metric precision. The result rows are what the
``eval-hr-models`` CLI posts to core's ``/api/v1/ai/hr/eval-runs`` endpoint.

Design notes:

- Non-LLM and deterministic (bundled fixed-seed model + stable seed sets), so
  a run is reproducible and the recorded numbers are comparable across weeks.
- Precision below the documented 0.70 threshold WARNS (exit code 0) instead of
  failing: an eval regression is an operator alert, not a hard deploy gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

from ai_agent.features.attrition.features import EmployeeFeatures
from ai_agent.features.attrition.model import LoadedModel, load_model
from ai_agent.features.attrition.scorer import ScoredEmployee, score_employee

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

DEFAULT_THRESHOLD = 0.70

# A score is "flagged attrition-prone" when its band is medium or high; LOW
# means the model does not call the employee at-risk. Precision counts a
# flagged (medium/high) result against its labeled seed.
_POSITIVE_BANDS = ("medium", "high")


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
) -> EvalMetric:
    """Score the seed cases against the loaded model and compute precision."""
    if model_name != "attrition":
        raise ValueError(f"no evaluator registered for model {model_name!r}")
    model = load_model(model_path)
    predicted_positive = 0
    confirmed = 0
    abstained = 0
    band_counts: dict[str, int] = {}
    for index, case in enumerate(cases):
        scored = _score_case(model_name, case, index, model)
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
        model_name=model_name,
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
    "DEFAULT_THRESHOLD",
    "EvalMetric",
    "evaluate_metric",
    "load_registry",
    "post_eval_runs",
    "run_registry",
    "to_payload",
]
