"""Base event schema and producer/consumer abstract classes.

All Kafka events in the Skyrict ecosystem inherit from BaseEvent.
All producers inherit from BaseProducer.
All consumers inherit from BaseConsumer.

This ensures every event has a consistent envelope, and every
producer/consumer follows the same lifecycle.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field


logger = structlog.get_logger("skyrict_events")


# ---------- Event Schema ----------

class BaseEvent(BaseModel):
    """Base envelope for all Kafka events in Skyrict.

    Every event published to Kafka MUST inherit from this and add
    domain-specific fields. The base fields ensure consistent
    traceability across services.

    Topic naming convention: {domain}.{entity}.{action}
    Example: identity.user.created, inventory.stock.level_changed
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event ID for deduplication and tracing",
    )
    event_type: str = Field(
        ...,
        description="Event type following {domain}.{entity}.{action} convention",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the event was created",
    )
    tenant_id: str = Field(
        ...,
        description="Tenant ID — every event is tenant-scoped",
    )
    version: int = Field(
        default=1,
        description="Schema version — increment when the event shape changes",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for request tracing across services",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata — source service, user agent, etc.",
    )

    def to_json(self) -> str:
        """Serialize to JSON for Kafka message value."""
        return self.model_dump_json()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for Kafka message value."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: str) -> "BaseEvent":
        """Deserialize from JSON. Subclasses should override with their specific type."""
        return cls.model_validate_json(data)


# ---------- Producer ----------

class BaseProducer(ABC):
    """Abstract base class for Kafka producers.

    Subclasses implement `produce()` for domain-specific events.
    The base class handles Kafka producer lifecycle and serialization.
    """

    def __init__(self, brokers: str, *, client_id: str | None = None) -> None:
        self.brokers = brokers
        self.client_id = client_id
        self._producer = None

    def connect(self) -> None:
        """Initialize the Kafka producer connection."""
        from kafka import KafkaProducer

        self._producer = KafkaProducer(
            bootstrap_servers=self.brokers,
            client_id=self.client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retries=3,
        )
        logger.info("producer.connected", brokers=self.brokers, client_id=self.client_id)

    def disconnect(self) -> None:
        """Flush and close the Kafka producer."""
        if self._producer:
            self._producer.flush()
            self._producer.close()
            self._producer = None
            logger.info("producer.disconnected")

    def publish(self, topic: str, event: BaseEvent, *, key: str | None = None) -> None:
        """Publish an event to a Kafka topic.

        Args:
            topic: Kafka topic (follow {domain}.{entity}.{action} convention).
            event: The event instance (must be a BaseEvent subclass).
            key: Optional partition key (usually tenant_id or entity ID).
        """
        if not self._producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        future = self._producer.send(
            topic,
            value=event.to_dict(),
            key=key or event.tenant_id,
        )
        future.add_callback(
            lambda metadata: logger.info(
                "event.published",
                topic=topic,
                event_type=event.event_type,
                event_id=event.event_id,
                partition=metadata.partition,
                offset=metadata.offset,
            )
        )
        future.add_errback(
            lambda exc: logger.error(
                "event.publish_failed",
                topic=topic,
                event_type=event.event_type,
                event_id=event.event_id,
                error=str(exc),
            )
        )

    @abstractmethod
    def produce(self, event: BaseEvent) -> None:
        """Produce a domain-specific event. Subclasses must implement this
        to call self.publish() with the correct topic."""
        ...


# ---------- Consumer ----------

class BaseConsumer(ABC):
    """Abstract base class for Kafka consumers.

    Subclasses implement `handle()` for domain-specific event processing.
    The base class handles consumer lifecycle, deserialization, and error handling.
    """

    def __init__(
        self,
        brokers: str,
        group_id: str,
        topics: list[str],
        *,
        client_id: str | None = None,
    ) -> None:
        self.brokers = brokers
        self.group_id = group_id
        self.topics = topics
        self.client_id = client_id
        self._consumer = None
        self._running = False

    def connect(self) -> None:
        """Initialize the Kafka consumer connection."""
        from kafka import KafkaConsumer

        self._consumer = KafkaConsumer(
            *self.topics,
            bootstrap_servers=self.brokers,
            group_id=self.group_id,
            client_id=self.client_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        self._running = True
        logger.info(
            "consumer.connected",
            brokers=self.brokers,
            group_id=self.group_id,
            topics=self.topics,
        )

    def disconnect(self) -> None:
        """Close the Kafka consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
            self._consumer = None
            logger.info("consumer.disconnected", group_id=self.group_id)

    def consume(self) -> None:
        """Main consume loop — poll, handle, commit."""
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect() first.")

        logger.info("consumer.loop_started", group_id=self.group_id)

        while self._running:
            try:
                records = self._consumer.poll(timeout_ms=1000)
                for topic_partition, messages in records.items():
                    for message in messages:
                        try:
                            self.handle(message.topic, message.value)
                            self._consumer.commit()
                        except Exception as exc:
                            logger.error(
                                "consumer.handle_failed",
                                topic=message.topic,
                                offset=message.offset,
                                error=str(exc),
                            )
                            # Don't commit — will retry on restart
                            raise
            except KeyboardInterrupt:
                logger.info("consumer.loop_interrupted", group_id=self.group_id)
                break
            except Exception as exc:
                logger.error("consumer.poll_failed", group_id=self.group_id, error=str(exc))

    @abstractmethod
    def handle(self, topic: str, payload: dict[str, Any]) -> None:
        """Handle a single event. Subclasses must implement this.

        Args:
            topic: The Kafka topic the event was received on.
            payload: The deserialized event payload (dict).
        """
        ...
