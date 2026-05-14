# Service Latency Runbook

Use this runbook when a service has elevated request latency or dependency slowdown symptoms.

## Expected Signals

- `telemetry_feature_windows.avg_latency_ms` and `max_latency_ms` can show latency spikes when telemetry provides latency features.
- `telemetry_events.numeric_features_json` may include latency, CPU, memory, or restart features.
- `topology_snapshots` describe service relationships for upstream and downstream checks.
- `incident_reports` can provide historical context for repeated latency patterns.

## Investigation Steps

1. Query feature windows for the affected service and time range.
2. Retrieve topology snapshots and identify directly connected services.
3. Search knowledge for latency runbooks, topology notes, anomalies, and incident reports.
4. Compare current symptoms with prior incidents before making remediation recommendations.

## Relevant Services

For Online Boutique, latency symptoms often involve `frontend`, `checkoutservice`, `recommendationservice`, `productcatalogservice`, or `cartservice`.
