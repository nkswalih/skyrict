# Runbooks

Operational runbooks for incident response and troubleshooting.

## Format

Each runbook follows this structure:

```markdown
# Runbook: {Incident Title}

## Severity
P0 / P1 / P2 / P3

## Symptoms
What the team observes (alerts, user reports, dashboard signals).

## Impact
Who is affected and how severely.

## Diagnosis
Step-by-step investigation process.

## Mitigation
Immediate actions to restore service.

## Recovery
Steps to fully resolve the issue.

## Prevention
What to change to prevent recurrence.

## References
Links to relevant dashboards, ADRs, docs.
```

## Naming Convention

File names: `{severity}-{short-description}.md`

Examples:
- `p0-identity-service-down.md`
- `p1-kafka-lag-spike.md`
- `p2-database-connection-pool-exhausted.md`
- `p3-high-error-rate-after-deploy.md`

## Adding a Runbook

1. Create a new `.md` file following the template above
2. Fill in all sections — leave no section empty
3. Test the diagnosis steps yourself before marking as complete
4. Link the runbook from the relevant Grafana alert rule
