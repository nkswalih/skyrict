"""V1 API router - aggregates all v1 endpoint modules.

The scaffold ships health/readiness; the AI routers (query, suggestions,
anomalies, forecast, abc) mount here as their commits land (SKY-57, SKY-68).
"""

from __future__ import annotations

from fastapi import APIRouter

from ai_agent.api.v1.health import router as health_router
from ai_agent.api.v1.routers.abc import router as abc_router
from ai_agent.api.v1.routers.account_suggest import router as account_suggest_router
from ai_agent.api.v1.routers.agents import router as agents_router
from ai_agent.api.v1.routers.anomalies import router as anomalies_router
from ai_agent.api.v1.routers.attrition import router as attrition_router
from ai_agent.api.v1.routers.chat import router as chat_router
from ai_agent.api.v1.routers.conversations import router as conversations_router
from ai_agent.api.v1.routers.crm import router as crm_router
from ai_agent.api.v1.routers.finance_ai import (
    anomaly_narrate_router,
    draft_entry_router,
    reminders_router,
)
from ai_agent.api.v1.routers.finance_lines import router as finance_lines_router
from ai_agent.api.v1.routers.forecast import router as forecast_router
from ai_agent.api.v1.routers.l3 import router as l3_router
from ai_agent.api.v1.routers.hr_copilot import router as hr_copilot_router
from ai_agent.api.v1.routers.inventory_search import router as inventory_search_router
from ai_agent.api.v1.routers.inventory_sync import router as inventory_sync_router
from ai_agent.api.v1.routers.narrator import router as narrator_router
from ai_agent.api.v1.routers.nl_query import router as nl_query_router
from ai_agent.api.v1.routers.rag import router as rag_router
from ai_agent.api.v1.routers.report_builder import router as report_builder_router
from ai_agent.api.v1.routers.restock import router as restock_router
from ai_agent.api.v1.routers.supplier_risk import router as supplier_risk_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(agents_router)
api_router.include_router(account_suggest_router)
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(nl_query_router)
api_router.include_router(restock_router)
api_router.include_router(anomalies_router)
api_router.include_router(narrator_router)
api_router.include_router(rag_router)
api_router.include_router(report_builder_router)
api_router.include_router(inventory_search_router)
api_router.include_router(inventory_sync_router)
api_router.include_router(attrition_router)
api_router.include_router(hr_copilot_router)
api_router.include_router(abc_router)
api_router.include_router(forecast_router)
api_router.include_router(l3_router)
api_router.include_router(crm_router)
api_router.include_router(draft_entry_router)
api_router.include_router(anomaly_narrate_router)
api_router.include_router(reminders_router)
api_router.include_router(finance_lines_router)
api_router.include_router(supplier_risk_router)
