"""/ai/forecast endpoints - demand forecasting per product."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ai_agent.api.deps import get_current_user
from ai_agent.api.v1.routers.nl_query import get_inventory_gateway
from ai_agent.features.forecast.service import ForecastService
from ai_agent.features.nl_query.gateway import InventoryGatewayPort

router = APIRouter(prefix="/ai/forecast", tags=["ai-forecast"])


class ForecastItem(BaseModel):
    product_id: str
    horizon_weeks: int
    avg_daily_demand: str
    weeks_of_supply: str | None
    stockout_date: str | None


class ForecastResponse(BaseModel):
    data: list[ForecastItem]


def get_forecast_service(
    request: Request,
    gateway: Annotated[InventoryGatewayPort, Depends(get_inventory_gateway)],
) -> ForecastService:
    async def gateway_factory() -> InventoryGatewayPort:
        return gateway

    return ForecastService(gateway_factory=gateway_factory)


@router.get("/{product_id}", response_model=ForecastResponse)
async def get_product_forecast(
    product_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ForecastService, Depends(get_forecast_service)],
) -> ForecastResponse:
    items = await service.get_forecast(product_id=product_id)
    return ForecastResponse(data=[ForecastItem.model_validate(item) for item in items])
