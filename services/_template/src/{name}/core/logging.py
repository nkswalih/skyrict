"""Structured JSON logging — re-exports skyrict_common.logging with context injection."""

from __future__ import annotations

import structlog

from skyrict_common.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]


def configure_{name}_logging(
    *,
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure logging with {name}-specific context injection."""
    configure_logging(log_level=log_level, json_output=json_output)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_tenant_id,
            _inject_request_id,
            *structlog.get_config()["processors"],  # type: ignore[arg-type]
        ],
    )


def _inject_tenant_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Auto-inject tenant_id from TenantContext if not already present."""
    from {name}.core.tenant_context import TenantContext

    if "tenant_id" not in event_dict:
        tenant_id = TenantContext.get_optional()
        if tenant_id:
            event_dict["tenant_id"] = tenant_id
    return event_dict


def _inject_request_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Auto-inject request_id from structlog contextvars."""
    return event_dict
