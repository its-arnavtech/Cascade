# Pod Kill / Restart Runbook

Use this runbook when a target service becomes unhealthy after a pod kill, restart, or Chaos Mesh pod failure experiment.

## Expected Signals

- `telemetry_events` should show warning, error, or unhealthy events for the affected service.
- `telemetry_feature_windows` should show increased `restart_rate`, `unhealthy_rate`, or `error_rate`.
- `anomaly_events` may contain a restart or unhealthy-service anomaly with service, namespace, workload, risk score, and evidence JSON.
- `experiment_events` can connect the time window to a Chaos Mesh pod-kill experiment.

## Investigation Steps

1. Query recent anomalies for the service and namespace.
2. Check feature windows around the restart time for restart and unhealthy rates.
3. Retrieve recent telemetry events for the pod and workload.
4. Compare the latest topology snapshot to identify downstream services that may show secondary symptoms.
5. Search incident history for prior pod kill or restart reports before planning any remediation.

## Cascade Services

- `observation-service` collects target service health.
- `feature-extractor-service` builds restart and health feature windows.
- `anomaly-detector-service` stores restart and unhealthy-service anomalies.
- `knowledge-retrieval-service` retrieves this runbook and related incident evidence.

## Example Queries

- `pod restart unhealthy service anomaly`
- `how do I investigate catalogue restart anomaly`
- `which incidents mention pod kill root cause`
