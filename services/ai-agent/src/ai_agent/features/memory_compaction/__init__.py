"""Advanced memory compaction (SKY-90).

A weekly background job folds older episodic memory rows into semantic
facts (query-response pairs compressed into distilled facts), then stamps
``compacted_at`` on the source rows so they stop consuming the recall
context budget. A per-agent token budget manager bounds how much total
context any agent may assemble.

This package is the pure feature slice: it depends only on injected ports
(repository + LLM router) and never imports ``ai_agent.db`` directly
(import-linter contract).
"""
