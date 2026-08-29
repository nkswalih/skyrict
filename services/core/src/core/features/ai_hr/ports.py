"""Ports for the HR/Payroll AI L1 aggregate and attrition repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from core.features.ai_hr.attrition_repository import FeatureVector, ScoredRisk
from core.features.ai_hr.quality_repository import EmployeeQuality
from core.features.ai_hr.repository import (
    DepartmentCount,
    HeadcountPoint,
    TenureBand,
)


class AiHrRepositoryPort(Protocol):
    async def total_headcount(self, tenant_id: uuid.UUID) -> int: ...

    async def headcount_trend(
        self, tenant_id: uuid.UUID, months: int = 12
    ) -> list[HeadcountPoint]: ...

    async def department_distribution(self, tenant_id: uuid.UUID) -> list[DepartmentCount]: ...

    async def tenure_bands(self, tenant_id: uuid.UUID) -> list[TenureBand]: ...


class AiHrAttritionRepositoryPort(Protocol):
    """Persistence + feature projection behind the attrition service."""

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_feature_vectors(self, tenant_id: uuid.UUID) -> list[FeatureVector]: ...

    async def upsert_scores(self, tenant_id: uuid.UUID, scored: Sequence[ScoredRisk]) -> None: ...

    async def list_scores(self, tenant_id: uuid.UUID) -> list[ScoredRisk]: ...

    async def get_score(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ScoredRisk | None: ...

    async def acknowledge_score(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
    ) -> ScoredRisk | None: ...


class AiHrQualityRepositoryPort(Protocol):
    """Persistence + signal projection behind the quality scorer (8.1.3)."""

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_quality_rows(self, tenant_id: uuid.UUID) -> list[EmployeeQuality]: ...

    async def upsert_quality(
        self, tenant_id: uuid.UUID, rows: Sequence[EmployeeQuality]
    ) -> None: ...

    async def list_quality(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[EmployeeQuality]: ...


__all__ = [
    "AiHrAttritionRepositoryPort",
    "AiHrQualityRepositoryPort",
    "AiHrRepositoryPort",
    "EmployeeQuality",
    "FeatureVector",
    "ScoredRisk",
]
