"""Audit Guardian feature — weekly integrity reports from audit log analysis.

The Audit Guardian agent watches audit logs across modules (ai-agent, core,
identity) and anomaly feeds to produce weekly integrity reports. It flags
suspicious access patterns such as off-hours exports and bulk reads. Reports
are evidence-linked to specific audit log entries.

The agent registers via the AGT-001 registry and streams through the
supervisor delegate pattern (SKY-90).
"""
