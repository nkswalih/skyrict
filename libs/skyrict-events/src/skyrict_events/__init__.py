"""Skyrict Events — shared Kafka event schemas and producer/consumer base classes."""

from skyrict_events.base import BaseConsumer, BaseEvent, BaseProducer

__all__ = [
    "BaseConsumer",
    "BaseEvent",
    "BaseProducer",
]

__version__ = "0.1.0"
