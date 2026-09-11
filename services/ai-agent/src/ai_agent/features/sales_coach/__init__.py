"""Sales Coach feature — coaching suggestions from deal activity analysis.

The Sales Coach agent analyzes CRM deal activities and call notes to produce
coaching suggestions per rep. Suggestions are manager-visible only via the
role-gated API. The agent registers via the AGT-001 registry and streams
through the supervisor delegate pattern (SKY-90).
"""
