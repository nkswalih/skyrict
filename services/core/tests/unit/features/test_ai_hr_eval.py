"""ai-agent eval harness recording (HR-AI-002, SKY-72) — unit contract checks.

No database. Pins the pieces the eval-write path depends on outside the ORM:
the ``erp.hr.ai.eval`` permission is catalogued (so ``require_permission`` can
fail-closed on it), the ``HrEvalRunWrite`` payload validates precision bounds
at the edge, and the repository's pure coercers round to the ``Numeric(5,4)``
column shape safely.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.core.permissions import (
    CATALOG,
    ERP_HR_AI_EVAL,
    PERMISSION_MODULES,
)
from core.features.ai_hr.eval_repository import _to_decimal, _to_int, _to_str
from core.features.ai_hr.schemas import HrEvalRunWrite

pytestmark = pytest.mark.unit


def test_eval_permission_is_catalogued() -> None:
    assert ERP_HR_AI_EVAL == "erp.hr.ai.eval"
    assert ERP_HR_AI_EVAL in CATALOG
    module_keys = {k for _, _, keys in PERMISSION_MODULES for k in keys}
    assert ERP_HR_AI_EVAL in module_keys


def test_permissions_module_import_asserts_catalog_union() -> None:
    # Importing the module raises on CATALOG <-> PERMISSION_MODULES drift.
    from core.core import permissions  # noqa: F401


def test_hr_eval_run_write_validates_precision_bounds() -> None:
    with pytest.raises(ValidationError):
        HrEvalRunWrite(model_name="attrition", metric="attrition_precision", precision=1.5)
    with pytest.raises(ValidationError):
        HrEvalRunWrite(model_name="attrition", metric="attrition_precision", precision=-0.1)


def test_hr_eval_run_write_defaults() -> None:
    run = HrEvalRunWrite(
        model_name="attrition",
        metric="attrition_precision",
        precision=0.82,
        considered=6,
    )
    assert run.threshold is None
    assert run.met_threshold is None
    assert run.details == {}


def test_hr_eval_run_write_accepts_threshold_flag_and_details() -> None:
    run = HrEvalRunWrite(
        model_name="attrition",
        metric="attrition_precision",
        precision=0.8333,
        considered=6,
        threshold=0.70,
        met_threshold=True,
        details={"confirmed": 4, "predicted_positive": 5, "abstained": 1},
    )
    assert run.met_threshold is True
    assert run.model_dump()["details"]["confirmed"] == 4


def test_to_decimal_rounds_to_four_places() -> None:
    assert _to_decimal("0.82346") == Decimal("0.8235")
    assert _to_decimal(0.7) == Decimal("0.7000")


def test_to_int_and_to_str_coerce_safely() -> None:
    assert _to_int("6") == 6
    assert _to_int(None) == 0
    assert _to_str("attrition") == "attrition"
    assert _to_str(None) == ""
