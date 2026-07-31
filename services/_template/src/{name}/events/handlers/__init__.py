"""Event handlers — map domain events to service calls."""

from __future__ import annotations

import structlog

logger = structlog.get_logger("{name}.events.handlers")


# TODO: Implement event handlers that map published events to service operations.
# Example:
#   async def handle_user_registered(event: dict) -> None:
#       """Send welcome email, create default workspace, etc."""
#       ...
