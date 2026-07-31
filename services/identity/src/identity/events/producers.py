"""Kafka event producers — publish domain events."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger("identity.events")


async def publish_event(topic: str, key: str, payload: dict[str, Any]) -> None:
    """Publish a domain event to Kafka.

    TODO: Replace with actual Kafka producer when libs/skyrict-events is created.
    For now, log the event for development.
    """
    logger.info(
        "event.published",
        topic=topic,
        key=key,
        payload_keys=list(payload.keys()),
    )
