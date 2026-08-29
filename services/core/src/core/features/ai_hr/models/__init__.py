"""HR/Payroll AI ORM models — one file per ``ai_*`` / ``erp_employee_documents`` table."""

from core.features.ai_hr.models.attrition_score import (
    AttritionRiskBand,
    AttritionScoreModel,
)
from core.features.ai_hr.models.compliance_check import (
    ComplianceCheckModel,
    ComplianceCheckType,
    ComplianceStatus,
)
from core.features.ai_hr.models.employee_document import (
    DocumentType,
    EmployeeDocumentModel,
)
from core.features.ai_hr.models.hr_eval_run import HrEvalRunModel
from core.features.ai_hr.models.leave_anomaly import LeaveAnomalyModel, LeaveAnomalyStatus
from core.features.ai_hr.models.leave_blackout_period import AiHrLeaveBlackoutPeriodModel
from core.features.ai_hr.models.leave_suggestion import LeaveSuggestionModel, LeaveSuggestionStatus
from core.features.ai_hr.models.payroll_anomaly import (
    AnomalySeverity,
    AnomalyStatus,
    AnomalyType,
    PayrollAnomalyModel,
)
from core.features.ai_hr.models.public_holiday import AiHrPublicHolidayModel
from core.features.ai_hr.models.quality_score import QualityGrade, QualityScoreModel
from core.features.ai_hr.models.utilization_alert import (
    UtilizationAlertModel,
    UtilizationAlertStatus,
    UtilizationAlertType,
)

__all__ = [
    "AiHrLeaveBlackoutPeriodModel",
    "AiHrPublicHolidayModel",
    "AnomalySeverity",
    "AnomalyStatus",
    "AnomalyType",
    "AttritionRiskBand",
    "AttritionScoreModel",
    "ComplianceCheckModel",
    "ComplianceCheckType",
    "ComplianceStatus",
    "DocumentType",
    "EmployeeDocumentModel",
    "HrEvalRunModel",
    "LeaveAnomalyModel",
    "LeaveAnomalyStatus",
    "LeaveSuggestionModel",
    "LeaveSuggestionStatus",
    "PayrollAnomalyModel",
    "QualityGrade",
    "QualityScoreModel",
    "UtilizationAlertModel",
    "UtilizationAlertStatus",
    "UtilizationAlertType",
]
