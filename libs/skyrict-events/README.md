# skyrict-events

Shared Kafka event schemas and producer/consumer base classes for all Skyrict services.

## Usage

```toml
# In any service's pyproject.toml
[project]
dependencies = ["skyrict-events"]
```

```python
from skyrict_events.base import BaseEvent, BaseProducer, BaseConsumer

# Define an event
class UserCreated(BaseEvent):
    event_type: str = "identity.user.created"
    user_id: str
    email: str

# Publish
producer = BaseProducer(brokers="localhost:9092")
producer.connect()
producer.publish("identity.user.created", UserCreated(
    tenant_id="tenant-123",
    user_id="user-456",
    email="alice@example.com",
))

# Consume
class UserCreatedConsumer(BaseConsumer):
    def handle(self, topic: str, payload: dict) -> None:
        event = UserCreated(**payload)
        # Process the event...
```

## Modules

| Module | Purpose |
|--------|---------|
| `base` | `BaseEvent` Pydantic model, `BaseProducer` ABC, `BaseConsumer` ABC |
| `schemas/` | Add domain-specific event Pydantic models here |
