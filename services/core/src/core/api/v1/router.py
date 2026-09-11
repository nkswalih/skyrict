"""V1 API router - aggregates all v1 endpoint modules.

Phase 1 hosts health/readiness, a protected ``/me`` exercise route, and the
feature routers for HR & payroll (HR-BE-002), inventory (INV-BE-002), finance
(FIN-BE-002), CRM & sales (CRM-BE-002). Feature routers for purchase arrive in
their own ERP tickets under ``core.features.*``.
"""

from __future__ import annotations

from fastapi import APIRouter

from core.api.v1.health import router as health_router
from core.api.v1.me import router as me_router
from core.api.v1.routers.hr import router as hr_router
from core.api.v1.routers.payroll import router as payroll_router
from core.api.v1.routers.payroll_automation import router as payroll_automation_router
from core.api.v1.routers.portal import router as portal_router
from core.features.ai.router import router as ai_router
from core.features.ai_agents.router import router as ai_agents_router
from core.features.ai_hr.router import router as ai_hr_router
from core.features.crm.router import router as crm_router
from core.features.crm.workspace_router import router as crm_workspace_router
from core.features.documents.router import router as documents_router
from core.features.finance.automation import router as finance_automation_router
from core.features.finance.router import router as finance_router
from core.features.inventory.router import router as inventory_router
from core.features.reporting.reports_router import router as reports_router
from core.features.reporting.router import router as reporting_router
from core.features.revenue_forecast.router import router as revenue_forecast_router
from core.features.sales.router import router as sales_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(me_router)
api_router.include_router(hr_router)
api_router.include_router(payroll_router)
api_router.include_router(payroll_automation_router)
api_router.include_router(portal_router)
api_router.include_router(finance_router)
api_router.include_router(finance_automation_router)
api_router.include_router(revenue_forecast_router)
api_router.include_router(inventory_router)
api_router.include_router(reporting_router)
api_router.include_router(reports_router)
api_router.include_router(crm_router)
api_router.include_router(crm_workspace_router)
api_router.include_router(sales_router)
api_router.include_router(documents_router)
api_router.include_router(ai_router)
api_router.include_router(ai_agents_router)
api_router.include_router(ai_hr_router)
