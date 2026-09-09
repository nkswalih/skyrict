"""Natural-language report builder (SKY-80, RPT-AI-001).

Slice layout: ``spec`` (validated LLM output schema + system prompt), ``validator``
(spec -> catalog whitelist re-check), ``params`` (timeframe -> template bind
params), ``gateway`` (read-only core HTTP port), ``engine`` (parse-validate-
resolve-execute pipeline), ``service`` (limits + logs + audit).
"""
