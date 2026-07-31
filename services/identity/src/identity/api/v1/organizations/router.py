"""Organization endpoints — CRUD for tenants."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from identity.api.deps import get_current_user, get_tenant_repo
from identity.application.tenant.repository.tenant import TenantRepository
from identity.application.tenant.schemas import TenantCreateRequest, TenantResponse
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me", response_model=ResponseEnvelope[TenantResponse])
async def get_my_organization(
    current_user: dict = Depends(get_current_user),
    tenant_repo: TenantRepository = Depends(get_tenant_repo),
) -> ResponseEnvelope[TenantResponse]:
    """Get the current user's organization."""
    from identity.core.tenant_context import TenantContext

    tenant_id = TenantContext.get()
    tenant = await tenant_repo.get_by_id(tenant_id)
    return ResponseEnvelope(data=TenantResponse.model_validate(tenant))


@router.post("", response_model=ResponseEnvelope[TenantResponse])
async def create_organization(
    body: TenantCreateRequest,
    current_user: dict = Depends(get_current_user),
    tenant_repo: TenantRepository = Depends(get_tenant_repo),
) -> ResponseEnvelope[TenantResponse]:
    """Create a new organization."""
    from identity.application.tenant.models.tenant import TenantModel

    if await tenant_repo.slug_exists(body.slug):
        from skyrict_common.exceptions import ValidationError
        raise ValidationError(f"Slug '{body.slug}' is already taken")

    tenant = TenantModel(name=body.name, slug=body.slug)
    await tenant_repo.create(tenant)
    return ResponseEnvelope(data=TenantResponse.model_validate(tenant), message="Organization created")
