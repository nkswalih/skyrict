"""Kafka event consumers — subscribe to domain events."""

from __future__ import annotations

import structlog

logger = structlog.get_logger("identity.events.consumers")


# TODO: Implement actual Kafka consumers when libs/skyrict-events is created.
# Each consumer should:
# 1. Subscribe to specific topics
# 2. Deserialize the event payload
# 3. Handle the event (update state, trigger side effects)
# 4. Acknowledge or retry
