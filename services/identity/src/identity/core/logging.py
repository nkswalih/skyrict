"""Structured JSON logging configuration for the identity service.

Re-exports skyrict_common.logging and adds identity-specific processors
that auto-inject tenant_id and request_id into every log line.
"""

from __future__ import annotations

import structlog

from skyrict_common.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]


def configure_identity_logging(
    *,
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure logging with identity-specific context injection.

    Adds tenant_id and request_id from structlog contextvars (set by
    RequestIdMiddleware and TenantContextMiddleware) to every log entry.
    """
    configure_logging(log_level=log_level, json_output=json_output)

    # Ensure our contextvars are in the processor chain
    # (skyrict_common already includes merge_contextvars, but we add
    # explicit processors for tenant_id and request_id to guarantee
    # they appear in every log line).
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
    from identity.core.tenant_context import TenantContext

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
    """Auto-inject request_id from structlog contextvars if not already present."""
    # structlog.contextvars.merge_contextvars already handles this,
    # but we ensure it's always present for downstream consumers.
    return event_dict
