# Observability

Infrastructure-as-code for monitoring, logging, and tracing.

## Directory Structure

```
observability/
├── otel-collector-config.yaml   # OpenTelemetry Collector configuration
├── prometheus.yml               # Prometheus scrape configuration
├── grafana/
│   ├── provisioning/
│   │   ├── dashboards/          # Dashboard provisioning config
│   │   └── datasources/         # Datasource provisioning config
│   └── dashboards/
│       ├── identity-service.json # Identity service metrics dashboard
│       └── _template.json        # Copy this for new service dashboards
└── alerts/
    ├── identity-service.yml      # Prometheus alert rules for identity
    └── _template.yml             # Copy this for new service alerts
```

## What Goes Where

| File | Purpose |
|------|---------|
| `otel-collector-config.yaml` | OTel Collector: receives traces/metrics/logs from services, exports to backends |
| `prometheus.yml` | Prometheus: scrape targets, recording rules, alert rules |
| `grafana/dashboards/*.json` | Grafana dashboards as JSON — committed to git, auto-provisioned |
| `grafana/provisioning/` | Tells Grafana where to find dashboards and datasources |
| `alerts/*.yml` | Prometheus alert rules — fire PagerDuty/Slack when thresholds breach |

## Adding a New Service Dashboard

1. Copy `grafana/dashboards/_template.json`
2. Rename to `{service-name}.json`
3. Update the dashboard title and panel queries
4. Add a Prometheus scrape config for the new service
5. Add alert rules in `alerts/{service-name}.yml`

## Stack

| Component | Purpose |
|-----------|---------|
| OpenTelemetry Collector | Trace/metric/log collection and routing |
| Prometheus | Metrics storage and alerting |
| Grafana | Dashboards and visualization |
| Loki (optional) | Log aggregation |
| Jaeger (optional) | Distributed tracing |
