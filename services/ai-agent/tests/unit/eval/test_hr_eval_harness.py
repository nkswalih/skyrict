"""Unit tests for the model eval harness (HR-AI-002, SKY-72).

No database: the harness is a pure compute layer over the bundled deterministic
attrition models + the labeled YAML registry. The suite pins the seed-set
precision so a regression in the deployed scoring contract is caught here even
before the operator ``eval-hr-models`` CLI warns on below-threshold runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.eval.harness import (
    ANOMALY_METRIC,
    ANOMALY_MODEL_NAME,
    DEFAULT_THRESHOLD,
    evaluate_metric,
    load_registry,
    run_registry,
    to_payload,
)

pytestmark = pytest.mark.unit

_REGISTRY = Path(__file__).resolve().parents[2] / "eval" / "hr_models.yaml"

_CALM_MEDIAN = tuple(
    {
        "employee": f"m{i}",
        "start": "2026-08-03",
        "end": "2026-08-03",
        "days": 1,
        "filed": "2026-08-01",
        "type": "annual",
    }
    for i in range(2, 6)
)


def test_registry_loads_attrition_model() -> None:
    registry = load_registry(_REGISTRY)
    assert registry["models"][0]["name"] == "attrition"
    assert registry["models"][0]["metrics"][0]["metric"] == "attrition_precision"
    assert registry["models"][0]["metrics"][0]["threshold"] == DEFAULT_THRESHOLD


def test_registry_loads_anomaly_model() -> None:
    registry = load_registry(_REGISTRY)
    assert registry["models"][1]["name"] == ANOMALY_MODEL_NAME
    assert registry["models"][1]["metrics"][0]["metric"] == ANOMALY_METRIC


def test_seed_set_precision_meets_documented_threshold() -> None:
    results = run_registry(_REGISTRY)
    (metric,) = [r for r in results if r.model_name == "attrition"]
    assert metric.model_name == "attrition"
    assert metric.metric == "attrition_precision"
    assert metric.considered == 6
    assert metric.abstained == 0
    assert metric.precision >= DEFAULT_THRESHOLD
    assert metric.met_threshold is True
    assert metric.details["confirmed"] == metric.details["predicted_positive"]


def test_anomaly_seed_precision_and_recall_are_perfect() -> None:
    results = run_registry(_REGISTRY)
    (metric,) = [r for r in results if r.model_name == ANOMALY_MODEL_NAME]
    assert metric.metric == ANOMALY_METRIC
    assert metric.considered == 4
    assert metric.precision == 1.0
    assert metric.details["recall"] == 1.0
    assert metric.details["false_positives"] == 0
    assert metric.details["false_negatives"] == 0
    assert metric.met_threshold is True


def test_anomaly_near_miss_cases_only_fire_overuse() -> None:
    results = run_registry(_REGISTRY)
    (metric,) = [r for r in results if r.model_name == ANOMALY_MODEL_NAME]
    case_pre_holiday_miss, case_short_notice_miss = (
        metric.details["cases"][2],
        metric.details["cases"][3],
    )
    for case in (case_pre_holiday_miss, case_short_notice_miss):
        assert any("leave_overuse" in p for p in case["predicted"])
    assert not any("pre_holiday_spike" in p for p in case_pre_holiday_miss["predicted"])
    assert not any("short_notice_monday_friday" in p for p in case_short_notice_miss["predicted"])


def test_precision_is_zero_when_no_positive_predictions() -> None:
    metric = evaluate_metric(
        model_name="attrition",
        metric="attrition_precision",
        cases=[{"features": [8.0, 1.15, 2.0, 12.0], "label": 0}],
        threshold=0.70,
        model_path=None,
    )
    assert metric.precision == 0.0
    assert metric.met_threshold is False
    assert metric.details["no_positive_predictions"] is True
    assert metric.details["band_counts"] == {"low": 1}


def test_abstention_is_counted_outside_precision_denominator() -> None:
    metric = evaluate_metric(
        model_name="attrition",
        metric="attrition_precision",
        cases=[
            {"features": [1.0, 0.85, 20.0, 1.0], "label": 1},
            {"features": [3.0, 1.00, 9.0, 4.0], "label": 0},  # abstains (<0.75)
        ],
        threshold=0.70,
        model_path=None,
    )
    assert metric.considered == 2
    assert metric.abstained == 1
    assert metric.details["confirmed"] == 1
    assert metric.details["predicted_positive"] == 1


def test_anomaly_missing_expected_finding_counts_recall_miss() -> None:
    metric = evaluate_metric(
        model_name=ANOMALY_MODEL_NAME,
        metric=ANOMALY_METRIC,
        cases=[
            {
                "team_size": 5,
                "today": "2026-08-24",
                "holidays": [],
                "requests": list(_CALM_MEDIAN),
                # no 6-day block -> no findings at all, but a label claims one
                "expected": [{"employee": "m1", "type": "pre_holiday_spike"}],
            }
        ],
        threshold=0.70,
        model_path=None,
    )
    assert metric.precision == 0.0
    assert metric.details["recall"] == 0.0
    assert metric.details["false_negatives"] == 1
    assert metric.met_threshold is False


def test_unknown_model_raises() -> None:
    with pytest.raises(ValueError, match="no evaluator registered"):
        evaluate_metric(
            model_name="nope",
            metric="precision",
            cases=[],
            threshold=0.70,
            model_path=None,
        )


def test_run_registry_threshold_override_short_circuits_met_flag() -> None:
    results = run_registry(_REGISTRY, threshold_override=2.0)
    assert results
    assert all(
        not metric.met_threshold for metric in results
    )  # 2.0 is above any reachable precision


def test_to_payload_matches_core_write_shape() -> None:
    metric = evaluate_metric(
        model_name="attrition",
        metric="attrition_precision",
        cases=[{"features": [1.0, 0.85, 20.0, 1.0], "label": 1}],
        threshold=0.70,
        model_path=None,
    )
    payload = to_payload(metric)
    assert payload["model_name"] == "attrition"
    assert payload["metric"] == "attrition_precision"
    assert payload["precision"] == 1.0
    assert payload["considered"] == 1
    assert payload["threshold"] == 0.70
    assert payload["met_threshold"] is True
    assert "details" in payload
