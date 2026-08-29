"""Background jobs for the AI agent service.

Scheduled tasks that run on timers within the FastAPI lifespan:
- Suggestion expiry: auto-expires pending suggestions after N days
- Anomaly auto-close: auto-closes open anomalies after N days
- Anomaly scan: runs detection rules on a 15-minute interval
"""
