"""HR/Payroll AI ORM models (HR-AI-001, Commit 2) — metadata contract checks.

Pure unit tests (no database). They pin the model metadata that migration 0020
and the integration tests rely on: table names, the ``(tenant_id, id)``
composite-PK convention, tenant scoping, and the native ``erp_document_type``
enum usage (``create_type=False`` — the type is created by the migration, never
by the model).
"""

from __future__ import annotations

import pytest

from core.features.ai_hr.models.attrition_score import AttritionRiskBand, AttritionScoreModel
from core.features.ai_hr.models.compliance_check import (
    ComplianceCheckModel,
    ComplianceCheckType,
    ComplianceStatus,
)
from core.features.ai_hr.models.employee_document import DocumentType, EmployeeDocumentModel
from core.features.ai_hr.models.hr_eval_run import HrEvalRunModel
from core.features.ai_hr.models.leave_anomaly import LeaveAnomalyModel, LeaveAnomalyStatus
from core.features.ai_hr.models.leave_suggestion import (
    LeaveSuggestionModel,
    LeaveSuggestionStatus,
)
from core.features.ai_hr.models.payroll_anomaly import (
    AnomalySeverity,
    AnomalyStatus,
    AnomalyType,
    PayrollAnomalyModel,
)
from core.features.ai_hr.models.quality_score import QualityGrade, QualityScoreModel
from core.features.ai_hr.models.utilization_alert import (
    UtilizationAlertModel,
    UtilizationAlertStatus,
    UtilizationAlertType,
)

pytestmark = pytest.mark.unit

ALL_MODELS = (
    EmployeeDocumentModel,
    AttritionScoreModel,
    PayrollAnomalyModel,
    ComplianceCheckModel,
    QualityScoreModel,
    UtilizationAlertModel,
    LeaveAnomalyModel,
    LeaveSuggestionModel,
    HrEvalRunModel,
)


@pytest.mark.parametrize(
    ("model", "table"),
    [
        (EmployeeDocumentModel, "erp_employee_documents"),
        (AttritionScoreModel, "ai_hr_attrition_scores"),
        (PayrollAnomalyModel, "ai_payroll_anomaly_log"),
        (ComplianceCheckModel, "ai_compliance_checks"),
        (QualityScoreModel, "ai_hr_quality_scores"),
        (UtilizationAlertModel, "ai_hr_utilization_alerts"),
        (LeaveAnomalyModel, "ai_hr_leave_anomalies"),
        (LeaveSuggestionModel, "ai_hr_leave_suggestions"),
        (HrEvalRunModel, "hr_eval_runs"),
    ],
)
def test_model_table_names(model: type, table: str) -> None:
    assert model.__tablename__ == table


@pytest.mark.parametrize("model", ALL_MODELS)
def test_composite_primary_key_is_tenant_id_plus_id(model: type) -> None:
    assert [c.name for c in model.__table__.primary_key.columns] == ["tenant_id", "id"]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_table_is_tenant_scoped(model: type) -> None:
    assert "tenant_id" in model.__table__.columns


def test_ai_tables_have_no_updated_at() -> None:
    for model in (
        AttritionScoreModel,
        PayrollAnomalyModel,
        ComplianceCheckModel,
        QualityScoreModel,
        UtilizationAlertModel,
        LeaveAnomalyModel,
        LeaveSuggestionModel,
        HrEvalRunModel,
    ):
        assert "updated_at" not in model.__table__.columns
        assert "created_at" in model.__table__.columns or "generated_at" in model.__table__.columns


def test_employee_document_has_created_and_updated_at() -> None:
    assert "created_at" in EmployeeDocumentModel.__table__.columns
    assert "updated_at" in EmployeeDocumentModel.__table__.columns


def test_document_type_enum_is_declared_by_migration_only() -> None:
    column_type = EmployeeDocumentModel.__table__.c.doc_type.type
    assert column_type.name == "erp_document_type"
    assert column_type.native_enum is True


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (
            DocumentType,
            (
                "work_permit",
                "visa",
                "national_id",
                "passport",
                "contract",
                "certification",
                "medical",
                "other",
            ),
        ),
        (AttritionRiskBand, ("low", "medium", "high")),
        (ComplianceCheckType, ("document_expiry", "training_overdue", "contract_missing_field")),
        (ComplianceStatus, ("open", "acknowledged", "resolved")),
        (AnomalyType, ("net_pay_delta", "duplicate_account", "ghost_employee")),
        (AnomalySeverity, ("low", "medium", "high", "critical")),
        (AnomalyStatus, ("open", "acknowledged", "dismissed", "resolved")),
        (QualityGrade, ("A", "B", "C", "D", "F")),
        (UtilizationAlertType, ("forfeit_risk", "negative_accrual")),
        (UtilizationAlertStatus, ("open", "acknowledged", "dismissed", "resolved")),
        (LeaveAnomalyStatus, ("open", "acknowledged", "dismissed", "resolved")),
        (LeaveSuggestionStatus, ("pending", "used", "dismissed")),
    ],
)
def test_member_values(enum_cls, expected: tuple[str, ...]) -> None:
    values = (
        [v.value for v in enum_cls]
        if hasattr(enum_cls, "__iter__")
        else [getattr(enum_cls, attr) for attr in enum_cls.__dict__ if attr.isupper()]
    )
    assert tuple(values) == expected
