"""V1 API router — aggregates all v1 endpoint modules.

The scaffold ships health/readiness; the AI routers (query, suggestions,
anomalies, forecast, abc) mount here as their commits land (SKY-57, SKY-68).
"""

from __future__ import annotations

from fastapi import APIRouter

from ai_agent.api.v1.health import router as health_router
from ai_agent.api.v1.routers.abc import router as abc_router
from ai_agent.api.v1.routers.anomalies import router as anomalies_router
from ai_agent.api.v1.routers.attrition import router as attrition_router
from ai_agent.api.v1.routers.forecast import router as forecast_router
from ai_agent.api.v1.routers.hr_copilot import router as hr_copilot_router
from ai_agent.api.v1.routers.nl_query import router as nl_query_router
from ai_agent.api.v1.routers.restock import router as restock_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(nl_query_router)
api_router.include_router(restock_router)
api_router.include_router(anomalies_router)
api_router.include_router(attrition_router)
api_router.include_router(hr_copilot_router)
api_router.include_router(abc_router)
api_router.include_router(forecast_router)
