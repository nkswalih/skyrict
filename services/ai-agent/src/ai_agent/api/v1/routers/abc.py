"""/ai/abc endpoints - ABC classification."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ai_agent.api.deps import get_current_user
from ai_agent.api.v1.routers.nl_query import get_inventory_gateway
from ai_agent.features.abc.service import AbcService
from ai_agent.features.nl_query.gateway import InventoryGatewayPort

router = APIRouter(prefix="/ai/abc", tags=["ai-abc"])


class AbcItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    revenue: str
    revenue_share: str
    band: str


class AbcListResponse(BaseModel):
    data: list[AbcItem]


class AbcSummaryResponse(BaseModel):
    data: dict[str, int]


def get_abc_service(
    request: Request,
    gateway: Annotated[InventoryGatewayPort, Depends(get_inventory_gateway)],
) -> AbcService:
    async def gateway_factory() -> InventoryGatewayPort:
        return gateway

    return AbcService(gateway_factory=gateway_factory)


@router.get("", response_model=AbcListResponse)
async def list_abc_classifications(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[AbcService, Depends(get_abc_service)],
) -> AbcListResponse:
    items = await service.compute_classification()
    return AbcListResponse(data=[AbcItem.model_validate(item) for item in items])


@router.get("/summary", response_model=AbcSummaryResponse)
async def get_abc_summary(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[AbcService, Depends(get_abc_service)],
) -> AbcSummaryResponse:
    summary = await service.get_summary()
    return AbcSummaryResponse(data=summary)
