"""Eval-harness result repository (HR-AI-002, SKY-72).

Append-only persistence for ai-agent model-eval precision rows. Unlike the
alert/suggestion tables there is no TTL and no per-tenant replace: every eval
run records one row per metric under the operator's tenant (a historical
telemetry log, mirrored by ``ix_hr_eval_runs_tenant_model``). Precision values
are rounded to 4dp to match the ``Numeric(5, 4)`` column before the insert.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.features.ai_hr.models.hr_eval_run import HrEvalRunModel

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class EvalRunRepository:
    """Appends model-eval metric rows for one tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        tenant_id: uuid.UUID,
        model_name: str,
        metric: str,
        precision: Decimal,
        considered: int,
        threshold: Decimal | None,
        met_threshold: bool | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Insert one precision result; ``generated_at`` is server-side now()."""
        row = HrEvalRunModel(
            tenant_id=tenant_id,
            model_name=model_name,
            metric=metric,
            precision=precision,
            considered=considered,
            threshold=threshold,
            met_threshold=met_threshold,
            details=details or {},
        )
        self._session.add(row)

    async def append_many(
        self,
        *,
        tenant_id: uuid.UUID,
        rows: Sequence[dict[str, Any]],
    ) -> int:
        """Insert a batch of eval rows; returns the number recorded."""
        for raw in rows:
            await self.append(
                tenant_id=tenant_id,
                model_name=_to_str(raw.get("model_name")),
                metric=_to_str(raw.get("metric")),
                precision=_to_decimal(raw.get("precision", 0)),
                considered=_to_int(raw.get("considered", 0)),
                threshold=(
                    None if raw.get("threshold") is None else _to_decimal(raw.get("threshold"))
                ),
                met_threshold=raw.get("met_threshold"),
                details=raw.get("details") if isinstance(raw.get("details"), dict) else {},
            )
        return len(rows)


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_str(value: Any) -> str:
    return str(value) if value is not None else ""


__all__ = ["EvalRunRepository"]
