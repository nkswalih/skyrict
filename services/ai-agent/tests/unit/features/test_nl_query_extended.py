"""Extended NL query tests — 7 actions, new engine result methods, prompt content."""

from __future__ import annotations

from ai_agent.features.nl_query.intent import (
    INTENT_SYSTEM_PROMPT,
    IntentAction,
    ParsedIntent,
    parse_intent_payload,
)


class TestIntentActionEnum:
    def test_all_seven_actions_defined(self) -> None:
        actions = list(IntentAction)
        assert len(actions) == 7
        names = {a.name for a in actions}
        assert names == {
            "STOCK_COUNT",
            "BELOW_REORDER",
            "RECENT_MOVEMENTS",
            "TOTAL_STOCK_VALUE",
            "HIGHEST_RESERVED",
            "LAST_RECEIPT",
            "WAREHOUSE_COUNT",
        }

    def test_stock_count_value(self) -> None:
        assert IntentAction.STOCK_COUNT.value == "stock_count"

    def test_total_stock_value_value(self) -> None:
        assert IntentAction.TOTAL_STOCK_VALUE.value == "total_stock_value"

    def test_highest_reserved_value(self) -> None:
        assert IntentAction.HIGHEST_RESERVED.value == "highest_reserved"

    def test_last_receipt_value(self) -> None:
        assert IntentAction.LAST_RECEIPT.value == "last_receipt"

    def test_warehouse_count_value(self) -> None:
        assert IntentAction.WAREHOUSE_COUNT.value == "warehouse_count"


class TestParseExtended:
    def test_parse_total_stock_value(self) -> None:
        raw = '{"action":"total_stock_value","product_name":null,"warehouse_name":"Delhi","movement_type":null,"confidence":0.9}'
        intent = parse_intent_payload(raw)
        assert intent.action is IntentAction.TOTAL_STOCK_VALUE
        assert intent.warehouse_name == "Delhi"

    def test_parse_highest_reserved(self) -> None:
        raw = '{"action":"highest_reserved","product_name":null,"warehouse_name":null,"movement_type":null,"confidence":0.85}'
        intent = parse_intent_payload(raw)
        assert intent.action is IntentAction.HIGHEST_RESERVED

    def test_parse_last_receipt(self) -> None:
        raw = '{"action":"last_receipt","product_name":"laptop charger","warehouse_name":null,"movement_type":null,"confidence":0.95}'
        intent = parse_intent_payload(raw)
        assert intent.action is IntentAction.LAST_RECEIPT
        assert intent.product_name == "laptop charger"

    def test_parse_warehouse_count(self) -> None:
        raw = '{"action":"warehouse_count","product_name":null,"warehouse_name":null,"movement_type":null,"confidence":0.7}'
        intent = parse_intent_payload(raw)
        assert intent.action is IntentAction.WAREHOUSE_COUNT


class TestSystemPromptContent:
    def test_prompt_lists_all_seven_actions(self) -> None:
        for action in IntentAction:
            assert action.value in INTENT_SYSTEM_PROMPT

    def test_prompt_instructs_json_only(self) -> None:
        assert "JSON" in INTENT_SYSTEM_PROMPT


class TestLogDictExtended:
    def test_log_dict_includes_all_fields(self) -> None:
        intent = ParsedIntent(
            action=IntentAction.TOTAL_STOCK_VALUE,
            product_name="widget",
            warehouse_name="Mumbai",
            confidence=0.9,
        )
        log = intent.to_log_dict()
        assert log["action"] == "total_stock_value"
        assert log["product_name"] == "widget"
        assert log["warehouse_name"] == "Mumbai"
        assert log["confidence"] == 0.9
