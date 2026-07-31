from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from skyrict_events.base import BaseEvent


class TestBaseEvent:
    def test_default_fields(self):
        event = BaseEvent(event_type="test.event", tenant_id="tenant-1")
        assert event.event_type == "test.event"
        assert event.tenant_id == "tenant-1"
        assert event.version == 1
        assert isinstance(event.event_id, str)
        assert uuid.UUID(event.event_id)
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_to_json_roundtrip(self):
        event = BaseEvent(event_type="test.roundtrip", tenant_id="t-1")
        data = event.to_json()
        parsed = json.loads(data)
        assert parsed["event_type"] == "test.roundtrip"
        assert parsed["tenant_id"] == "t-1"

    def test_to_dict(self):
        event = BaseEvent(event_type="test.dict", tenant_id="t-1")
        d = event.to_dict()
        assert d["event_type"] == "test.dict"
        assert d["tenant_id"] == "t-1"

    def test_from_json(self):
        event = BaseEvent(event_type="test.from_json", tenant_id="t-1")
        json_str = event.to_json()
        restored = BaseEvent.from_json(json_str)
        assert restored.event_id == event.event_id
        assert restored.event_type == "test.from_json"
